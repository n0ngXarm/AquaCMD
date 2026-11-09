"""Phase 2 contracts; all sample rows and temporary databases stay in tests/."""
import hashlib
import http.client
import importlib
import json
import select
import socket
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from collector import probe_once as probe

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def sample(identifier, check, result='ok', age=0, source='real', error=None):
    return {'id': identifier, 'host': '192.0.2.11', 'check': check, 'result': result,
            'error': error, 'latency_ms': 0.4, 'ts': (NOW-timedelta(seconds=age)).isoformat(),
            'detail': '{}', 'source': source}


class TemporaryEvidence(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='.phase2-', dir=ROOT/'tests')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.db = self.directory/'data.db'

    def store(self):
        store = probe.EvidenceStore(self.db)
        self.addCleanup(store.close)
        return store

    def record(self, store, host='192.0.2.11', check='tcp', result='ok', source='real'):
        return store.record(host, check, (result, None if result == 'ok' else 'OS detail', 0.4, {'port': 4840}), source=source)


class MigrationTests(TemporaryEvidence):
    def test_existing_phase1_rows_are_preserved_and_default_to_real(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('''CREATE TABLE probe_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT NOT NULL, "check" TEXT NOT NULL,
                result TEXT NOT NULL, error TEXT, latency_ms REAL NOT NULL, ts TEXT NOT NULL, detail TEXT NOT NULL)''')
            connection.execute('INSERT INTO probe_evidence VALUES(7,?,?,?,?,?,?,?)',
                               ('192.0.2.11', 'tcp', 'REFUSED', 'original OS error', 0.5, NOW.isoformat(), '{"errno":111}'))
        first = self.store()
        row = dict(first.connection.execute('SELECT * FROM probe_evidence').fetchone())
        self.assertEqual((row['id'], row['source'], row['error'], row['detail']),
                         (7, 'real', 'original OS error', '{"errno":111}'))
        second = self.store()
        self.assertEqual(second.connection.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0], 1)

    def test_source_is_validated_and_rejected_without_inserting(self):
        store = self.store()
        for source in ('SIMULATED', '', None, True):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.record(store, source=source)
        self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0], 0)
        with self.assertRaises(sqlite3.IntegrityError):
            store.connection.execute('''INSERT INTO probe_evidence(host,"check",result,latency_ms,ts,detail,source)
                                       VALUES('192.0.2.11','tcp','ok',1,?,'{}','invalid')''', (NOW.isoformat(),))

    def test_config_sim_flag_controls_only_its_target_and_not_os_inventory(self):
        config = self.directory/'targets.json'
        config.write_text(json.dumps({'targets': [{'host': '192.0.2.11', 'port': 4840, 'sim': True},
                                                 {'host': '192.0.2.12', 'port': 4840}],
                                      'ping_timeout_s': 1, 'tcp_timeout_s': 2}))
        observed = ('ok', None, 0.4, {'observed_by': 'test'})
        with patch.object(probe, 'ip_check', return_value=observed), \
             patch.object(probe, 'ping_check', return_value=observed), \
             patch.object(probe, 'tcp_check', return_value=observed):
            probe.run(config, self.db, lambda line: None)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT source,COUNT(*) FROM probe_evidence GROUP BY source ORDER BY source').fetchall(),
                             [('real', 5), ('sim', 3)])

    def test_nonboolean_sim_is_rejected_before_creating_database(self):
        config = self.directory/'targets.json'
        config.write_text(json.dumps({'targets': [{'host': '192.0.2.11', 'port': 4840, 'sim': 'true'}],
                                      'ping_timeout_s': 1, 'tcp_timeout_s': 2}))
        with self.assertRaises(ValueError):
            probe.run(config, self.db)
        self.assertFalse(self.db.exists())


class StateTests(unittest.TestCase):
    def derive(self, rows):
        return importlib.import_module('collector.evidence_api').derive_state(rows, NOW)

    def test_no_rows_is_unknown_with_no_observed_source_or_timestamp(self):
        self.assertEqual(self.derive([]), {'state':'UNKNOWN','reason':None,'last_check_ts':None,'source':None,
            'freshness':'UNKNOWN','age_seconds':None,'age_label':'ยังไม่มีหลักฐาน',
            'result_check':None,'result_ts':None,'check_label':None,'check_summary':'ยังไม่มีหลักฐาน','checks':{}})

    def test_route_ping_and_discovery_alone_do_not_assert_transport_or_session(self):
        for check in ('route', 'ping', 'ua_endpoints'):
            with self.subTest(check=check):
                self.assertEqual(self.derive([sample(1, check)])['state'], 'UNKNOWN')

    def test_success_levels_and_priority_use_real_checks(self):
        for check, state in (('tcp', 'TCP_OPEN'), ('ua_session', 'UA_OK'), ('ua_read', 'READ_OK')):
            with self.subTest(check=check):
                result = self.derive([sample(1, check, age=2), sample(2, 'route')])
                self.assertEqual(result['state'], state)
                self.assertIsNone(result['reason'])

    def test_new_failure_invalidates_older_read_success_and_preserves_reason(self):
        result = self.derive([sample(1, 'ua_read', age=1), sample(2, 'tcp', 'REFUSED', error='[Errno 111] Connection refused')])
        self.assertEqual(result['state'], 'UNREACHABLE')
        self.assertEqual(result['reason'], '[Errno 111] Connection refused')

    def test_route_success_does_not_erase_transport_failure(self):
        result = self.derive([sample(1, 'tcp', 'TIMEOUT', age=1, error='timed out'), sample(2, 'route')])
        self.assertEqual((result['state'], result['reason']), ('UNREACHABLE', 'timed out'))

    def test_recovery_promotes_only_to_newly_verified_level(self):
        result = self.derive([sample(1, 'ua_read', age=2), sample(2, 'ua_session', 'CERT_ERROR', age=1), sample(3, 'tcp')])
        self.assertEqual(result['state'], 'TCP_OPEN')

    def test_age_boundary_and_stale_failure_reason(self):
        self.assertEqual(self.derive([sample(1, 'tcp', age=60)])['state'], 'TCP_OPEN')
        result = self.derive([sample(1, 'tcp', 'TIMEOUT', age=70, error='timed out')])
        self.assertEqual((result['state'], result['reason']), ('UNREACHABLE', 'timed out'))
        self.assertEqual((result['freshness'],result['age_seconds']),('STALE',70))

    def test_recent_route_does_not_refresh_old_read_success(self):
        result = self.derive([sample(1, 'ua_read', age=70), sample(2, 'route')])
        self.assertEqual(result['state'], 'READ_OK')
        self.assertEqual((result['freshness'],result['age_seconds']),('STALE',70))

    def test_sources_are_not_combined_into_false_read_success(self):
        result = self.derive([sample(1, 'ua_read', source='sim'), sample(2, 'tcp', 'REFUSED', source='real', error='refused')])
        self.assertEqual((result['state'], result['source']), ('UNREACHABLE', 'real'))

    def test_stale_recovery_does_not_reuse_the_pre_recovery_failure_reason(self):
        result = self.derive([sample(1, 'tcp', 'REFUSED', age=80, error='old refusal'), sample(2, 'ua_read', age=70)])
        self.assertEqual((result['state'], result['reason']), ('READ_OK', None))
        self.assertEqual((result['freshness'],result['age_seconds']),('STALE',70))

    def test_invalid_timestamp_is_an_error_instead_of_success(self):
        row = sample(1, 'tcp'); row['ts'] = 'invalid'
        with self.assertRaises(ValueError):
            self.derive([row])


class ApiTests(TemporaryEvidence):
    def setUp(self):
        super().setUp()
        self.api = importlib.import_module('collector.evidence_api')
        self.storage = self.store()
        self.initial = self.record(self.storage)
        self.server = self.api.make_server(self.db, hosts=['192.0.2.11', '192.0.2.12'], port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_port

    def close_server(self):
        self.server.stop_event.set()
        self.server.shutdown(); self.server.server_close()
        self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())

    def request(self, path, method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def stream(self, last_id=None):
        connection = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        self.addCleanup(connection.close)
        extra = '' if last_id is None else f'Last-Event-ID: {last_id}\r\n'
        connection.sendall(f'GET /api/stream HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n{extra}\r\n'.encode())
        reader = connection.makefile('rb')
        self.addCleanup(reader.close)
        status = reader.readline()
        self.assertIn(b'200', status)
        while reader.readline() != b'\r\n':
            pass
        return connection, reader

    def event(self, reader):
        lines = []
        while True:
            line = reader.readline()
            self.assertTrue(line, 'SSE connection closed before evidence')
            if line == b'\n':
                break
            lines.append(line.decode().rstrip('\n'))
        fields = dict(line.split(': ', 1) for line in lines)
        self.assertEqual(fields['event'], 'evidence')
        row = json.loads(fields['data'])
        self.assertEqual(int(fields['id']), row['id'])
        return row

    def test_topology_states_and_all_counters_match_independent_sql_counts(self):
        self.record(self.storage, check='ua_session')
        self.record(self.storage, check='ua_session')
        self.record(self.storage, check='ua_read', source='sim')
        self.record(self.storage, host='192.0.2.12', result='TIMEOUT')
        self.record(self.storage, host='local-test', check='nic_inventory')
        status, body, headers = self.request('/api/topology')
        self.assertEqual(status, 200)
        with closing(sqlite3.connect(self.db)) as connection:
            expected = dict(remote_hosts=connection.execute('''SELECT COUNT(DISTINCT host) FROM probe_evidence
                WHERE "check" IN ('route','ping','tcp','ua_endpoints','ua_session','ua_read')''').fetchone()[0],
                remote_responding=connection.execute("SELECT COUNT(DISTINCT host) FROM probe_evidence WHERE result='ok' AND \"check\" IN ('ping','arp','tcp','ua_endpoints','ua_session','ua_read')").fetchone()[0],
                ua_sessions=connection.execute('SELECT COUNT(*) FROM probe_evidence WHERE "check"=\'ua_session\' AND result=\'ok\'').fetchone()[0],
                read_receipts=connection.execute('SELECT COUNT(*) FROM probe_evidence WHERE "check"=\'ua_read\' AND result=\'ok\'').fetchone()[0],
                committed_rows=connection.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0])
        self.assertEqual(body['counters'], expected)
        nodes = {node['host']: node for node in body['nodes']}
        self.assertEqual((nodes['192.0.2.11']['state'], nodes['192.0.2.11']['source']), ('READ_OK', 'sim'))
        self.assertEqual(nodes['192.0.2.12']['state'], 'UNREACHABLE')
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_unobserved_configured_host_is_unknown_and_has_no_source(self):
        _, body, _ = self.request('/api/topology')
        node = next(node for node in body['nodes'] if node['host'] == '192.0.2.12')
        self.assertEqual((node['state'], node['source'], node['last_check_ts']), ('UNKNOWN', None, None))

    def test_empty_database_counters_are_sql_zero_and_no_success_is_inferred(self):
        self.storage.connection.execute('DELETE FROM probe_evidence')
        self.storage.connection.commit()
        status, body, _ = self.request('/api/topology')
        self.assertEqual(status, 200)
        self.assertEqual(body['counters'], dict(remote_hosts=0, remote_responding=0, ua_sessions=0, read_receipts=0, committed_rows=0))
        self.assertTrue(all(node['state'] == 'UNKNOWN' and node['source'] is None for node in body['nodes']))

    def test_topology_keeps_old_failure_context_when_a_new_route_cannot_verify_recovery(self):
        failure = self.record(self.storage, result='TIMEOUT')
        self.storage.connection.execute('UPDATE probe_evidence SET ts=?',
                                        ((datetime.now(timezone.utc)-timedelta(seconds=70)).isoformat(),))
        self.storage.connection.commit()
        latest = self.record(self.storage, check='route')
        _, body, _ = self.request('/api/topology')
        node = next(node for node in body['nodes'] if node['host'] == failure['host'])
        self.assertEqual((node['state'], node['reason'], node['last_check_ts']),
                         ('UNREACHABLE', failure['error'], latest['ts']))

    def test_raw_evidence_is_not_rewritten_and_limit_is_applied_by_sql(self):
        latest = self.record(self.storage, result='REFUSED', source='sim')
        status, body, _ = self.request('/api/evidence?host=192.0.2.11&limit=1')
        self.assertEqual(status, 200)
        self.assertEqual(body['rows'], [latest])
        self.assertEqual(body['rows'][0]['detail'], latest['detail'])

    def test_invalid_limits_duplicate_arguments_and_write_methods_are_rejected(self):
        for query in ('limit=0', 'limit=-1', 'limit=1001', 'limit=NaN', 'limit=', 'limit=1&limit=2', 'other=1'):
            with self.subTest(query=query):
                self.assertEqual(self.request('/api/evidence?'+query)[0], 400)
        self.assertEqual(self.request('/api/topology', method='POST')[0], 405)
        self.assertEqual(self.request('/missing')[0], 404)

    def test_host_filter_is_a_bound_sql_value(self):
        status, body, _ = self.request('/api/evidence?host=%27%20OR%201%3D1--')
        self.assertEqual((status, body['rows']), (200, []))

    def test_api_does_not_write_database_or_create_missing_database(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.request('/api/topology'); self.request('/api/evidence')
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.db.unlink()
        status, body, _ = self.request('/api/topology')
        self.assertEqual(status, 503); self.assertIn('error', body)
        self.assertFalse(self.db.exists())

    def test_other_origins_and_nonloopback_binding_are_rejected(self):
        self.assertEqual(self.request('/api/topology', headers={'Origin': 'https://example.invalid'})[0], 403)
        with self.assertRaises(ValueError):
            self.api.make_server(self.db, bind='0.0.0.0')

    def test_live_stream_sends_only_new_rows_once_and_is_silent_when_idle(self):
        connection, reader = self.stream()
        self.assertEqual(select.select([connection], [], [], 0.65)[0], [])
        first = self.record(self.storage, result='TIMEOUT')
        second = self.record(self.storage, host='192.0.2.12', source='sim')
        self.assertEqual(self.event(reader), first)
        self.assertEqual(self.event(reader), second)
        self.assertEqual(select.select([connection], [], [], 0.65)[0], [])

    def test_stream_resume_uses_last_event_id_without_duplicates(self):
        next_row = self.record(self.storage, result='REFUSED')
        _, reader = self.stream(last_id=self.initial['id'])
        self.assertEqual(self.event(reader), next_row)


if __name__ == '__main__':
    unittest.main()
