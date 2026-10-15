"""Supervisor checks use isolated files and fake processes; never touch live LINE."""
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('line_service', Path(__file__).parent / 'scripts/run-bot.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.config = dict(LINE_CHANNEL_ACCESS_TOKEN='test-token', W5_WEBHOOK_URL='https://script.google.com/macros/s/test/exec',
                           PUBLIC_BASE_URL='https://old-test.trycloudflare.com', PORT='3000')
        self.runner = service.Service(self.config, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_expected_local_cloudflared_is_eligible_for_stop(self):
        self.assertTrue(service.owned_tunnel('/opt/homebrew/bin/cloudflared tunnel --url http://127.0.0.1:3000', 3000))
        for command in ['python app.py', 'cloudflared tunnel --url http://127.0.0.1:8080',
                        'cloudflared tunnel --url https://example.org:3000',
                        'cloudflared tunnel --url http://user:pass@localhost:3000',
                        'cloudflared tunnel --token something']:
            self.assertFalse(service.owned_tunnel(command, 3000), command)
        (self.root / 'data/cloudflared-process.json').write_text('{"pid":123}')
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=0, stdout='python app.py')), patch.object(service.os, 'kill') as kill:
            with self.assertRaises(RuntimeError):
                self.runner.stop_previous_tunnel()
            kill.assert_not_called()

    def test_restore_only_own_previous_route_never_an_unknown_application(self):
        local = self.config['PUBLIC_BASE_URL'] + '/webhook'
        with patch.object(service.bot, 'read_http', return_value=json.dumps(dict(endpoint=local)).encode()), patch.object(service.bot, 'restore_webhook') as restore:
            self.runner.restore_owned_route()
            restore.assert_called_once_with('test-token', self.config['W5_WEBHOOK_URL'])
        with patch.object(service.bot, 'read_http', return_value=b'{"endpoint":"https://other-app.example/webhook"}'), patch.object(service.bot, 'restore_webhook') as restore:
            with self.assertRaises(RuntimeError):
                self.runner.restore_owned_route()
            restore.assert_not_called()

    def test_healthy_new_tunnel_updates_private_config_before_bot_start(self):
        (self.root / '.env').write_text('PUBLIC_BASE_URL=https://old-test.trycloudflare.com\n')
        process = Mock(pid=456)
        process.poll.return_value = None
        def spawn(*args, **kwargs):
            (self.root / 'data/managed-tunnel.log').write_text('https://new-test.trycloudflare.com\nRegistered tunnel connection')
            return process
        with patch.object(service.shutil, 'which', return_value='/usr/bin/cloudflared'), patch.object(self.runner, 'stop_previous_tunnel'), patch.object(self.runner, 'tunnel_ready', return_value=True), patch.object(self.runner.stop, 'wait', return_value=False), patch.object(service.subprocess, 'Popen', side_effect=spawn):
            self.runner.open_tunnel()
        self.assertEqual(self.runner.config['PUBLIC_BASE_URL'], 'https://new-test.trycloudflare.com')
        self.assertIn('new-test', (self.root / '.env').read_text())
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.runner.pid_path.read_text())['pid'], 456)

    def test_public_dns_error_is_not_treated_as_tunnel_ready(self):
        with patch.object(service.requests, 'get', return_value=Mock(status_code=530)):
            self.assertFalse(self.runner.tunnel_ready('https://example.trycloudflare.com'))
        with patch.object(service.requests, 'get', return_value=Mock(status_code=502)):
            self.assertTrue(self.runner.tunnel_ready('https://example.trycloudflare.com'))

    def test_dns_fallback_keeps_tls_hostname_and_rejects_private_addresses(self):
        dns = Mock()
        dns.json.return_value = {"Answer": [{"type": 1, "data": "1.1.1.1"}]}
        pool = Mock()
        pool.__enter__ = Mock(return_value=pool)
        pool.__exit__ = Mock(return_value=False)
        pool.urlopen.return_value = Mock(status=200, data=b"ok")
        with patch.object(service.requests, 'get', side_effect=[service.requests.ConnectionError(), dns]), patch.object(service.urllib3, 'HTTPSConnectionPool', return_value=pool) as factory:
            self.assertTrue(self.runner.health('https://new-test.trycloudflare.com'))
            self.assertEqual(factory.call_args.kwargs['assert_hostname'], 'new-test.trycloudflare.com')
            self.assertEqual(factory.call_args.kwargs['server_hostname'], 'new-test.trycloudflare.com')
        dns.json.return_value = {"Answer": [{"type": 1, "data": "127.0.0.1"}]}
        with patch.object(service.requests, 'get', side_effect=[service.requests.ConnectionError(), dns]), patch.object(service.urllib3, 'HTTPSConnectionPool') as factory:
            self.assertFalse(self.runner.health('https://new-test.trycloudflare.com'))
            factory.assert_not_called()

    def test_busy_port_prevents_a_second_bot_and_webhook_changes(self):
        with patch.object(self.runner, 'port_in_use', return_value=True), patch.object(self.runner, 'restore_owned_route') as restore:
            with self.assertRaises(RuntimeError):
                self.runner.run()
            restore.assert_not_called()

    def test_tunnel_exit_triggers_a_clean_restart(self):
        self.runner.child = Mock()
        self.runner.child.poll.return_value = None
        self.runner.tunnel = Mock()
        self.runner.tunnel.poll.return_value = 1
        self.runner.stop = Mock()
        self.runner.stop.is_set.return_value = False
        self.runner.stop.wait.side_effect = [False, False, True]
        with patch.object(self.runner, 'port_in_use', return_value=False), patch.object(self.runner, 'restore_owned_route') as restore, \
             patch.object(self.runner, 'open_tunnel') as open_tunnel, patch.object(self.runner, 'start_bot') as start, \
             patch.object(self.runner, 'stop_children') as stop:
            self.runner.run()
        self.assertEqual(restore.call_count, 2)
        self.assertEqual(open_tunnel.call_count, 2)
        self.assertEqual(start.call_count, 2)
        self.assertTrue(stop.called)

    def test_shutdown_waits_for_bot_restoration_before_stopping_tunnel(self):
        order = []
        child, tunnel = Mock(), Mock()
        child.poll.side_effect = [None, None, 0]
        child.send_signal.side_effect = lambda sig: order.append('interrupt')
        child.wait.side_effect = lambda **kw: order.append('bot-exited')
        tunnel.poll.return_value = None
        tunnel.terminate.side_effect = lambda: order.append('tunnel-stop')
        self.runner.child, self.runner.tunnel = child, tunnel
        self.runner.stop_children()
        self.assertEqual(order, ['interrupt', 'bot-exited', 'tunnel-stop'])
        child.send_signal.assert_called_once_with(signal.SIGINT)
        child.kill.assert_not_called()
