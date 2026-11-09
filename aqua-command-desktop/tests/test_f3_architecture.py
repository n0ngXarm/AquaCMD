import json
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from collector.probe_once import EvidenceStore
from collector.evidence_api import EvidenceReader
from desktop.f3_projection import F3Projection

class Architecture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.store=EvidenceStore(Path(self.temp.name)/'data.db')
        self.settings={'targets':[{'host':'192.0.2.1','kind':'device','port':4840}],'interval_s':5}
        self.metadata={'192.0.2.1':{'label':'192.0.2.1','kind':'wincc'}}
        self.reader=F3Projection(EvidenceReader(self.store.path,hosts=['192.0.2.1']),self.settings,self.metadata)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def record(self,check='tcp',result='ok',age=0):
        row=self.store.record('192.0.2.1',check,(result,None,1,{'observer':'test'}),source='sim')
        if age:
            self.store.connection.execute('UPDATE probe_evidence SET ts=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),row['id']));self.store.connection.commit()
        return row
    def test_stale_success_not_current(self):
        self.record(age=3600);n=self.reader.topology()['nodes'][0]
        self.assertEqual(n['current_state'],'UNKNOWN');self.assertEqual(n['last_known_state'],'TCP_OPEN')
    def test_stale_failure_not_current(self):
        self.record(result='TIMEOUT',age=3600);n=self.reader.topology()['nodes'][0]
        self.assertEqual(n['current_state'],'UNKNOWN');self.assertEqual(n['last_known_state'],'UNREACHABLE')
    def test_session_receipt_is_not_live_session(self):
        self.record('ua_session');value=self.reader.topology()
        self.assertIsNone(value['f3_metrics']['ua_sessions_connected']);self.assertEqual(value['nodes'][0]['session_state'],'UNKNOWN')
    def test_counts_and_bounds_are_sql(self):
        self.record();self.record();value=self.reader.topology()
        self.assertEqual(value['f3_metrics']['evidence_records'],2)
        self.assertEqual(value['f3_metrics']['configured_sources'],1)
        self.assertEqual(value['f3_metrics']['reachability_verified'],1)
        self.assertEqual(value['f3_metrics']['last_commit_ts'],self.store.connection.execute('SELECT MAX(ts) FROM probe_evidence').fetchone()[0])
    def test_unknown_inventory_and_dynamic_count(self):
        for i in range(2,42):self.metadata[f'192.0.2.{i}']={'kind':'wincc','label':f'192.0.2.{i}'}
        value=self.reader.topology();self.assertEqual(value['f3_metrics']['configured_sources'],41);self.assertEqual(len(value['nodes']),41)
        self.assertTrue(all(n['current_state']=='UNKNOWN' for n in value['nodes']))
    def test_no_writes(self):
        self.record();before=self.store.path.read_bytes();self.reader.topology();self.assertEqual(before,self.store.path.read_bytes())
    def test_empty(self):
        value=self.reader.topology();self.assertEqual(value['f3_metrics']['reachability_verified'],0);self.assertIsNone(value['f3_metrics']['last_commit_ts'])
    def test_old_endpoint_cannot_confirm_current_read(self):
        self.settings['targets'][0]['ua']={'endpoint':'opc.tcp://192.0.2.1:4840/new','security_policy':'None'}
        self.store.record('192.0.2.1','ua_read',('ok',None,1,{'endpoint':'opc.tcp://192.0.2.1:4840/old'}),source='sim')
        self.assertEqual(self.reader.topology()['nodes'][0]['current_state'],'UNKNOWN')
    def test_pipeline_not_built(self):
        value=self.reader.topology();self.assertEqual(value['modules']['task']['state'],'NOT_BUILT');self.assertEqual(value['modules']['outbox']['state'],'NOT_BUILT')

if __name__=='__main__':unittest.main(verbosity=2)
