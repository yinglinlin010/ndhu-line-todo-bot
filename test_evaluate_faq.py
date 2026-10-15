"""Checks for evaluation integrity; no model or network calls."""
import importlib.util
import json
import queue
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('faq_evaluator', Path(__file__).parent/'scripts/evaluate-faq.py')
eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval)


class FAQEvaluationTests(unittest.TestCase):
    def test_reference_answers_and_labels_are_not_in_the_bot_event(self):
        case = dict(id='case',conversation='chain',user='A',question='Test question?',
                    split='holdout',check=dict(kind='fact',all_of=[['SECRET_REFERENCE_ANSWER']]))
        event = eval.make_event(case)
        payload = json.dumps(event)
        self.assertEqual(event['message']['text'], case['question'])
        for private in ['SECRET_REFERENCE_ANSWER','holdout','all_of','check']:
            self.assertNotIn(private,payload)
        other = eval.make_event(dict(case,user='B'))
        self.assertNotEqual(event['source']['userId'],other['source']['userId'])

    def test_facts_refusals_and_failures_are_separate(self):
        check = dict(kind='fact',all_of=[['Canberra']],sources=True)
        self.assertEqual(eval.grade('這次沒有找到足以確認答案的相關來源',check),('查不到',False))
        self.assertEqual(eval.grade('這次沒有找到足以確認答案的相關來源',dict(kind='refusal')),('查不到',True))
        self.assertEqual(eval.grade('Canberra',check),('缺少來源',False))
        self.assertEqual(eval.grade('本機模型暫時無法回答',dict(kind='refusal')),('執行失敗',False))

    def test_current_source_presence_does_not_automatically_count_as_true(self):
        answer=[dict(type='text',text='Unverified current claim'),dict(type='flex',contents=dict(action=dict(type='uri',uri='https://official.example/page')))]
        status,passed=eval.grade(answer,dict(kind='manual',source_hosts=['official.example']))
        self.assertEqual(status,'待人工核對')
        self.assertIsNone(passed)

    def test_out_of_order_and_late_replies_do_not_cross_case_boundaries(self):
        capture=eval.ReplyCapture()
        capture.register('A')
        capture.register('B')
        with self.assertRaises(queue.Empty):
            capture.wait('A',timeout=0)
        capture.send({'webhookEventId':'B'},'B answer')
        capture.send({'webhookEventId':'A'},'late A answer')
        self.assertEqual(capture.wait('B',timeout=0),'B answer')
        self.assertEqual(capture.wait('A',timeout=0),'late A answer')

    def test_bank_has_distinct_cases_and_an_explicit_holdout(self):
        cases=json.loads((Path(__file__).parent/'evaluation/faq-cases.json').read_text())['cases']
        self.assertEqual(len({r['id'] for r in cases}),len(cases))
        dev={r['question'] for r in cases if r['split']=='development'}
        held={r['question'] for r in cases if r['split']=='holdout'}
        self.assertFalse(dev & held)
        self.assertGreaterEqual(len(held),8)


if __name__=='__main__':
    unittest.main()
