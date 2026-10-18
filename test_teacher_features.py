"""Teacher feature tests never write to a real Google account or send LINE messages."""
import io
import json
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import line_bot_local as bot
from test_line_bot_local import NOW, USER


def event(raw="明天下午三點開會", identifier="evt-google", kind="text"):
    return dict(type="message", webhookEventId=identifier, replyToken="test-reply", **USER,
                message=dict(type=kind, **(dict(text=raw) if kind == "text" else dict(id="12345"))))


class FakeAI:
    def __init__(self):
        self.calls = []

    def extract_event(self, text):
        self.calls.append(("event", text))
        return bot.validate_event("明天下午三點開會", dict(isEvent=True, title="開會", date="2026-10-11", time="15:00"), NOW)

    def remember(self, key, previous, question, answer):
        self.calls.append(("remember", key, answer))

    def describe_image(self, image, model):
        self.calls.append(("image", model))
        return "照片顯示一個藍色方塊。"

    def ask(self, raw, conversation):
        self.calls.append(("ask", raw))
        return "回答完成"


class FakeGoogle:
    sheet_id = "test-sheet-only"

    def __init__(self):
        self.calls = []

    def save_photo(self, image, key):
        self.calls.append(("drive", key))
        return "https://drive.google.com/file/d/test-only/view"

    def add_calendar(self, ev, key):
        self.calls.append(("calendar", key))
        return "https://calendar.google.com/calendar/event?eid=test-only"

    def write_sheet(self, row):
        self.calls.append(("sheet", row))
        return True


class TeacherFeatureTests(unittest.TestCase):
    def test_explicit_sheet_save_treats_question_as_literal_content(self):
        from unittest.mock import Mock
        self.google.read_sheet = Mock(side_effect=AssertionError('Save must not read'))
        teacher = self.teacher(sheet_logging=False)
        raw = '存試算表：我今天有哪些行程？'
        self.assertIn('已將指定內容', teacher.before_text(raw, event(raw)))
        self.assertEqual(self.google.calls[0][1][2], '我今天有哪些行程？')
        self.google.read_sheet.assert_not_called()

    def test_english_calendar_read_preserves_day(self):
        from unittest.mock import Mock
        self.google.read_calendar = Mock(return_value=[])
        teacher = self.teacher(sheet_logging=False)
        for text, day in [('show my calendar tomorrow', 1), ('show my calendar today', 0), ('查我的日曆今日有什麼', 0)]:
            teacher.before_text(text, event(text))
            actual = self.google.read_calendar.call_args.args[0]
            self.assertEqual(actual.start.day, 10 + day)
            self.assertEqual((actual.end - actual.start).days, 1)

    def test_literal_commands_do_not_execute_embedded_school_queries(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        school = Mock(side_effect=AssertionError('Literal command must not query school'))
        replies=[]
        runtime = bot.BotRuntime('s','',bot.TodoStore(self.path/'todos'), self.ai,
            teacher=self.teacher(sheet_logging=False), elearn=SimpleNamespace(handle=school),
            sender=lambda e,a:replies.append(a))
        runtime.submit(event('記錄：我的e學苑待辦有哪些', 'literal-todo'))
        runtime.submit(event('存試算表：我的e學苑待辦有哪些', 'literal-sheet'))
        runtime.close()
        self.assertIn('已記錄', replies[0])
        self.assertIn('已將指定內容', replies[1])
        school.assert_not_called()
        self.assertEqual(self.google.calls[0][1][2], '我的e學苑待辦有哪些')

    def test_explicit_school_personal_query_reaches_school(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        school = Mock(return_value='SCHOOL_RESULT')
        replies=[]
        runtime = bot.BotRuntime('s','',bot.TodoStore(self.path/'todos'), self.ai,
            teacher=self.teacher(sheet_logging=False), elearn=SimpleNamespace(handle=school),
            sender=lambda e,a:replies.append(a))
        runtime.submit(event('我的e學苑待辦有哪些', 'explicit-school'))
        runtime.close()
        school.assert_called_once()
        self.assertEqual(replies, ['SCHOOL_RESULT'])

    def test_ambiguous_invalid_calendar_period_requires_clarification_without_read(self):
        from unittest.mock import Mock
        self.google.read_calendar = Mock(side_effect=AssertionError('Ambiguous period must not read'))
        teacher = self.teacher(sheet_logging=False)
        for q in ['查日曆2026-02-30', '查日曆今天和明天', '查日曆下個月']:
            self.assertNotIn('暫時讀取失敗', teacher.before_text(q, event()))
        self.google.read_calendar.assert_not_called()

    def test_explicit_calendar_date_week_and_relative_period_are_read_exactly(self):
        from unittest.mock import Mock
        self.google.read_calendar = Mock(return_value=[])
        teacher = self.teacher(sheet_logging=False)
        for q, start, end in [('查日曆2026年10月25日','2026-10-25','2026-10-26'),
            ('我的下週行程有哪些','2026-10-12','2026-10-19'),
            ('查日曆大後天','2026-10-13','2026-10-14'),
            ('show my calendar in 3 days','2026-10-13','2026-10-14')]:
            answer = teacher.before_text(q,event(q))
            period = self.google.read_calendar.call_args.args[0]
            self.assertEqual(period.start.date().isoformat(),start)
            self.assertEqual(period.end.date().isoformat(),end)
            self.assertIn('唯讀',answer)

    def test_runtime_personal_reads_do_not_get_intercepted_by_school_calendar(self):
        from types import SimpleNamespace
        def unexpected(*args):
            raise AssertionError('Personal store must not route to school calendar')
        self.google.read_sheet = lambda: [['時間', '類型', '內容'], ['2026-10-18', '紀錄', 'PRIVATE_ROW']]
        replies = []
        runtime = bot.BotRuntime('secret', 'token', bot.TodoStore(self.path/'todos'), self.ai,
            teacher=self.teacher(sheet_logging=False), elearn=SimpleNamespace(handle=unexpected),
            sender=lambda e,a: replies.append(a), show_runtime=True)
        runtime.submit(event('我的待辦有哪些', 'route-todo'))
        runtime.submit(event('我的試算表有哪些資料', 'route-sheet'))
        runtime.close()
        self.assertEqual(len(replies), 2)
        self.assertIn('私人本機待辦', replies[0])
        self.assertIn('PRIVATE_ROW', replies[1])
        self.assertIn('私人試算表', replies[1])
        self.assertEqual(self.ai.calls, [])

    def test_private_reads_are_owner_only_and_never_write_or_call_model(self):
        self.google.read_sheet = lambda: [['時間', '類型', '內容'], ['2026-10-18', '手動紀錄', 'PRIVATE_ROW']]
        days = []
        self.google.read_calendar = lambda day: days.append(day) or [dict(summary='PRIVATE_EVENT', start=dict(dateTime='2026-10-19T15:00:00+08:00'))]
        teacher = self.teacher(sheet_logging=False)
        self.assertIn('PRIVATE_ROW', teacher.before_text('我的試算表有哪些資料', event()))
        self.assertIn('PRIVATE_EVENT', teacher.before_text('我明天有什麼行程', event()))
        self.assertEqual(days[0].label, "明天")
        self.assertEqual(days[0].start.day, 11)
        for source in [dict(type='user', userId='bob'), dict(type='group', userId='alice', groupId='g')]:
            self.assertIn('綁定者', teacher.before_text('查試算表', event() | dict(source=source)))
        self.assertEqual(self.google.calls, [])
        self.assertEqual(self.ai.calls, [])
        self.google.read_sheet = lambda: (_ for _ in ()).throw(RuntimeError('private token'))
        answer = teacher.before_text('查試算表', event())
        self.assertIn('暫時讀取失敗', answer)
        self.assertNotIn('private token', answer)

    def test_english_commands_keep_owner_and_confirmation_boundaries(self):
        teacher = self.teacher(sheet_logging=False)
        self.assertTrue(bot.event_candidate('Schedule W6 phone test on 2026-10-17 at 15:00'))
        self.assertFalse(bot.event_candidate('Who scheduled 2026-10-17 15:00?'))
        self.assertIn('沒有可確認', teacher.before_text('confirm schedule', event()))
        teacher.before_text('save to sheet: W6 phone test', event(identifier='english-sheet'))
        self.assertEqual(self.google.calls[0][1][2], 'W6 phone test')
        incoming = event() | dict(source=dict(type='user', userId='bob'))
        self.assertIn('綁定者', teacher.before_text('save to sheet: private', incoming))
        self.assertEqual(len(self.google.calls), 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.ai, self.google = FakeAI(), FakeGoogle()
        image = io.BytesIO()
        Image.new("RGB", (300, 400), "blue").save(image, "PNG")
        self.image = image.getvalue()

    def tearDown(self):
        self.temp.cleanup()

    def teacher(self, **kwargs):
        defaults = dict(ai=self.ai, google=self.google, enabled=True, owner_id="alice", token="test-token",
                        sheet_logging=True,
                        http=lambda *a, **k: self.image, state_file=self.path / "google.json", clock=lambda: NOW)
        return bot.TeacherFeatures(**(defaults | kwargs))

    def test_manual_sheet_save_works_without_automatic_logging_and_deduplicates(self):
        teacher=self.teacher(sheet_logging=False)
        incoming=event("存試算表：W6 課堂版驗收：手動保存功能", "manual-sheet")
        result=teacher.before_text(incoming["message"]["text"],incoming)
        self.assertIn("已將指定內容",result)
        self.assertFalse(teacher.sheet_logging)
        self.assertEqual([call[0] for call in self.google.calls],["sheet"])
        self.assertEqual(self.google.calls[0][1][1:4],["手動紀錄","W6 課堂版驗收：手動保存功能","使用者明確指定保存"])
        reopened=self.teacher(sheet_logging=False)
        reopened.before_text(incoming["message"]["text"],incoming)
        self.assertEqual(len(self.google.calls),1)
        self.assertEqual(reopened.record(event("今天新聞"),"回答"),"回答")

    def test_manual_sheet_validation_owner_group_and_no_duplicate_auto_row(self):
        teacher=self.teacher()
        for i,raw in enumerate(["存試算表：", "存試算表："+"a"*2001]):
            self.assertIn("2000字",teacher.before_text(raw,event(raw,str(i))))
        for source in [dict(type="user",userId="bob"),dict(type="group",userId="alice",groupId="g")]:
            incoming=event("存試算表：不能保存") | dict(source=source)
            self.assertIn("綁定者",teacher.before_text(incoming["message"]["text"],incoming))
        self.assertEqual(self.google.calls,[])
        self.assertIn("尚未設定",self.teacher(enabled=False).before_text("存試算表：測試",event()))
        incoming=event("存試算表：=1+1","raw-value")
        result=teacher.before_text(incoming["message"]["text"],incoming)
        teacher.record(incoming,result,kind="行程")
        self.assertEqual(len(self.google.calls),1)
        self.assertEqual(self.google.calls[0][1][2],"=1+1")

    def test_manual_sheet_failure_does_not_claim_success_or_retry_after_reload(self):
        def fail(row):
            self.google.calls.append(("sheet",row))
            raise RuntimeError("private credential")
        self.google.write_sheet=fail
        incoming=event("存試算表：驗收","uncertain-sheet")
        first=self.teacher(sheet_logging=False).before_text(incoming["message"]["text"],incoming)
        second=self.teacher(sheet_logging=False).before_text(incoming["message"]["text"],incoming)
        self.assertNotIn("private credential",first)
        self.assertIn("未確認",first)
        self.assertNotIn("已將指定內容",second)
        self.assertEqual(len(self.google.calls),1)

    def test_runtime_routes_manual_save_without_model_or_automatic_sheet_row(self):
        replies=[]
        teacher=self.teacher(sheet_logging=False)
        runtime=bot.BotRuntime("s","t",bot.TodoStore(self.path/"todos"),self.ai,teacher=teacher,
            sender=lambda e,a:replies.append(a),show_runtime=True)
        try:
            runtime.capacity.acquire()
            runtime.process(event("存試算表：課堂驗收","runtime-save"))
            self.assertEqual(len(replies),1)
            self.assertIn("已將指定內容",replies[0])
            self.assertNotIn("本機模型設定",replies[0])
            self.assertEqual(self.ai.calls,[])
            self.assertEqual([call[0] for call in self.google.calls],["sheet"])
        finally:runtime.close()

    def test_runtime_footer_preserves_cards_and_does_not_mutate_answer(self):
        replies=[]
        runtime=bot.BotRuntime("s","t",bot.TodoStore(self.path/"todos"),self.ai,
            sender=lambda e,a:replies.append(a),show_runtime=True)
        try:
            answer=[dict(type="text",text="回答 [1]"),dict(type="flex",contents=dict(example="unchanged"))]
            runtime.deliver(event(),answer,bot.time.monotonic(),"test-local-model")
            self.assertIn("test-local-model",replies[0][0]["text"])
            self.assertIn("本題處理",replies[0][0]["text"])
            self.assertEqual(replies[0][1],answer[1])
            self.assertEqual(answer[0]["text"],"回答 [1]")
            runtime.deliver(event(),"已記錄待辦",bot.time.monotonic())
            self.assertEqual(replies[1],"已記錄待辦")
        finally:runtime.close()

    def test_calendar_model_time_spacing_is_normalized(self):
        parsed = bot.validate_event("2026-10-11 下午3點到4點模型測試",
            dict(isEvent=True, title="模型測試", date="2026-10-11", time="15:00 - 16:00"), NOW)
        self.assertEqual(parsed["time"], "15:00–16:00")

    def test_event_validation_rejects_invalid_and_hallucinated_dates(self):
        valid = dict(isEvent=True, title="開會", date="2026-10-11", time="15:00-16:00")
        self.assertIsNotNone(bot.validate_event("明天下午三點開會", valid, NOW))
        self.assertIsNotNone(bot.validate_event("明天下午三點開會", valid | dict(time="15:00:00"), NOW))
        self.assertIsNone(bot.validate_event("明天開會", valid, NOW))
        self.assertTrue(bot.event_candidate("明天下午三點開會"))
        self.assertFalse(bot.event_candidate("明天有什麼新聞？"))
        for raw, value in [("明天下午三點開會", valid | dict(date="2026-10-12")),
                           ("10月12日開會", valid), ("2月30日開會", valid | dict(date="2026-02-28")),
                           ("幫我開會", valid), ("明天開會", valid | dict(time="25:99")),
                           ("明天開會", valid | dict(time="16:00-15:00")),
                           ("明天開會", valid | dict(isEvent=False))]:
            self.assertIsNone(bot.validate_event(raw, value, NOW), raw)

    def test_calendar_requires_owner_private_chat_and_confirmation(self):
        teacher = self.teacher()
        preview = teacher.before_text("明天下午三點開會", event())
        self.assertIn("待確認行程", preview)
        self.assertEqual(self.google.calls, [])
        stranger = event("確認排程") | dict(source=dict(type="user", userId="bob"))
        self.assertIn("綁定者", teacher.before_text("確認排程", stranger))
        group = event("確認排程") | dict(source=dict(type="group", userId="alice", groupId="test-group"))
        self.assertIn("個人聊天", teacher.before_text("確認排程", group))
        reopened = self.teacher()
        reply = reopened.before_text("確認排程", event("確認排程", "confirm"))
        self.assertIn("已排進 Google 日曆", reply)
        self.assertEqual([c[0] for c in self.google.calls], ["calendar"])
        self.assertIn("沒有可確認", reopened.before_text("確認排程", event()))

    def test_cancel_expiry_and_disabled_google_never_write(self):
        teacher = self.teacher()
        teacher.before_text("明天下午三點開會", event())
        self.assertIn("已取消", teacher.before_text("取消排程", event()))
        self.assertIn("沒有可確認", teacher.before_text("確認排程", event()))
        teacher.before_text("明天下午三點開會", event())
        teacher.clock = lambda: NOW + 1201
        self.assertIn("沒有可確認", teacher.before_text("確認排程", event()))
        teacher = self.teacher(enabled=False)
        self.assertIn("尚未啟用", teacher.before_text("明天下午三點開會", event()))
        self.assertEqual(self.google.calls, [])

    def test_drive_vision_sheet_workflow_persists_dedup(self):
        teacher = self.teacher()
        incoming = event(kind="image")
        reply = teacher.image(incoming)
        self.assertIn("藍色方塊", reply)
        self.assertIn("照片已存進 Google Drive", reply)
        self.assertIn("已記進 Google 試算表", reply)
        self.assertEqual([c[0] for c in self.google.calls], ["drive", "sheet"])
        self.teacher().image(incoming)
        self.assertEqual([c[0] for c in self.google.calls], ["drive", "sheet"])
        self.assertEqual(self.google.calls[1][1][2], "（照片）")

    def test_unbound_image_keeps_local_vision_without_cloud_writes(self):
        incoming = event(kind="image") | dict(source=dict(type="user", userId="bob"))
        reply = self.teacher().image(incoming)
        self.assertIn("藍色方塊", reply)
        self.assertIn("未上傳", reply)
        self.assertEqual(self.google.calls, [])

    def test_google_failure_is_redacted_and_not_retried_after_restart(self):
        class FailingGoogle(FakeGoogle):
            def save_photo(self, image, key):
                self.calls.append(("drive", key))
                raise RuntimeError("secret-token and private-sheet-id must not leak")
        google = FailingGoogle()
        teacher = self.teacher(google=google)
        reply = teacher.image(event(kind="image"))
        self.assertIn("結果未確認", reply)
        self.assertNotIn("secret-token", reply)
        self.assertNotIn("private-sheet-id", reply)
        self.teacher(google=google).image(event(kind="image"))
        self.assertEqual([c[0] for c in google.calls].count("drive"), 1)

    def test_image_event_only_stages_calendar_and_vision_failure_is_honest(self):
        self.ai.describe_image = lambda *a: "明天下午三點開會"
        reply = self.teacher().image(event(kind="image"))
        self.assertIn("待確認行程", reply)
        self.assertNotIn("calendar", [c[0] for c in self.google.calls])
        def fail(*args):
            raise ValueError("no vision")
        self.ai.describe_image = fail
        reply = self.teacher().image(event(kind="image", identifier="second"))
        self.assertIn("暫時無法辨識", reply)
        self.assertIn("照片已存進", reply)

    def test_sheet_preserves_source_cards_and_skips_greetings_and_strangers(self):
        teacher = self.teacher()
        messages = [dict(type="text", text="回答 [1]"), dict(type="flex", altText="來源", contents={})]
        reply = teacher.record(event("今天新聞", "news"), messages)
        self.assertEqual(reply[1], messages[1])
        self.assertIn("已記進", reply[0]["text"])
        self.assertEqual(messages[0]["text"], "回答 [1]")
        teacher.record(event("你好", "hello"), "嗨")
        teacher.record(event("新聞", "stranger") | dict(source=dict(type="user", userId="bob")), "回答")
        self.assertEqual(len(self.google.calls), 1)

    def test_disabled_sheet_logging_keeps_drive_calendar_and_answers(self):
        teacher = self.teacher(sheet_logging=False)
        answer = [dict(type="text", text="回答"), dict(type="flex", contents={})]
        self.assertEqual(teacher.record(event("今天新聞"), answer), answer)
        self.assertNotIn("已記進", teacher.image(event(kind="image", identifier="photo-no-log")))
        teacher.before_text("明天下午三點開會", event(identifier="schedule-no-log"))
        reply = teacher.before_text("確認排程", event(identifier="confirm-no-log"))
        self.assertEqual(teacher.record(event("確認排程"), reply, kind="行程"), reply)
        self.assertEqual([c[0] for c in self.google.calls], ["drive", "calendar"])

    def test_sheet_keeps_results_without_casual_or_schedule_preview_noise(self):
        teacher = self.teacher()
        for i, raw in enumerate(["謝謝！", "好喔", "你好，謝謝", "測試一下", "在嗎？"]):
            self.assertEqual(teacher.record(event(raw, str(i)), "回覆"), "回覆")
        teacher.record(event("明天下午三點開會", "preview"), "請確認行程", kind="行程")
        teacher.record(event("取消排程", "cancel"), "已取消待確認行程", kind="行程")
        teacher.record(event("確認排程", "missing"), "沒有可確認的行程", kind="行程")
        teacher.record(event("今天新聞", "failed"), "本機模型暫時無法回答，請稍後再試。")
        self.assertEqual(self.google.calls, [])
        teacher.record(event("確認排程", "done"), "已排進 Google 日曆：開會", kind="行程")
        teacher.record(event("好喔，解釋牛頓第二定律", "question"), "F = ma")
        self.assertEqual(len(self.google.calls), 2)
        self.assertEqual(self.google.calls[0][1][1], "行程")
        self.assertEqual(self.google.calls[0][1][5], "已建立")

    def test_gws_commands_use_no_shell_raw_sheet_values_and_private_events(self):
        calls = []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:4] == ["sheets", "spreadsheets", "values"]:
                data = dict(updates=dict(updatedRows=1))
            else:
                data = dict(id="test-only", htmlLink="https://calendar.google.com/test")
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")
        google = bot.GoogleWorkspace("gws-test", sheet_id="test-sheet-only", run=run)
        google.write_sheet(["=IMPORTXML(\"http://evil\",\"//x\")"])
        params = json.loads(calls[0][0][calls[0][0].index("--params") + 1])
        self.assertEqual(params["valueInputOption"], "RAW")
        parsed = self.ai.extract_event("明天下午三點開會")
        google.add_calendar(parsed, "stable-event-key")
        body = json.loads(calls[1][0][calls[1][0].index("--json") + 1])
        self.assertNotIn("attendees", body)
        self.assertEqual(body["start"]["timeZone"], "Asia/Taipei")
        self.assertEqual(len(body["id"]), 64)
        self.assertFalse(calls[0][1].get("shell", False))
        google.run = lambda *a, **k: subprocess.CompletedProcess([], 1, "", "private credential")
        with self.assertRaises(RuntimeError) as error:
            google.write_sheet(["test"])
        self.assertNotIn("private credential", str(error.exception))

    def test_gws_photo_upload_is_temporary_private_and_folder_name_escaped(self):
        calls, temporary = [], []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:4] == ["drive", "files", "list"]:
                data = dict(files=[dict(id="test-folder")])
            else:
                temporary.append(Path(kwargs["cwd"]))
                self.assertEqual(Path(kwargs["cwd"], "photo.jpg").read_bytes(), b"image")
                data = dict(id="test-photo", webViewLink="https://drive.google.com/test")
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")
        google = bot.GoogleWorkspace("gws-test", folder="photo's folder", run=run)
        self.assertEqual(google.save_photo(b"image", "evt"), "https://drive.google.com/test")
        params = json.loads(calls[0][0][calls[0][0].index("--params") + 1])
        self.assertIn("photo\\'s folder", params["q"])
        self.assertFalse(temporary[0].exists())
        self.assertNotIn("permissions", " ".join(calls[1][0]))

    def test_vision_model_capability_and_structured_calendar_format(self):
        calls = []
        def http(url, **kwargs):
            calls.append((url, kwargs))
            return json.dumps(dict(capabilities=["vision"]) if url.endswith("/api/show") else dict(message=dict(content="照片內容"))).encode()
        ai = bot.LocalAI(http=http)
        self.assertEqual(ai.describe_image(b"image"), "照片內容")
        self.assertEqual(calls[1][1]["json"]["model"], "gemma4:e4b-it-q4_K_M")
        self.assertIn("images", calls[1][1]["json"]["messages"][0])
        ai.http = lambda *a, **k: b'{"capabilities":["completion"]}'
        with self.assertRaises(ValueError):
            ai.describe_image(b"image", "qwen2.5:3b")

    def test_webhook_accepts_images_validates_id_and_preserves_todo_routes(self):
        done, replies = threading.Event(), []
        teacher = self.teacher()
        def sender(received, answer):
            replies.append(answer)
            done.set()
        runtime = bot.BotRuntime("test-secret", "test-token", bot.TodoStore(self.path / "todos"), self.ai,
                                 teacher=teacher, sender=sender)
        client = bot.create_app(runtime).test_client()
        import base64, hashlib, hmac
        def post(incoming):
            body = json.dumps(dict(events=[incoming])).encode()
            signed = base64.b64encode(hmac.new(b"test-secret", body, hashlib.sha256).digest()).decode()
            return client.post("/webhook", data=body, headers={"x-line-signature": signed})
        try:
            self.assertEqual(post(event(kind="image")).status_code, 200)
            self.assertTrue(done.wait(2))
            self.assertIn("藍色方塊", replies[0])
            malformed = event(kind="image")
            malformed["message"]["id"] = 123
            self.assertEqual(post(malformed).status_code, 400)
            done.clear()
            self.assertEqual(post(event("記錄：星期五交報告", "todo")).status_code, 200)
            self.assertTrue(done.wait(2))
            self.assertIn("已記錄", replies[-1])
            self.assertNotIn("已記進 Google", replies[-1])
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
