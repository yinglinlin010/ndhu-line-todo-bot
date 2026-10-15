"""Ordering, deadlines and calendar replacement: isolated data, no real sends/writes."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import line_bot_local as bot
from test_teacher_features import FakeAI, FakeGoogle, event
from test_line_bot_local import NOW


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.google = FakeGoogle()
        self.teacher = bot.TeacherFeatures(FakeAI(), self.google, enabled=True, owner_id="alice",
            state_file=self.root / "actions.json", clock=lambda: NOW)

    def tearDown(self):
        bot.WORK_CONTEXT.deadline = None
        self.temp.cleanup()

    def test_image_followup_waits_for_image_and_other_user_can_continue(self):
        started, release, replies = threading.Event(), threading.Event(), queue.Queue()
        ai = bot.LocalAI(http=lambda *a, **k: json.dumps(dict(message=dict(content="圖片日期2026-10-17。"))).encode())
        teacher = self.teacher
        def image(incoming):
            started.set()
            if not release.wait(2):
                raise RuntimeError("test barrier timed out")
            ai.remember(bot.conversation_key(incoming), [], "使用者上傳了一張圖片，請依圖片辨識內容接續回答。", "日期2026-10-17。")
            return "照片辨識完成"
        teacher.image = image
        runtime = bot.BotRuntime("s", "", bot.TodoStore(self.root / "todos"), ai, teacher=teacher,
                                 sender=lambda e,a: replies.put((e["webhookEventId"],a)))
        try:
            runtime.submit(event(identifier="image", kind="image"))
            self.assertTrue(started.wait(1))
            runtime.submit(event("圖片上的日期是什麼？", "followup"))
            other = event("hi", "other") | dict(source=dict(type="user",userId="bob"))
            runtime.submit(other)
            self.assertEqual(replies.get(timeout=1)[0], "other")
            self.assertTrue(replies.empty())
            release.set()
            self.assertEqual(replies.get(timeout=2)[0], "image")
            identity, answer = replies.get(timeout=2)
            self.assertEqual(identity, "followup")
            self.assertIn("2026-10-17", answer)
            self.assertNotIn("請先傳送", answer)
        finally:
            release.set()
            runtime.close()
        self.assertEqual(runtime.queues, {})

    def test_sender_failure_does_not_block_the_next_turn(self):
        replies=[]
        def sender(e,a):
            replies.append(e["webhookEventId"])
            if len(replies)==1:
                raise RuntimeError("synthetic send failure")
        runtime=bot.BotRuntime("s","",bot.TodoStore(self.root/"todos"),FakeAI(),sender=sender)
        runtime.submit(event("hi","first"))
        runtime.submit(event("hi","second"))
        runtime.close()
        self.assertEqual(replies,["first","second"])
        self.assertEqual(runtime.queues,{})

    def test_expired_queued_turn_skips_ai_and_clears_context(self):
        ai, replies=FakeAI(),[]
        runtime=bot.BotRuntime("s","",bot.TodoStore(self.root/"todos"),ai,sender=lambda e,a:replies.append(a))
        try:
            incoming=event("搜尋測試","expired") | dict(_received_at=time.monotonic()-60)
            runtime.capacity.acquire();runtime.process(incoming)
            self.assertIn("已停止後續步驟",replies[0])
            self.assertEqual(ai.calls,[])
            self.assertIsNone(bot.WORK_CONTEXT.deadline)
            runtime.capacity.acquire();runtime.process(event("正常問題","next"))
            self.assertEqual(replies[1],"回答完成")
        finally:runtime.close()

    def test_slow_model_cannot_start_sheet_write_after_deadline(self):
        ai=FakeAI()
        def ask(*args):
            time.sleep(.03)
            return "模型的晚到回答"
        ai.ask=ask
        self.teacher.sheet_logging=True
        replies=[]
        runtime=bot.BotRuntime("s","",bot.TodoStore(self.root/"todos"),ai,teacher=self.teacher,
            sender=lambda e,a:replies.append(a),work_seconds=.01)
        try:
            runtime.capacity.acquire();runtime.process(event("知識問答","late"))
            self.assertIn("已停止後續步驟",replies[0])
            self.assertEqual(self.google.calls,[])
            self.assertEqual(self.teacher.state["operations"],{})
        finally:runtime.close()

    def test_http_and_google_calls_are_bounded_by_remaining_budget(self):
        bot.WORK_CONTEXT.deadline=12
        response=MagicMock();response.status_code=200;response.iter_content.return_value=[b"{}"]
        response.__enter__.return_value=response
        with patch.object(bot.time,"monotonic",return_value=10),patch.object(bot.requests,"request",return_value=response) as request:
            self.assertEqual(bot.read_http("https://example.org",timeout=40),b"{}")
            self.assertEqual(request.call_args.kwargs["timeout"],(2,2))
        result=MagicMock(returncode=0,stdout="{}")
        run=MagicMock(return_value=result)
        google=bot.GoogleWorkspace(executable="synthetic-gws",run=run)
        with patch.object(bot.time,"monotonic",return_value=10):
            google.call("drive","files","list")
            self.assertEqual(run.call_args.kwargs["timeout"],2)
        bot.WORK_CONTEXT.deadline=time.monotonic()-1
        memory=bot.LocalAI(memory_path=self.root/"late-memory.json")
        with self.assertRaises(bot.WorkDeadline):
            memory.remember("owner",[],"question","late answer")
        self.assertEqual(memory.conversations,{})
        self.assertFalse((self.root/"late-memory.json").exists())
        with self.assertRaises(bot.WorkDeadline):
            self.teacher.operation("expired",lambda: self.fail("Must not write"))
        self.assertEqual(self.teacher.state["operations"],{})

    def test_loading_is_private_only_and_failure_is_nonfatal(self):
        calls=[]
        def loading(e):
            calls.append(e["webhookEventId"])
            raise RuntimeError("synthetic loading failure")
        runtime=bot.BotRuntime("s","",bot.TodoStore(self.root/"todos"),FakeAI(),sender=lambda *a:None,loading_sender=loading)
        try:
            runtime.show_loading(event(identifier="private"))
            runtime.show_loading(event(identifier="group") | dict(source=dict(type="group",userId="alice",groupId="g")))
            self.assertEqual(calls,["private"])
        finally:runtime.close()

    def test_loading_endpoint_is_mocked_and_uses_only_private_destination(self):
        runtime=bot.BotRuntime("s","synthetic-token",bot.TodoStore(self.root/"todos"),FakeAI(),sender=lambda *a:None)
        try:
            with patch.object(bot.requests,"post") as post:
                runtime.start_loading(event())
                runtime.start_loading(event() | dict(source=dict(type="group",userId="alice",groupId="g")))
                self.assertEqual(post.call_count,1)
                self.assertTrue(post.call_args.args[0].endswith("/chat/loading/start"))
                self.assertEqual(post.call_args.kwargs["json"],dict(chatId="alice",loadingSeconds=60))
        finally:runtime.close()

    def test_queued_turn_expires_without_starting_another_model_job(self):
        started=threading.Event();calls=[];replies=[]
        ai=FakeAI()
        def ask(*args):
            calls.append(args[0]);started.set();time.sleep(.04);return "late"
        ai.ask=ask
        runtime=bot.BotRuntime("s","",bot.TodoStore(self.root/"todos"),ai,
            sender=lambda e,a:replies.append(a),work_seconds=.01)
        try:
            runtime.submit(event("first","first"))
            self.assertTrue(started.wait(1))
            runtime.submit(event("second","second"))
        finally:runtime.close()
        self.assertEqual(calls,["first"])
        self.assertEqual(len(replies),2)
        self.assertTrue(all("已停止後續步驟" in answer for answer in replies))

    def stage_two(self):
        a=dict(title="會議A",date="2026-10-17",time="15:00–15:30")
        b=dict(title="會議B",date="2026-10-18",time="16:00–16:30")
        self.teacher.stage_event(a,event(identifier="a"))
        reply=self.teacher.stage_event(b,event(identifier="b"))
        self.assertIn("原行程仍保留",reply)
        self.assertEqual(self.teacher.state["pending"]["event"],a)
        return a,b

    def test_replace_requires_a_choice_then_another_confirmation_and_survives_reload(self):
        _,b=self.stage_two()
        self.assertIn("先回覆",self.teacher.before_text("確認排程",event("確認排程")))
        restored=bot.TeacherFeatures(FakeAI(),self.google,enabled=True,owner_id="alice",state_file=self.root/"actions.json",clock=lambda:NOW)
        preview=restored.before_text("取代排程",event("取代排程"))
        self.assertIn("會議B",preview)
        self.assertEqual(restored.state["pending"]["event"],b)
        self.assertEqual(self.google.calls,[])
        self.assertIn("已排進",restored.before_text("確認排程",event("確認排程")))
        self.assertEqual(len(self.google.calls),1)

    def test_keep_cancel_expiry_and_duplicate_do_not_overwrite_original(self):
        a,_=self.stage_two()
        self.teacher.stage_event(a,event(identifier="a"))
        self.assertIsNotNone(self.teacher.state["replacement"])
        self.assertIn("會議A",self.teacher.before_text("保留原排程",event("保留原排程")))
        self.assertEqual(self.teacher.state["pending"]["event"],a)
        self.stage_two()
        self.teacher.before_text("取消排程",event("取消排程"))
        self.assertIsNone(self.teacher.state["pending"])
        self.assertIsNone(self.teacher.state["replacement"])
        self.stage_two()
        self.teacher.clock=lambda:NOW+1201
        self.assertIn("沒有可確認",self.teacher.before_text("確認排程",event("確認排程")))
        self.assertIsNone(self.teacher.state["replacement"])
        self.assertEqual(self.google.calls,[])


if __name__ == "__main__":
    unittest.main()
