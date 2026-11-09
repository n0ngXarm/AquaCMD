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
import cairo
import f3_network
from gi.repository import GLib, Gtk


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
        self.assertEqual(self.view.stack.get_visible_child_name(), "topology")
        self.assertFalse(self.view.inspector.get_visible(), "Details should open after device selection")

    def test_device_list_has_a_full_height_view(self):
        window = self.show_window()
        self.view.stack.set_visible_child_name("cards")
        self.spin()
        self.assertIn("เลื่อนลง", self.view.guide.get_text())
        scroll = self.view.cards_grid.get_ancestor(Gtk.ScrolledWindow)
        self.assertGreaterEqual(scroll.get_height(), window.get_height() * 0.6)

    def test_selected_device_details_do_not_take_half_the_screen(self):
        self.show_window()
        self.view.select_device("PC1")
        self.spin()
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
        self.view.select_device("PC1")
        self.assertIn("พอร์ต", self.view.inspector.btn_test_opc.get_label())
        self.assertFalse(self.view.inspector.btn_read_once.get_sensitive(), "F3 live single-tag read is unavailable")
        self.view._on_mode_toggle(None)
        self.assertTrue(self.view.inspector.btn_read_once.get_sensitive())

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
        window = self.show_window()
        scroll = self.view.canvas.get_ancestor(Gtk.ScrolledWindow)
        window.set_default_size(1366, window.get_height() - scroll.get_height() + 407)
        self.spin()
        for name in ("PC1", "PC2", "PC3"):
            _, y, _, height = self.view.canvas.node_rects[name]
            self.assertLessEqual(y + height, scroll.get_height(), name)

    def test_list_explains_status_and_accounts_for_configured_devices(self):
        self.assertEqual(len(self.view.cards), len(self.view.store.devices))
        self.assertEqual(self.view.cards["PC1"].lbl_summary.get_text(), "ยังไม่ได้ตรวจสอบ")
        self.assertFalse(self.view.cards["TELEGRAM"].btn_detect.get_sensitive())
        self.view.select_device("TELEGRAM")
        self.assertFalse(self.view.inspector.btn_detect.get_sensitive())

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
