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
            if kwargs["json"].get("format", {}).get("properties", {}).get("source"):
                return json.dumps(dict(message=dict(content=json.dumps(dict(source="model"))))).encode()
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

    def test_search_followup_resolves_topic_then_keeps_latest_answer_for_continuation(self):
        prompts = []
        def http(url, **kwargs):
            self.assertTrue(url.startswith('http://127.0.0.1'))
            body = kwargs['json']; prompts.append(body)
            if body.get('format'):
                return json.dumps({'message':{'content':json.dumps({'question':'測試人物出生地在哪裡？'},ensure_ascii=False)}}).encode()
            return json.dumps({'message':{'content':'出生地回答 [1]'}},ensure_ascii=False).encode()
        ai=bot.LocalAI(http=http,clock=lambda:NOW)
        ai.remember('owner',[],'現在的總統是誰','現任總統是測試人物。[1]')
        seen=[]
        ai.lookup=lambda q,news=False,*args: seen.append(q) or [dict(title='測試人物介紹',snippet='已查證的出生地',url='https://example.org/person',published=None)]
        ai.ask('他出生在哪裡？','owner')
        self.assertEqual(seen,['測試人物出生地在哪裡？'])
        self.assertEqual(len(prompts[-1]['messages']),2)
        self.assertIn('測試人物出生地',prompts[-1]['messages'][-1]['content'])
        ai.ask('幫我翻成英文','owner')
        self.assertEqual(len(seen),1)
        self.assertIn('出生地回答',str(prompts[-1]['messages'][:-1]))
        self.assertIn('現在的總統',str(ai.conversations['owner']))

    def test_unresolved_followup_does_not_search_an_unrelated_pronoun(self):
        ai=bot.LocalAI(http=lambda *a,**k:b'{"message":{"content":"{}"}}',clock=lambda:NOW)
        ai.remember('owner',[],'問題','回答')
        ai.lookup=lambda *a: self.fail('Must not search an unresolved pronoun')
        self.assertIn('請補上名稱',ai.ask('他幾歲','owner'))

    def test_continuation_keeps_source_evidence_and_does_not_force_chinese_identity(self):
        payloads = []
        def http(url, **kwargs):
            payloads.append(kwargs["json"])
            return json.dumps(dict(message=dict(content="The winner is Test Winner."))).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        evidence = [dict(title="官方資料", snippet="Test Winner; verified research details", url="https://api.nobelprize.org/2.1/nobelPrizes?test=1", published=None,
                         verified_answer="2026 年得主是 Test Winner。[1]")]
        ai.remember("owner", [], "2026 年諾貝爾物理獎得主是誰", "2026 年得主是 Test Winner。[1]", evidence=evidence)
        reply = ai.ask("翻成英文", "owner")
        self.assertEqual(reply[0]["text"], "The winner is Test Winner.")
        self.assertIn("verified research details", payloads[-1]["messages"][-1]["content"])
        self.assertEqual(reply[1]["type"], "flex")
        ai.ask("清除對話", "owner")
        self.assertNotIn("owner", ai.conversations)

    def test_concise_followup_removes_extra_sections(self):
        ai = bot.LocalAI(http=lambda *a, **k: json.dumps(dict(message=dict(content="玉山3952公尺。\n\n補充：其他資料"))).encode(), clock=lambda: NOW)
        ai.remember("owner", [], "玉山多高", "玉山3952公尺。")
        self.assertEqual(ai.ask("簡短一點", "owner"), "玉山3952公尺。")

    def test_private_image_followups_stay_local_and_keep_anchor_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            payloads = []
            def local_http(url, **kwargs):
                payloads.append(kwargs["json"])
                if kwargs["json"].get("format"):
                    return json.dumps(dict(message=dict(content='{"source":"web"}'))).encode()
                self.assertTrue(url.startswith("http://127.0.0.1:11434/"))
                return json.dumps(dict(message=dict(content="圖片上的行程是15:00開始。"))).encode()
            ai = bot.LocalAI(http=local_http, memory_path=path)
            ai.remember("owner", [], "使用者上傳了一張圖片，請依圖片辨識內容接續回答。", "私人的行程2026-10-16 15:00")
            ai.lookup = lambda *a: self.fail("Private OCR must not be sent to search")
            self.assertIn("15:00", ai.ask("那幾點開始？", "owner"))
            photos = bot.Photos("https://quality.example", download=lambda *a, **k: self.fail("Private OCR must not trigger public photos"))
            ai = bot.LocalAI(http=local_http, memory_path=path, photos=photos)
            ai.lookup = lambda *a: self.fail("Private OCR must remain local after reload")
            self.assertIn("15:00", ai.ask("圖片上的日期是什麼？", "owner"))
            self.assertIn("私人的行程2026-10-16 15:00", "\n".join(m["content"] for m in payloads[-1]["messages"]))
            self.assertIn("公開人物", ai.ask("給我他的照片", "owner"))
            lookups = []
            ai.lookup = lambda *a: lookups.append(a) or []
            ai.ask("台灣最高的山是哪一座？多高？", "owner")
            self.assertTrue(lookups)

    def test_shutdown_restore_preserves_another_applications_route(self):
        local = "https://tunnel.example.org"
        backup = "https://script.google.com/macros/s/test/exec"
        with patch.object(bot, "read_http", return_value=b'{"endpoint":"https://other.example.org/webhook"}'), patch.object(bot, "restore_webhook") as restore:
            self.assertFalse(bot.release_local_webhook("test-token", local, backup))
            restore.assert_not_called()
        with patch.object(bot, "read_http", return_value=json.dumps(dict(endpoint=local+"/webhook")).encode()), patch.object(bot, "restore_webhook") as restore:
            self.assertTrue(bot.release_local_webhook("test-token", local, backup))
            restore.assert_called_once_with("test-token", backup)

    def test_nobel_official_lookup_validates_year_category_and_names(self):
        def prize(year="2026", category="Physics", laureates=None):
            return dict(nobelPrizes=[dict(awardYear=year, category=dict(en=category), laureates=laureates if laureates is not None else [dict(knownName=dict(en="Test Winner"))])])
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if "api.nobelprize.org" in url:
                self.assertEqual(kwargs["headers"]["User-Agent"], "Mozilla/5.0")
                return json.dumps(prize()).encode()
            if "nobelprize.org" in url:
                return b'<title>Nobel Prize in Physics 2026 - NobelPrize.org</title><main>Test Winner</main>'
            return json.dumps(dict(message=dict(content="Wrong invented answer"))).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        reply = ai.ask("2026 年諾貝爾物理獎得主是誰？", "owner")
        self.assertEqual(reply[0]["text"], "2026 年諾貝爾物理學獎得主是 Test Winner。[1]")
        self.assertEqual(len(reply[1]["contents"]["contents"]), 2)
        self.assertIn("nobelPrizeYear=2026", calls[0])
        for bad in [prize("2025"), prize(category="Chemistry"), prize(laureates=[]), prize(laureates=[dict(knownName=dict(en=""))])]:
            ai = bot.LocalAI(http=lambda *a, **k: json.dumps(bad).encode(), clock=lambda: NOW)
            self.assertEqual(ai.lookup("2026 年諾貝爾物理獎得主是誰？"), [])
        self.assertEqual(ai.nobel_spec("去年諾貝爾化學獎得主是誰"), (2025, "che", "化學獎"))
        self.assertIsNone(ai.nobel_spec("2026 年諾貝爾物理獎得主幾歲"))
        self.assertEqual(ai.nobel_spec("2100 年諾貝爾物理獎得主是誰？"), (2100, "phy", "物理學獎"))
        self.assertIsNone(ai.nobel_spec("2026 年諾貝爾物理獎得主的研究貢獻是什麼？"))

    def test_nobel_api_still_usable_when_human_page_is_blocked(self):
        def http(url, **kwargs):
            if "api.nobelprize.org" in url:
                return json.dumps(dict(nobelPrizes=[dict(awardYear="2026", category=dict(en="Physics"), laureates=[dict(knownName=dict(en="Test Winner"))])])).encode()
            raise RuntimeError("website unavailable")
        rows = bot.LocalAI(http=http).lookup("2026 年諾貝爾物理獎得主是誰？")
        self.assertEqual(len(rows), 1)
        self.assertIn("Test Winner", rows[0]["snippet"])

    def test_general_search_uses_wikipedia_text_after_both_providers_fail(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if "w/api.php" in url:
                return json.dumps(dict(query=dict(pages={"1":dict(title="玉山", fullurl="https://zh.wikipedia.org/wiki/玉山", extract="玉山是台灣最高山峰，海拔3952公尺。"),
                    "2":dict(title="玉山", fullurl="https://evil.example.org", extract="玉山台灣最高山峰海拔") })),ensure_ascii=False).encode()
            raise RuntimeError("provider unavailable")
        rows = bot.LocalAI(http=http).lookup("台灣最高的山是哪一座？多高？")
        self.assertEqual(len(rows), 1)
        self.assertIn("3952", rows[0]["snippet"])
        self.assertEqual(len(calls), 3)

    def test_public_news_redirects_are_bounded_and_do_not_forward_credentials(self):
        redirect = ResponseStub(302, {"Location": "https://news.google.com/rss/topics/test"})
        done = ResponseStub(200)
        done.iter_content = lambda size: [b"<rss/>"]
        with patch.object(bot.requests, "request", side_effect=[redirect, done]) as request:
            self.assertEqual(bot.read_http("https://news.google.com/rss/start", redirect_hosts=("news.google.com",)), b"<rss/>")
            self.assertEqual(request.call_count, 2)
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
        outside = ResponseStub(302, {"Location": "https://evil.example/rss"})
        with patch.object(bot.requests, "request", return_value=outside) as request:
            with self.assertRaises(ValueError):
                bot.read_http("https://news.google.com/rss/start", redirect_hosts=("news.google.com",))
            self.assertEqual(request.call_count, 1)
        with patch.object(bot.requests, "request") as request:
            with self.assertRaises(ValueError):
                bot.read_http("https://news.google.com/rss/start", headers={"Authorization": "Bearer private"}, redirect_hosts=("news.google.com",))
            request.assert_not_called()
        with patch.object(bot.requests, "request", return_value=redirect) as request:
            with self.assertRaises(RuntimeError):
                bot.read_http("https://news.google.com/rss/start", redirect_hosts=("news.google.com",))
            self.assertEqual(request.call_count, 4)

    def test_missing_context_requests_clarification_without_network_or_model(self):
        ai = bot.LocalAI(http=lambda *a, **k: self.fail("No lookup for missing context"), photos=bot.Photos("https://quality.example"))
        for question in ["今天天氣如何？", "明天天氣會怎樣？", "今天會下雨嗎？"]:
            self.assertIn("地點", ai.ask(question, question))
        for question in ["他幾歲？", "這位今年幾歲？"]:
            self.assertIn("人物", ai.ask(question, question))
        for question in ["圖片上的日期是什麼？", "這張圖片寫了什麼？"]:
            self.assertIn("圖片", ai.ask(question, question))
            self.assertIn("傳送", ai.ask(question, question))
        seen = []
        ai.lookup = lambda *a: seen.append(a) or []
        ai.ask("台北明天天氣", "named-city")
        self.assertTrue(seen)

    def test_general_news_uses_dated_topic_feed_and_excludes_yesterday(self):
        from datetime import datetime, timezone
        from email.utils import format_datetime
        now = NOW
        today = format_datetime(datetime.fromtimestamp(now - 60, timezone.utc))
        yesterday = format_datetime(datetime.fromtimestamp(now - 12 * 3600, timezone.utc))
        rss = f'<rss><channel><item><title>Unrelated literal words but topical story</title><link>https://example.org/today</link><pubDate>{today}</pubDate></item><item><title>Yesterday story</title><link>https://example.org/yesterday</link><pubDate>{yesterday}</pubDate></item></channel></rss>'.encode()
        calls = []
        def http(url, **kw):
            calls.append(url)
            return rss
        ai = bot.LocalAI(http=http, clock=lambda: now)
        rows = ai.lookup("今天有哪些台灣新聞？請附來源。", news=True)
        self.assertEqual([r["url"] for r in rows], ["https://example.org/today"])
        self.assertIn("/topic/NATION", calls[0])
        self.assertEqual(bot.broad_news_topic("今天台灣新聞，附上來源"), "NATION")
        self.assertIsNone(bot.broad_news_topic("台積電今天有什麼新聞？"))
        self.assertEqual(bot.search_query("加拿大首都？請附來源。"), "加拿大首都")

    def test_world_news_checks_publisher_section_date_and_preserves_financial_world_news(self):
        from datetime import datetime, timezone
        from email.utils import format_datetime
        from xml.sax.saxutils import escape
        def rss(items):
            return ("<rss><channel>" + "".join(f"<item><title>{escape(title)}</title><link>{escape(url)}</link><description>原始發稿前言</description><pubDate>{format_datetime(datetime.fromtimestamp(at,timezone.utc))}</pubDate></item>" for title,url,at in items) + "</channel></rss>").encode()
        cna = rss([
            ("國際利率政策影響全球ETF", "https://www.cna.com.tw/news/aopl/202610100001.aspx?utm_source=test", NOW-60),
            ("台股ETF心得", "https://www.cna.com.tw/news/afe/202610100002.aspx", NOW-30),
            ("假冒來源", "https://evil.example/news/aopl/202610100003.aspx", NOW-20),
            ("昨日舊聞", "https://www.cna.com.tw/news/aopl/202610090004.aspx", NOW-12*3600),
            ("未來稿件", "https://www.cna.com.tw/news/aopl/202610100005.aspx", NOW+60),
            ("路徑跳轉", "https://www.cna.com.tw/news/aopl/%2e%2e/afe/202610100006.aspx", NOW-10),
            ("無效連接埠", "https://www.cna.com.tw:bad/news/aopl/202610100007.aspx", NOW-10),
            ("另一則國際消息", "https://www.cna.com.tw/news/aopl/202610100008.aspx", NOW-120),
        ])
        ltn = rss([
            ("歐洲外交會議", "https://news.ltn.com.tw/news/world/breakingnews/100", NOW-180),
            ("國內證券", "https://news.ltn.com.tw/news/business/breakingnews/101", NOW-10),
        ])
        calls=[]
        def http(url,**kw):
            calls.append(url)
            return cna if "feedburner" in url else ltn
        ai=bot.LocalAI(http=http,clock=lambda:NOW)
        rows=ai.lookup("今天有哪些國際新聞？請附來源。",news=True)
        self.assertEqual(len(rows),3)
        self.assertEqual({r["publisher"] for r in rows},{"中央通訊社","自由時報"})
        self.assertTrue(all(r["section"]=="國際" and r["published"]<=NOW for r in rows))
        self.assertTrue(any("全球ETF" in r["title"] for r in rows))
        self.assertFalse(any("台股ETF" in r["title"] or "昨日" in r["title"] for r in rows))
        self.assertTrue(all("?" not in r["url"] for r in rows))
        self.assertEqual(len(calls),2)
        # One blocked publisher still leaves usable, correctly classified news.
        def blocked(url,**kw):
            if "feedburner" in url:raise RuntimeError("blocked")
            return ltn
        rows=bot.LocalAI(http=blocked,clock=lambda:NOW).lookup_world_news("今天國際新聞")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["publisher"],"自由時報")

    def test_news_invalid_citations_do_not_publish_the_model_claim(self):
        rows=[dict(title="中央通訊社｜某國公布選舉結果",url="https://www.cna.com.tw/news/aopl/202610100001.aspx",snippet="某國公布選舉結果",published=NOW)]
        ai=bot.LocalAI(clock=lambda:NOW,http=lambda *a,**k: json.dumps(dict(message=dict(content="不在來源內的虛構消息 [9]"))).encode())
        ai.lookup=lambda *a:rows
        reply=ai.ask("今天國際新聞")
        self.assertNotIn("虛構消息",reply[0]["text"])
        self.assertIn("未能正確標示引用",reply[0]["text"])
        self.assertIn("某國公布選舉結果 [1]",reply[0]["text"])
        self.assertTrue(bot.valid_source_citations("第一則[1]，合併[1、2]",2))
        self.assertFalse(bot.valid_source_citations("來源[0]",2))
        self.assertFalse(bot.valid_source_citations("沒有引用",2))

    def test_news_guard_rejects_changed_numbers_names_dates_negation_and_uncertainty(self):
        original = "甲國外交部據報尚未批准乙國2026年投資15億元計畫"
        rows = [dict(title="中央通訊社｜" + original, publisher="中央通訊社", url="https://example.org/a", snippet="官方表示仍在審查。", published=NOW)]
        for claim in [original.replace("15億元", "16億元"), original.replace("甲國", "丙國"),
                      original.replace("2026", "2027"), original.replace("尚未", "已"),
                      original.replace("據報", ""), original + "，將促進經濟成長"]:
            with self.subTest(claim=claim):
                result, status = bot.grounded_news_answer(claim + " [1]", rows)
                self.assertEqual(status, "headline_fallback")
                self.assertIn(original, result)
                self.assertIn("尚未獨立核實", result)
        result, status = bot.grounded_news_answer(original + " [1]", rows)
        self.assertEqual(status, "source_extract")
        self.assertEqual(result, original + " [1]")
        self.assertEqual(bot.grounded_news_answer("官方表示仍在審查。 [1]", rows)[1], "source_extract")
        self.assertEqual(bot.grounded_news_answer("官方表示仍在審查。 [2]", rows)[1], "headline_fallback")
        self.assertEqual(bot.grounded_news_answer(original + " [1]\n虛構補充", rows)[1], "headline_fallback")
        rows[0]["title"] = "某國公布利率1.5%調整方案"
        self.assertEqual(bot.grounded_news_answer("某國公布利率15%調整方案 [1]", rows)[1], "headline_fallback")

    def test_news_guard_checks_citation_mapping_and_followup(self):
        rows = [dict(title="甲國據報尚未批准2026年投資計畫", url="https://example.org/1", snippet="仍在審查。", published=NOW, section="國際"),
                dict(title="乙國公布2027年外交預算", url="https://example.org/2", snippet="預算仍需審議。", published=NOW, section="國際")]
        self.assertEqual(bot.grounded_news_answer(rows[0]["title"]+" [2]",rows)[1],"headline_fallback")
        ai=bot.LocalAI(clock=lambda:NOW,http=lambda *a,**k:json.dumps(dict(message=dict(content="甲國已批准2026年投資計畫 [1]"))).encode())
        ai.remember("news-followup", [], "今天國際新聞", "原始導讀", evidence=rows)
        reply=ai.ask("簡短一點","news-followup")
        self.assertIn("尚未批准",reply[0]["text"])
        self.assertNotIn("甲國已批准",reply[0]["text"])
        self.assertIn("[2]",reply[0]["text"])

    def test_domestic_news_followup_keeps_source_guard(self):
        row = dict(title="甲市據報尚未批准2026年道路計畫", url="https://example.org/local", snippet="計畫仍在審查。", published=NOW)
        ai = bot.LocalAI(clock=lambda:NOW, http=lambda *a,**k:json.dumps(dict(message=dict(content="甲市已批准2026年道路計畫 [1]"))).encode())
        calls=[]
        ai.lookup=lambda *args:calls.append(args) or [row]
        ai.ask("今天有哪些台灣新聞", "domestic")
        reply=ai.ask("簡短一點", "domestic")
        self.assertIn("尚未批准",reply[0]["text"])
        self.assertNotIn("甲市已批准",reply[0]["text"])
        self.assertEqual(len(calls),1)
        self.assertEqual(ai.conversations["domestic"]["evidence"][0]["evidence_type"],"news")
        self.assertNotIn("evidence_type",row)

    def test_merged_news_sources_survive_memory_reload_and_followup(self):
        title="甲國據報尚未批准乙國投資方案"
        rows=[dict(title=name+"｜"+title,publisher=name,url="https://example.org/"+name,snippet="仍在審查。",published=NOW,evidence_type="news") for name in ["a","b"]]
        groups=bot.cluster_news(rows)
        ai=bot.LocalAI(clock=lambda:NOW,memory_path=self.path/"memory.json")
        ai.remember("owner",[],"今天國際新聞",title+" [1]",evidence=groups)
        def http(*a,**k):
            return json.dumps(dict(message=dict(content=title+" [1]"))).encode()
        restored=bot.LocalAI(clock=lambda:NOW,memory_path=self.path/"memory.json",http=http)
        reply=restored.ask("詳細一點","owner")
        buttons=reply[1]["contents"]["contents"][0]["footer"]["contents"]
        self.assertEqual([x["action"]["uri"] for x in buttons],[rows[0]["url"],rows[1]["url"]])
        self.assertEqual(restored.conversations["owner"]["evidence"][0]["related_sources"][0]["snippet"],"仍在審查。")
        self.assertNotIn("owner",restored.ask("清除對話","owner"))
        self.assertNotIn("owner",restored.conversations)

    def test_news_guard_preserves_display_order_and_does_not_silently_drop_events(self):
        rows=[dict(title="甲國公布外交投資計畫",snippet="",url="https://example.org/1"),dict(title="乙國舉行地方選舉",snippet="",url="https://example.org/2")]
        complete="甲國公布外交投資計畫 [1]\n乙國舉行地方選舉 [2]"
        self.assertEqual(bot.grounded_news_answer(complete,rows)[1],"source_extract")
        for answer in ["乙國舉行地方選舉 [2]\n甲國公布外交投資計畫 [1]","甲國公布外交投資計畫 [1]",complete+"\n甲國公布外交投資計畫 [1]"]:
            self.assertEqual(bot.grounded_news_answer(answer,rows)[1],"headline_fallback")

    def test_news_event_clustering_is_conservative_preserves_originals_and_links(self):
        title = "甲國外交部據報尚未批准乙國投資計畫"
        def row(name, headline=title, at=NOW, snippet="仍在審查。"):
            return dict(title=name+"｜"+headline, publisher=name, url="https://example.org/"+name, published=at, snippet=snippet)
        a, b = row("媒體甲"), row("媒體乙", "甲國外交部 據報尚未批准乙國投資計畫")
        original = json.loads(json.dumps([a,b]))
        groups = bot.cluster_news([a,b])
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]["related_sources"][0]["url"], b["url"])
        self.assertEqual([a,b],original)
        reply = bot.source_reply(title+" [1]",groups)
        buttons = reply[1]["contents"]["contents"][0]["footer"]["contents"]
        self.assertEqual([x["action"]["uri"] for x in buttons],[a["url"],b["url"]])
        for other in [row("丙",title.replace("甲國","丙國")), row("丙",title.replace("尚未","已")),
                      row("丙",title.replace("據報","")),row("丙",at=NOW-37*3600),
                      row("丙",snippet="仍在審查15億元。"), row("丙",title+"第二案")]:
            with self.subTest(other=other):
                self.assertEqual(len(bot.cluster_news([a,other])),2)
        self.assertEqual(len(bot.cluster_news([a,a])),1)

    def test_wikipedia_query_removes_question_words_without_inserting_answers(self):
        from urllib.parse import parse_qs, urlsplit
        seen = []
        def http(url, **kwargs):
            seen.append(parse_qs(urlsplit(url).query)["gsrsearch"][0])
            return b'{"query":{"pages":{}}}'
        ai = bot.LocalAI(http=http)
        ai.lookup_wikipedia("某條運河連接哪兩個海？")
        ai.lookup_wikipedia("某個衛星叫什麼？")
        ai.lookup_wikipedia("某個海溝位於哪個海洋？")
        self.assertTrue(all(not any(word in q for word in ["哪兩個", "叫什麼", "位於", "哪個"]) for q in seen))
        self.assertIn("運河連接", seen[0])
        self.assertIn("衛星", seen[1])
        self.assertIn("海溝", seen[2])

    def test_teacher_questions_greeting_offline_year_and_search_topic(self):
        ai = bot.LocalAI(http=lambda *a, **k: self.fail("No model or search call expected"), clock=lambda: NOW)
        self.assertIn("小幫手", ai.ask("hi"))
        ai.search_enabled = False
        self.assertIn("--search", ai.ask("2026 年諾貝爾物理獎得主是誰？"))
        rows = [dict(title="2026 年台灣行事曆", snippet="2026 連假", url="https://example.org/holidays")]
        self.assertEqual(bot.relevant_sources(rows, "2026 年諾貝爾物理獎得主"), [])
        rows = [dict(title="台灣銀行", snippet="台灣最高品質金融服務", url="https://example.org/bank")]
        self.assertEqual(bot.relevant_sources(rows, "台灣最高的山是哪一座 多高"), [])

    def test_named_new_topic_is_not_a_continuation(self):
        calls, searches = [], []
        def http(url, **kwargs):
            calls.append(kwargs["json"])
            if kwargs["json"].get("format"):
                return json.dumps(dict(message=dict(content='{"source":"web"}'))).encode()
            return json.dumps(dict(message=dict(content="新主題回答 [1]"))).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        ai.remember("owner", [], "解釋牛頓定律", "F=ma")
        ai.lookup = lambda q, *args: searches.append(q) or [dict(title="周星馳", snippet="人物介紹", url="https://example.org/person", published=None)]
        ai.ask("詳細介紹周星馳", "owner")
        self.assertEqual(searches, ["詳細介紹周星馳"])
        self.assertNotIn("F=ma", str(calls[-1]["messages"]))
        self.assertNotIn("只針對緊接上一則", calls[-1]["messages"][-1]["content"])
        self.assertEqual(ai.conversations["owner"]["topic"][0]["content"], "詳細介紹周星馳")
        for text in ["翻成英文", "幫我翻成英文", "再詳細一點", "那詳細說明一下", "Translate your last answer to English"]:
            self.assertTrue(bot.continuation_request(text), text)
        for text in ["詳細介紹周星馳", "給我台灣新聞", "翻譯這篇新文章", "Explain more about Newton"]:
            self.assertFalse(bot.continuation_request(text), text)

    def test_english_president_identity_does_not_replace_age_or_policy(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if "president.gov.tw" in url:
                return '<title>測試人物總統-總統與副總統｜中華民國總統府</title>'.encode()
            return b'<rss><channel/></rss>'
        ai = bot.LocalAI(http=http)
        self.assertEqual(ai.lookup("Who is the current president of Taiwan?")[0]["url"], "https://www.president.gov.tw/Page/694")
        for text in ["How old is the president of Taiwan?", "What are the policies of the president of Taiwan?", "Who was the president of Taiwan in 2020?"]:
            calls.clear()
            ai.lookup(text)
            self.assertFalse(any("president.gov.tw/Page/694" in url for url in calls), text)

    def test_photo_pronoun_uses_topic_after_translation(self):
        from unittest.mock import Mock
        photos = Mock()
        photos.handle.return_value = [dict(type="text", text="照片來源")]
        def http(url, **kwargs):
            history = json.loads(kwargs["json"]["messages"][-1]["content"])["history"]
            self.assertIn("瀨戶環奈", str(history))
            return json.dumps(dict(message=dict(content=json.dumps(dict(question="瀨戶環奈的照片"), ensure_ascii=False)))).encode()
        ai = bot.LocalAI(http=http, photos=photos, clock=lambda: NOW)
        ai.remember("owner", [], "瀨戶環奈介紹", "瀨戶環奈人物介紹")
        ai.remember("owner", [], "翻成英文", "English description")
        ai.ask("給我她的照片", "owner")
        photos.handle.assert_called_once_with("瀨戶環奈的照片")
        self.assertEqual(ai.conversations["owner"]["topic"][0]["content"], "瀨戶環奈")
        photos.handle.reset_mock()
        self.assertIn("補上名稱", ai.ask("給我他的照片", "other"))
        photos.handle.assert_not_called()

    def test_failed_new_topic_updates_context_before_translation(self):
        bodies = []
        def http(url, **kwargs):
            bodies.append(kwargs["json"])
            if kwargs["json"].get("format"):
                return json.dumps(dict(message=dict(content='{"source":"web"}'))).encode()
            return json.dumps(dict(message=dict(content="Translated latest refusal"))).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        ai.remember("owner", [], "牛頓定律", "F=ma")
        ai.lookup = lambda *args: []
        ai.ask("詳細介紹周星馳", "owner")
        ai.ask("翻成英文", "owner")
        self.assertNotIn("F=ma", str(bodies[-1]["messages"]))
        self.assertIn("沒有找到", str(bodies[-1]["messages"]))
        self.assertIn("周星馳", str(ai.conversations["owner"]["topic"]))

    def test_photo_command_prefix_and_unrelated_provider_results(self):
        self.assertEqual(bot.photo_subject("提供周星馳的照片"), "周星馳")
        def download(url, **kwargs):
            if "w/api.php" in url:
                return dict(body=b'{}', url=url)
            if "duckduckgo" in url:
                return dict(body=b'<html></html>', url=url)
            return dict(body='<rss><channel><item><title>提供股票行情</title><link>https://example.org/stock</link><description>提供免費查詢</description></item></channel></rss>'.encode(), url=url)
        photos = bot.Photos("https://example.org", download=download)
        self.assertEqual(list(photos.source_pages("周星馳", time.monotonic()+5)), [])

    def test_source_cards_deduplicate_same_url_fragment_and_slash(self):
        rows = [dict(title="台灣總統", snippet="官方", url=url) for url in
                ["https://example.org/person", "https://example.org/person/#bio", "https://example.org/person#title", "https://other.example/person"]]
        results = bot.relevant_sources(rows, "台灣總統")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], rows[0]["url"])
        wiki = [dict(title="周星馳", snippet="周星馳", url=url) for url in ["https://zh.wikipedia.org/zh-tw/%E5%91%A8%E6%98%9F%E9%A6%B3", "https://zh.wikipedia.org/wiki/周星馳", "https://zh.wikipedia.org/zh/周星馳"]]
        self.assertEqual(len(bot.relevant_sources(wiki, "周星馳")), 1)

    def test_startup_activation_failure_stops_and_preserves_unknown_webhook(self):
        from contextlib import ExitStack
        from unittest.mock import Mock
        server = Mock(server_port=3000)
        runtime = Mock()
        thread = Mock(ident=None)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, dict(LINE_CHANNEL_SECRET="test-secret", LINE_CHANNEL_ACCESS_TOKEN="test-token",
                PUBLIC_BASE_URL="https://tunnel.example", W5_WEBHOOK_URL="https://backup.example"), clear=True))
            stack.enter_context(patch.object(bot, "load_dotenv"))
            stack.enter_context(patch.object(bot.logging, "basicConfig"))
            stack.enter_context(patch.object(bot, "Elearn", return_value=Mock(url=None, bind_code=None, state={})))
            for name in ["LocalAI", "Photos", "GoogleWorkspace", "TeacherFeatures", "TodoStore"]:
                stack.enter_context(patch.object(bot, name))
            stack.enter_context(patch.object(bot, "check_model", return_value=True))
            stack.enter_context(patch.object(bot, "make_server", return_value=server))
            stack.enter_context(patch.object(bot, "BotRuntime", return_value=runtime))
            stack.enter_context(patch.object(bot, "create_app"))
            stack.enter_context(patch.object(bot.threading, "Thread", return_value=thread))
            stack.enter_context(patch.object(bot.signal, "signal"))
            activate = stack.enter_context(patch.object(bot, "activate_local_webhook", side_effect=RuntimeError("unknown webhook")))
            restore = stack.enter_context(patch.object(bot, "restore_webhook"))
            with self.assertRaisesRegex(RuntimeError, "Webhook activation failed"):
                bot.main()
            activate.assert_called_once()
            restore.assert_not_called()
            server.handle_request.assert_not_called()
            server.server_close.assert_called_once()
            runtime.close.assert_called_once()
            thread.start.assert_not_called()

    def test_unrelated_english_sources_and_restart_memory(self):
        rows = [dict(title="PChome 股票行情", snippet="今天的股市", url="https://example.org/stock")]
        self.assertEqual(bot.relevant_sources(rows, "who is the current president of Taiwan"), [])
        path = self.path / "memory.json"
        first = bot.LocalAI(clock=lambda: NOW, memory_path=path)
        first.remember("a", [], "總統", "賴清德")
        first.remember("a", [], "翻成英文", "Lai Ching-te")
        second = bot.LocalAI(clock=lambda: NOW + 60, memory_path=path)
        self.assertEqual(second.conversations["a"]["topic"][1]["content"], "賴清德")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        second.ask("清除對話", "a")
        self.assertNotIn("a", bot.LocalAI(clock=lambda: NOW + 60, memory_path=path).conversations)
        self.assertEqual(bot.LocalAI(clock=lambda: NOW + 1300, memory_path=path).conversations, {})

    def test_clear_is_private_and_simulation_disables_external_search(self):
        calls = []
        ai = bot.LocalAI(http=lambda url, **kwargs: calls.append(url))
        ai.remember("a", [], "秘密", "答案")
        ai.remember("b", [], "其他", "答案")
        self.assertIn("已清除", ai.ask("清除對話", "a"))
        self.assertNotIn("a", ai.conversations)
        self.assertIn("b", ai.conversations)
        ai.search_enabled = False
        self.assertIn("--search", ai.ask("今天的新聞", "a"))
        self.assertEqual(calls, [])

    def test_search_failures_and_model_failure_do_not_fake_news(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if url.startswith("https:"):
                raise RuntimeError("unavailable")
            self.assertIn("不可猜測", kwargs["json"]["messages"][0]["content"])
            return json.dumps(dict(message=dict(content="基本背景"))).encode()
        reply = bot.LocalAI(http=http).ask("今天有什麼新聞")
        self.assertIn("沒有找到足以確認", reply)
        self.assertEqual(calls, ["https://feeds.feedburner.com/rsscna/intworld", "https://news.ltn.com.tw/rss/world.xml"])
        def no_model(url, **kwargs):
            if url.startswith("https:"):
                return RSS.replace(b"https://example.org/new", b"https://www.cna.com.tw/news/aopl/202610090001.aspx")
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
                body = '<a class="result-link" href="https://school.example.org/teacher">東華大學</a>'.encode()
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

    def test_photo_wiki_title_match_avoids_similarly_named_person(self):
        buffer=io.BytesIO();Image.new('RGB',(200,300),'blue').save(buffer,'PNG')
        seen=[]
        def download(url,**kwargs):
            seen.append(url)
            if 'w/api.php' in url:
                body=json.dumps({'query':{'pages':{'1':{'title':'橋本環奈','index':1,'thumbnail':{'source':'https://images.example.org/wrong.png'},'fullurl':'https://example.org/wrong'},'2':{'title':'瀨戶環奈','index':2,'thumbnail':{'source':'https://images.example.org/right.png'},'fullurl':'https://example.org/right'}}}},ensure_ascii=False).encode()
            elif url.endswith('/right.png'):body=buffer.getvalue()
            else:self.fail('Wrong person or unnecessary fallback requested')
            return dict(body=body,url=url)
        photos=bot.Photos('https://bot.example.org',self.path,download)
        reply=photos.handle('搜尋瀨戶環奈的照片')
        self.assertEqual(reply[1]['type'],'image');self.assertIn('example.org/right',reply[0]['text'])
        self.assertEqual(len(seen),2)

    def test_photo_search_falls_back_when_primary_source_is_blocked(self):
        def download(url,**kwargs):
            if 'bing.com' in url:return dict(body=RSS,url=url)
            raise RuntimeError('source blocked')
        photos=bot.Photos('https://bot.example.org',self.path,download)
        self.assertEqual(len(list(photos.source_pages('科學新聞',time.monotonic()+10))),1)

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
            for url in ("https://evil.example.org/exec", "http://script.google.com/macros/s/x/exec",
                        "https://script.google.com/macros/s/x/exec?key=weak",
                        "https://script.google.com/macros/s/x/exec?key=" + 'a'*64 + '&other=1'):
                with self.assertRaises(ValueError):
                    bot.restore_webhook("test-token", url)
        self.assertEqual(len(calls), 2)
        keyed = "https://script.google.com/macros/s/test-only/exec?key=" + 'a'*64
        with patch.object(bot, "read_http", side_effect=[b'{}', json.dumps({'endpoint': keyed}).encode()]) as call:
            bot.restore_webhook('test-token', keyed)
            self.assertEqual(call.call_args_list[0].kwargs['json']['endpoint'], keyed)
        with patch.object(bot, "read_http", return_value=b'{}'):
            with self.assertRaises(RuntimeError):
                bot.restore_webhook("test-token", "https://script.google.com/macros/s/test-only/exec")

    def test_start_switches_only_known_backup_and_is_idempotent(self):
        backup = 'https://script.google.com/macros/s/test-only/exec'
        local = 'https://tunnel.example.org/webhook'
        with patch.object(bot, 'read_http', side_effect=[json.dumps({'endpoint':backup}).encode(),b'{}',json.dumps({'endpoint':local}).encode()]) as call:
            bot.activate_local_webhook('test-token','https://tunnel.example.org',backup)
            self.assertEqual(call.call_args_list[1].kwargs['json']['endpoint'],local)
        with patch.object(bot, 'read_http', return_value=json.dumps({'endpoint':local}).encode()) as call:
            bot.activate_local_webhook('test-token','https://tunnel.example.org',backup)
            self.assertEqual(call.call_count,1)
        with patch.object(bot, 'read_http', return_value=b'{"endpoint":"https://other.example.org"}') as call:
            with self.assertRaises(RuntimeError):
                bot.activate_local_webhook('test-token','https://tunnel.example.org',backup)
            self.assertEqual(call.call_count,1)

    def test_activation_readback_failure_rolls_back_known_previous_endpoint(self):
        backup = "https://script.google.com/macros/s/test-only/exec"
        with patch.object(bot, "read_http", return_value=json.dumps(dict(endpoint=backup)).encode()), \
             patch.object(bot, "set_line_webhook", side_effect=[RuntimeError("readback timeout"), None]) as setter:
            with self.assertRaisesRegex(RuntimeError, "Could not activate"):
                bot.activate_local_webhook("test-token", "https://tunnel.example.org", backup)
            self.assertEqual([call.args[1] for call in setter.call_args_list], ["https://tunnel.example.org/webhook", backup])

    def test_real_http_server_start_health_and_sigint_without_line_calls(self):
        environment = dict(os.environ, LINE_CHANNEL_SECRET="test-secret", LINE_CHANNEL_ACCESS_TOKEN="test-token",
                           ELEARN_CALENDAR_URL="", ELEARN_STATE_FILE=str(self.path / "state.json"),
                           TODO_FILE=str(self.path / "tasks.jsonl"), PUBLIC_BASE_URL="", W5_WEBHOOK_URL="", APPS_SCRIPT_RELAY_MODE="0",
                           OLLAMA_MODEL="qwen2.5:3b", OLLAMA_BASE_URL="http://127.0.0.1:11434", PORT="0")
        process = subprocess.Popen([sys.executable, str(Path(bot.__file__).resolve())], env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stderr.readline()
            while line and "listening on" not in line:
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
