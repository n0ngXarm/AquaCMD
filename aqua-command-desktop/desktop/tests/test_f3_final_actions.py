"""Bounded manual probes; synthetic calls only, all real sockets mocked."""
import threading
import unittest
from unittest.mock import Mock, patch

import f3_network as f3


class FinalActionTests(unittest.TestCase):
    def run_probe(self, device, cancel=None, ping=None):
        done = threading.Event()
        results = []
        def callback(result):
            results.append(result)
            done.set()
        with patch.object(f3.GLib, 'idle_add', side_effect=lambda cb, result: cb(result)), \
                patch.object(f3.subprocess, 'run', side_effect=ping or (lambda *a, **k: Mock(returncode=0))) as run, \
                patch.object(f3.socket, 'socket') as socket:
            socket.return_value.__enter__.return_value.connect_ex.return_value = 0
            f3.RealDetectionEngine.detect_device_network(device, False, callback, cancel=cancel)
            self.assertTrue(done.wait(3), 'Probe must finish within its bounded phases')
        return results[0], run, socket

    def test_multi_target_or_hostname_never_causes_probe_or_dns(self):
        for value in ('127.0.0.1 127.0.0.2', 'lab-host.invalid', '', '127.0.0.1;id'):
            with self.subTest(value=value):
                result, ping, sock = self.run_probe({'id': 'lab', 'configured_ip': value, 'port': 49327})
                ping.assert_not_called()
                sock.assert_not_called()
                self.assertEqual(result['reachability'], 'NOT_TESTED')
                self.assertTrue(result['error'])

    def test_cancel_after_ping_prevents_tcp_and_returns_no_receipt(self):
        cancelled = threading.Event()
        def ping(*args, **kwargs):
            self.assertEqual(kwargs['timeout'], 1.5)
            cancelled.set()
            return Mock(returncode=0)
        result, _, sock = self.run_probe({'id': 'lab', 'configured_ip': '127.0.0.1', 'port': 49327}, cancelled, ping)
        sock.assert_not_called()
        self.assertTrue(result['cancelled'])

    def test_cancel_before_start_performs_no_io(self):
        cancelled = threading.Event()
        cancelled.set()
        result, ping, sock = self.run_probe({'id': 'lab', 'configured_ip': '127.0.0.1'}, cancelled)
        ping.assert_not_called()
        sock.assert_not_called()
        self.assertTrue(result['cancelled'])

    def test_external_service_only_uses_its_explicit_tcp_port(self):
        result, ping, sock = self.run_probe({'id': 'lab', 'type': 'service', 'configured_ip': '127.0.0.1', 'port': 49327})
        ping.assert_not_called()
        connection = sock.return_value.__enter__.return_value
        connection.settimeout.assert_called_once_with(1.0)
        connection.connect_ex.assert_called_once_with(('127.0.0.1', 49327))
        self.assertIsNone(result['ping_ok'])
        self.assertEqual(result['reachability'], 'REACHABLE')

    def test_local_api_failures_are_not_remote_unreachable_evidence(self):
        done = threading.Event()
        results = []
        def callback(result):
            results.append(result)
            done.set()
        with patch.object(f3.GLib, 'idle_add', side_effect=lambda cb, result: cb(result)), \
                patch.object(f3.subprocess, 'run', side_effect=FileNotFoundError('ping unavailable')), \
                patch.object(f3.socket, 'socket', side_effect=PermissionError('local API denied')):
            f3.RealDetectionEngine.detect_device_network({'id': 'lab', 'configured_ip': '127.0.0.1', 'port': 49327}, False, callback)
            self.assertTrue(done.wait(3))
        self.assertIsNone(results[0]['ping_ok'])
        self.assertIsNone(results[0]['tcp_ok'])
        self.assertEqual(results[0]['reachability'], 'NOT_TESTED')
        self.assertIn('PermissionError', results[0]['error'])


if __name__ == '__main__':
    unittest.main()
