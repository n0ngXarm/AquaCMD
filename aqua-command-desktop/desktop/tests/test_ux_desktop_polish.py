"""Presentation regressions on the real GTK4 window; no operational action is started."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gi.repository import Gdk, Gio, Gtk
import app
from ux_native_capture import wait, settle


class DesktopPolishTests(unittest.TestCase):
    application_index = 0
    def setUp(self):
        self.profile = tempfile.TemporaryDirectory(prefix='aqua-native-ux-unit-')
        self.addCleanup(self.profile.cleanup)
        self.directory = Path(self.profile.name)
        self.patches = [patch.object(app, 'CONFIG_DIR', self.directory),
                        patch.object(app, 'DEFAULT_WINCC_EXPORT', self.directory/'missing.txt')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        type(self).application_index += 1
        self.application = Gtk.Application(application_id=f'org.aqua.ux.unit{self.application_index}', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.application.register(None)
        self.window = app.AquaWinCCWindow(self.application)
        self.window.present()
        wait(self.window.get_mapped)
        self.addCleanup(self.close_window)

    def close_window(self):
        window = self.window
        if getattr(window, '_close_dialog', None):
            window._close_dialog.response(Gtk.ResponseType.CANCEL)
        # Cleanup after a test, not a user-initiated close action.
        window._close_confirmed = True
        window.on_close_request()
        window.unified_workspace.f1_api.web.terminate_web_process()
        window.destroy()
        self.application.quit()
        settle(.05)

    def test_f8_always_asks_even_when_idle_and_cancel_keeps_monitoring_resources(self):
        window = self.window
        self.assertEqual(window.polling_engine.get_telemetry()['state'], 'STOPPED')
        self.assertTrue(window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0))
        dialog = getattr(window, '_close_dialog', None)
        self.assertIsNotNone(dialog)
        wait(dialog.get_mapped)
        self.assertTrue(dialog.get_modal())
        self.assertEqual(dialog.get_default_widget(), dialog.get_widget_for_response(Gtk.ResponseType.CANCEL))
        self.assertFalse(window.f3_network_view.closed)
        window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0)
        self.assertIs(window._close_dialog, dialog)
        dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIsNone(window._close_dialog)
        self.assertTrue(window.get_visible())
        self.assertFalse(window.f3_network_view.closed)

    def test_normal_close_runs_original_cleanup_only_after_explicit_acceptance(self):
        window = self.window
        with patch.object(window.f3_network_view, 'close', wraps=window.f3_network_view.close) as close:
            window.close()
            dialog = getattr(window, '_close_dialog', None)
            self.assertIsNotNone(dialog)
            close.assert_not_called()
            dialog.response(Gtk.ResponseType.ACCEPT)
            close.assert_called_once_with()
        self.assertFalse(window.get_visible())
        self.assertTrue(window.f3_network_view.closed)


if __name__ == '__main__':
    unittest.main()
