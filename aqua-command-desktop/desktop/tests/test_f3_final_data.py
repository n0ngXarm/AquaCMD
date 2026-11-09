"""Current F3 remediation contracts; only synthetic/local fixtures, no remote I/O."""
import json
import tempfile
import time
import threading
from datetime import datetime, timezone
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import f3_network as f3
from gi.repository import GLib


class FinalDataTests(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory()
        self.addCleanup(self.profile.cleanup)
        directory = Path(self.profile.name)
        (directory / 'network_topology.json').write_text(json.dumps({'devices': [
            {'device_id': 'switch-a', 'type': 'switch', 'configured_ip': '127.0.0.2'},
            {'device_id': 'unknown-a', 'configured_ip': '127.0.0.3'},
        ]}))
        owner = SimpleNamespace(config_dir=directory, topology_data={})
        with patch.object(f3.F3NetworkTopologyView, 'refresh_local_state'):
            self.view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)

    def snapshot(self, address='127.0.0.7/8'):
        return {'state': 'OBSERVED_LOCAL', 'observed_at': time.time(), 'timestamp': '2026-11-05T00:00:00+00:00',
            'source': 'NETWORKMANAGER_DBUS', 'hostname': 'synthetic-host', 'active_interface': 'lab-wifi',
            'default_gw_iface': 'lab-wifi', 'default_gateway': '127.0.0.1',
            'interfaces': {'lab-wifi': {'ipv4': address, 'carrier': True, 'active': True,
                'interface_type': 'WIFI', 'connection_state': 'CONNECTED', 'speed_mbps': 72},
                'lab-ethernet': {'ipv4': None, 'carrier': False, 'active': False, 'interface_type': 'ETHERNET'}}}

    def test_local_interfaces_and_remote_hosts_have_separate_counts(self):
        self.view._apply_local_state(self.snapshot())
        stats = self.view.store.get_summary_stats()
        self.assertEqual(stats.get('observed_local_interfaces'), 2)
        self.assertEqual(stats.get('verified_remote_hosts'), 0)
        self.assertIn('2', self.view.lbl_stat_det.get_text())
        self.assertEqual(stats['opc_connected'], 0)

    def test_local_address_changes_replace_current_binding(self):
        self.view._apply_local_state(self.snapshot())
        self.view._apply_local_state(self.snapshot('127.0.0.8/8'))
        host = next(d for d in self.view.store.devices.values() if d['type'] == 'local_host')
        self.assertEqual(host['observed_ip'], '127.0.0.8/8')
        self.assertNotIn('127.0.0.7', host['observed_ip'])

    def test_local_configured_address_mismatch_is_explicit_without_zone_inference(self):
        dev = {'type': 'local_host', 'configured_ip': '127.0.0.9', 'network_zone': 'UNASSIGNED'}
        status, reason = f3.evidence.network_binding(dev, self.snapshot(), {})
        self.assertEqual(status, 'CONFIGURATION MISMATCH')
        self.assertTrue(reason)
        dev['configured_ip'] = '127.0.0.7'
        status, reason = f3.evidence.network_binding(dev, self.snapshot(), {})
        self.assertEqual(status, 'UNVERIFIED')
        self.assertIn('assign', reason.lower())

    def test_missing_observation_and_expired_observation_are_not_healthy(self):
        self.view._apply_local_state({'interfaces': {}, 'state': 'UNKNOWN', 'error': 'LOCAL_API_UNAVAILABLE'})
        host = next(d for d in self.view.store.devices.values() if d['type'] == 'local_host')
        self.assertFalse(f3.evidence.reachable(host))
        old = self.snapshot()
        old['observed_at'] = time.time() - 120
        self.view._apply_local_state(old)
        self.assertIsNone(self.view.store.get_summary_stats().get('observed_local_interfaces'))
        self.assertIn('STALE', self.view.lbl_stat_det.get_text())

    def test_unknown_type_does_not_default_to_scada(self):
        self.assertEqual(self.view.store.devices['unknown-a']['type'], 'unknown')

    def test_switch_has_no_implicit_opcua_action_or_port(self):
        self.view.inspector.inspect_device('switch-a')
        self.assertFalse(self.view.inspector.btn_test_opc.get_visible())
        self.assertFalse(self.view.inspector.btn_read_once.get_visible())
        self.assertIsNone(self.view.store.devices['switch-a']['port'])

    def test_never_tested_session_is_not_reported_disconnected(self):
        self.view.inspector.inspect_device('switch-a')
        self.assertIn(self.view.inspector.lbl_session.get_text(), ('UNKNOWN', 'NOT_TESTED', 'NOT_APPLICABLE'))

    def test_device_inspector_is_docked_instead_of_an_owned_window(self):
        self.view.toggle_inspector(True)
        self.assertIs(self.view.inspector.get_parent(), self.view.main_split)
        self.assertIsNone(self.view.details_window)
        self.assertFalse(self.view.inspector.btn_close.get_visible())

    def drain(self, seconds=1):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            if not self.view._remote_busy and not self.view._local_pending and not self.view._runtime_pending:
                return
            time.sleep(0.005)
        self.fail('Worker did not finish')

    def test_local_reader_failure_releases_pending_state_and_is_unknown(self):
        with patch.object(f3, 'safe_get_local_network_state', side_effect=OSError('unavailable')):
            self.view.refresh_local_state()
            self.drain()
        self.assertFalse(self.view._local_pending)
        self.assertEqual(self.view.store.get_summary_stats()['local_observation_state'], 'UNKNOWN')
        self.assertIn('LOCAL_API_UNAVAILABLE', self.view.local_state['errors'])

    def test_cancelled_read_remains_busy_until_worker_closes_and_discards_value(self):
        release = threading.Event()
        started = threading.Event()
        self.addCleanup(release.set)
        self.view.store.update_device('switch-a', {'capabilities': ['opcua']})
        device = self.view.store.devices['switch-a']
        def delayed(*args):
            started.set()
            release.wait(1)
            return {'session_verified': True, 'read_success': True, 'value': 42.5, 'quality': 'GOOD'}
        with patch.object(self.view.secure_opcua, 'read_sync', side_effect=delayed):
            self.view._execute_read_once(device)
            self.assertTrue(started.wait(1))
            self.view.cancel_remote_action()
            self.assertTrue(self.view._remote_busy)
            self.assertFalse(self.view.inspector.btn_cancel.get_sensitive())
            release.set()
            self.drain()
        self.assertFalse(self.view._remote_busy)
        self.assertFalse(f3.evidence.read_verified(device))
        self.assertIsNone(device['last_read_value'])
        self.assertEqual(device['opcua_state'], 'CANCELLED')

    def test_type_or_interface_edit_invalidates_all_target_receipts(self):
        device = self.view.store.devices['switch-a']
        device.update(reachability='REACHABLE', session_state='CONNECTED')
        f3.evidence.record_evidence(device, 'reachability', 'OBSERVED_REMOTE')
        f3.evidence.record_evidence(device, 'session', 'VERIFIED_OPCUA')
        self.view.store.update_device('switch-a', {'type': 'router', 'interface_name': 'lab-wifi'})
        device = self.view.store.devices['switch-a']
        self.assertFalse(f3.evidence.reachable(device))
        self.assertFalse(f3.evidence.session_connected(device))

    def test_one_busy_job_and_half_second_rate_guard(self):
        device = self.view.store.devices['switch-a']
        token = self.view._begin_remote(device)
        self.assertIsNotNone(token)
        self.assertIsNone(self.view._begin_remote(device))
        self.view._remote_busy = False
        self.assertIsNone(self.view._begin_remote(device))

    def test_explicit_local_settings_persist_instead_of_being_dropped(self):
        self.view.store.update_device('dev-collector-01', {'alias': 'LAB local alias', 'interface_name': 'lab-wifi'})
        reloaded = f3.F3DeviceStore(self.view.store.config_file)
        self.assertEqual(reloaded.devices['dev-collector-01']['alias'], 'LAB local alias')
        self.assertEqual(reloaded.devices['dev-collector-01']['interface_name'], 'lab-wifi')

    def test_local_mismatch_is_visible_in_primary_status(self):
        self.view._apply_local_state(self.snapshot())
        self.view.store.update_device('dev-collector-01', {'configured_ip': '127.0.0.9'})
        self.view.select_device('dev-collector-01')
        self.assertIn('MISMATCH', self.view.inspector.lbl_ping.get_text())
        self.assertIn('MISMATCH', self.view.cards['dev-collector-01'].lbl_summary.get_text())

    def test_expired_snapshot_cannot_validate_an_assigned_network_role(self):
        snapshot = self.snapshot()
        snapshot['observed_at'] = time.time() - 120
        status, reason = f3.evidence.network_binding({'type': 'local_host', 'network_zone': 'SCADA_OT'},
            snapshot, {'SCADA_OT': {'interface': 'lab-wifi', 'subnet': '127.0.0.0/8'}})
        self.assertEqual(status, 'UNVERIFIED')
        self.assertIn('STALE', reason)

    def runtime_owner(self, age=0, allowed=True):
        endpoint = 'opc.tcp://127.0.0.1:49327'
        arrived = datetime.fromtimestamp(time.time()-age, timezone.utc)
        observations = [SimpleNamespace(tag_name='LAB.Level', node_id='ns=2;s=Level', value=0, quality='GOOD',
            raw_status_name='Good', source_time=arrived, server_time=arrived, arrival_time=arrived,
            endpoint_url=endpoint, session_state='CONNECTED')]
        from unittest.mock import Mock
        self.view.owner.opcua_store = SimpleNamespace(snapshot_observations=Mock(return_value=observations))
        self.view.owner.opcua_mapper = SimpleNamespace(is_allowed=lambda tag: allowed)
        self.view.owner.polling_engine = SimpleNamespace(endpoint_url=endpoint,
            get_telemetry=Mock(return_value={'state': 'RUNNING'}), start_monitoring=Mock())
        local_refresh = patch.object(self.view, 'refresh_local_state')
        local_refresh.start()
        self.addCleanup(local_refresh.stop)
        return self.view.owner.polling_engine

    def test_existing_collector_receipts_count_without_starting_a_poller_or_inventing_nic_state(self):
        poller = self.runtime_owner()
        self.view._observe_runtime()
        self.drain()
        self.view.select_device('dev-collector-01')
        stats = self.view.store.get_summary_stats()
        self.assertEqual(stats['opc_connected'], 1)
        self.assertEqual(stats['opc_read_verified'], 1)
        self.assertIsNone(stats['observed_local_interfaces'])
        self.assertIn('RUNNING', self.view.inspector.lbl_polling.get_text())
        self.assertIn('CONNECTED', self.view.inspector.lbl_client.get_text())
        self.assertIn(': 0 [GOOD]', self.view.inspector.lbl_shared_read.get_text())
        poller.start_monitoring.assert_not_called()

    def test_expired_or_unmapped_collector_receipts_do_not_verify_sessions(self):
        for age, allowed in ((120, True), (0, False)):
            with self.subTest(age=age, allowed=allowed):
                self.runtime_owner(age, allowed)
                self.view._observe_runtime()
                self.drain()
                self.view.select_device('dev-collector-01')
                self.assertEqual(self.view.store.get_summary_stats()['opc_connected'], 0)
                self.assertEqual(self.view.store.get_summary_stats()['opc_read_verified'], 0)
                self.assertNotIn('CONNECTED', self.view.inspector.lbl_client.get_text())
                if age:
                    self.assertIn('STALE', self.view.inspector.lbl_shared_read.get_text())

    def test_remote_collector_does_not_inherit_this_hosts_runtime_or_nic(self):
        self.runtime_owner()
        self.view._observe_runtime()
        self.drain()
        self.view.store.update_device('unknown-a', {'type': 'remote_collector'})
        self.view.select_device('unknown-a')
        self.assertIn('UNKNOWN', self.view.inspector.lbl_client.get_text())
        self.assertIn('UNKNOWN', self.view.inspector.lbl_polling.get_text())
        self.assertFalse(self.view.store.devices['unknown-a'].get('interface_observations'))

    def test_external_delivery_log_is_not_a_bound_provider_ack(self):
        self.view.store.update_device('switch-a', {'type': 'service', 'port': 49327})
        snapshot = {'available': True, 'checked_at': time.time(), 'counts': {}, 'marks': {},
            'delivery_state': 'RECORDED_UNVERIFIED', 'last_delivery': {'status': 'SUCCESS', 'http_status': 200}}
        self.view.runtime.accept(snapshot)
        self.view.select_device('switch-a')
        self.assertIn('UNVERIFIED', self.view.inspector.lbl_delivery.get_text())
        self.assertNotIn('DELIVERED', self.view.inspector.lbl_delivery.get_text())

    def test_expired_runtime_snapshot_is_not_drawn_as_current_counts(self):
        self.view.runtime.accept({'available': True, 'checked_at': time.time()-120, 'marks': {},
            'counts': {'storage': 25, 'task': 0, 'outbox': 0, 'delivery': 0}})
        with patch.object(f3, 'draw_pango_text') as text:
            surface = f3.cairo.ImageSurface(f3.cairo.FORMAT_ARGB32, 1000, 343)
            self.view.canvas.on_draw(self.view.canvas, f3.cairo.Context(surface), 1000, 343)
        labels = [str(call.args[1]) for call in text.call_args_list]
        self.assertIn('STALE committed rows', labels)
        self.assertNotIn('25 committed rows', labels)

    def test_periodic_passive_refresh_replaces_changed_ip_without_remote_actions(self):
        self.view._apply_local_state(self.snapshot())
        self.view._local_requested_at = time.monotonic()-11
        with patch.object(f3, 'safe_get_local_network_state', return_value=self.snapshot('127.0.0.8/8')):
            self.view._observe_runtime()
            self.drain()
        self.assertEqual(self.view.store.devices['dev-collector-01']['observed_ip'], '127.0.0.8/8')

    def test_global_nic_badge_uses_fresh_snapshot_instead_of_legacy_carrier(self):
        import app
        self.view._apply_local_state(self.snapshot())
        owner = SimpleNamespace(f3_network_view=self.view, pill_scada_ip=f3.Gtk.Label())
        app.AquaWinCCWindow.update_local_nic_badge(owner, False)
        self.assertIn('lab-wifi', owner.pill_scada_ip.get_text())
        self.assertIn('LINK', owner.pill_scada_ip.get_text())
        self.view.local_state['observed_at'] = time.time()-120
        app.AquaWinCCWindow.update_local_nic_badge(owner, True)
        self.assertIn('STALE', owner.pill_scada_ip.get_text())

    def test_host_metrics_uses_cached_network_snapshot_without_synchronous_os_query(self):
        import app
        with patch.object(f3, 'safe_get_local_network_state', side_effect=AssertionError('OS query on UI path')) as query:
            values = app.read_real_machine_data(self.snapshot())
        query.assert_not_called()
        self.assertIn('127.0.0.7/8', values['ip_lan'])


if __name__ == '__main__':
    unittest.main()
