"""No real LINE calls: validate the Python port with isolated data and mocks."""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from PIL import Image
import line_bot_local as bot

NOW = 1791590400.0  # 2026-10-10 00:00 UTC, Taipei 08:00
RSS = '''<rss><channel><item><title>New report</title><link>https://example.org/new</link><description>Verified report 科學新聞 東華消息</description><pubDate>Fri, 09 Oct 2026 12:00:00 GMT</pubDate></item><item><title>Old report</title><link>https://example.org/old</link><pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'''.encode()
ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:assignment-1\r\nDTSTART:20261011T000000Z\r\nDTEND:20261011T000000Z\r\nSUMMARY:作業一\r\nCATEGORIES:物理課\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
CALENDAR_URL = "https://elearn4.ndhu.edu.tw/moodle/calendar/export_execute.php?authtoken=test-only"
USER = dict(source=dict(type="user", userId="alice"))


class ResponseStub:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class PythonBotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def elearn(self, **kwargs):
        return bot.Elearn(calendar_url=CALENDAR_URL, state_file=self.path / "calendar.json",
                          bind_code="test-bind", clock=lambda: NOW, http=lambda *a, **k: ICS.encode(), **kwargs)

    def test_todo_legacy_data_isolation_and_reopen(self):
        path = self.path / "todos.jsonl"
        path.write_text(json.dumps(dict(content="legacy", userId=None)) + "\n")
        store = bot.TodoStore(path)
        self.assertIn("已記錄", store.reply("記錄：星期五交報告", "alice", "one"))
        store.reply("記錄：星期五交報告", "alice", "one")
        self.assertEqual(len(store.read()), 2)
        self.assertIn("星期五", bot.TodoStore(path).reply("查詢", "alice"))
        self.assertNotIn("legacy", store.reply("查詢", "alice"))
        self.assertIn("沒有待辦", store.reply("查詢", "bob"))
        self.assertIn("無法辨識", store.reply("查詢"))

    def test_todo_empty_limit_order_and_corrupt_file(self):
        store = bot.TodoStore(self.path / "tasks")
        self.assertIn("請輸入", store.reply("記錄：", "alice"))
        self.assertIn("縮短", store.reply("記錄:" + "🙂" * 151, "alice"))
        for i in range(12):
            store.reply(f"紀録:{i}", "alice", str(i))
        reply = store.reply("查詢", "alice")
        self.assertIn("共 12 筆，顯示最新 10 筆", reply)
        self.assertIn("1. 11", reply)
        self.assertNotIn("11. ", reply)
        store.path.write_text("invalid JSON")
        self.assertIn("無法讀取", store.reply("查詢", "alice"))

    def test_signature_checks_exact_raw_body(self):
        body = b'{"events": []}'
        signature = base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
        self.assertTrue(bot.verify_signature(body, signature, "secret"))
        self.assertFalse(bot.verify_signature(body + b" ", signature, "secret"))
        for value in (None, "wrong", "中文"):
            self.assertFalse(bot.verify_signature(body, value, "secret"))

    def test_news_dates_xml_entities_and_search_links(self):
        results = bot.parse_search_feed(RSS, recent=True, now=NOW)
        self.assertEqual([r["title"] for r in results], ["New report"])
        self.assertEqual(len(bot.parse_search_feed(RSS)), 2)
        with self.assertRaises(Exception):
            bot.parse_search_feed(b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>')
        html = '<table><tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Freview">心得</a></td></tr><tr><td>摘要</td></tr></table>'
        result = bot.parse_search_html(html)[0]
        self.assertEqual(result["url"], "https://example.org/review")
        self.assertEqual(result["snippet"], "摘要")
        self.assertEqual(bot.parse_search_html("<html>驗證頁</html>"), [])

    def test_search_calls_local_model_and_attaches_real_sources(self):
        calls = []
        def http(url, **kwargs):
            calls.append((url, kwargs))
            return RSS if url.startswith("https:") else json.dumps(dict(message=dict(content="答覆。[1] https://fake.invalid/link"))).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        reply = ai.ask("最新：科學新聞")
        self.assertIn("news.google.com", calls[0][0])
        self.assertIn("127.0.0.1:11434/api/chat", calls[1][0])
        prompt = calls[1][1]["json"]["messages"][-1]["content"]
        self.assertIn("New report", prompt)
        self.assertNotIn("Old report", prompt)
        self.assertNotIn("fake.invalid", reply[0]["text"])
        uri = reply[1]["contents"]["contents"][0]["footer"]["contents"][0]["action"]["uri"]
        self.assertEqual(uri, "https://example.org/new")

    def test_current_taiwan_president_uses_live_official_title(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            return '<title>測試人物總統-總統與副總統｜中華民國總統府</title>'.encode()
        ai = bot.LocalAI(http=http)
        for question in ["現在的總統是誰？", "台灣目前的總統是誰", "現在台灣總統是誰"]:
            result = ai.lookup(question)
            self.assertIn("測試人物", result[0]["snippet"])
            self.assertEqual(result[0]["url"], "https://www.president.gov.tw/Page/694")
        self.assertEqual(len(calls), 3)

    def test_search_removes_instructions_and_filters_before_top_three(self):
        self.assertEqual(bot.search_query("請幫我查詢台灣目前的總統是誰？"), "台灣現任 總統")
        rows = [dict(title="國語辭典：台灣", snippet="台灣", url="https://dictionary.example/a"),
                dict(title="現在時間", snippet="台灣時間", url="https://clock.example/a"),
                dict(title="無關結果", snippet="其他", url="https://example.org/other"),
                dict(title="現任總統介紹", snippet="台灣總統", url="https://www.president.gov.tw/Page/694")]
        result = bot.relevant_sources(rows, "現任 總統")
        self.assertEqual([r["title"] for r in result], ["現任總統介紹"])
        self.assertTrue(bot.relevant_sources(rows[:1], "台灣", definitions=True))

    def test_president_fallback_rejects_unrelated_clock_results(self):
        ai = bot.LocalAI(http=lambda url, **kw: b'<title>unavailable</title>' if 'president.gov.tw/Page' in url else RSS)
        self.assertEqual(ai.lookup("現在的總統是誰？"), [])

    def test_live_president_fact_overrides_wrong_model_and_old_history(self):
        def http(url, **kwargs):
            if url.startswith("https:"):
                return '<title>測試人物總統-總統與副總統｜中華民國總統府</title>'.encode()
            self.assertEqual(len(kwargs['json']['messages']), 2)
            return json.dumps({'message': {'content': '錯誤人物當選，這只是舊資料'}}).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        ai.remember('owner', [], '總統當選人', '錯誤人物')
        reply = ai.ask('現在的總統是誰', 'owner')
        self.assertEqual(reply[0]['text'], '台灣（中華民國）的現任總統是測試人物。[1]')
        self.assertNotIn('錯誤人物', str(ai.conversations['owner']))
        self.assertIn('哪一年的總統選舉', ai.ask('總統當選人', 'owner'))

    def test_no_search_for_teaching_and_history_isolation_expiry(self):
        calls, clock = [], [NOW]
        def http(url, **kwargs):
            self.assertTrue(url.startswith("http://127.0.0.1"))
            calls.append(kwargs["json"])
            return b'{"message":{"content":"F=ma"}}'
        ai = bot.LocalAI(http=http, clock=lambda: clock[0])
        self.assertEqual(ai.ask("教我牛頓第二定律", "alice"), "F=ma")
        ai.ask("那詳細說明一下", "alice")
        self.assertEqual(len(calls[1]["messages"]), 4)
        ai.ask("教我公式", "bob")
        self.assertEqual(len(calls[2]["messages"]), 2)
        clock[0] += 1201
        ai.ask("教我公式", "alice")
        self.assertEqual(len(calls[3]["messages"]), 2)
        with self.assertRaises(ValueError):
            bot.LocalAI(base_url="https://cloud.example.org")

    def test_search_failures_and_model_failure_do_not_fake_news(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if url.startswith("https:"):
                raise RuntimeError("unavailable")
            self.assertIn("不可猜測", kwargs["json"]["messages"][0]["content"])
            return json.dumps(dict(message=dict(content="基本背景"))).encode()
        reply = bot.LocalAI(http=http).ask("今天有什麼新聞")
        self.assertIn("沒查到可確認", reply)
        self.assertEqual(len(calls), 4)
        def no_model(url, **kwargs):
            if url.startswith("https:"):
                return RSS
            raise RuntimeError("offline")
        reply = bot.LocalAI(http=no_model, clock=lambda: NOW).ask("最新：新聞")
        self.assertIn("本機模型暫時無法整理", reply[0]["text"])
        self.assertEqual(reply[1]["type"], "flex")

    def test_news_expands_then_uses_web(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if "news.google" in url:
                return b"<rss><channel/></rss>"
            if "duckduckgo" in url:
                return b"<html>blocked</html>"
            if "bing.com" in url:
                return RSS
            return b'{"message":{"content":"Answer [1]"}}'
        reply = bot.LocalAI(http=http, clock=lambda: NOW).ask("東華最近有什麼消息？")
        self.assertIn("when%3A7d", calls[0])
        self.assertIn("when%3A30d", calls[1])
        self.assertIn("duckduckgo", calls[2])
        self.assertEqual(reply[1]["type"], "flex")

    def test_calendar_timezone_cancellation_and_recurrence(self):
        events = bot.parse_calendar(ICS)
        self.assertEqual(events[0]["at"], int((NOW + bot.DAY) * 1000))
        self.assertIn("10/11 08:00", bot.format_calendar(events, NOW))
        local = ICS.replace("20261011T000000Z", "20261011T080000").replace("DTSTART:", "DTSTART;TZID=Asia/Taipei:")
        self.assertEqual(bot.parse_calendar(local)[0]["at"], events[0]["at"])
        self.assertEqual(bot.parse_calendar(ICS.replace("SUMMARY:", "STATUS:CANCELLED\r\nSUMMARY:")), [])
        for invalid in ("<html>login</html>", ICS.replace("SUMMARY:", "RRULE:FREQ=DAILY\r\nSUMMARY:")):
            with self.assertRaises(ValueError):
                bot.parse_calendar(invalid)
        all_day = ICS.replace("DTSTART:20261011T000000Z", "DTSTART;VALUE=DATE:20261011")
        self.assertTrue(bot.parse_calendar(all_day)[0]["allDay"])

    def test_calendar_url_and_intent_routing(self):
        self.assertEqual(bot.validate_calendar_url(CALENDAR_URL), CALENDAR_URL)
        for url in ("http://127.0.0.1/?authtoken=x", CALENDAR_URL.replace("export_execute", "login")):
            with self.assertRaises(ValueError):
                bot.validate_calendar_url(url)
        self.assertEqual(bot.calendar_intent("明天要交什麼？")["range"], "tomorrow")
        for question in ("搜尋 e學院介紹", "教我怎麼寫作業", "老師評價", "今天的新聞"):
            self.assertIsNone(bot.calendar_intent(question))

    def test_calendar_binding_private_isolation_refresh_and_legacy_state(self):
        service = self.elearn()
        self.assertIn("尚未綁定", service.handle("e學苑", USER))
        self.assertIn("不正確", service.handle("綁定e學苑 wrong", USER))
        self.assertIn("個人聊天", service.handle("綁定e學苑 test-bind", dict(source=dict(type="group", userId="alice"))))
        self.assertIn("已綁定", service.handle("綁定e學院 test-bind", USER))
        self.assertIn("尚未綁定", service.handle("e學苑", dict(source=dict(type="user", userId="bob"))))
        self.assertIn("沒有今天", service.handle("我今天有什麼作業？", USER))
        self.assertIn("作業一", service.handle("明天要交什麼？", USER))
        service.http = lambda *a, **k: ICS.replace("作業一", "改期作業").encode()
        self.assertIn("作業一", service.handle("e學苑", USER))
        self.assertIn("改期作業", service.handle("同步e學苑", USER))
        self.assertIsNone(self.elearn().bind_code)
        self.assertIn("已關閉", service.handle("關閉提醒", USER))

    def test_reminder_retry_key_survives_restart_and_deduplicates(self):
        pushes, fail = [], [True]
        def send(url, **kwargs):
            pushes.append(kwargs)
            return ResponseStub(500 if fail[0] else 200)
        service = self.elearn(push_http=send)
        service.handle("綁定e學苑 test-bind", USER)
        service.tick()
        fail[0] = False
        reopened = self.elearn(push_http=send)
        reopened.tick()
        self.assertEqual(pushes[0]["headers"]["X-Line-Retry-Key"], pushes[1]["headers"]["X-Line-Retry-Key"])
        before = len(pushes)
        reopened.tick()
        self.assertEqual(len(pushes), before)
        self.assertEqual(pushes[-1]["json"]["to"], "alice")
        reopened.handle("關閉提醒", USER)
        reopened.tick()
        self.assertEqual(len(pushes), before)

    def test_expired_uncertain_push_does_not_generate_new_key(self):
        service = self.elearn(push_http=lambda *a, **k: self.fail("Should not send"))
        service.state.update(ownerId="alice", reminders=True)
        service.state["notices"]["test"] = dict(retryKey="old-key", createdAt=int((NOW - bot.DAY) * 1000), sent=False)
        service.push("test", "message")
        self.assertEqual(service.state["notices"]["test"]["retryKey"], "old-key")

    def test_photos_followup_and_private_ip_rejection(self):
        self.assertEqual(bot.photo_subject("給我東華大學陳文盛老師的照片"), "東華大學陳文盛老師")
        self.assertEqual(bot.photo_subject("他的照片呢？", "東華大學陳文盛老師的評價"), "東華大學陳文盛老師")
        self.assertIsNone(bot.photo_subject("幫我生成圖片"))
        for address in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "fc00::1", "224.0.0.1"):
            self.assertFalse(bot.public_ip(address))
        self.assertTrue(bot.public_ip("8.8.8.8"))
        for url in ("https://127.0.0.1/private", "http://example.org/a"):
            with self.assertRaises(ValueError):
                bot.get_public(url)

    def test_photos_convert_source_and_limit_public_routes(self):
        buffer = io.BytesIO()
        Image.new("RGB", (300, 400), "blue").save(buffer, "PNG")
        def download(url, **kwargs):
            if "duckduckgo" in url:
                body = b'<a class="result-link" href="https://school.example.org/teacher">Teacher</a>'
            elif url.endswith("/teacher"):
                body = b'<title>Teacher</title><img src="https://school.example.org/photo.png">'
            else:
                body = buffer.getvalue()
            return dict(body=body, url=url)
        photos = bot.Photos("https://bot.example.org", self.path, download)
        messages = photos.handle("給我東華大學的照片")
        self.assertEqual(messages[1]["type"], "image")
        self.assertIn("school.example.org/teacher", messages[0]["text"])
        filename = messages[1]["previewImageUrl"].split("/")[-1]
        with Image.open(self.path / filename) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 320)
        runtime = bot.BotRuntime("secret", "token", None, None, photos=photos)
        try:
            client = bot.create_app(runtime).test_client()
            response = client.get("/photos/" + filename)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "image/jpeg")
            response.close()
            self.assertEqual(client.get("/photos/../../.env").status_code, 404)
            self.assertEqual(photos.handle("給我東華大學的照片"), messages)
        finally:
            runtime.close()

    def test_webhook_immediate_ack_dedup_validation_and_background_reply(self):
        gate, done, calls, replies = threading.Event(), threading.Event(), [], []
        class AI:
            def ask(self, raw, conversation):
                calls.append((raw, conversation))
                gate.wait(2)
                return "回答完成"
        def sender(event, answer):
            replies.append(answer)
            done.set()
        runtime = bot.BotRuntime("secret", "token", bot.TodoStore(self.path / "tasks"), AI(), sender=sender)
        client = bot.create_app(runtime).test_client()
        event = dict(type="message", webhookEventId="evt", replyToken="reply", **USER, message=dict(type="text", text="最新新聞"))
        def post(data, signature=None):
            body = json.dumps(data).encode()
            signed = signature or base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
            return client.post("/webhook", data=body, headers={"x-line-signature": signed})
        try:
            self.assertEqual(client.get("/health").data, b"ok")
            self.assertEqual(post(dict(events=[event]), "bad").status_code, 401)
            self.assertEqual(post(dict(events=[event])).status_code, 200)
            self.assertFalse(done.is_set())
            self.assertEqual(post(dict(events=[event])).status_code, 200)
            gate.set()
            self.assertTrue(done.wait(2))
            self.assertEqual(len(calls), 1)
            self.assertEqual(replies, ["回答完成"])
            self.assertEqual(post(dict(events="wrong")).status_code, 400)
            malformed = dict(event, message=dict(type="text", text=123))
            self.assertEqual(post(dict(events=[malformed])).status_code, 400)
            self.assertEqual(client.post("/webhook", data=b"x" * (1024 * 1024 + 1)).status_code, 413)
        finally:
            gate.set()
            runtime.close()

    def test_w5_restore_validation_and_put_without_logging_url(self):
        calls = []
        def fake_http(*args, **kwargs):
            calls.append((args, kwargs))
            return b'{}' if kwargs.get("method") == "PUT" else b'{"endpoint":"https://script.google.com/macros/s/test-only/exec"}'
        with patch.object(bot, "read_http", side_effect=fake_http):
            bot.restore_webhook("test-token", "https://script.google.com/macros/s/test-only/exec")
            self.assertEqual(calls[0][1]["method"], "PUT")
            self.assertEqual(calls[0][1]["json"]["endpoint"], "https://script.google.com/macros/s/test-only/exec")
            for url in ("https://evil.example.org/exec", "http://script.google.com/macros/s/x/exec"):
                with self.assertRaises(ValueError):
                    bot.restore_webhook("test-token", url)
        self.assertEqual(len(calls), 2)
        with patch.object(bot, "read_http", return_value=b'{}'):
            with self.assertRaises(RuntimeError):
                bot.restore_webhook("test-token", "https://script.google.com/macros/s/test-only/exec")

    def test_real_http_server_start_health_and_sigint_without_line_calls(self):
        environment = dict(os.environ, LINE_CHANNEL_SECRET="test-secret", LINE_CHANNEL_ACCESS_TOKEN="test-token",
                           ELEARN_CALENDAR_URL="", ELEARN_STATE_FILE=str(self.path / "state.json"),
                           TODO_FILE=str(self.path / "tasks.jsonl"), PUBLIC_BASE_URL="", W5_WEBHOOK_URL="",
                           OLLAMA_MODEL="qwen2.5:3b", OLLAMA_BASE_URL="http://127.0.0.1:11434", PORT="0")
        process = subprocess.Popen([sys.executable, str(Path(bot.__file__).resolve())], env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stderr.readline()
            match = re.search(r"http://127.0.0.1:(\d+)", line)
            self.assertIsNotNone(match, line)
            with urlopen(f"http://127.0.0.1:{match[1]}/health", timeout=3) as response:
                self.assertEqual(response.read(), b"ok")
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertIn("已停止", stderr)
            self.assertNotIn("test-secret", stdout + stderr)
            self.assertNotIn("test-token", stdout + stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
