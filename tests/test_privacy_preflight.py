"""Repository guard uses index bytes and rejects private data under renamed files."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('privacy_preflight', Path(__file__).resolve().parents[1] / 'aqua-command-desktop/packaging/privacy_preflight.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PrivacyPreflightTests(unittest.TestCase):
    def test_credentials_are_blocked_without_returning_values(self):
        sentinel = '12345678' + ':' + 'X' * 35
        reasons = guard.check('renamed.txt', sentinel.encode(), None)
        self.assertIn('credential shape', reasons)
        self.assertNotIn(sentinel, str(reasons))

    def test_private_file_names_and_runtime_mapping_are_blocked(self):
        for name in ['Export all copy.txt', '.env', 'pwa.env', 'state.db', 'release.rpm', 'private.key', 'pump-status-tags.txt']:
            with self.subTest(name=name):
                self.assertTrue(guard.check(name, b'private data', None))
        self.assertTrue(guard.check('config/opcua_tag_mapping.json', b'{"mappings":{"LAB.Tag":{}}}', None))
        self.assertFalse(guard.check('config/opcua_tag_mapping.json', b'{"mappings":{}}', None))

    def test_private_names_are_detected_even_when_file_is_renamed(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / 'owner-catalog.txt'
            catalog.write_text('header\nheader\nheader\nPRIVATE_SYNTHETIC_TAG\tType\n')
            names = guard.private_names(catalog)
            reasons = guard.check('renamed-notes.md', b'Use PRIVATE_SYNTHETIC_TAG here', names)
            self.assertEqual(reasons, ['known private Tag'])
            self.assertEqual(guard.check('safe.md', b'Use PRIVATE_SYNTHETIC_TAG_LONGER here', names), [])

    def test_arbitrary_binary_cannot_hide_under_font_directory(self):
        self.assertTrue(guard.check('aqua-command-desktop/fonts/unreviewed.woff2', b'\xffPRIVATE', None))
        self.assertTrue(guard.check('aqua-command-desktop/fonts/IBMPlexMono-Regular.woff2', b'\xffPRIVATE', None))

    def test_reviewed_font_hashes_are_accepted(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / 'aqua-command-desktop/fonts').glob('*.woff2'):
            self.assertEqual(guard.check(path.relative_to(root).as_posix(), path.read_bytes(), None), [])

    def test_staged_guard_reads_staged_bytes_even_when_worktree_is_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            secret = '12345678' + ':' + 'X' * 35
            path = root / 'notes.md'
            path.write_text(secret)
            subprocess.run(['git', '-C', str(root), 'add', 'notes.md'], check=True)
            path.write_text('safe unstaged substitute')
            output = io.StringIO()
            with patch.object(guard, 'ROOT', root), contextlib.redirect_stdout(output):
                code = guard.main(['--staged'])
            self.assertEqual(code, 1)
            self.assertNotIn(secret, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())['findings'][0]['reasons'], ['credential shape'])

    def test_deleted_private_file_does_not_block_staged_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            path = root / '.env'
            path.write_text('KEY=value')
            subprocess.run(['git', '-C', str(root), 'add', '.env'], check=True)
            subprocess.run(['git', '-C', str(root), 'rm', '-q', '--cached', '.env'], check=True)
            with patch.object(guard, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(guard.main(['--staged']), 0)

    def test_staged_symlink_is_rejected_even_when_worktree_is_regular(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            path = root / 'notes.txt'
            path.symlink_to('private-input')
            subprocess.run(['git', '-C', str(root), 'add', 'notes.txt'], check=True)
            path.unlink()
            path.write_text('safe worktree substitute')
            output = io.StringIO()
            with patch.object(guard, 'ROOT', root), contextlib.redirect_stdout(output):
                self.assertEqual(guard.main(['--staged']), 1)
            self.assertIn('symlink requires separate review', output.getvalue())
