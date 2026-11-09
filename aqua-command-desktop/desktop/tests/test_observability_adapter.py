import json
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from observability.adapter import OwnerProjection, graph
from observability.contract import Contract
from opcua_store import ObservableStateStore, TagObservation
from f3_evidence import record_evidence


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.endpoint = "opc.tcp://127.0.0.1:4840"
        self.contract = Contract(b"k" * 32)
        self.adapter = OwnerProjection(self.contract)
        self.owner = SimpleNamespace(opcua_store=ObservableStateStore(),
            entry_opc_url=SimpleNamespace(get_text=lambda: self.endpoint),
            polling_engine=SimpleNamespace(endpoint_url=self.endpoint, get_telemetry=lambda:
                {"state": "RUNNING", "successful_polls": 100, "last_error": "SECRET_ERROR"}),
            f3_network_view=SimpleNamespace(store=SimpleNamespace(is_demo_mode=False, devices={})),
            task_engine=Mock(), notification_worker=Mock())

    def test_poll_success_without_receipts_never_means_read_verified(self):
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertEqual(result["tags"], [])
        self.assertEqual(result["devices"][0]["connection_status"], "CONFIGURED")
        self.assertNotIn("SECRET_ERROR", json.dumps(result))
        self.assertEqual(self.owner.task_engine.mock_calls, [])
        self.assertEqual(self.owner.notification_worker.mock_calls, [])

    def test_existing_core_receipt_target_and_closed_session(self):
        self.owner.opcua_store.update_observation(TagObservation("PRIVATE_TAG", value=False, quality="GOOD",
            arrival_time=datetime.fromtimestamp(self.now, timezone.utc), endpoint_url=self.endpoint, session_state="CLOSED"))
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertIs(result["tags"][0]["value"], False)
        self.assertEqual(result["devices"][0]["connection_status"], "READ_VERIFIED")
        self.assertEqual(result["devices"][0]["session_state"], "CLOSED")
        changed = "opc.tcp://127.0.0.1:4841"
        self.owner.polling_engine.endpoint_url = changed
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertIsNone(result["tags"][0]["value"])
        self.assertEqual(result["devices"][0]["connection_status"], "CONFIGURED")

    def test_synthetic_inventory_and_ambiguous_endpoint_do_not_bind(self):
        store = self.owner.f3_network_view.store
        store.devices = {str(i): {"device_id": str(i), "endpoint_url": self.endpoint} for i in range(2)}
        self.owner.opcua_store.update_observation(TagObservation("PRIVATE_TAG", value=42, quality="GOOD",
            arrival_time=datetime.fromtimestamp(self.now, timezone.utc), endpoint_url=self.endpoint))
        self.assertIsNone(self.adapter.capture(self.owner, now=self.now)["tags"][0]["value"])
        store.is_demo_mode = True
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertTrue(result["synthetic_inventory_excluded"])
        self.assertEqual(len(result["devices"]), 1)  # existing shared runtime target only

    def test_dynamic_graph_has_valid_logical_edges_and_no_delivery_ack(self):
        store = self.owner.f3_network_view.store
        store.devices = {str(i): {"device_id": str(i), "endpoint_url": "opc.tcp://127.0.0.1:" + str(5000+i)} for i in range(40)}
        result = self.adapter.capture(self.owner, now=self.now)
        topology = graph(result["devices"], result["tags"], {"state": "AVAILABLE"}, self.now)
        ids = {n["id"] for n in topology["nodes"]}
        self.assertEqual(len(ids), 46)
        self.assertTrue(all(e["source"] in ids and e["target"] in ids for e in topology["edges"]))
        self.assertEqual(next(n for n in topology["nodes"] if n["id"] == "relay")["mainStat"], "UNVERIFIED")
        self.assertTrue(all("Logical" in e["detail__relation"] for e in topology["edges"]))

    def test_refresh_records_only_a_local_event(self):
        self.adapter.record_refresh(457, now=self.now)
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertFalse(result["refresh_events"][0]["network_probe"])
        self.assertEqual(result["tags"], [])

    def test_unknown_quality_is_unknown_instead_of_an_invented_error(self):
        self.owner.opcua_store.update_observation(TagObservation("PRIVATE_TAG", quality="NOT_OBSERVED",
            arrival_time=datetime.fromtimestamp(self.now, timezone.utc), endpoint_url=self.endpoint))
        result = self.adapter.capture(self.owner, now=self.now)
        self.assertEqual(result["devices"][0]["connection_status"], "UNKNOWN")

    def test_probe_history_uses_its_own_kind_result(self):
        dev = {"device_id": "source", "endpoint_url": self.endpoint, "configured_ip": "127.0.0.1",
            "tcp_ok": True, "read_success": True, "last_read_quality": "GOOD", "last_read_time": self.now}
        record_evidence(dev, "tcp", "OBSERVED_REMOTE", now=self.now - 1)
        record_evidence(dev, "read", "VERIFIED_OPCUA", now=self.now)
        self.owner.f3_network_view.store.devices = {"source": dev}
        result = self.adapter.capture(self.owner, now=self.now)
        tcp = next(row for row in result["probes"] if row["event_type"] == "TCP")
        self.assertEqual(tcp["status"], "TCP_CONNECTED")
        self.assertFalse(tcp["new_probe"])


if __name__ == "__main__":
    unittest.main()
