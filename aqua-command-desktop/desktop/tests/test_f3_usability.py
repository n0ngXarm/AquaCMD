"""Native-widget checks for the operator's reported F3 usability failures."""
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cairo
import f3_network
from gi.repository import GLib, Gtk
from f3_reconciliation_fixture import assert_all_pages_fit
from gtk_wait import wait_for, wait_for_layout_stable


class TestF3Usability(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        local = {"interfaces": {}, "ip_forwarding": False, "timestamp": "test", "default_gateway": None}
        patcher = patch("f3_network.safe_get_local_network_state", return_value=local)
        patcher.start()
        self.addCleanup(patcher.stop)
        from f3_fixture import configure_legacy_inventory
        configure_legacy_inventory(profile.name)
        owner = SimpleNamespace(config_dir=Path(profile.name), topology_data={})
        self.view = f3_network.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)

    def spin(self):
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)

    def show_window(self):
        window = Gtk.Window()
        window.set_default_size(1366, 768)
        window.set_child(self.view.root_widget)
        self.addCleanup(window.destroy)
        window.present()
        self.spin()
        return window

    def test_startup_gives_the_diagram_full_attention(self):
        # G21: library dock is intentional; active F3 starts with its HTML dialog closed.
        self.assertEqual(self.view.stack.get_visible_child_name(), 'topology')
        self.assertIs(self.view.inspector.get_parent(), self.view.main_split)
        self.assertTrue(self.view.inspector.get_visible())
        self.assertIsNone(self.view.details_window)
        minimum, _, _, _ = self.view.root_widget.measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertLessEqual(minimum, 1366)

    def test_device_list_has_a_full_height_view(self):
        window = self.show_window()
        self.view.stack.set_visible_child_name("cards")
        cards_page = self.view.stack.get_child_by_name("cards")
        scroll = self.view.cards_grid.get_ancestor(Gtk.ScrolledWindow)

        def condition(sw):
            return cards_page.get_mapped() and sw.get_height() > 0

        wait_for_layout_stable(scroll, condition=condition, timeout=5.0, stable_cycles=2)
        self.assertIn("เลื่อนลง", self.view.guide.get_text())
        observed_height = scroll.get_height()
        min_expected = window.get_height() * 0.6
        self.assertGreaterEqual(
            observed_height,
            min_expected,
            f"Observed scroll height {observed_height}px < expected {min_expected}px (window={window.get_height()}px)",
        )

    def test_selected_device_details_do_not_take_half_the_screen(self):
        self.show_window()
        self.view.select_device("PC1")
        wait_for(self.view.inspector.get_mapped, timeout=5.0)
        self.assertTrue(self.view.inspector.get_mapped())
        self.assertLessEqual(self.view.inspector.get_width(), 400)

    def test_station_nodes_and_addresses_are_readable(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1000, 560)
        with patch("f3_network.draw_pango_text", wraps=f3_network.draw_pango_text) as text:
            self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1000, 560)
        _, _, width, height = self.view.canvas.node_rects["PC1"]
        self.assertGreaterEqual(width, 180)
        self.assertGreaterEqual(height, 80)
        address = self.view.store.devices["PC1"]["configured_ip"]
        address_calls = [call for call in text.call_args_list if call.args[1] == address]
        self.assertTrue(address_calls, "Unknown hostname must leave the complete configured address readable")
        self.assertGreaterEqual(float(re.findall(r"[\d.]+", address_calls[0].args[4])[-1]), 12)

    def test_live_actions_describe_the_implemented_capability(self):
        # G20: implemented secure actions remain disabled until actual readiness passes.
        from opcua_mapping import NodeIdMapper, TagMapping
        from opcua_pki import PkiManager
        self.view.select_device('PC1')
        inspector = self.view.inspector
        self.assertIn('Secure', inspector.btn_test_opc.get_label())
        self.assertFalse(inspector.btn_read_once.get_sensitive())
        self.assertIsNotNone(self.view.secure_opcua.readiness(
            self.view.store.devices['PC1'], self.view._opcua_options(self.view.store.devices['PC1']), require_mapping=True))
        self.view.secure_opcua.pki = PkiManager(Path(self.view.owner.config_dir) / 'pki')
        mapper = NodeIdMapper()
        self.view.secure_opcua.mapper = mapper
        self.view.store.update_device('PC1', {'sec_policy': 'Basic256Sha256', 'test_tag': 'LAB.Level'})
        self.view.select_device('PC1')
        self.assertTrue(inspector.btn_test_opc.get_sensitive())
        self.assertFalse(inspector.btn_read_once.get_sensitive())
        mapper.add_mapping(TagMapping('LAB.Level', 's=Exact.LAB.Level', 'urn:lab:only', verified=True))
        self.view.select_device('PC1')
        self.assertTrue(inspector.btn_read_once.get_sensitive())
        self.view.store.update_device('PC1', {'sec_policy': 'None'})
        self.view.select_device('PC1')
        self.assertFalse(inspector.btn_test_opc.get_sensitive())
        self.assertFalse(inspector.btn_read_once.get_sensitive())
        self.view._on_mode_toggle(None)
        demo_id = next(k for k, d in self.view.store.devices.items() if d['type'] == 'wincc')
        self.view.select_device(demo_id)
        self.assertTrue(inspector.btn_read_once.get_sensitive())

    def test_unobserved_internet_does_not_claim_online_or_offline(self):
        with patch.object(Path, "home", return_value=self.view.store.config_file.parent):
            import app
        owner = SimpleNamespace(
            live_status={"scada_carrier": False}, internet_online=None,
            pill_net=Gtk.Label(), alarm_text=Gtk.Label(),
            topology_canvas=MagicMock(), render_network_table=MagicMock())
        app.AquaWinCCWindow.apply_network_rescan_results(owner, None)
        self.assertIn("ยังไม่ได้ตรวจสอบ", owner.pill_net.get_text())
        self.assertNotIn("Offline", owner.pill_net.get_text())

    def test_default_stations_fit_a_shorter_operator_viewport(self):
        # G05: all configured sources remain reachable via pages; no ScrolledWindow assumption.
        window = self.show_window()
        window.set_default_size(1366, 650)
        self.spin()
        assert_all_pages_fit(self, self.view, self.view.canvas.get_width(), self.view.canvas.get_height())

    def test_list_explains_status_and_accounts_for_configured_devices(self):
        # G19: preserve UNKNOWN semantics and prohibit implicit-port service actions.
        self.assertEqual(len(self.view.cards), len(self.view.store.devices))
        summary = self.view.cards['PC1'].lbl_summary.get_text()
        self.assertIn('ยังไม่ได้ตรวจสอบ', summary)
        self.assertIn('UNKNOWN', summary)
        self.assertNotIn('Offline', summary)
        self.assertIsNone(self.view.store.devices['TELEGRAM']['port'])
        self.assertFalse(self.view.cards['TELEGRAM'].btn_detect.get_sensitive())
        self.view.store.update_device('TELEGRAM', {'configured_ip': '127.0.0.2', 'port': 443})
        self.view.select_device('TELEGRAM')
        self.assertTrue(self.view.inspector.btn_detect.get_sensitive())
        with patch('f3_network.OTAuthorizationDialog') as dialog, \
                patch('f3_network.RealDetectionEngine.detect_device_network') as adapter:
            self.view.trigger_device_detect('TELEGRAM')
            dialog.assert_called_once()
            adapter.assert_not_called()
        self.view.store.update_device('TELEGRAM', {'port': None})
        self.view.select_device('TELEGRAM')
        self.assertFalse(self.view.cards['TELEGRAM'].btn_detect.get_sensitive())
        self.assertFalse(self.view.inspector.btn_detect.get_sensitive())
        with patch('f3_network.OTAuthorizationDialog') as dialog, \
                patch('f3_network.RealDetectionEngine.detect_device_network') as adapter:
            self.view.trigger_device_detect('TELEGRAM')
            dialog.assert_not_called()
            adapter.assert_not_called()

    def test_device_outline_has_a_flat_bottom_and_rounded_corners(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 200)
        context = cairo.Context(surface)
        context.move_to(220, 180)
        f3_network.draw_rounded_rect(context, 10, 10, 100, 60, 8)
        _, _, right, bottom = context.stroke_extents()
        self.assertLessEqual(right, 111)
        self.assertLessEqual(bottom, 71)
        self.assertTrue(context.in_fill(60, 69), "A rounded rectangle must include its lower centre")
        self.assertFalse(context.in_fill(10.5, 69.5), "The lower left corner must remain rounded")


if __name__ == "__main__":
    unittest.main()
