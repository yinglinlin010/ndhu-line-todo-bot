"""Deterministic period and official-document boundaries; no real network/cloud."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
import line_bot_local as bot
from calendar_queries import calendar_period
from research_documents import extract_references

class QuerySourceTests(unittest.TestCase):
    def test_periods_include_timezone_and_exclusive_end(self):
        now = datetime(2026, 10, 18, 15, 0, tzinfo=bot.TAIPEI)
        for raw, start, end in [('查日曆2026-10-25','2026-10-25','2026-10-26'),
            ('十月二十五日','2026-10-25','2026-10-26'),('本週','2026-10-12','2026-10-19'),
            ('下週','2026-10-19','2026-10-26'),('上週','2026-10-05','2026-10-12'),
            ('in 3 days','2026-10-21','2026-10-22')]:
            period = calendar_period(raw,now)
            self.assertEqual(period.start.date().isoformat(),start)
            self.assertEqual(period.end.date().isoformat(),end)
            self.assertEqual(period.start.utcoffset().total_seconds(),8*3600)
        for raw in ['今天和明天','2026-02-30','2026-10-25到2026-10-26','下個月','in 500 days']:
            with self.assertRaises(ValueError): calendar_period(raw,now)

    def test_google_query_uses_parsed_interval_without_writing(self):
        workspace=bot.GoogleWorkspace.__new__(bot.GoogleWorkspace)
        workspace.clock=lambda:0
        workspace.calendar_id='synthetic-calendar'
        workspace.call=Mock(return_value={'items':[]})
        period=calendar_period('2026-10-25',datetime(2026,10,18,tzinfo=bot.TAIPEI))
        self.assertEqual(workspace.read_calendar(period),[])
        args=workspace.call.call_args.args
        self.assertEqual(args[:3],('calendar','events','list'))
        params=json.loads(args[-1]);self.assertEqual(params['timeMin'],'2026-10-25T00:00:00+08:00')
        self.assertEqual(params['timeMax'],'2026-10-26T00:00:00+08:00')

    def test_pricing_uses_verified_official_units_and_separates_subscription(self):
        def http(url,**kwargs):
            if url.endswith('/api/chat'):
                return json.dumps({'message':{'content':'不應採用的月費猜測'}}).encode()
            self.assertEqual(url,'https://developers.openai.com/api/docs/pricing/')
            return b'<title>Pricing | OpenAI API</title><main>Prices per 1M tokens. Input Output Synthetic rates.</main>'
        ai=bot.LocalAI(http=http)
        result=ai.ask('解釋 ChatGPT 價格的計算公式','pricing')
        self.assertIn('ChatGPT訂閱月費',result[0]['text'])
        self.assertIn('API用量',result[0]['text'])
        self.assertIn('÷100萬',result[0]['text'])
        self.assertNotIn('月費猜測',result[0]['text'])
        bad=bot.LocalAI(http=lambda *a,**k:b'<main>Pricing unavailable</main>')
        self.assertEqual(bad.lookup_pricing('ChatGPT價格'),[])

    def test_pdf_worker_reads_actual_synthetic_bibliography_and_rejects_non_pdf(self):
        writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 700 Td (Physics 2026) Tj 0 -20 Td (References) Tj 0 -20 Td ([1] Synthetic Author, Synthetic Journal 1 \\(2020\\) 5.) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        buffer=io.BytesIO();writer.write(buffer)
        extracted=extract_references(buffer.getvalue(),timeout=5)
        self.assertIn('2026',extracted['header'])
        self.assertEqual(len(extracted['references']),1)
        self.assertIn('Synthetic Author',extracted['references'][0]['text'])
        with self.assertRaises(ValueError):extract_references(b'<html>not pdf</html>',5)

    def test_crossref_requires_exact_journal_year_volume_and_article(self):
        from reference_metadata import verified_reference_papers
        ref=[dict(number=7,text='Synthetic Collaboration, Science 42 (2020) 100.')]
        item=dict(type='journal-article',title=['Synthetic title'],DOI='10.1234/synthetic',
            published={'date-parts':[[2020]]}, **{'container-title':['Science'],'volume':'42','article-number':'100'})
        def response(value):
            return lambda *a,**k:json.dumps({'message':{'items':[value]}}).encode()
        self.assertEqual(verified_reference_papers(ref,response(item))[0]['doi'],'10.1234/synthetic')
        for modified in [item|{'volume':'43'},item|{'article-number':'101'},
            item|{'published':{'date-parts':[[2021]]}},item|{'container-title':['Different journal']},
            item|{'DOI':'invalid doi'}]:
            self.assertEqual(verified_reference_papers(ref,response(modified)),[])

    def test_research_pdf_metadata_cannot_invent_papers_or_wrong_year(self):
        def http(url,**kwargs):
            if url.endswith('.pdf'):return b'%PDF-synthetic'
            return b'<title>Nobel Prize in Physics 2026</title><main>Official text <a href="/uploads/2026/test.pdf">PDF</a></main>'
        ai=bot.LocalAI(http=http)
        refs=[dict(number=12,text='Synthetic Author, "Synthetic Paper" (2020).')]
        with patch.object(bot,'extract_references',return_value=dict(header='Physics 2026',references=refs,pages=2)):
            rows=ai.lookup_nobel_research((2026,'phy','物理學獎'))
            self.assertEqual(rows[0]['bibliography'],refs)
            self.assertTrue(rows[0]['url'].endswith('.pdf'))
        with patch.object(bot,'extract_references',return_value=dict(header='Physics 2025',references=refs,pages=2)):
            rows=ai.lookup_nobel_research((2026,'phy','物理學獎'))
            self.assertFalse(any(r.get('bibliography') for r in rows))

if __name__=='__main__':unittest.main()
