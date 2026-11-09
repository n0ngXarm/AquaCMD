"""Phase4 receipts and availability regressions; all data lives under tests/."""
import ast
import importlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from collector import probe_once as probe,evidence_api as api
ROOT=Path(__file__).resolve().parents[1]

class Phase4Contracts(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name);self.db=self.directory/'data.db'
        self.store=probe.EvidenceStore(self.db);self.addCleanup(self.store.close)

    def config(self):
        value={'targets':[{'host':'127.0.0.1','port':4850,'sim':True,'ua':{
            'endpoint':'opc.tcp://127.0.0.1:4850/aqua-sim/','nodes':{'T-101.level':'ns=2;s=T-101.level'},'security_policy':'None'}}],
            'ping_timeout_s':1,'tcp_timeout_s':2,'interval_s':1.2}
        path=self.directory/'config.json';path.write_text(json.dumps(value));return path

    def test_explicit_endpoint_and_node_allowlist_cannot_redirect_or_embed_credentials(self):
        path=self.config();settings=probe.load_settings(path)
        self.assertEqual(settings['targets'][0]['ua']['nodes'],{'T-101.level':'ns=2;s=T-101.level'})
        self.assertEqual(settings['interval_s'],1.2)
        for endpoint in ('opc.tcp://192.0.2.11:4850/','opc.tcp://127.0.0.1:4840/',
                         'opc.tcp://user:secret@127.0.0.1:4850/','http://127.0.0.1:4850/'):
            value=json.loads(path.read_text());value['targets'][0]['ua']['endpoint']=endpoint;path.write_text(json.dumps(value))
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):probe.load_settings(path)
        self.config();value=json.loads(path.read_text());value['targets'][0]['sim']=False;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):probe.load_settings(path)

    def test_sample_and_evidence_commit_atomically_with_foreign_key(self):
        observation=('ok',None,.4,{'observer':'collector-test','node_id':'ns=2;s=T-101.level'})
        row=self.store.record_read('127.0.0.1','T-101.level','ns=2;s=T-101.level',observation,42.5,'Good',source='sim')
        sample=dict(self.store.connection.execute('SELECT * FROM tag_samples').fetchone())
        self.assertEqual(sample['evidence_id'],row['id']);self.assertEqual(sample['ts'],row['ts'])
        self.assertEqual((json.loads(sample['value']),sample['quality']),(42.5,'Good'))
        self.store.connection.execute("CREATE TRIGGER reject_sample BEFORE INSERT ON tag_samples BEGIN SELECT RAISE(ABORT,'test sample failure'); END")
        self.store.connection.commit();before=self.store.connection.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_read('127.0.0.1','T-101.level','ns=2;s=T-101.level',observation,43.5,'Good',source='sim')
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0],before)
        self.assertEqual(self.store.connection.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_new_failure_hides_previous_value_without_erasing_sample_history(self):
        self.store.record_read('127.0.0.1','T-101.level','ns=2;s=T-101.level',('ok',None,.4,{}),0,'Good',source='sim')
        reader=api.EvidenceReader(self.db)
        sample=reader.topology()['nodes'][0]['samples'][0]
        self.assertEqual(sample['value'],0);self.assertTrue(sample['available']);self.assertEqual(sample['source'],'sim')
        self.store.record('127.0.0.1','ua_endpoints',('REFUSED','[Errno 111] Connection refused',.4,{}),source='sim')
        node=reader.topology()['nodes'][0]
        self.assertEqual(node['state'],'UNREACHABLE');self.assertFalse(node['samples'][0]['available'])
        self.assertIsNone(node['samples'][0]['value'])
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM tag_samples').fetchone()[0],1)

    def test_ip_forward_is_observed_and_warns_without_changing_the_os(self):
        run=importlib.import_module('collector.run')
        path=self.directory/'ip_forward';path.write_text('1\n')
        row=self.store.record('collector-test','ip_forward',run.ip_forward_check(path))
        local=api.EvidenceReader(self.db).topology()['components']['collector']
        self.assertEqual(local['ip_forward'],1);self.assertIn('IP forwarding',local['warning'])
        self.assertEqual(local['ip_forward_evidence_id'],row['id']);self.assertEqual(path.read_text(),'1\n')
        path.write_text('not an integer');self.assertEqual(run.ip_forward_check(path)[0],'ERROR')

    def test_built_client_is_unknown_until_an_actual_attempt_and_source_has_no_control_calls(self):
        self.assertEqual(api.EvidenceReader(self.db).topology()['components']['client']['state'],'UNKNOWN')
        banned={'write_value','set_value','write_values','set_values','call_method','call_methods'}
        self.assertTrue((ROOT/'src/collector/opcua_read.py').exists())
        for path in (ROOT/'src').rglob('*.py'):
            for item in ast.walk(ast.parse(path.read_text())):
                if isinstance(item,ast.Call) and isinstance(item.func,ast.Attribute):self.assertNotIn(item.func.attr,banned,str(path))

    def test_local_network_facts_cannot_be_borrowed_from_another_observer(self):
        self.store.record('observer-B','local_nic',('ok',None,.1,{'observer':'observer-B','parsed':[]}))
        self.store.record('observer-A','ip_forward',('ok',None,.1,{'observer':'observer-A','value':1}))
        self.store.record('192.0.2.11','route',('ok',None,.1,{'observer':'observer-A','parsed':[{'dev':'test0','prefsrc':'192.0.2.1'}]}))
        local=api.EvidenceReader(self.db).topology()['components']['collector']
        self.assertEqual((local['ip_forward'],len(local['routes'])),(None,0))

    def test_samples_from_a_previous_node_binding_are_not_current_config_values(self):
        self.store.record_read('127.0.0.1','old-tag','ns=2;s=old',('ok',None,.1,{'endpoint':'opc.tcp://127.0.0.1:4850/old/'}),42.5,'Good',source='sim')
        reader=api.EvidenceReader(self.db,ua_targets={'127.0.0.1':{'endpoint':'opc.tcp://127.0.0.1:4850/new/','nodes':{'new-tag':'i=2259'}}})
        self.assertEqual(reader.topology()['nodes'][0]['samples'],[])

    def test_first_kernel_observation_proves_internal_pairs_before_nic_inventory(self):
        row=self.store.record('collector-test','ip_forward',('ok',None,.1,{'observer':'collector-test','path':'/proc/sys/net/ipv4/ip_forward','value':0}))
        snapshot=api.EvidenceReader(self.db).topology()
        pairs={(edge['source'],edge['target']) for edge in snapshot['edges']}
        self.assertEqual(pairs,{('os','collector'),('collector','sqlite')})
        self.assertTrue(all(edge['evidence_id']==row['id'] for edge in snapshot['edges']))
        self.assertEqual(snapshot['components']['collector']['state'],'UNKNOWN')

if __name__=='__main__':unittest.main()
