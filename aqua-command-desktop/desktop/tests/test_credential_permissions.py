#!/usr/bin/env python3
"""
Test suite for SEC-02 Credential File Permissions.
Asserts atomic write with strict 0600 mode, randomized temp files,
symlink attack prevention, directory ownership validation, concurrent writes,
and crash recovery data preservation.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add desktop module to path
desktop_dir = Path(__file__).resolve().parent.parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from app import save_atomic_json, IS_WINDOWS


class TestCredentialFilePermissions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name) / "config_sub"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_atomic_json_enforces_0600_mode(self):
        """Verifies that save_atomic_json with mode=0o600 creates and replaces file with 0600 permissions."""
        if IS_WINDOWS:
            self.skipTest("POSIX file permission bits not applicable on Windows")

        test_file = self.target_dir / "secret_config.json"
        data = {"bot_token": "TEST_TOKEN_123", "chat_id": "9999"}

        success = save_atomic_json(test_file, data, mode=0o600)
        self.assertTrue(success, "Atomic save should return True")
        self.assertTrue(test_file.exists(), "Target file must exist after atomic save")

        # Check file mode
        file_mode = test_file.stat().st_mode & 0o777
        self.assertEqual(file_mode, 0o600, f"File permission must be exactly 0600, got {oct(file_mode)}")

        # Verify rewrite / replace preserves 0600
        data["updated"] = True
        success_update = save_atomic_json(test_file, data, mode=0o600)
        self.assertTrue(success_update)
        updated_mode = test_file.stat().st_mode & 0o777
        self.assertEqual(updated_mode, 0o600, f"Updated file permission must remain 0600, got {oct(updated_mode)}")

        # Verify no .tmp file left behind
        temp_file = test_file.with_suffix('.tmp')
        self.assertFalse(temp_file.exists(), "Fixed .tmp file must never exist")

    def test_randomized_temp_file_no_static_tmp(self):
        """Verifies that temporary files use random names and do not collide with static .tmp."""
        test_file = self.target_dir / "opcua_config.json"
        static_tmp = test_file.with_suffix(".tmp")
        # Pre-create a static .tmp file to simulate potential conflict
        self.target_dir.mkdir(parents=True, exist_ok=True)
        static_tmp.write_text("DO_NOT_OVERWRITE", encoding="utf-8")

        data = {"endpoint": "opc.tcp://127.0.0.1:4840", "policy": "Basic256Sha256"}
        success = save_atomic_json(test_file, data, mode=0o600)
        self.assertTrue(success)

        # Static .tmp file should remain untouched
        self.assertEqual(static_tmp.read_text(encoding="utf-8"), "DO_NOT_OVERWRITE")
        # Target file must have new content
        with open(test_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["endpoint"], "opc.tcp://127.0.0.1:4840")

        # Verify no stray randomized temp files in directory
        all_tmp = list(self.target_dir.glob(".*.tmp"))
        self.assertEqual(len(all_tmp), 0, "All randomized temp files must be cleaned up")

    def test_symlink_target_rejected_fail_closed(self):
        """Negative test: Attempting to overwrite a symlinked target file must fail closed with PermissionError."""
        if IS_WINDOWS:
            self.skipTest("Symlinks test applies to POSIX")

        self.target_dir.mkdir(parents=True, exist_ok=True)
        victim_file = self.target_dir / "sensitive_target.txt"
        victim_file.write_text("SENSITIVE_ORIGINAL_CONTENT", encoding="utf-8")

        symlink_file = self.target_dir / "attack_link.json"
        symlink_file.symlink_to(victim_file)

        with self.assertRaises(PermissionError) as ctx:
            save_atomic_json(symlink_file, {"evil": "payload"}, mode=0o600)

        self.assertIn("symlink", str(ctx.exception).lower())
        # Verify victim file was not overwritten
        self.assertEqual(victim_file.read_text(encoding="utf-8"), "SENSITIVE_ORIGINAL_CONTENT")

    def test_directory_ownership_mismatch_fails_closed(self):
        """Negative test: Directory not owned by current user must fail closed with PermissionError."""
        if IS_WINDOWS:
            self.skipTest("Ownership checks apply to POSIX")

        test_file = self.target_dir / "creds.json"
        self.target_dir.mkdir(parents=True, exist_ok=True)

        fake_stat = MagicMock()
        fake_stat.st_uid = os.getuid() + 999  # Different UID

        with patch.object(Path, "stat", return_value=fake_stat):
            with self.assertRaises(PermissionError) as ctx:
                save_atomic_json(test_file, {"data": 123}, mode=0o600)
            self.assertIn("ownership mismatch", str(ctx.exception).lower())

    def test_crash_recovery_preserves_existing_data(self):
        """Verifies that a failure during data dump aborts atomically and preserves the existing file intact."""
        test_file = self.target_dir / "resilient.json"
        original_data = {"version": 1, "status": "ORIGINAL_SAFE"}
        save_atomic_json(test_file, original_data, mode=0o600)

        # Simulate crash/failure during JSON dump of update
        with patch("json.dump", side_effect=IOError("Simulated disk error")):
            with self.assertRaises(IOError):
                save_atomic_json(test_file, {"version": 2, "status": "CORRUPTED"}, mode=0o600)

        # Verify original file content is 100% intact
        with open(test_file, "r", encoding="utf-8") as f:
            content = json.load(f)
        self.assertEqual(content["status"], "ORIGINAL_SAFE")
        self.assertEqual(content["version"], 1)

        # Verify no orphaned temp files
        all_tmp = list(self.target_dir.glob(".*.tmp"))
        self.assertEqual(len(all_tmp), 0)

    def test_post_replace_verification_fails_closed(self):
        """Negative test: If post-replace file mode cannot be verified to match requested mode, fail-closed and purge."""
        if IS_WINDOWS:
            self.skipTest("POSIX mode tests")

        test_file = self.target_dir / "mode_fail.json"
        fake_bad_stat = MagicMock()
        fake_bad_stat.st_uid = os.getuid()
        fake_bad_stat.st_mode = 0o666  # Insecure mode leaked

        # Ensure target_dir exists and has correct stat
        self.target_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(Path, "stat", return_value=fake_bad_stat):
            with patch("os.chmod"):
                with self.assertRaises(PermissionError) as ctx:
                    save_atomic_json(test_file, {"sensitive": True}, mode=0o600)
                self.assertIn("SEC-02", str(ctx.exception))
                self.assertIn("unlinked", str(ctx.exception).lower())

    def test_parent_directory_fsync_called_on_posix(self):
        """Verifies that parent directory fsync is invoked to persist directory entries on POSIX."""
        if IS_WINDOWS:
            self.skipTest("POSIX directory fsync")

        test_file = self.target_dir / "fsync_test.json"
        data = {"key": "durable_value"}

        fsync_fds = []
        real_fsync = os.fsync

        def mock_fsync(fd):
            fsync_fds.append(fd)
            return real_fsync(fd)

        with patch("os.fsync", side_effect=mock_fsync):
            success = save_atomic_json(test_file, data, mode=0o600)
            self.assertTrue(success)

        # Must have fsynced at least twice: once for temp file fd, once for parent dir fd
        self.assertGreaterEqual(len(fsync_fds), 2, f"Expected at least 2 fsync calls (file + dir), got {len(fsync_fds)}")

    def test_symlink_directory_unowned_fails_closed(self):
        """Negative test: Parent directory symlink pointing to an unowned path fails closed."""
        if IS_WINDOWS:
            self.skipTest("Symlink directory test applies to POSIX")

        self.target_dir.mkdir(parents=True, exist_ok=True)
        test_file = self.target_dir / "symdir_test.json"

        # Mock parent_dir.is_symlink to return True and resolve().stat().st_uid to mismatch
        mock_resolved = MagicMock()
        mock_resolved.stat.return_value.st_uid = os.getuid() + 999

        with patch.object(Path, "is_symlink", return_value=True):
            with patch.object(Path, "resolve", return_value=mock_resolved):
                with self.assertRaises(PermissionError) as ctx:
                    save_atomic_json(test_file, {"data": 1}, mode=0o600)
                self.assertIn("SEC-02", str(ctx.exception))
                self.assertIn("unowned target", str(ctx.exception))

    def test_concurrent_writes(self):
        """Verifies that concurrent writes across threads succeed without corruption or race condition collisions."""
        test_file = self.target_dir / "concurrent.json"
        errors = []

        def worker(thread_id):
            try:
                for i in range(10):
                    data = {"thread_id": thread_id, "iter": i}
                    save_atomic_json(test_file, data, mode=0o600)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent writes produced errors: {errors}")
        self.assertTrue(test_file.exists())
        with open(test_file, "r", encoding="utf-8") as f:
            final_data = json.load(f)
        self.assertIn("thread_id", final_data)


if __name__ == '__main__':
    unittest.main()
