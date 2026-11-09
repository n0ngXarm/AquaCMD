"""Verify Task labels describe the Tag tied to the displayed F3 read evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from collector.probe_once import EvidenceStore
from desktop.f3_handoff import project_f3


class TestF3TaskGroups(unittest.TestCase):
    host = '192.0.2.11'
    endpoint = 'opc.tcp://192.0.2.11:4840'
    tag = 'LAB.WaterLevel'
    node_id = 'ns=2;s=LAB.WaterLevel'
    groups = (
        {'id': 'level', 'name': 'กลุ่มระดับน้ำ', 'tags': [tag]},
        {'id': 'alert', 'name': 'แจ้งเตือนสูง', 'tags': [tag]},
        {'id': 'pump', 'name': 'เฝ้าระวังปั๊ม', 'tags': ['LAB.PumpRunning']},
    )

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'probe.db'
        self.store = EvidenceStore(self.database)
        self.addCleanup(self.store.close)
        self.settings = {'targets': [{
            'host': self.host, 'kind': 'device', 'source': 'real',
            'ua': {'endpoint': self.endpoint, 'nodes': {self.tag: self.node_id}},
        }]}

    def read(self, *, endpoint=None, tag=None, source='real'):
        return self.store.record_read(
            self.host, tag or self.tag, self.node_id,
            ('ok', None, 1.0, {'endpoint': endpoint or self.endpoint}),
            62, 'Good', source=source,
        )

    def nodes(self):
        snapshot = project_f3(self.database, self.settings, {}, task_groups=self.groups)
        return {node['id']: node for node in snapshot['nodes']}

    def test_same_tag_can_belong_to_multiple_configured_groups(self):
        observed = self.read()
        nodes = self.nodes()
        for node_id in (self.host, 'opc'):
            last = nodes[node_id]['last']
            self.assertEqual(last['id'], observed['id'])
            self.assertCountEqual(last['task_groups'], [
                {'id': 'level', 'name': 'กลุ่มระดับน้ำ'},
                {'id': 'alert', 'name': 'แจ้งเตือนสูง'},
            ])
        for node_id in ('task', 'outbox', 'relay', 'tg'):
            self.assertFalse(nodes[node_id]['built'])
            self.assertIsNone(nodes[node_id]['last'])

    def test_different_source_or_endpoint_cannot_label_displayed_read(self):
        observed = self.read(tag='LAB.Unassigned')
        self.read(source='sim')
        self.read(endpoint=self.endpoint + '/other')
        for node_id in (self.host, 'opc'):
            last = self.nodes()[node_id]['last']
            self.assertEqual(last['id'], observed['id'])
            self.assertFalse(last.get('task_groups'))

    def test_legacy_read_without_tag_sample_cannot_reuse_previous_group(self):
        self.read()
        unpaired = self.store.record(
            self.host, 'ua_read',
            ('ok', None, 1.0, {'endpoint': self.endpoint, 'tag': self.tag}),
        )
        last = self.nodes()[self.host]['last']
        self.assertEqual(last['id'], unpaired['id'])
        self.assertFalse(last.get('task_groups'))


if __name__ == '__main__':
    unittest.main()
