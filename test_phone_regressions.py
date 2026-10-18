"""Cases derived from real phone failures; isolated fake HTTP, no LINE/cloud writes."""
import json
import unittest
from datetime import datetime
from unittest.mock import Mock

import line_bot_local as bot
from test_line_bot_local import NOW


class PhoneRegressionTests(unittest.TestCase):
    def test_public_photo_provenance_is_not_model_knowledge(self):
        ai = bot.LocalAI(photos=Mock())
        ai.photos.handle.return_value = [dict(type='text', text='圖片來源'), dict(type='image', originalContentUrl='https://example.com/test.jpg', previewImageUrl='https://example.com/test.jpg')]
        result = ai.ask('給我玉山的照片', 'public-photo')
        self.assertEqual(result[1]['type'], 'image')
        self.assertEqual(bot.WORK_CONTEXT.route, '網路圖片來源')

    def test_private_recency_and_classifier_failure_never_publish(self):
        ai = bot.LocalAI()
        ai.lookup = Mock(side_effect=AssertionError('Private query escaped to web'))
        ai.classify_source = Mock(side_effect=TimeoutError('unavailable'))
        for q in ['我今天跟客戶有哪些會議？', '我今天存的紀錄有哪些？', '我的銀行帳號目前記在哪裡', '幫我找昨天存的那筆', '查一下今天存在表裡的客戶電話']:
            answer = ai.ask(q, q)
            self.assertIn('私人', answer)
        ai.lookup.assert_not_called()
        ai.classify_source = Mock(side_effect=TimeoutError('unavailable'))
        self.assertIn('無法確定', ai.ask('某個不明主題', 'uncertain'))
        ai.lookup.assert_not_called()

    def test_price_formula_keeps_web_and_continuation_keeps_provenance(self):
        ai = bot.LocalAI(http=lambda *a, **k: json.dumps({'message': {'content': '費率來源 [1]'}}).encode())
        ai.lookup = Mock(return_value=[dict(title='費率', url='https://example.com/pricing', snippet='價格說明', published=None)])
        ai.ask('解釋 ChatGPT 價格的計算公式', 'price')
        ai.lookup.assert_called_once()
        self.assertEqual(bot.WORK_CONTEXT.route, '網路查證')
        ai.ask('再簡短一點', 'price')
        ai.lookup.assert_called_once()
        self.assertEqual(bot.WORK_CONTEXT.route, '沿用先前網路來源')

    def test_semantic_source_selection_overrides_keywords_without_private_search(self):
        def http(url, **kwargs):
            self.assertTrue(url.endswith('/api/chat'))
            return json.dumps({'message': {'content': '回答'}}).encode()
        ai = bot.LocalAI(http=http, clock=lambda: NOW)
        ai.classify_source = Mock(return_value='model')
        ai.lookup = Mock(side_effect=AssertionError('Concept should not search'))
        self.assertEqual(ai.ask('什麼是牛頓第二定律', 'concept'), '回答')
        ai.lookup.assert_not_called()
        ai.classify_source = Mock(return_value='web')
        ai.lookup = Mock(return_value=[dict(title='官方招生說明', url='https://example.edu/admissions', snippet='招生規定', published=None)])
        self.assertIsInstance(ai.ask('解釋某研究所的招生規定', 'fact'), list)
        ai.lookup.assert_called_once()
        ai.classify_source = Mock(return_value='private')
        ai.lookup.reset_mock()
        self.assertIn('私人紀錄', ai.ask('幫我找昨天存的那筆', 'private'))
        ai.lookup.assert_not_called()
        self.assertIn('不能用網路代替', ai.ask('我的試算表有哪些資料', 'sheet'))
        self.assertIn('不會把', ai.ask('我上次記了什麼', 'unclear'))
        ai.lookup.assert_not_called()
        ai.classify_source = Mock(return_value='model')
        ai.lookup = Mock(side_effect=AssertionError('Weather mechanism is a concept, not a forecast'))
        self.assertEqual(ai.ask('解釋天氣預報的原理', 'weather-concept'), '回答')
        ai.lookup.assert_not_called()

    def test_private_store_intent_does_not_confuse_tool_tutorial_with_user_records(self):
        for question, expected in [('我的待辦有哪些', 'todo'), ('查試算表', 'sheet'), ('我的試算表記了什麼', 'sheet'), ('我明天有什麼行程', 'calendar'), ('show my calendar', 'calendar')]:
            self.assertEqual(bot.private_store_intent(question), expected)
        for question in ['Google試算表是什麼', '教我用Google日曆', '建立行程：明天15:00開會']:
            self.assertIsNone(bot.private_store_intent(question))
        self.assertIsNone(bot.private_store_intent('我的e學苑待辦有哪些'))

    def test_nobel_paper_question_forces_current_year_official_web_lookup(self):
        calls = []
        def http(url, **kwargs):
            calls.append(url)
            if url.endswith('/api/chat'):
                return json.dumps({'message': {'content': '研究主題見官方說明；原始論文題名尚未核對。[1]'}}).encode()
            self.assertTrue(url.startswith('https://www.nobelprize.org/prizes/physics/2026/'))
            return b'<title>Nobel Prize in Physics 2026 - Scientific background</title><main>Verified current research description <a href="/uploads/2026/10/research.pdf">Scientific background PDF</a></main>'
        for question in ['這次諾貝爾物理學獎的論文是什麼', '解釋今年諾貝爾物理獎的研究主題', 'What papers underlie the 2026 Nobel physics prize?']:
            ai = bot.LocalAI(http=http, clock=lambda: NOW)
            result = ai.ask(question, question)
            self.assertTrue(result[0]['text'].startswith('已上網查證'))
            self.assertEqual(ai.nobel_spec(question, research=True), (2026, 'phy', '物理學獎'))
        self.assertTrue(any('/advanced-information/' in url for url in calls))
        self.assertFalse(any('bing' in url or 'duckduckgo' in url for url in calls))
        stale = bot.LocalAI(http=lambda *a, **k: b'<title>Nobel Prize in Physics 2025</title><main>Ig Nobel wrong year</main>', clock=lambda: NOW)
        self.assertIn('已嘗試上網查證', stale.ask('這次諾貝爾物理學獎的論文是什麼', 'stale'))

    def test_english_private_image_followup_never_searches(self):
        requests = []
        def http(url, **kwargs):
            requests.append((url, kwargs))
            self.assertTrue(url.endswith('/api/chat'))
            return json.dumps({'message': {'content': '15:00–16:00'}}).encode()
        for question in ['What time is on the image?', 'What date is in this photo?', 'What does my uploaded picture say?']:
            ai = bot.LocalAI(http=http, clock=lambda: NOW)
            ai.remember('private', [], '使用者上傳了一張圖片，請依圖片辨識內容接續回答。', 'PRIVATE_MARKER 活動時間15:00–16:00。')
            ai.lookup = Mock(side_effect=AssertionError('Private image must remain local'))
            self.assertIn('15:00', ai.ask(question, 'private'))
            ai.lookup.assert_not_called()
            self.assertIn('PRIVATE_MARKER', str(requests[-1][1]['json']['messages']))
        empty = bot.LocalAI(http=http, clock=lambda: NOW)
        self.assertIn('請先傳送', empty.ask('What time is on the image?', 'empty'))

    def test_english_news_routes_and_date_filter_without_catching_specific_topics(self):
        for question in ["Recent international news, cite sources.", "What are today's international news headlines? Please cite sources.", "Latest world news, provide sources."]:
            self.assertEqual(bot.broad_news_topic(question), "WORLD")
            self.assertTrue(bot.question_mode(question)[2])
        self.assertEqual(bot.broad_news_topic("Latest Taiwan news, cite sources."), "NATION")
        self.assertIsNone(bot.broad_news_topic("Recent international news about an election"))
        midnight=datetime.fromtimestamp(NOW,bot.TAIPEI).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        self.assertEqual(bot.news_cutoff("Today's international news",NOW),midnight)
        self.assertEqual(bot.news_cutoff("Recent international news",NOW),NOW-7*bot.DAY)

    def test_mountain_height_excludes_generic_portals_and_wrong_rank(self):
        rows=[dict(title="Taiwan portal",snippet="Taiwan tourism",url="https://example.org/portal",published=None),
              dict(title="雪山",snippet="雪山是台灣第二高山，雪山山脈最高峰，海拔3886公尺。高度僅次於台灣最高峰玉山（3952公尺）。",url="https://example.org/second",published=None),
              dict(title="測試峰",snippet="測試峰為台灣最高的山，海拔1,234公尺。",url="https://example.org/highest",published=None)]
        result=bot.relevant_sources(rows,"台灣 最高 山 海拔 高度")
        self.assertEqual([row["url"] for row in result],["https://example.org/highest"])
        without_height=[dict(rows[-1],snippet="測試峰為台灣最高的山。")]
        self.assertEqual(bot.relevant_sources(without_height,"台灣最高山高度"),[])

    def test_english_mountain_query_translates_intent_not_the_answer(self):
        urls=[]
        def http(url,**kwargs):
            urls.append(url)
            if "wikipedia.org/w/api.php" in url:
                return json.dumps(dict(query=dict(pages={"1":dict(title="測試峰",extract="測試峰為台灣最高的山，海拔1,234公尺。",fullurl="https://zh.wikipedia.org/wiki/Test_peak")})),ensure_ascii=False).encode()
            return b"<rss><channel></channel></rss>" if "bing.com" in url else b"<html></html>"
        ai=bot.LocalAI(http=http)
        result=ai.lookup("Taiwan highest mountain height?")
        self.assertEqual(len(result),1)
        self.assertTrue(any("wikipedia.org/w/api.php" in url for url in urls))
        from urllib.parse import unquote
        decoded=" ".join(unquote(url) for url in urls)
        self.assertNotIn("3952",decoded)
        self.assertNotIn("玉山",decoded)

    def test_pronoun_attribute_cannot_invent_a_new_named_mountain(self):
        ai=bot.LocalAI()
        ai.structured_chat=Mock(side_effect=AssertionError("Must not let the model change this subject"))
        history=[dict(role="user",content="Taiwan highest mountain height?"),dict(role="assistant",content="玉山，但高度尚未確認。")]
        query=ai.resolve_followup("What about its height in meters?",history)
        self.assertIn("Taiwan highest mountain",query)
        self.assertNotIn("雪山",query)
        ai.structured_chat.assert_not_called()
        ai.structured_chat=Mock(return_value=json.dumps(dict(question="日本最高山高度"),ensure_ascii=False))
        self.assertIn("日本",ai.resolve_followup("What about Japan's highest mountain?",history))
        ai.structured_chat.assert_called_once()

    def test_non_definition_queries_exclude_recent_dictionary_snippets(self):
        rows=[dict(title="recent_百度百科",snippet="柯林斯词典解釋recent",url="https://example.org/recent",published=None)]
        self.assertEqual(bot.relevant_sources(rows,"Recent international news"),[])
        self.assertTrue(bot.relevant_sources(rows,"recent definition",definitions=True))


if __name__ == "__main__":
    unittest.main()
