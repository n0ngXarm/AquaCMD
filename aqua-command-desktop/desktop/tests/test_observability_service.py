import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from observability.contract import Contract, iso
from observability.service import ProjectionService
from test_observability_transport import UnixConnection


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aqua-bridge-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "bridge.sock"
        self.now = time.time()
        self.history = SimpleNamespace(read=lambda *args: {"state": "NO_DATA", "observations": [], "events": [], "outbox": [], "attempts": []})
        self.service = ProjectionService(self.path, "k" * 40, Contract(b"x" * 32), self.history)

    def snapshot(self):
        return {"captured_at": iso(self.now), "state": "AVAILABLE", "stream": "RUNTIME",
            "devices": [{"device_id": "device-1", "alias": "Device 1", "kind": "OPC_UA_SOURCE", "connection_status": "READ_VERIFIED",
                         "data_quality": "GOOD", "session_state": "CONNECTED", "tcp_status": "TCP_CONNECTED", "certificate_status": "TRUSTED",
                         "provenance": "VERIFIED_OPCUA", "observed_at": iso(self.now), "target_ref": "target-1"}],
            "tags": [{"quality": "GOOD", "value": 42, "session_state": "CONNECTED"}],
            "worker": {"state": "RUNNING"}, "probes": [], "refresh_events": []}

    def test_frozen_owner_cannot_keep_live_values_or_green_graph(self):
        snapshot = self.snapshot()
        self.service.publish(snapshot)
        snapshot["tags"][0]["value"] = 999
        self.assertEqual(self.service.current(now=self.now)["tags"][0]["value"], 42)
        stale = self.service.current(now=self.now + 16)
        self.assertEqual(stale["state"], "STALE")
        self.assertIsNone(stale["tags"][0]["value"])
        self.assertEqual(stale["devices"][0]["session_state"], "UNKNOWN")
        with patch("observability.service.time.time", return_value=self.now + 16):
            topology = self.service.payload("/v1/runtime/graph", {})
        self.assertTrue(all(row["mainStat"] == "STALE" for row in topology["nodes"]))
        self.assertTrue(all(row["display_state"] == "STALE" for row in topology["nodes"]))
        collector = next(row for row in topology["nodes"] if row["id"] == "collector")
        self.assertEqual(collector["detail__observed_at"], iso(self.now))

    def test_authenticated_unix_service_start_collision_and_owned_cleanup(self):
        self.service.publish(self.snapshot())
        self.service.start()
        self.addCleanup(self.service.stop)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        connection = UnixConnection(self.path)
        self.addCleanup(connection.close)
        connection.request("GET", "/v1/runtime/tags", headers={"Authorization": "Bearer " + "k" * 40})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["data"][0]["value"], 42)
        collision = ProjectionService(self.path, "z" * 40, self.service.contract, self.history)
        with self.assertRaises(FileExistsError):
            collision.start()
        collision.stop()
        self.assertTrue(self.path.exists())

    def test_fresh_owner_cannot_refresh_an_old_individual_read(self):
        snapshot = self.snapshot()
        snapshot["captured_at"] = iso(self.now + 10)
        snapshot["tags"][0].update(arrival_timestamp=iso(self.now), source_timestamp=iso(self.now))
        self.service.publish(snapshot)
        current = self.service.current(now=self.now + 16)
        self.assertEqual(current["state"], "AVAILABLE")
        self.assertEqual(current["tags"][0]["quality"], "STALE")
        self.assertIsNone(current["tags"][0]["value"])
        self.assertEqual(current["devices"][0]["connection_status"], "STALE")

    def test_missing_data_and_synthetic_routes_fail_closed(self):
        self.assertEqual(self.service.payload("/v1/runtime/graph", {})["nodes"], [])
        self.assertEqual(self.service.payload("/v1/runtime/tags", {})["data"], [])
        with self.assertRaises(KeyError):
            self.service.payload("/v1/synthetic/tags", {})
        os.chmod(self.path.parent, 0o755)
        with self.assertRaises(PermissionError):
            self.service.start()


if __name__ == "__main__":
    unittest.main()
