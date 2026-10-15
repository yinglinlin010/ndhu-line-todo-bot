"""Cases derived from real phone failures; isolated fake HTTP, no LINE/cloud writes."""
import json
import unittest
from datetime import datetime
from unittest.mock import Mock

import line_bot_local as bot
from test_line_bot_local import NOW


class PhoneRegressionTests(unittest.TestCase):
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
