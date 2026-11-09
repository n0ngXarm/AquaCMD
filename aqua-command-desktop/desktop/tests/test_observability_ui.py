import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gi.repository import Gtk
from observability.ui import DashboardUI
import app


class DashboardUITests(unittest.TestCase):
    def owner(self):
        stack = Gtk.Stack()
        stack.add_named(Gtk.Box(), "network")
        stack.add_named(Gtk.Box(), "tags")
        stack.set_visible_child_name("network")
        return SimpleNamespace(stack=stack, polling_engine=Mock(), notification_worker=Mock(),
            task_engine=Mock(), running=True, browse_cancel_flag=Mock())

    def test_disabled_integration_retains_native_navigation_without_browser(self):
        owner = self.owner()
        with patch("observability.ui.start_optional", return_value=None), patch("observability.ui.Gio.AppInfo.launch_default_for_uri") as launch:
            ui = DashboardUI(owner)
            self.assertFalse(ui.open())
            self.assertFalse(ui.menu.get_sensitive())
            self.assertEqual(owner.stack.get_visible_child_name(), "network")
            launch.assert_not_called()
            owner.polling_engine.assert_not_called()

    def test_context_link_and_tag_use_existing_bridge_only(self):
        owner = self.owner()
        bridge = Mock(state="AVAILABLE")
        bridge.link.return_value = "http://127.0.0.1:4567/d/aqua-f1?var-tag=opaque"
        with patch("observability.ui.start_optional", return_value=bridge), patch("observability.ui.Gio.AppInfo.launch_default_for_uri") as launch:
            ui = DashboardUI(owner)
            self.assertTrue(ui.open("tags", "selected-tag"))
            bridge.link.assert_called_once_with("tags", tag="selected-tag")
            launch.assert_called_once_with(bridge.link.return_value, None)
            self.assertEqual(owner.stack.get_visible_child_name(), "network")
            self.assertEqual(owner.polling_engine.mock_calls, [])
            self.assertEqual(owner.notification_worker.mock_calls, [])

    def test_browser_failure_does_not_change_or_stop_core(self):
        owner = self.owner()
        with patch("observability.ui.start_optional", return_value=Mock()), patch("observability.ui.Gio.AppInfo.launch_default_for_uri", side_effect=RuntimeError("private error")):
            ui = DashboardUI(owner)
            self.assertFalse(ui.open())
            self.assertEqual(ui.state, "BROWSER_UNAVAILABLE")
            self.assertEqual(owner.polling_engine.mock_calls, [])
            self.assertEqual(owner.stack.get_visible_child_name(), "network")

    def test_close_preserves_existing_lifecycle_and_only_stops_optional_bridge(self):
        owner = self.owner()
        owner.hybrid_ui = Mock()
        self.assertFalse(app.AquaWinCCWindow.on_close_request(owner))
        owner.hybrid_ui.stop.assert_called_once_with()
        owner.browse_cancel_flag.set.assert_called_once_with()
        self.assertFalse(owner.running)
        self.assertEqual(owner.polling_engine.mock_calls, [])
        self.assertEqual(owner.notification_worker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
