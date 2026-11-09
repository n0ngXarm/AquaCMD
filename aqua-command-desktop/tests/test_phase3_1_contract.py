"""Corrected phase 3.1 evidence contracts; rows exist only in temporary tests DBs."""
import json
import ssl
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from collector import evidence_api as api, probe_once as probe

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,6,13,31,tzinfo=timezone.utc)


class Phase31Tests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name);self.db=self.directory/'data.db'
        self.store=probe.EvidenceStore(self.db);self.addCleanup(self.store.close)

    def row(self,host,check,result='ok',error=None,detail=None,age=0):
        row=self.store.record(host,check,(result,error,.4,detail or {}))
        self.store.connection.execute('UPDATE probe_evidence SET ts=? WHERE id=?',((NOW-timedelta(seconds=age)).isoformat(),row['id']))
        self.store.connection.commit()
        return dict(self.store.connection.execute('SELECT * FROM probe_evidence WHERE id=?',(row['id'],)).fetchone())

    def test_old_failure_stays_red_with_separate_stale_age(self):
        row=self.row('192.0.2.11','tcp','TIMEOUT','timed out',age=960)
        result=api.derive_state([row],NOW)
        self.assertEqual(result['state'],'UNREACHABLE')
        self.assertEqual(result['freshness'],'STALE')
        self.assertEqual(result['age_seconds'],960)
        self.assertEqual(result['reason'],'timed out')

    def test_sqlite_is_directly_observed_with_count_and_last_write(self):
        row=self.row('192.0.2.11','tcp','TIMEOUT','timed out',age=960)
        snapshot=api.EvidenceReader(self.db).topology(NOW)
        storage=snapshot['components']['sqlite']
        self.assertEqual(storage['state'],'OBSERVED_LOCAL')
        self.assertEqual(storage['committed_rows'],1)
        self.assertEqual(storage['last_write_ts'],row['ts'])
        self.assertEqual(snapshot['components']['task']['state'],'NOT_BUILT')

    def test_router_uses_ping_and_arp_ignoring_old_tcp4840(self):
        self.row('192.0.2.1','route')
        self.row('192.0.2.1','ping')
        self.row('192.0.2.1','tcp','TIMEOUT','obsolete port check',{'port':4840})
        rows=[dict(row) for row in self.store.connection.execute('SELECT * FROM probe_evidence')]
        result=api.derive_state(rows,NOW,kind='router')
        self.assertEqual(result['state'],'REACHABLE')
        self.assertEqual(result['result_check'],'ping')
        self.assertNotIn('tcp',result['checks'])

    def test_remote_counts_are_checked_and_current_round_responses_from_sql(self):
        for host in ('192.0.2.11','192.0.2.12'):
            self.row(host,'route');self.row(host,'ping','TIMEOUT','timed out')
        self.row('192.0.2.11','tcp')
        snapshot=api.EvidenceReader(self.db).topology(NOW)
        self.assertEqual(snapshot['counters']['remote_hosts'],2)
        self.assertEqual(snapshot['counters']['remote_responding'],1)
        self.row('192.0.2.11','route')
        self.row('192.0.2.11','tcp','REFUSED','connection refused')
        self.assertEqual(api.EvidenceReader(self.db).topology(NOW)['counters']['remote_responding'],0)

    def test_local_nic_and_per_target_route_define_mismatch_without_inferred_connectivity(self):
        self.row('collector-test','local_nic',detail={'parsed':[{'ifname':'wifi-test','addr_info':[{'family':'inet','local':'198.51.100.177','prefixlen':24}]}]})
        self.row('192.0.2.11','route',detail={'observer':'collector-test','parsed':[{'dst':'192.0.2.11','dev':'wifi-test','prefsrc':'198.51.100.177','gateway':'198.51.100.1'}]})
        snapshot=api.EvidenceReader(self.db,hosts=['192.0.2.11'],ot_subnet='192.0.2.0/24').topology(NOW)
        local=snapshot['components']['collector']
        self.assertEqual(local['state'],'OBSERVED_LOCAL')
        self.assertEqual(local['configuration_state'],'CONFIGURATION MISMATCH')
        self.assertEqual(local['interfaces'][0]['cidrs'],['198.51.100.177/24'])
        self.assertEqual(local['routes'][0]['dev'],'wifi-test')
        self.assertEqual(local['routes'][0]['gateway'],'198.51.100.1')
        self.assertEqual(snapshot['nodes'][0]['state'],'UNKNOWN')

    def test_no_edges_without_pair_evidence_then_explicit_actor_creates_labelled_pair(self):
        self.row('collector-test','local_nic',detail={'observer':'collector-test','parsed':[]})
        row=self.row('192.0.2.11','tcp','TIMEOUT','timed out')
        self.store.connection.execute('UPDATE probe_evidence SET detail=\'{}\' WHERE id=?',(row['id'],));self.store.connection.commit()
        snapshot=api.EvidenceReader(self.db).topology(NOW)
        self.assertFalse(any(edge['target']=='host:192.0.2.11' for edge in snapshot['edges']))
        self.row('192.0.2.11','tcp','TIMEOUT','timed out',{'observer':'collector-test','port':4840})
        snapshot=api.EvidenceReader(self.db).topology(NOW)
        edge=next(edge for edge in snapshot['edges'] if edge['target']=='host:192.0.2.11')
        self.assertEqual(edge['source'],'collector')
        self.assertEqual(edge['check'],'tcp')
        self.assertEqual(edge['result'],'TIMEOUT')

    def test_collector_never_connects_tcp_to_a_router(self):
        config=self.directory/'config.json'
        config.write_text(json.dumps({'targets':[{'host':'192.0.2.1','kind':'router'}],
                                      'ping_timeout_s':1,'tcp_timeout_s':2}))
        observed=('ok',None,.4,{'parsed':[]})
        with patch.object(probe,'ip_check',return_value=observed),patch.object(probe,'ping_check',return_value=observed), \
             patch.object(probe,'arp_check',return_value=observed,create=True),patch.object(probe,'tcp_check') as tcp:
            probe.run(config,self.directory/'router.db',lambda line:None)
        tcp.assert_not_called()

    def test_arp_cache_requires_a_current_reachable_neighbor(self):
        for state,result in [('REACHABLE','ok'),('STALE','UNVERIFIED_NEIGHBOR'),('FAILED','UNVERIFIED_NEIGHBOR')]:
            with self.subTest(state=state),patch.object(probe,'command',return_value=(
                {'returncode':0,'stdout':json.dumps([{'dst':'192.0.2.1','state':[state]}])},.1)):
                observed=probe.arp_check('192.0.2.1')
                self.assertEqual(observed[0],result)
                self.assertTrue(observed[3]['passive'])

    def test_internet_failure_keeps_dns_or_certificate_reason_without_application_request(self):
        with patch.object(probe,'command',return_value=({'returncode':2,'stdout':'','stderr':'resolver failure'},.1)), \
             patch.object(probe.socket,'create_connection') as connect:
            result=probe.internet_check('api.telegram.org',443,2)
            self.assertEqual(result[0],'DNS_ERROR');self.assertIn('resolver failure',result[1])
            connect.assert_not_called()
        with patch.object(probe,'command',return_value=({'returncode':0,'stdout':'203.0.113.10 STREAM\n'},.1)), \
             patch.object(probe.socket,'create_connection'),patch.object(probe.ssl,'create_default_context') as context:
            context.return_value.wrap_socket.side_effect=ssl.SSLCertVerificationError('certificate verify failed')
            result=probe.internet_check('api.telegram.org',443,2)
            self.assertEqual(result[0],'CERT_ERROR');self.assertIn('certificate verify failed',result[1])
            self.assertFalse(result[3]['application_request_sent'])
            self.assertEqual(result[3]['stage'],'tls')
            context.return_value.wrap_socket.assert_called_once()


if __name__=='__main__':unittest.main()
