import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from observability.integration import start_optional, local_url
from opcua_store import ObservableStateStore


class IntegrationTests(unittest.TestCase):
    def test_default_disabled_has_no_owner_calls_or_socket(self):
        owner = Mock()
        with patch("socket.socket", side_effect=AssertionError("No socket when disabled")):
            self.assertIsNone(start_optional(owner, environment={}))
        self.assertEqual(owner.mock_calls, [])

    def test_external_credential_and_path_urls_are_rejected(self):
        for url in ("http://192.0.2.10:3000", "http://user:pass@127.0.0.1:3000", "https://example.invalid:443",
                    "http://127.0.0.1:3000/path", "http://127.0.0.1:3000?token=secret"):
            with self.assertRaises(ValueError):
                local_url(url)
        self.assertEqual(local_url("http://127.0.0.1:3000/"), "http://127.0.0.1:3000")

    def test_bad_config_and_socket_collision_do_not_escape_into_owner(self):
        with tempfile.TemporaryDirectory(prefix="aqua-optin-") as folder:
            config = Path(folder) / "config.json"
            config.write_text("invalid-json")
            config.chmod(0o600)
            owner = Mock()
            self.assertIsNone(start_optional(owner, environment={"AQUA_OBSERVABILITY_CONFIG": str(config)}))
            self.assertEqual(owner.mock_calls, [])

    def test_enabled_uses_same_owner_and_hashed_deeplink(self):
        with tempfile.TemporaryDirectory(prefix="aqua-optin-") as folder:
            root = Path(folder)
            for name, data in (("key", b"k" * 32), ("token", b"t" * 40)):
                (root / name).write_bytes(data)
                (root / name).chmod(0o600)
            settings = {"enabled": True, "grafana_url": "http://127.0.0.1:3000", "id_key_file": str(root / "key"),
                        "projection_token_file": str(root / "token"), "socket_path": str(root / "bridge.sock")}
            config = root / "config.json"
            config.write_text(json.dumps(settings))
            config.chmod(0o600)
            owner = SimpleNamespace(opcua_store=ObservableStateStore(), durable_storage=SimpleNamespace(db_path=root / "absent.db"),
                polling_engine=SimpleNamespace(endpoint_url="", get_telemetry=lambda: {"state": "STOPPED"}))
            scheduler = Mock(return_value=None)
            bridge = start_optional(owner, environment={"AQUA_OBSERVABILITY_CONFIG": str(config)}, scheduler=scheduler)
            self.assertIsNotNone(bridge)
            try:
                self.assertIs(bridge.owner, owner)
                self.assertEqual(bridge.state, "AVAILABLE")
                self.assertEqual(scheduler.call_count, 1)
                link = bridge.link("tags", "PRIVATE_TAG")
                self.assertNotIn("PRIVATE_TAG", link)
                self.assertIn("/d/aqua-f1", link)
                self.assertIn("var-tag=tag-", link)
                collision = start_optional(owner, environment={"AQUA_OBSERVABILITY_CONFIG": str(config)}, scheduler=scheduler)
                self.assertIsNone(collision)
                self.assertEqual(bridge.state, "AVAILABLE")
            finally:
                bridge.stop()
            self.assertFalse((root / "bridge.sock").exists())
            self.assertFalse((root / "absent.db").exists())


if __name__ == "__main__":
    unittest.main()
