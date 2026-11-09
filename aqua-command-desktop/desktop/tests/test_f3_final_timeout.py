"""Real silent loopback endpoint: bounded UA timeouts, UI heartbeat and cleanup."""
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import f3_network as f3
from f3_opcua import SecureF3OpcUa
from opcua_mapping import NodeIdMapper, TagMapping
from opcua_pki import PkiManager
from gi.repository import GLib


class SilentLoopbackTests(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory(prefix='aqua-f3-timeout-')
        self.addCleanup(self.profile.cleanup)
        self.directory = Path(self.profile.name)
        self.stop = threading.Event()
        self.accepted = threading.Event()
        self.closed = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.endpoint = f'opc.tcp://127.0.0.1:{self.port}/silent/'
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
        self.mapper = NodeIdMapper()
        self.mapper.add_mapping(TagMapping('LAB.Level', 's=Level', 'urn:aquacmd:f3:lab', verified=True))
        self.pki = PkiManager(self.directory / 'pki')
        self.adapter = SecureF3OpcUa(self.mapper, self.pki, self.directory)
        self.device = {'device_id': 'silent', 'type': 'wincc', 'configured_ip': '127.0.0.1',
            'endpoint_url': self.endpoint, 'port': self.port, 'test_tag': 'LAB.Level', 'sec_policy': 'Basic256Sha256'}

    def serve(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                self.accepted.set()
                connection.settimeout(0.1)
                while not self.stop.is_set():
                    try:
                        if not connection.recv(4096):
                            self.closed.set()
                            return
                    except socket.timeout:
                        continue
                    except OSError:
                        self.closed.set()
                        return

    def cleanup_server(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(1)

    def test_timeout_has_a_reason_and_is_not_auth_or_certificate_failure(self):
        result = self.adapter.result()
        self.adapter.failure(result, TimeoutError())
        self.assertEqual(result['opcua_state'], 'TIMEOUT')
        self.assertTrue(result['last_error'])
        self.assertEqual(result['certificate_trust'], 'NOT_TESTED')

    def test_actual_silent_probe_times_out_and_closes_socket(self):
        started = time.monotonic()
        result = self.adapter.probe_sync(self.device, {'sec_policy': 'Basic256Sha256'})
        self.assertLess(time.monotonic()-started, 6.5)
        self.assertTrue(self.accepted.is_set())
        self.assertTrue(self.closed.wait(1), 'Timed-out client socket must close')
        self.assertFalse(result['session_verified'])
        self.assertEqual(result['opcua_state'], 'TIMEOUT')
        self.assertTrue(result['last_error'])

    def test_actual_silent_read_times_out_without_fabricated_value(self):
        started = time.monotonic()
        result = self.adapter.read_sync(self.device, {'sec_policy': 'Basic256Sha256'})
        self.assertLess(time.monotonic()-started, 6.5)
        self.assertTrue(self.closed.wait(1))
        self.assertFalse(result['read_success'])
        self.assertIsNone(result.get('value'))
        self.assertEqual(result['opcua_state'], 'TIMEOUT')

    def test_cancel_during_silent_probe_keeps_ui_heartbeat_and_waits_for_cleanup(self):
        (self.directory / 'network_topology.json').write_text(json.dumps({'devices': [self.device]}))
        owner = SimpleNamespace(config_dir=self.directory, topology_data={}, pki=self.pki, opcua_mapper=self.mapper)
        with patch.object(f3.F3NetworkTopologyView, 'refresh_local_state'):
            view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
        device = view.store.devices['silent']
        started = time.monotonic()
        view._execute_opcua_test(device)
        self.assertTrue(self.accepted.wait(1))
        view.cancel_remote_action()
        self.assertTrue(view._remote_busy)
        tick_before = view.canvas.anim_tick_count
        context = GLib.MainContext.default()
        while view._remote_busy and time.monotonic()-started < 6.5:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)
        self.assertFalse(view._remote_busy)
        self.assertGreater(view.canvas.anim_tick_count-tick_before, 10)
        self.assertTrue(self.closed.wait(1))
        self.assertEqual(device['opcua_state'], 'CANCELLED')
        self.assertFalse(f3.evidence.session_connected(device))
        self.assertFalse(f3.evidence.read_verified(device))


if __name__ == '__main__':
    unittest.main()
