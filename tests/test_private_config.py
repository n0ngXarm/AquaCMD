"""Private profile permissions, load precedence, and real atomic-write rollback."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dotenv import dotenv_values
from src import private_config as storage


class PrivateStorageTests(unittest.TestCase):
    def test_unknown_values_round_trip_and_backup_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'legacy'
            original = b'CUSTOM="quote \\" slash \\\\ dollar ${KEEP}"\nEMPTY=\nFLAG\nMULTI="a\\nb"\n'
            source.write_bytes(original)
            path = root / 'private/pwa.env'
            storage.save_environment(path, {'TELEGRAM_BOT_TOKEN': 'synthetic-sentinel'}, source=source)
            values = dotenv_values(path, interpolate=False)
            expected = dotenv_values(stream=io.StringIO(original.decode()), interpolate=False)
            self.assertEqual({key: values[key] for key in expected}, expected)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(path.with_suffix('.env.bak').read_bytes(), original)
            self.assertEqual(path.with_suffix('.env.bak').stat().st_mode & 0o777, 0o600)

    def test_explicit_missing_profile_never_loads_legacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / 'legacy'
            legacy.write_text('PRIVATE_LOAD_SENTINEL=legacy\n')
            with patch.dict(os.environ, {'AQUACMD_ENV_FILE': str(root / 'missing')}, clear=True):
                _, selected = storage.load_environment(legacy)
                self.assertEqual(selected, root / 'missing')
                self.assertNotIn('PRIVATE_LOAD_SENTINEL', os.environ)

    def test_private_profile_precedes_legacy_but_not_process_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'pwa.env'
            private.write_text('PRIVATE_LOAD_SENTINEL=private\nKEEP_PROCESS=profile\n')
            private.chmod(0o600)
            legacy = root / 'legacy'
            legacy.write_text('PRIVATE_LOAD_SENTINEL=legacy\n')
            with patch.dict(os.environ, {'AQUACMD_ENV_FILE': str(private), 'KEEP_PROCESS': 'process'}, clear=True):
                self.assertEqual(storage.load_environment(legacy), (private, private))
                self.assertEqual(os.environ['PRIVATE_LOAD_SENTINEL'], 'private')
                self.assertEqual(os.environ['KEEP_PROCESS'], 'process')

    def test_symlink_file_and_backup_are_rejected_without_mutating_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'target'
            target.write_text('ORIGINAL=value\n')
            private = root / 'private/pwa.env'
            private.parent.mkdir()
            private.symlink_to(target)
            with self.assertRaises(PermissionError):
                storage.save_environment(private, {'KEY': 'new'})
            private.unlink()
            private.with_suffix('.env.bak').symlink_to(target)
            with self.assertRaises(PermissionError):
                storage.save_environment(private, {'KEY': 'new'}, source=target)
            self.assertEqual(target.read_text(), 'ORIGINAL=value\n')
            self.assertFalse(private.exists())

    def test_symlink_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'target'
            target.mkdir()
            (root / 'link').symlink_to(target, target_is_directory=True)
            with self.assertRaises(PermissionError):
                storage.save_environment(root / 'link/nested/pwa.env', {'KEY': 'value'})
            self.assertFalse((target / 'nested').exists())

    def test_insecure_private_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'pwa.env'
            path.write_text('KEY=value\n')
            path.chmod(0o644)
            with patch.dict(os.environ, {'AQUACMD_ENV_FILE': str(path)}, clear=True):
                with self.assertRaises(PermissionError):
                    storage.load_environment(Path(temporary) / 'legacy')

    def test_default_private_path_inside_repository_is_rejected(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path(storage.__file__).resolve().parents[1] / 'config')}, clear=True):
            with self.assertRaises(PermissionError):
                storage.private_env_path()

    def test_failed_replace_leaves_original_and_exact_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'private/pwa.env'
            storage.save_environment(path, {'KEY': 'old'})
            before = path.read_bytes()
            replace = os.replace
            def fail_final(source, destination):
                if Path(destination) == path:
                    raise OSError('synthetic write failure')
                return replace(source, destination)
            with patch.object(storage.os, 'replace', side_effect=fail_final):
                with self.assertRaises(storage.PrivateConfigSaveError) as caught:
                    storage.save_environment(path, {'KEY': 'new'})
            self.assertFalse(caught.exception.committed)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.with_suffix('.env.bak').read_bytes(), before)
            self.assertEqual(list(path.parent.glob('.pwa-*')), [])

    def test_failed_backup_stops_before_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'pwa.env'
            storage.save_environment(path, {'KEY': 'old'})
            before = path.read_bytes()
            with patch.object(storage.os, 'replace', side_effect=OSError('synthetic backup failure')):
                with self.assertRaises(storage.PrivateConfigSaveError):
                    storage.save_environment(path, {'KEY': 'new'})
            self.assertEqual(path.read_bytes(), before)

    def test_backup_can_restore_the_previous_profile_and_load_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'private/pwa.env'
            storage.save_environment(path, {'ROLLBACK_VALUE': 'old', 'CUSTOM_KEY': 'preserved'})
            before = path.read_bytes()
            storage.save_environment(path, {'ROLLBACK_VALUE': 'new'})
            storage._atomic_private_write(path, path.with_suffix('.env.bak').read_bytes())
            self.assertEqual(path.read_bytes(), before)
            with patch.dict(os.environ, {'AQUACMD_ENV_FILE': str(path)}, clear=True):
                storage.load_environment(Path(temporary) / 'legacy')
                self.assertEqual(os.environ['ROLLBACK_VALUE'], 'old')
                self.assertEqual(os.environ['CUSTOM_KEY'], 'preserved')

    def test_post_replace_directory_sync_failure_reports_committed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'pwa.env'
            sync = os.fsync
            count = 0
            def fail_directory(descriptor):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError('synthetic directory sync failure')
                return sync(descriptor)
            with patch.object(storage.os, 'fsync', side_effect=fail_directory):
                with self.assertRaises(storage.PrivateConfigSaveError) as caught:
                    storage.save_environment(path, {'KEY': 'new'})
            self.assertTrue(caught.exception.committed)
            self.assertEqual(dotenv_values(path)['KEY'], 'new')

    def test_newline_update_is_rejected_without_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'private/pwa.env'
            with self.assertRaises(ValueError):
                storage.save_environment(path, {'KEY': 'a\nb'})
            self.assertFalse(path.parent.exists())

    def test_real_non_tty_setup_refuses_echo_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = os.environ.copy()
            env.update(HOME=temporary, XDG_CONFIG_HOME=str(root / 'config'), AQUACMD_ENV_FILE=str(root / 'profile/pwa.env'))
            sentinel = 'synthetic-piped-credential'
            run = subprocess.run([sys.executable, '-B', 'main.py', 'setup'], input=sentinel + '\n', text=True, capture_output=True, env=env, cwd=Path(storage.__file__).resolve().parents[1], timeout=15, start_new_session=True)
            self.assertEqual(run.returncode, 1)
            self.assertNotIn(sentinel, run.stdout + run.stderr)
            self.assertFalse((root / 'profile/pwa.env').exists())
