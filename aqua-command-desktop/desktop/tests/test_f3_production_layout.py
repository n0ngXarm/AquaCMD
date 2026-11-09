"""Automatic native flow geometry and truthful evidence rendering."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f3_layout import flow_layout, page_inventory


class TestF3FlowLayout(unittest.TestCase):
    def test_many_sources_remain_distinct_readable_and_inside_each_width(self):
        devices = [{"device_id": f"source-{i}", "type": "wincc", "network_zone": f"OT-{i % 3}"} for i in range(40)]
        devices.append({"device_id": "collector", "type": "local_host"})
        for width in (1000, 1366, 1600, 1920):
            with self.subTest(width=width):
                layout = flow_layout(devices, width, 450)
                rects = layout["devices"]
                self.assertEqual(set(rects), {d["device_id"] for d in devices})
                self.assertEqual(len(set(rects.values())), len(devices))
                for x, y, w, h in rects.values():
                    self.assertGreaterEqual(w, 130)
                    self.assertGreaterEqual(h, 84)
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertLessEqual(y + h, layout["height"])
                sources = sorted([rects[d["device_id"]] for d in devices if d["type"] == "wincc"], key=lambda r: r[1])
                self.assertTrue(all(a[1] + a[3] <= b[1] for a, b in zip(sources, sources[1:])))
                self.assertEqual([g["label"] for g in layout["groups"]], ["OT-0", "OT-1", "OT-2"])

    def test_logical_processing_nodes_never_fabricate_inventory_ids(self):
        layout = flow_layout([], 1000, 450)
        self.assertEqual(layout["devices"], {})
        self.assertEqual(set(layout["stages"]), {"lan", "collector", "storage", "task", "outbox", "delivery"})
        self.assertEqual(layout["groups"], [])

    def test_source_pages_keep_processing_visible_and_cover_every_device(self):
        sources = [{"device_id": f"source-{i:02d}", "type": "wincc", "network_zone": f"OT-{i % 3}"} for i in range(40)]
        collector = {"device_id": "collector", "type": "local_host"}
        seen = set()
        for page in range(20):
            inventory, info = page_inventory(sources + [collector], 430, page)
            self.assertIn(collector, inventory)
            self.assertLessEqual(len(inventory), 4)
            self.assertLessEqual(flow_layout(inventory, 1366, 450)["height"], 600)
            seen.update(d["device_id"] for d in inventory if d["type"] == "wincc")
        self.assertEqual(seen, {d["device_id"] for d in sources})
        self.assertEqual(info["total"], 40)


if __name__ == "__main__":
    unittest.main()
