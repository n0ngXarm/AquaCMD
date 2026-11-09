import json
import time
import unittest
from datetime import datetime, timezone

from observability.contract import Contract
from opcua_store import TagObservation


class PrivacyTests(unittest.TestCase):
    def test_unknown_session_metadata_cannot_export_a_raw_message(self):
        now = time.time()
        obs = TagObservation("private", value=42, quality="GOOD",
            arrival_time=datetime.fromtimestamp(now, timezone.utc),
            endpoint_url="opc.tcp://127.0.0.1:4840", session_state="SECRET_RAW_MESSAGE")
        result = Contract(b"k" * 32).tag(obs, {obs.endpoint_url: "source"}, now)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["session_state"], "UNKNOWN")

    def test_invalid_endpoint_never_binds_a_current_good_value(self):
        now = time.time()
        obs = TagObservation("private", value=42, quality="GOOD",
            arrival_time=datetime.fromtimestamp(now, timezone.utc), endpoint_url="not-an-endpoint")
        result = Contract(b"k" * 32).tag(obs, {obs.endpoint_url: "source"}, now)
        self.assertIsNone(result["value"])
        self.assertEqual(result["provenance"], "UNBOUND_LOCAL_RUNTIME")


if __name__ == "__main__":
    unittest.main()
