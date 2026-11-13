"""Test icon availability and graceful text fallback when icon themes/SVGs are missing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, Gdk, Gtk
import app
from gtk_wait import pump_events


def iter_children(widget):
    child = widget.get_first_child()
    while child:
        yield child
        child = child.get_next_sibling()


def has_image_missing(widget):
    if isinstance(widget, Gtk.Image):
        paintable = widget.get_paintable()
        if paintable is not None and hasattr(paintable, 'get_file'):
            f = paintable.get_file()
            if f and 'image-missing' in (f.get_uri() or f.get_path() or ''):
                return True
        if widget.get_icon_name() == 'image-missing':
            return True
    child = widget.get_first_child()
    while child:
        if has_image_missing(child):
            return True
        child = child.get_next_sibling()
    return False


class IconFallbackTests(unittest.TestCase):
    serial = 0

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.patches = [
            patch.object(app, 'CONFIG_DIR', Path(self.dir.name)),
            patch.object(app, 'DEFAULT_WINCC_EXPORT', Path(self.dir.name) / 'absent.txt')
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        type(self).serial += 1
        self.app = Gtk.Application(application_id=f'org.aqua.icon.test{self.serial}', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self.window = app.AquaWinCCWindow(self.app)
        self.addCleanup(self.window.destroy)

    def test_normal_theme_uses_icons_when_available(self):
        window = self.window
        display = window.get_display()
        theme = Gtk.IconTheme.get_for_display(display)
        if not theme.has_icon('weather-clear-night-symbolic'):
            self.skipTest("System icon theme lacks weather-clear-night-symbolic")

        window._sync_theme_controls()
        pump_events()

        self.assertEqual(window.theme_button.get_icon_name(), 'weather-clear-night-symbolic')
        self.assertFalse(window.theme_button.get_label())

        self.assertEqual(window.help_button.get_icon_name(), 'help-browser-symbolic')
        self.assertFalse(window.help_button.get_label())

        for item, icon_name, label in window._status_items:
            images = [child for child in iter_children(item) if isinstance(child, Gtk.Image)]
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0].get_icon_name(), icon_name)

    def test_missing_icon_theme_degrades_gracefully_to_thai_labels_without_missing_image(self):
        window = self.window
        display = window.get_display()
        theme = Gtk.IconTheme.get_for_display(display)
        saved_paths = theme.get_search_path()
        with tempfile.TemporaryDirectory() as empty_dir:
            theme.set_search_path([empty_dir])
            try:
                window._sync_theme_controls()
                pump_events()

                # Theme button degrades to 'ธีม', accessible label & tooltip preserved
                self.assertEqual(window.theme_button.get_label(), 'ธีม')
                self.assertFalse(window.theme_button.get_icon_name())
                self.assertEqual(window.theme_button.get_tooltip_text(), 'สลับธีม (สว่าง/มืด)')

                # Help button degrades to 'ช่วย', accessible label & tooltip preserved
                self.assertEqual(window.help_button.get_label(), 'ช่วย')
                self.assertFalse(window.help_button.get_icon_name())
                self.assertEqual(window.help_button.get_tooltip_text(), 'คู่มือการใช้งาน · F9')

                # Network status icon (absent from minimal setup) is omitted, no image child
                net_item = [item for item, icon_name, _ in window._status_items if icon_name == 'network-transmit-receive-symbolic'][0]
                net_images = [child for child in iter_children(net_item) if isinstance(child, Gtk.Image)]
                self.assertEqual(len(net_images), 0, "Network status icon should be omitted when missing")

                # No widget renders an image-missing glyph
                self.assertFalse(has_image_missing(window))

                # Re-evaluation on theme change (Light <-> Dark)
                window.set_theme('dark')
                self.assertEqual(window.theme_button.get_label(), 'ธีม')
                self.assertFalse(window.theme_button.get_icon_name())
                self.assertFalse(has_image_missing(window))

                window.set_theme('light')
                self.assertEqual(window.theme_button.get_label(), 'ธีม')
                self.assertFalse(window.theme_button.get_icon_name())
                self.assertFalse(has_image_missing(window))
            finally:
                theme.set_search_path(saved_paths)
                window._sync_theme_controls()

        # When all icons are absent, all status icons are omitted
        with patch('app.is_icon_available', return_value=False):
            window._sync_theme_controls()
            pump_events()
            self.assertEqual(window.theme_button.get_label(), 'ธีม')
            self.assertEqual(window.help_button.get_label(), 'ช่วย')
            for item, icon_name, label in window._status_items:
                images = [child for child in iter_children(item) if isinstance(child, Gtk.Image)]
                self.assertEqual(len(images), 0, f"Status item for {icon_name} should omit icon")
                self.assertIn(label, list(iter_children(item)))

    def test_button_sizes_do_not_jump_beyond_2px(self):
        window = self.window
        display = window.get_display()
        theme = Gtk.IconTheme.get_for_display(display)
        saved_paths = theme.get_search_path()

        window._sync_theme_controls()
        pump_events()
        _, h_icon_theme, _, _ = window.theme_button.measure(Gtk.Orientation.VERTICAL, -1)
        _, h_icon_help, _, _ = window.help_button.measure(Gtk.Orientation.VERTICAL, -1)

        with tempfile.TemporaryDirectory() as empty_dir:
            theme.set_search_path([empty_dir])
            try:
                window._sync_theme_controls()
                pump_events()
                _, h_lbl_theme, _, _ = window.theme_button.measure(Gtk.Orientation.VERTICAL, -1)
                _, h_lbl_help, _, _ = window.help_button.measure(Gtk.Orientation.VERTICAL, -1)
                self.assertLessEqual(abs(h_icon_theme - h_lbl_theme), 2)
                self.assertLessEqual(abs(h_icon_help - h_lbl_help), 2)
            finally:
                theme.set_search_path(saved_paths)
                window._sync_theme_controls()


if __name__ == '__main__':
    unittest.main()
