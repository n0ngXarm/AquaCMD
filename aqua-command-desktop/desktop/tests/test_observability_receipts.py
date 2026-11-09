"""Optional observability must use actual receipts, without changing read semantics."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from opcua_store import ObservableStateStore, TagObservation, Quality


class ReceiptTests(unittest.TestCase):
    def test_snapshot_does_not_expose_mutable_store_entries(self):
        store = ObservableStateStore()
        obs = TagObservation("private-tag", value=False, quality=Quality.GOOD)
        store.update_observation(obs)
        snapshot = store.snapshot_observations()
        self.assertEqual(len(snapshot), 1)
        snapshot[0].quality = Quality.BAD
        self.assertEqual(store.get_observation("private-tag").quality, Quality.GOOD)

    def test_actual_datavalue_retains_target_and_closed_manual_session(self):
        store = ObservableStateStore()
        now = datetime.now(timezone.utc)
        dv = SimpleNamespace(StatusCode=SimpleNamespace(is_good=lambda: True,
                             is_bad=lambda: False, name="Good"),
                             Value=SimpleNamespace(Value=0), SourceTimestamp=now)
        obs = store.update_from_datavalue("private-tag", "s=private", dv,
                   endpoint_url="opc.tcp://127.0.0.1:4840", session_state="CLOSED")
        self.assertEqual(obs.value, 0)
        self.assertEqual(obs.quality, Quality.GOOD)
        self.assertEqual(obs.endpoint_url, "opc.tcp://127.0.0.1:4840")
        self.assertEqual(obs.session_state, "CLOSED")

    def test_old_callers_remain_unbound(self):
        obs = TagObservation("old-caller", quality=Quality.GOOD, value=False)
        self.assertIsNone(obs.endpoint_url)
        self.assertEqual(obs.session_state, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
