"""Regression coverage for the unfinished F3 identity and topology workflow."""
import sys
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
        self.view.store.update_device("PC1", {"alias": "Operator alias"})
        self.view._on_mode_toggle(None)
        self.view.store.devices["PC1"].update({
            "reachability": "REACHABLE", "opcua_state": OpcUaState.READ_VERIFIED,
            "last_read_value": 42, "last_read_quality": "Good (Demo)",
        })
        self.view._on_mode_toggle(None)
        device = self.view.store.devices["PC1"]
        self.assertEqual(device["alias"], "Operator alias")
        self.assertEqual(device["reachability"], "NOT_TESTED")
        self.assertEqual(device["opcua_state"], OpcUaState.NOT_TESTED)
        self.assertIsNone(device["last_read_value"])
        self.assertEqual(self.view.store.get_summary_stats()["opc_connected"], 0)

    def test_late_demo_callback_cannot_update_live_status(self):
        self.view._on_mode_toggle(None)
        with patch("f3_network.RealDetectionEngine.detect_opcua_session") as detect:
            self.view.trigger_device_opcua_test("PC1")
            callback = detect.call_args.args[2]
        self.view._on_mode_toggle(None)
        callback({"opcua_state": OpcUaState.CONNECTED, "session_state": "CONNECTED",
                  "security_status": "Demo", "last_error": None, "timestamp": "00:00:00"})
        self.assertNotEqual(self.view.store.devices["PC1"]["opcua_state"], OpcUaState.CONNECTED)
        self.assertEqual(self.view.store.get_summary_stats()["opc_connected"], 0)

    def test_remote_opcua_actions_require_existing_authorization_gate(self):
        actions = ((self.view.trigger_device_opcua_test, "detect_opcua_session"),
                   (self.view.trigger_device_read_once, "read_opcua_single_tag"))
        for action, engine_method in actions:
            with self.subTest(action=engine_method):
                with patch("f3_network.OTAuthorizationDialog") as dialog, \
                        patch("f3_network.RealDetectionEngine." + engine_method) as engine:
                    action("PC1")
                    dialog.assert_called_once()
                    engine.assert_not_called()
                    dialog.call_args.kwargs["on_authorized"]()
                    engine.assert_called_once()

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
        self.assertNotIn("Online", self.view.lbl_stat_wan.get_text())
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 500)
        with patch.object(self.view.canvas, "_draw_connection_line") as draw:
            self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1200, 500)
        self.assertEqual(draw.call_args_list[1].args[-1], ConnectionState.UNKNOWN)

    def test_verified_connections_render_and_animate(self):
        self.view.store.devices["PC1"]["opcua_state"] = OpcUaState.CONNECTED
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 500)
        context = cairo.Context(surface)
        self.view.canvas.on_draw(self.view.canvas, context, 1200, 500)
        surface.flush()
        first_frame = bytes(surface.get_data())
        self.view.canvas._on_anim_tick()
        self.view.canvas.on_draw(self.view.canvas, context, 1200, 500)
        surface.flush()
        self.assertNotEqual(first_frame, bytes(surface.get_data()))

    def test_layout_fits_1366_with_inspector_visible(self):
        self.view.select_device("dev-scada-01")
        minimum, _, _, _ = self.view.root_widget.measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertLessEqual(minimum, 1366)

    def test_collector_does_not_draw_unverified_wan_as_link_up(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 180)
        with patch("f3_network.draw_pango_text") as text:
            self.view.canvas._draw_pc4_node(
                cairo.Context(surface), 0, 0, 350, 130, self.view.store.devices["PC4"])
        labels = [call.args[1] for call in text.call_args_list]
        self.assertNotIn("✅ LINK UP", labels)
        self.assertIn("NOT VERIFIED", labels)

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
