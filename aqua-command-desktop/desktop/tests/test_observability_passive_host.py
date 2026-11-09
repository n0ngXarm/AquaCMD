import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


class PassiveHostTests(unittest.TestCase):
    def test_local_carrier_refresh_never_claims_scada_online(self):
        for carrier in (True, False):
            with self.subTest(carrier=carrier):
                owner = SimpleNamespace(live_status={"scada_carrier": carrier},
                    pill_scada_ip=app.Gtk.Label(), internet_online=None,
                    topology_canvas=SimpleNamespace(queue_draw=lambda: None), render_network_table=lambda: None)
                owner.update_local_nic_badge = lambda state: app.AquaWinCCWindow.update_local_nic_badge(owner, state)
                app.AquaWinCCWindow.apply_network_rescan_results(owner, None)
                self.assertIn("NIC", owner.pill_scada_ip.get_text())
                self.assertNotIn("SCADA", owner.pill_scada_ip.get_text())

    def test_host_metrics_does_not_connect_to_external_address_or_resolve_dns(self):
        with patch.object(app.socket, "socket") as constructor, patch.object(app.socket, "gethostbyname") as resolve:
            result = app.read_real_machine_data()
        constructor.assert_not_called()
        resolve.assert_not_called()
        self.assertIsInstance(result["ip_lan"], str)
        self.assertNotIn("Active Network", result["ip_lan"])


if __name__ == "__main__":
    unittest.main()
