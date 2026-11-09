import json
import unittest
from datetime import datetime, timezone

from observability.contract import Contract
from opcua_store import TagObservation
import f3_evidence as evidence


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).timestamp()
        self.contract = Contract(b"x" * 32)
        self.dev = {"device_id": "private-device", "configured_ip": "192.0.2.10",
                    "hostname": "private-host", "endpoint_url": "opc.tcp://192.0.2.10:4840",
                    "alias": "private-plant", "tcp_ok": True, "session_state": "CONNECTED",
                    "read_success": True, "last_read_quality": "GOOD"}

    def test_configuration_and_raw_flags_do_not_prove_connection(self):
        row = self.contract.device(self.dev, self.now)
        self.assertEqual(row["connection_status"], "CONFIGURED")
        self.assertEqual(row["session_state"], "UNKNOWN")

    def test_tcp_does_not_prove_opcua_and_target_change_invalidates(self):
        evidence.record_evidence(self.dev, "tcp", evidence.Provenance.REMOTE, now=self.now)
        row = self.contract.device(self.dev, self.now)
        self.assertEqual(row["connection_status"], "TCP_CONNECTED")
        self.assertEqual(row["session_state"], "UNKNOWN")
        self.dev["configured_ip"] = "192.0.2.11"
        self.assertEqual(self.contract.device(self.dev, self.now)["connection_status"], "STALE")

    def test_read_and_closed_manual_session_are_distinct(self):
        for kind in ("read", "session"):
            evidence.record_evidence(self.dev, kind, evidence.Provenance.OPCUA, now=self.now)
        self.dev["session_state"] = "CLOSED"
        row = self.contract.device(self.dev, self.now)
        self.assertEqual(row["connection_status"], "READ_VERIFIED")
        self.assertEqual(row["session_state"], "CLOSED")
        self.assertEqual(self.contract.device(self.dev, self.now + 16)["connection_status"], "STALE")

    def test_synthetic_and_private_fields_do_not_enter_runtime(self):
        self.dev.update(is_demo=True, password="VERY_SECRET", raw_status="VERY_SECRET")
        evidence.record_evidence(self.dev, "read", evidence.Provenance.DEMO, now=self.now)
        row = self.contract.device(self.dev, self.now)
        self.assertNotEqual(row["connection_status"], "READ_VERIFIED")
        text = json.dumps(row)
        for private in ("192.0.2.10", "private-host", "private-device", "private-plant", "VERY_SECRET"):
            self.assertNotIn(private, text)

    def test_bad_unknown_stale_unbound_and_good_zero_false(self):
        now = datetime.fromtimestamp(self.now, timezone.utc)
        targets = {self.dev["endpoint_url"]: self.dev["device_id"]}
        for value in (0, False):
            obs = TagObservation("private-tag", value=value, quality="GOOD", arrival_time=now,
                                 endpoint_url=self.dev["endpoint_url"])
            row = self.contract.tag(obs, targets, self.now)
            self.assertIs(type(row["value"]), type(value))
            self.assertEqual(row["value"], value)
            for q in ("BAD", "NOT_OBSERVED", "DISCONNECTED", "UNCERTAIN"):
                obs.quality = q
                self.assertIsNone(self.contract.tag(obs, targets, self.now)["value"])
            obs.quality = "GOOD"
            self.assertIsNone(self.contract.tag(obs, targets, self.now + 16)["value"])
            self.assertIsNone(self.contract.tag(obs, {}, self.now)["value"])

    def test_future_timestamp_and_nonfinite_payload_fail_closed(self):
        future = datetime.fromtimestamp(self.now + 60, timezone.utc)
        obs = TagObservation("tag", value=float("nan"), quality="GOOD", arrival_time=future,
                             endpoint_url=self.dev["endpoint_url"])
        row = self.contract.tag(obs, {self.dev["endpoint_url"]: self.dev["device_id"]}, self.now)
        self.assertIsNone(row["value"])
        self.assertEqual(row["quality"], "STALE")
        self.assertNotIn("NaN", json.dumps(row, allow_nan=False))

    def test_invalid_evidence_or_missing_endpoint_cannot_verify_read(self):
        evidence.record_evidence(self.dev, "read", evidence.Provenance.OPCUA, now=float("nan"))
        self.assertNotEqual(self.contract.device(self.dev, self.now)["connection_status"], "READ_VERIFIED")
        self.dev["endpoint_url"] = ""
        evidence.record_evidence(self.dev, "read", evidence.Provenance.OPCUA, now=self.now)
        self.assertNotEqual(self.contract.device(self.dev, self.now)["connection_status"], "READ_VERIFIED")


if __name__ == "__main__":
    unittest.main()
