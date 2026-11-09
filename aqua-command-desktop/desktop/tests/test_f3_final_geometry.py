"""Compact dock geometry and infrastructure pagination use synthetic inventory."""
import unittest

from f3_layout import flow_layout, page_inventory


class FinalGeometryTests(unittest.TestCase):
    def test_compact_view_fits_two_source_groups_without_wasting_a_page(self):
        devices = [{'device_id': 'source-a', 'type': 'wincc', 'network_zone': 'LAB-A'},
            {'device_id': 'source-b', 'type': 'wincc', 'network_zone': 'LAB-B'},
            {'device_id': 'local', 'type': 'local_host'}]
        inventory, info = page_inventory(devices, 343, 0, 995)
        self.assertEqual(info['pages'], 1)
        self.assertEqual({d['device_id'] for d in inventory}, {'source-a', 'source-b', 'local'})
        self.assertLessEqual(flow_layout(inventory, 995, 343)['height'], 343)

    def test_extra_infrastructure_pages_keep_valid_source_ranges_and_all_devices(self):
        devices = [{'device_id': 'source', 'type': 'wincc'}, {'device_id': 'local', 'type': 'local_host'},
            {'device_id': 'router', 'type': 'router'}, {'device_id': 'service', 'type': 'service'}]
        seen = set()
        for page in range(2):
            inventory, info = page_inventory(devices, 500, page, 1200)
            self.assertLessEqual(info['start'], info['end'])
            self.assertLessEqual(info['end'], info['total'])
            self.assertTrue(inventory)
            seen.update(d['device_id'] for d in inventory)
        self.assertEqual(seen, {d['device_id'] for d in devices})

    def test_compact_nodes_and_processing_stages_fit_without_intersection(self):
        devices = [{'device_id': 'source', 'type': 'wincc'}, {'device_id': 'local', 'type': 'local_host'},
            {'device_id': 'switch', 'type': 'switch'}, {'device_id': 'router', 'type': 'router'}]
        layout = flow_layout(devices, 995, 343)
        occupied = set(layout['device_stages'].values())
        rects = list(layout['devices'].values()) + [r for stage, r in layout['stages'].items() if stage not in occupied]
        for index, (x, y, w, h) in enumerate(rects):
            self.assertLessEqual(x + w, 995)
            self.assertLessEqual(y + h, 343)
            for x2, y2, w2, h2 in rects[index+1:]:
                self.assertFalse(x < x2+w2 and x2 < x+w and y < y2+h2 and y2 < y+h)


if __name__ == '__main__':
    unittest.main()
