"""Regression coverage for the unfinished F3 identity and topology workflow."""
import sys
import hashlib
import sqlite3
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cairo
from f3_network import ConnectionState, F3NetworkTopologyView, OpcUaState
from gi.repository import GLib, Gtk
import f3_network as f3
from f3_reconciliation_fixture import HeldThread, drain, new_view


class TestF3Continuation(unittest.TestCase):
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory()
        self.addCleanup(self.profile.cleanup)
        local_state = {"interfaces": {}, "ip_forwarding": False,
                       "timestamp": "2026-11-04T00:00:00", "default_gateway": None}
        local_patch = patch("f3_network.safe_get_local_network_state", return_value=local_state)
        local_patch.start()
        self.addCleanup(local_patch.stop)
        from f3_fixture import configure_legacy_inventory
        configure_legacy_inventory(self.profile.name)
        self.owner = SimpleNamespace(config_dir=Path(self.profile.name), topology_data={})
        self.view = F3NetworkTopologyView(self.owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)

    def test_canvas_has_one_visible_parent(self):
        self.assertIs(self.view.canvas.get_parent(), self.view.stack)
        self.assertIs(self.view.stack.get_visible_child(), self.view.canvas)
        self.assertIsNotNone(self.view.stack.get_parent())

    def test_legacy_and_stable_selection_highlight_the_same_card(self):
        for device_id in ("PC2", "dev-scada-02"):
            with self.subTest(device_id=device_id):
                self.view.select_device(device_id)
                selected = [card for card in self.view.cards.values()
                            if card.has_css_class("f3-card-selected")]
                self.assertEqual(selected, [self.view.cards[device_id]])

    def table_text(self):
        labels = []
        child = self.view.ip_grid.get_first_child()
        while child:
            if hasattr(child, "get_text"):
                labels.append(child.get_text())
            child = child.get_next_sibling()
        return "\n".join(labels)

    def test_store_add_and_remove_update_cards_and_table(self):
        self.view.store.add_device({"device_id": "dev-extra", "type": "wincc", "configured_ip": "127.0.0.20"})
        self.assertIn("dev-extra", self.view.cards)
        self.assertIn("127.0.0.20", self.table_text())
        self.view.store.remove_device("dev-extra")
        self.assertNotIn("dev-extra", self.view.cards)
        self.assertNotIn("127.0.0.20", self.table_text())

    def test_add_after_removal_preserves_remaining_device(self):
        original = self.view.store.devices["dev-scada-03"]
        self.view.store.remove_device("PC2")
        count = len(self.view.store.devices)
        self.view._on_add_device_clicked(None)
        self.assertEqual(len(self.view.store.devices), count + 1)
        self.assertIs(self.view.store.devices["dev-scada-03"], original)

    def test_configuration_updates_cannot_replace_stable_identity(self):
        self.view.store.update_device("PC1", {"device_id": "replacement", "id": "replacement"})
        self.assertEqual(self.view.store.devices["PC1"]["device_id"], "dev-scada-01")
        self.assertEqual(self.view.store.devices["PC1"]["id"], "dev-scada-01")
        reloaded = type(self.view.store)(self.view.store.config_file)
        self.assertIn("dev-scada-01", reloaded.devices)

    def test_switching_to_live_clears_demo_observations(self):
        # G02: mode-specific IDs are intentionally disjoint, not legacy aliases.
        self.view.store.update_device("PC1", {"alias": "Operator alias"})
        before = self.view.store.config_file.read_bytes()
        live_ids = set(self.view.store.devices)
        self.view._on_mode_toggle(None)
        self.assertTrue(live_ids.isdisjoint(self.view.store.devices))
        demo = next(d for d in self.view.store.devices.values() if d['type'] == 'wincc')
        demo.update(reachability="REACHABLE", opcua_state=OpcUaState.READ_VERIFIED,
                    last_read_value=42, last_read_quality="SYNTHETIC_DEMO")
        f3.evidence.record_evidence(demo, 'read', f3.evidence.Provenance.DEMO)
        self.view._on_mode_toggle(None)
        self.assertEqual(set(self.view.store.devices), live_ids)
        device = self.view.store.devices["PC1"]
        self.assertEqual(device["alias"], "Operator alias")
        self.assertEqual(device["reachability"], "NOT_TESTED")
        self.assertEqual(device["opcua_state"], OpcUaState.NOT_TESTED)
        self.assertIsNone(device["last_read_value"])
        self.assertIsNone(device['last_read_quality'])
        self.assertFalse(device['read_success'])
        self.assertFalse(f3.evidence.read_verified(device))
        self.assertEqual(self.view.store.get_summary_stats()["opc_connected"], 0)
        self.assertEqual(self.view.store.config_file.read_bytes(), before)

    def test_late_demo_callback_cannot_update_live_status(self):
        # G01: hold the actual secure-action worker, then deliver it after mode switch.
        before = self.view.store.config_file.read_bytes()
        self.view._on_mode_toggle(None)
        demo_id = next(k for k, d in self.view.store.devices.items() if d['type'] == 'wincc')
        HeldThread.started = []
        with patch('f3_network.threading.Thread', HeldThread), \
                patch.object(self.view.secure_opcua, 'probe_sync') as probe, \
                patch.object(self.view.secure_opcua, 'read_sync') as read:
            self.view.trigger_device_opcua_test(demo_id)
            self.assertEqual(len(HeldThread.started), 1)
            self.view._on_mode_toggle(None)
            HeldThread.started[0].run()
            drain()
            probe.assert_not_called()
            read.assert_not_called()
        device = self.view.store.devices['PC1']
        self.assertNotEqual(device['opcua_state'], OpcUaState.CONNECTED)
        self.assertEqual(device['session_state'], 'NOT_TESTED')
        self.assertIsNone(device['last_read_value'])
        self.assertFalse(f3.evidence.read_verified(device))
        self.assertEqual(self.view.store.get_summary_stats()['opc_connected'], 0)
        self.assertEqual(self.view.store.config_file.read_bytes(), before)

    def test_remote_opcua_actions_require_existing_authorization_gate(self):
        # G07/G08: independent fixtures avoid leaving the first worker busy.
        actions = (("trigger_device_opcua_test", "probe_sync"),
                   ("trigger_device_read_once", "read_sync"))
        for action, adapter_method in actions:
            with self.subTest(action=adapter_method):
                view = new_view(self)
                HeldThread.started = []
                receipt = dict(view.secure_opcua.result(), opcua_state='ERROR', last_error='LAB refusal')
                with patch('f3_network.OTAuthorizationDialog') as dialog, \
                        patch('f3_network.threading.Thread', HeldThread), \
                        patch.object(view.secure_opcua, adapter_method, return_value=receipt) as adapter, \
                        patch('f3_network.RealDetectionEngine.detect_opcua_session') as legacy_probe, \
                        patch('f3_network.RealDetectionEngine.read_opcua_single_tag') as legacy_read:
                    getattr(view, action)('PC1')
                    dialog.assert_called_once()
                    adapter.assert_not_called()
                    self.assertEqual(HeldThread.started, [])
                    dialog.call_args.kwargs['on_authorized']()
                    self.assertEqual(len(HeldThread.started), 1)
                    adapter.assert_not_called()
                    # A duplicate click may not bypass busy serialization.
                    getattr(view, action)('PC1')
                    self.assertEqual(dialog.call_count, 1)
                    self.assertEqual(len(HeldThread.started), 1)
                    HeldThread.started[0].run()
                    drain()
                    adapter.assert_called_once()
                    self.assertEqual(adapter.call_args.args[0]['endpoint_url'],
                                     view.store.devices['PC1']['endpoint_url'])
                    self.assertFalse(view._remote_busy)
                    self.assertFalse(f3.evidence.read_verified(view.store.devices['PC1']))
                    legacy_probe.assert_not_called()
                    legacy_read.assert_not_called()

    def test_authorization_callback_is_invalid_after_target_or_mode_changes(self):
        # A previously shown confirmation never authorizes another target or mode.
        for mutation in ('disable', 'endpoint', 'mode'):
            for action in ('trigger_device_opcua_test', 'trigger_device_read_once'):
                with self.subTest(mutation=mutation, action=action):
                    view = new_view(self)
                    HeldThread.started = []
                    with patch('f3_network.OTAuthorizationDialog') as dialog, \
                            patch('f3_network.threading.Thread', HeldThread), \
                            patch.object(view.secure_opcua, 'probe_sync') as probe, \
                            patch.object(view.secure_opcua, 'read_sync') as read:
                        getattr(view, action)('PC1')
                        dialog.assert_called_once()
                        callback = dialog.call_args.kwargs['on_authorized']
                        if mutation == 'disable':
                            view.store.update_device('PC1', {'enabled': False})
                        elif mutation == 'endpoint':
                            view.store.update_device('PC1', {'endpoint_url': 'opc.tcp://127.0.0.9:4840'})
                        else:
                            view._on_mode_toggle(None)
                        callback()
                        self.assertEqual(HeldThread.started, [])
                        probe.assert_not_called()
                        read.assert_not_called()

    def test_disabled_device_does_not_start_remote_actions(self):
        self.view.store.update_device("PC1", {"enabled": False})
        with patch("f3_network.OTAuthorizationDialog") as dialog, \
                patch("f3_network.RealDetectionEngine.detect_device_network") as network, \
                patch("f3_network.RealDetectionEngine.detect_opcua_session") as opcua, \
                patch("f3_network.RealDetectionEngine.read_opcua_single_tag") as read:
            self.view.trigger_device_detect("PC1")
            self.view.trigger_device_opcua_test("PC1")
            self.view.trigger_device_read_once("PC1")
            dialog.assert_not_called()
            network.assert_not_called()
            opcua.assert_not_called()
            read.assert_not_called()

    def test_unverified_wan_has_no_online_badge_or_verified_flow(self):
        # G03: inspect the renderer actually called by on_draw, not the retired line method.
        self.assertEqual(self.view.store.get_summary_stats()['verified_remote_hosts'], 0)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 500)
        with patch('f3_network.draw_pango_text') as text:
            self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1200, 500)
        labels = [str(call.args[1]) for call in text.call_args_list]
        self.assertIn('UNKNOWN', labels)
        self.assertFalse(any('ONLINE' in label.upper() or 'DELIVERED' in label for label in labels))
        self.assertEqual(self.view.runtime.active(), [])
        self.assertFalse(any(f3.evidence.reachable(d) for d in self.view.store.devices.values()
                             if d['type'] in ('router', 'service')))

    def test_verified_connections_render_and_animate(self):
        # G09: flags emit no pulses; an actual new SQLite commit emits a finite pulse.
        from opcua_storage import DurableStorage
        from f3_runtime import read_snapshot
        path = Path(self.profile.name) / 'synthetic-runtime.db'
        DurableStorage(path)
        self.view.runtime.accept(read_snapshot(path), now=100)
        self.view.store.devices['PC1']['opcua_state'] = OpcUaState.CONNECTED
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 500)
        def frame(now):
            with patch('f3_runtime.time.monotonic', return_value=now):
                self.view.canvas._on_anim_tick()
                self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1200, 500)
            surface.flush()
            return hashlib.sha256(bytes(surface.get_data())).hexdigest()
        self.assertEqual(frame(100), frame(100.1))
        self.assertEqual(self.view.runtime.active(now=100.1), [])
        with sqlite3.connect(path) as conn:
            conn.execute("INSERT INTO tag_observations(tag_name, quality, arrival_timestamp) VALUES ('LAB.Level','GOOD',datetime('now'))")
        self.view.runtime.accept(read_snapshot(path), now=100.2)
        self.assertEqual([p['stage'] for p in self.view.runtime.active(now=100.3)], ['storage'])
        self.assertNotEqual(frame(100.3), frame(100.7))
        self.assertEqual(self.view.runtime.active(now=102), [])
        self.assertEqual(frame(102), frame(102.2))

    def test_layout_fits_1366_with_inspector_visible(self):
        self.view.select_device("dev-scada-01")
        minimum, _, _, _ = self.view.root_widget.measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertLessEqual(minimum, 1366)

    def test_collector_does_not_draw_unverified_wan_as_link_up(self):
        # G06: carrier/config flags alone cannot verify the active collector presentation.
        self.view.store.devices['PC4']['wan_link_status'] = 'LINK_UP'
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 500)
        with patch('f3_network.draw_pango_text') as text:
            self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1200, 500)
        labels = [str(call.args[1]) for call in text.call_args_list]
        self.assertNotIn('✅ LINK UP', labels)
        self.assertIn('Local IPv4 UNKNOWN', labels)
        self.assertIn('NIC UNKNOWN · poller UNKNOWN', labels)
        self.assertEqual(self.view.runtime.active(), [])

    def test_identity_save_preserves_existing_network_configuration(self):
        existing = {"scada_lan": {"subnet": "127.0.0.0/8"},
                    "gateway_bridge": {"nic_scada": {"ip": "127.0.0.20"}}}
        config = self.view.store.config_file
        config.write_text(json.dumps(existing))
        self.view.store.update_device("PC1", {"alias": "Operator alias"})
        saved = json.loads(config.read_text())
        for key, value in existing.items():
            self.assertEqual(saved[key], value)
        self.assertIn("devices", saved)


if __name__ == "__main__":
    unittest.main()
