"""Historical test IDs retained: current dock ownership; active WebKit lifecycle has separate coverage."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import f3_network
from gi.repository import Gtk, GLib
from gtk_wait import wait_for


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
        self.assertIs(root, self.window, "Docked details must belong to the real owner")
        self.assertIs(self.view.inspector.get_parent(), self.view.main_split)
        self.assertIsNone(self.view.details_window)
        return root

    def test_selection_opens_a_floating_owned_window(self):
        # G13: current library docks details; no second native window is created.
        self.assertTrue(self.view.inspector.get_visible())
        self.view.select_device('PC1')
        wait_for(self.view.inspector.get_mapped, timeout=5.0)
        self.assertIs(self.popup(), self.window)
        self.assertTrue(self.view.inspector.get_mapped())
        self.assertEqual(self.view.inspector.current_device_id, 'PC1')
        self.assertFalse(self.window.get_modal())

    def test_opening_details_preserves_the_full_diagram_width(self):
        width = self.view.canvas.get_width()
        self.view.select_device("PC1")
        self.spin()
        self.assertEqual(self.view.canvas.get_width(), width)

    def test_reuses_closes_and_reopens_the_same_window(self):
        # G12: reuse the dock; HTML dialog close/reopen/focus is tested in the active view.
        self.view.select_device('PC1')
        inspector = self.view.inspector
        self.view.select_device('PC2')
        self.assertIs(self.view.inspector, inspector)
        self.assertIs(self.popup(), self.window)
        self.assertEqual(inspector.current_device_id, 'PC2')
        self.assertIn(self.view.store.devices['PC2']['configured_ip'], inspector.lbl_disp_name.get_text())
        self.view.toggle_inspector(False)
        wait_for(lambda: not self.view.inspector.get_visible(), timeout=5.0)
        self.assertFalse(inspector.get_visible())
        self.view.btn_toggle_insp.emit('clicked')
        wait_for(self.view.inspector.get_mapped, timeout=5.0)
        self.assertIs(self.view.inspector, inspector)
        self.assertTrue(inspector.get_mapped())

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
        wait_for(lambda: created and created[0].get_mapped(), timeout=5.0)
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
        # G10: no orphan dock after owner destruction; listener teardown is covered separately.
        self.view.select_device('PC1')
        self.assertIs(self.popup(), self.window)
        self.window.destroy()
        wait_for(lambda: not self.view.inspector.get_mapped(), timeout=5.0)
        self.assertFalse(self.view.inspector.get_mapped())
        self.assertIsNone(self.view.details_window)


if __name__ == "__main__":
    unittest.main()
