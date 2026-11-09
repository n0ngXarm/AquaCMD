"""Real OPC UA acceptance: a separate loopback server process and temporary tests DBs."""
import asyncio
import json
import os
import select
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from collector import evidence_api as api,probe_once as probe
from collector.opcua_read import read_target
from collector import opcua_read
from desktop.opcua_pki import PkiManager

ROOT=Path(__file__).resolve().parents[1]


class RealOpcUaPhase4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='.phase4-protocol-',dir=ROOT/'tests')
        cls.directory=Path(cls.temporary.name)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as guard:guard.bind(('127.0.0.1',4850))
        cls.server_log=(cls.directory/'server.log').open('w+')
        cls.server=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/sim/opcua_server.py'),
            '--data-dir',str(cls.directory/'server'),'--level','12.5'],cwd=ROOT,stdout=subprocess.PIPE,stderr=cls.server_log,text=True)
        if not select.select([cls.server.stdout],[],[],20)[0]:raise AssertionError('Simulator readiness timed out')
        line=cls.server.stdout.readline()
        if not line:
            cls.server_log.seek(0);raise AssertionError('Simulator did not start: '+cls.server_log.read())
        cls.ready=json.loads(line);assert cls.ready['ready'] and cls.ready['source']=='sim'

    @classmethod
    def tearDownClass(cls):
        if cls.server.poll() is None:cls.server.terminate();cls.server.wait(timeout=8)
        cls.server.stdout.close();cls.server_log.close();cls.temporary.cleanup()

    def setUp(self):
        self.db=self.directory/(self._testMethodName+'.db')
        self.store=probe.EvidenceStore(self.db);self.addCleanup(self.store.close)
        self.target={'host':'127.0.0.1','port':4850,'source':'sim','kind':'device','ua':{
            'endpoint':self.ready['endpoint'],'nodes':{'T-101.level':self.ready['node_id']},'security_policy':'None'}}
        self.output=[]

    def read(self):asyncio.run(read_target(self.target,2,self.store,self.output.append))
    def snapshot(self):return api.EvidenceReader(self.db).topology()
    def rows(self):return [dict(row) for row in self.store.connection.execute('SELECT * FROM probe_evidence ORDER BY id')]

    def test_a_real_read_changes_value_and_preserves_quality_certificate_and_source(self):
        self.read();node=self.snapshot()['nodes'][0]
        self.assertEqual(node['state'],'READ_OK');self.assertEqual(node['samples'][0]['value'],12.5)
        self.assertEqual((node['samples'][0]['quality'],node['samples'][0]['source']),('Good','sim'))
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/sim/set_level.py'),'73.25'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['observed_level'],73.25)
        self.read();node=self.snapshot()['nodes'][0]
        self.assertEqual(node['samples'][0]['value'],73.25)
        self.assertEqual(self.snapshot()['counters']['read_receipts'],2)
        for row in self.rows():
            if row['check']=='ua_read':
                detail=json.loads(row['detail']);self.assertTrue(detail['certificate']['subject'])
                self.assertTrue(detail['certificate']['not_after']);self.assertEqual(len(detail['certificate']['sha256']),64)
                self.assertIsNotNone(detail['source_ts']);self.assertEqual(detail['value'],json.loads(self.store.connection.execute('SELECT value FROM tag_samples WHERE evidence_id=?',(row['id'],)).fetchone()[0]))
        self.assertEqual(self.store.connection.execute('PRAGMA foreign_key_check').fetchall(),[])
        print(json.dumps({'protocol':'real-loopback','source':'sim','first_value':12.5,'changed_value':node['samples'][0]['value'],'quality':node['samples'][0]['quality'],'certificate':json.loads(self.rows()[-2]['detail'])['certificate']}),flush=True)

    def test_b_bad_node_status_is_not_a_successful_read(self):
        self.target['ua']['nodes']={'bad':'ns=2;s=does-not-exist'};self.read()
        node=self.snapshot()['nodes'][0];self.assertEqual(node['state'],'UNREACHABLE')
        self.assertEqual(self.snapshot()['counters']['read_receipts'],0)
        read=next(row for row in self.rows() if row['check']=='ua_read')
        self.assertIn(read['result'],('BAD_QUALITY','UA_ERROR'));self.assertIn('BadNodeIdUnknown',read['error'])
        self.assertFalse(any(sample['available'] for sample in node['samples']))

    def test_b_server_status_uses_the_explicit_standard_node_and_real_structured_value(self):
        self.target['ua']['nodes']={'ServerStatus':'i=2256'};self.read()
        sample=self.snapshot()['nodes'][0]['samples'][0]
        self.assertTrue(sample['available']);self.assertEqual(sample['quality'],'Good')
        self.assertIsInstance(sample['value'],dict)
        self.assertIn('State',sample['value']);self.assertIn('CurrentTime',sample['value'])

    def test_c_untrusted_certificate_is_rejected_then_explicitly_trusted_secure_read_succeeds(self):
        pki_dir=self.directory/'client-pki';self.target['ua'].update(security_policy='Basic256Sha256',pki_dir=str(pki_dir))
        self.read();snapshot=self.snapshot()
        self.assertEqual(snapshot['nodes'][0]['state'],'UNREACHABLE');self.assertEqual(snapshot['counters']['read_receipts'],0)
        rejected=next(row for row in self.rows() if row['check']=='ua_session')
        self.assertEqual(rejected['result'],'CERT_ERROR');self.assertIn('BadCertificateUntrusted',rejected['error'])
        self.assertFalse(json.loads(rejected['detail'])['session_attempted'])
        pki=PkiManager(pki_dir);self.assertEqual(list(pki.trusted_certs_dir.iterdir()),[])
        pki.trust_certificate(Path(self.ready['certificate']))
        self.read();snapshot=self.snapshot()
        self.assertEqual(snapshot['nodes'][0]['state'],'READ_OK');self.assertTrue(snapshot['nodes'][0]['samples'][0]['available'])
        session=[row for row in self.rows() if row['check']=='ua_session'][-1]
        self.assertEqual(json.loads(session['detail'])['certificate_validation']['valid'],True)
        self.assertEqual(json.loads(session['detail'])['security_policy'],'Basic256Sha256')

    def test_d_actual_loop_respects_configured_interval_and_stops_cleanly(self):
        config=self.directory/'loop.json';db=self.directory/'loop.db'
        config.write_text(json.dumps({'targets':[{'host':'127.0.0.1','port':4850,'sim':True,'ua':self.target['ua']}],
            'ping_timeout_s':1,'tcp_timeout_s':2,'interval_s':1.2}))
        with (self.directory/'loop.stdout').open('w') as out,(self.directory/'loop.stderr').open('w') as err:
            child=subprocess.Popen([sys.executable,'-B','-m','collector.run','--config',str(config),'--db',str(db),'--loop'],cwd=ROOT,stdout=out,stderr=err)
            try:
                deadline=time.monotonic()+15;times=[]
                while time.monotonic()<deadline:
                    if db.exists():
                        try:
                            with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as connection:
                                times=[row[0] for row in connection.execute('SELECT ts FROM tag_samples ORDER BY id')]
                        except sqlite3.Error:pass
                    if len(times)>=2:break
                    self.assertIsNone(child.poll(),'Collector exited before two real reads');time.sleep(.05)
                self.assertGreaterEqual(len(times),2)
                delta=(datetime.fromisoformat(times[1])-datetime.fromisoformat(times[0])).total_seconds()
                self.assertGreaterEqual(delta,1.1)
                child.send_signal(signal.SIGTERM);self.assertEqual(child.wait(timeout=8),0)
                print(json.dumps({'loop_samples':len(times),'configured_interval_s':1.2,'actual_receipt_delta_s':delta,'stop_exit':child.returncode}),flush=True)
            finally:
                if child.poll() is None:child.terminate();child.wait(timeout=8)

    def test_e_storage_failure_aborts_the_read_and_closes_actual_client_sockets(self):
        clients=[]
        class TrackedClient(opcua_read.Client):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);clients.append(self)
        original=self.store.record
        def reject_session(host,check,*args,**kwargs):
            if check=='ua_session':raise sqlite3.OperationalError('Controlled test storage failure')
            return original(host,check,*args,**kwargs)
        with patch.object(opcua_read,'Client',TrackedClient),patch.object(self.store,'record',side_effect=reject_session):
            with self.assertRaises(sqlite3.OperationalError):self.read()
        self.assertEqual(len(clients),2)
        self.assertTrue(all(client.uaclient.protocol is None for client in clients))
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM tag_samples').fetchone()[0],0)

    def test_z_stopped_simulator_records_refused_and_never_displays_old_value(self):
        self.read();self.assertEqual(self.snapshot()['nodes'][0]['state'],'READ_OK')
        self.server.terminate();self.assertEqual(self.server.wait(timeout=8),0)
        self.read();node=self.snapshot()['nodes'][0]
        self.assertEqual(node['state'],'UNREACHABLE');self.assertIn(node['checks']['ua_endpoints']['result'],('REFUSED','TIMEOUT'))
        self.assertFalse(node['samples'][0]['available']);self.assertIsNone(node['samples'][0]['value'])
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM tag_samples').fetchone()[0],1)
        print(json.dumps({'stopped_server_evidence':self.rows()[-1],'current_sample':node['samples'][0]},ensure_ascii=False),flush=True)


if __name__=='__main__':unittest.main()
