"""Relay boundary tests: no external calls or real credentials."""
import base64
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import Mock, patch
import line_bot_local as bot


class RelayTests(unittest.TestCase):
    def test_basic_concepts_stay_local_but_recent_research_does_not(self):
        self.assertTrue(bot.model_knowledge_intent('用一句話解釋慣性'))
        self.assertFalse(bot.model_knowledge_intent('解釋今年最新的慣性研究論文'))

    def test_teacher_search_prefix_is_explicit_without_swallowing_private_commands(self):
        self.assertEqual(bot.question_mode('查 台灣最高的山是哪一座？多高？'),
                         ('台灣最高的山是哪一座？多高？', True, False))
        self.assertEqual(bot.question_mode('查 解釋慣性'), ('解釋慣性', True, False))
        self.assertEqual(bot.question_mode('查詢')[0], '查詢')
        self.assertEqual(bot.question_mode('查日曆')[0], '查日曆')

    def setUp(self):
        self.runtime = Mock(secret='line-test-secret', photos=None)
        self.runtime.submit.return_value = True
        self.client = bot.create_app(self.runtime).test_client()
        self.config = {'APPS_SCRIPT_RELAY_KEY': 'a' * 64, 'GOOGLE_OWNER_ID': 'owner', 'APPS_SCRIPT_BOT_ID': 'bot'}
        self.event = {'type': 'message', 'webhookEventId': 'unique-test', 'replyToken': 'test',
                      'source': {'type': 'user', 'userId': 'owner'}, 'message': {'type': 'text', 'text': 'hi'}}

    def send(self, event=None, stamp=None, signature=None):
        body = json.dumps({'destination': 'bot', 'events': [event or self.event]}).encode()
        stamp = str(int(time.time())) if stamp is None else stamp
        sig = base64.b64encode(hmac.new(b'a' * 64, stamp.encode() + b'\n' + body, hashlib.sha256).digest()).decode()
        with patch.dict('os.environ', self.config):
            return self.client.post('/apps-script', data=body, headers={
                'x-relay-time': stamp, 'x-relay-signature': sig if signature is None else signature})

    def test_valid_owner_enters_existing_queue(self):
        self.assertEqual(self.send().status_code, 200)
        self.runtime.submit.assert_called_once_with(self.event)

    def test_invalid_signature_and_stale_request_rejected(self):
        self.assertEqual(self.send(signature='wrong').status_code, 401)
        self.assertEqual(self.send(stamp=str(int(time.time()) - 120)).status_code, 401)
        self.runtime.submit.assert_not_called()

    def test_other_user_rejected_even_with_valid_signature(self):
        event = dict(self.event, source={'type': 'user', 'userId': 'other'})
        self.assertEqual(self.send(event).status_code, 403)
        self.runtime.submit.assert_not_called()

    def test_direct_line_route_still_requires_line_signature(self):
        self.assertEqual(self.client.post('/webhook', json={'events': []}).status_code, 401)

    def test_unconfigured_relay_disabled(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(self.client.post('/apps-script', data=b'{}').status_code, 503)

    def test_authenticated_probe_never_submits_a_message(self):
        body = json.dumps({'action': 'probe', 'destination': 'bot', 'events': []}).encode()
        stamp = str(int(time.time()))
        signature = base64.b64encode(hmac.new(b'a' * 64, stamp.encode() + b'\n' + body, hashlib.sha256).digest()).decode()
        with patch.dict('os.environ', self.config):
            response = self.client.post('/apps-script', data=body, headers={'x-relay-time': stamp, 'x-relay-signature': signature})
        self.assertEqual(response.data, b'relay ready')
        self.runtime.submit.assert_not_called()
