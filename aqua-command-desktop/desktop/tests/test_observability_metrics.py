import unittest
from observability.contract import Contract
from observability.metrics import HostMetrics, rate


class MetricsTests(unittest.TestCase):
    def test_rate_warmup_reset_and_elapsed_time(self):
        self.assertIsNone(rate(10, None, 1))
        self.assertIsNone(rate(3, 10, 1))
        self.assertIsNone(rate(10, 5, 0))
        self.assertEqual(rate(20, 10, 2), 5)
        self.assertEqual(rate(10, 10, 1), 0)

    def test_real_host_first_cpu_and_rates_are_unknown(self):
        sampler = HostMetrics(Contract(b"k" * 32))
        first = sampler.sample()
        self.assertEqual(first["state"], "WARMING_UP")
        self.assertIsNone(first["cpu_percent"])
        self.assertIsNone(first["network_rx_bytes_per_sec"])
        self.assertGreater(first["memory_total_bytes"], 0)
        second = sampler.sample()
        self.assertEqual(second["state"], "AVAILABLE")
        self.assertGreaterEqual(second["cpu_percent"], 0)
        self.assertLessEqual(second["cpu_percent"], 100)
        self.assertGreater(second["process_rss_bytes"], 0)
        for row in second["interfaces"]:
            self.assertTrue(row["interface_id"].startswith("nic-"))
            self.assertIn(row["link_state"], ("UP", "DOWN", "UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
