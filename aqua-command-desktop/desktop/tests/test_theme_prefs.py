"""Preference round-trip/fail-closed tests without GTK or operator profiles."""
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from theme_prefs import load_theme, save_theme
from theme_tokens import DEFAULT_THEME


class ThemePreferenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='aqua-native-ux-prefs-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def test_roundtrip_is_private_and_writes_only_the_preference(self):
        other = self.directory / 'other.json'
        other.write_text('{"preserve":"unchanged"}')
        original = other.read_bytes()
        self.assertEqual(load_theme(self.directory), DEFAULT_THEME)
        for mode in ('dark', 'light'):
            save_theme(self.directory, mode)
            path = self.directory / 'ui_prefs.json'
            self.assertEqual(load_theme(self.directory), mode)
            self.assertEqual(json.loads(path.read_text()), {'theme': mode})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(other.read_bytes(), original)
            self.assertEqual({p.name for p in self.directory.iterdir()}, {'ui_prefs.json', 'other.json'})

    def test_invalid_values_fall_back_without_rewriting_them(self):
        path = self.directory / 'ui_prefs.json'
        for raw in ('{', 'null', '[]', '"dark"', '{}', '{"theme":true}', '{"theme":[]}',
                    '{"theme":"system"}', '{"theme":"dark","extra":1}', ' ' * 129):
            with self.subTest(raw=raw):
                path.write_text(raw)
                self.assertEqual(load_theme(self.directory), DEFAULT_THEME)
                self.assertEqual(path.read_text(), raw)

    def test_symlink_is_not_followed(self):
        target = self.directory / 'other.json'
        target.write_text('{"theme":"dark"}')
        (self.directory / 'ui_prefs.json').symlink_to(target)
        self.assertEqual(load_theme(self.directory), DEFAULT_THEME)
        save_theme(self.directory, 'light')
        self.assertEqual(target.read_text(), '{"theme":"dark"}')
        self.assertFalse((self.directory / 'ui_prefs.json').is_symlink())

    def test_failed_atomic_replace_preserves_the_old_file_and_cleans_temp(self):
        save_theme(self.directory, 'light')
        original = (self.directory / 'ui_prefs.json').read_bytes()
        with patch('theme_prefs.os.replace', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                save_theme(self.directory, 'dark')
        self.assertEqual((self.directory / 'ui_prefs.json').read_bytes(), original)
        self.assertEqual([p.name for p in self.directory.iterdir()], ['ui_prefs.json'])


if __name__ == '__main__':
    unittest.main()
