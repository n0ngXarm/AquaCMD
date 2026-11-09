"""Verify that F3 details float above the unchanged main diagram."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f3_network
from gi.repository import Gtk, GLib


class TestF3DetailsWindow(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        local = {"interfaces": {}, "timestamp": "test", "ip_forwarding": False}
        patcher = patch("f3_network.safe_get_local_network_state", return_value=local)
        patcher.start()
        self.addCleanup(patcher.stop)
        from f3_fixture import configure_legacy_inventory
        configure_legacy_inventory(profile.name)
        owner = SimpleNamespace(config_dir=Path(profile.name), topology_data={})
        self.view = f3_network.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)
        self.window = Gtk.Window()
        self.window.set_default_size(1366, 768)
        self.window.set_child(self.view.root_widget)
        self.addCleanup(self.close_ui)
        self.window.present()
        self.spin()

    def spin(self):
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 0.12
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)

    def close_ui(self):
        # Release native toplevels and drain queued Wayland events before the next test.
        self.view.toggle_inspector(False)
        if self.view.details_window is not None:
            self.view.details_window.set_transient_for(None)
            self.view.details_window.destroy()
        self.window.destroy()
        self.spin()

    def popup(self):
        root = self.view.inspector.get_root()
        self.assertIsInstance(root, Gtk.Window)
        self.assertIsNot(root, self.window, "Details must use a separate window")
        return root

    def test_selection_opens_a_floating_owned_window(self):
        self.assertFalse(self.view.inspector.get_visible())
        self.view.select_device("PC1")
        self.spin()
        popup = self.popup()
        self.assertTrue(popup.get_visible())
        self.assertIs(popup.get_transient_for(), self.window)
        self.assertFalse(popup.get_modal())

    def test_opening_details_preserves_the_full_diagram_width(self):
        width = self.view.canvas.get_width()
        self.view.select_device("PC1")
        self.spin()
        self.assertEqual(self.view.canvas.get_width(), width)

    def test_reuses_closes_and_reopens_the_same_window(self):
        self.view.select_device("PC1")
        popup = self.popup()
        self.view.select_device("PC2")
        self.assertIs(self.popup(), popup)
        address = self.view.store.devices["PC2"]["configured_ip"]
        self.assertIn(address, popup.get_title())
        popup.close()
        self.spin()
        self.assertFalse(popup.get_visible())
        self.assertFalse(self.view.inspector.get_visible())
        self.view.btn_toggle_insp.emit("clicked")
        self.spin()
        self.assertIs(self.popup(), popup)
        self.assertTrue(popup.get_visible())

    def test_settings_are_owned_by_the_details_window(self):
        self.view.select_device("PC1")
        popup = self.popup()
        original = f3_network.DeviceSettingsDialog
        created = []
        def create(*args):
            dialog = original(*args)
            created.append(dialog)
            self.addCleanup(dialog.destroy)
            return dialog
        with patch("f3_network.DeviceSettingsDialog", side_effect=create):
            self.view.inspector._on_settings_clicked(None)
        self.spin()
        self.assertTrue(created[0].get_mapped())
        self.assertIs(created[0].get_transient_for(), popup)
        self.assertTrue(created[0].get_destroy_with_parent())

    def test_remote_confirmation_uses_the_popup_without_starting_a_probe(self):
        self.view.select_device("PC1")
        popup = self.popup()
        with patch("f3_network.OTAuthorizationDialog") as dialog, \
                patch("f3_network.RealDetectionEngine.detect_device_network") as probe:
            self.view.trigger_device_detect("PC1")
            self.assertIs(dialog.call_args.kwargs["parent_win"], popup)
            probe.assert_not_called()

    def test_closing_the_main_window_closes_its_popup(self):
        self.view.select_device("PC1")
        popup = self.popup()
        self.window.destroy()
        self.spin()
        self.assertFalse(popup.get_visible())


if __name__ == "__main__":
    unittest.main()
