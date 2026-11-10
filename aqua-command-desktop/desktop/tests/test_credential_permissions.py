#!/usr/bin/env python3
"""
Test suite for SEC-02 Credential File Permissions.
Asserts atomic write with strict 0600 mode on sensitive configuration files.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertFalse(temp_file.exists(), "Temporary file must be cleaned up")


if __name__ == '__main__':
    unittest.main()
