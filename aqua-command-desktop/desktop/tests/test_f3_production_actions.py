"""Manual F3 controller receipts, exact targets, and late callback rejection."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f3_network as f3
from gi.repository import GLib


class TestF3ProductionActions(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        directory = Path(profile.name)
        (directory / "network_topology.json").write_text(json.dumps({"devices": [{
            "device_id": "source", "type": "wincc", "configured_ip": "127.0.0.1", "port": 49327,
            "endpoint_url": "opc.tcp://127.0.0.1:49327", "test_tag": "LAB.Level"}]}))
        self.owner = SimpleNamespace(config_dir=directory, topology_data={},
            opcua_config={"endpoint_url": "opc.tcp://127.0.0.2:49327", "security_policy": "Basic256Sha256", "auth_mode": "Username", "username": "secret-user"},
            opcua_session_password="private-password")
        with patch("f3_network.safe_get_local_network_state", return_value={"interfaces": {}}):
            self.view = f3.F3NetworkTopologyView(self.owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)
        self.dev = self.view.store.devices["source"]

    def drain(self):
        for _ in range(100):
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            if not self.view._remote_busy:
                return
            time.sleep(0.01)
        self.fail("F3 worker did not finish")

    def test_credentials_are_never_borrowed_from_another_endpoint(self):
        options = self.view._opcua_options(self.dev)
        self.assertNotIn("password", options)
        self.assertNotIn("username", options)
        self.assertNotEqual(options.get("sec_policy"), "Basic256Sha256")

    def test_missing_network_target_cannot_be_probed_or_classified_unreachable(self):
        self.view.store.update_device("source", {"configured_ip": ""})
        with patch("f3_network.OTAuthorizationDialog") as authorization, \
                patch("f3_network.RealDetectionEngine.detect_device_network") as probe:
            self.view.trigger_device_detect("source")
        authorization.assert_not_called()
        probe.assert_not_called()
        self.assertEqual(self.view.store.devices["source"]["reachability"], "NOT_TESTED")
        self.assertFalse(self.view.cards["source"].btn_detect.get_sensitive())

    def test_actual_read_receipt_keeps_manual_session_disconnected(self):
        receipt = {"session_state": "DISCONNECTED", "opcua_state": "READ_VERIFIED", "read_success": True,
                   "session_verified": True, "certificate_trust": "TRUSTED", "value": 42.5,
                   "quality": "GOOD", "timestamp": "2026-11-05T00:00:00+00:00", "source_timestamp": "source-time"}
        with patch.object(self.view.secure_opcua, "read_sync", return_value=receipt) as read:
            self.view._execute_read_once(self.dev)
            self.drain()
        self.assertEqual(read.call_count, 1)
        self.assertTrue(f3.evidence.read_verified(self.dev))
        self.assertFalse(f3.evidence.session_connected(self.dev))
        self.assertEqual(self.dev["last_read_value"], 42.5)
        self.assertEqual(self.dev["source_timestamp"], "source-time")
        self.assertEqual(self.view.runtime.active(), [])

    def test_changed_target_discards_pending_worker_result(self):
        import threading
        released = threading.Event()
        self.addCleanup(released.set)
        def delayed(*_):
            released.wait(1)
            return {"read_success": True, "session_state": "DISCONNECTED", "value": 42.5, "quality": "GOOD"}
        with patch.object(self.view.secure_opcua, "read_sync", side_effect=delayed):
            self.view._execute_read_once(self.dev)
            self.view.store.update_device("source", {"endpoint_url": "opc.tcp://127.0.0.2:49327"})
            released.set()
            self.drain()
        self.assertIsNone(self.view.store.devices["source"]["last_read_value"])
        self.assertFalse(f3.evidence.read_verified(self.view.store.devices["source"]))


if __name__ == "__main__":
    unittest.main()
