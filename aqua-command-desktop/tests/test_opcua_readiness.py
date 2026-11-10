"""Readiness gates use explicit inputs and one attempt; real OPC UA stays on loopback."""

import contextlib
import io
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from collector import probe_once
from desktop.opcua_pki import PkiManager
from tools import check_opcua_readiness as readiness

SOURCE_ROOT = Path(probe_once.__file__).resolve().parents[2]
SWITCH = '10.0.78.1'
FIRST = '10.0.78.10'
SECOND = '10.0.78.11'
OK = ('ok', None, 1, {})
REFUSED = ('REFUSED', 'connection refused', 1, {})


def target(host, pki=None, *, endpoint=None, identifier='ns=1;s=Tank.Level', sim=False):
    port = 4850 if sim else 4840
    opcua = {
        'endpoint': endpoint or f'opc.tcp://{host}:{port}',
        'security_policy': 'Basic256Sha256',
        'nodes': {'Tank.Level': identifier},
    }
    if pki is not None:
        opcua['pki_dir'] = str(pki)
    return {'host': host, 'port': port, 'sim': sim, 'ua': opcua}


def write_config(directory, targets):
    path = directory / 'readiness.json'
    path.write_text(json.dumps({'targets': targets, 'ping_timeout_s': 1, 'tcp_timeout_s': 2}))
    return path


def states(station):
    return {item['stage']: item['status'] for item in station['stages']}


class ReadinessGates(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = write_config(self.directory, [target(FIRST), target(SECOND)])

    def test_default_is_configuration_only_and_creates_no_report(self):
        report = self.directory / 'report.json'
        with patch.object(readiness, 'run_readiness') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            status = readiness.main(['--config', str(self.config), '--switch', SWITCH, '--report', str(report)])
        self.assertEqual(status, 0)
        self.assertIn('No probes run', output.getvalue())
        run.assert_not_called()
        self.assertFalse(report.exists())

    def test_existing_report_blocks_probes_and_is_not_replaced(self):
        report = self.directory / 'report.json'
        report.write_text('existing')
        with patch.object(readiness, 'run_readiness') as run, contextlib.redirect_stderr(io.StringIO()):
            status = readiness.main(['--config', str(self.config), '--switch', SWITCH, '--report', str(report), '--execute'])
        self.assertEqual(status, 2)
        self.assertEqual(report.read_text(), 'existing')
        run.assert_not_called()

    def test_switch_failure_blocks_every_station_without_fabricated_evidence(self):
        config, switch = readiness.readiness_settings(self.config, SWITCH)
        with (
            patch.object(readiness, 'ping_check', return_value=('TIMEOUT', 'no response', 2, {})) as ping,
            patch.object(readiness, 'tcp_check') as tcp,
            patch.object(readiness, 'read_target') as opcua,
        ):
            report = readiness.run_readiness(config, switch)
        ping.assert_called_once_with(SWITCH, 1)
        tcp.assert_not_called()
        opcua.assert_not_awaited()
        checks = report['readiness']
        self.assertFalse(checks['passed'])
        self.assertEqual(checks['switch']['status'], 'FAIL')
        self.assertEqual([(row['host'], row['check']) for row in checks['evidence']], [(SWITCH, 'ping')])
        self.assertTrue(all(set(states(station).values()) == {'SKIPPED'} for station in checks['stations']))
        node = next(node for node in report['nodes'] if node['id'] == FIRST)
        self.assertIsNone(node['last'])
        self.assertEqual(node['via'], SWITCH)

    def test_tcp_failure_blocks_only_that_station(self):
        config, switch = readiness.readiness_settings(self.config, SWITCH)

        async def successful_protocol(target, timeout, store, output):
            self.assertNotEqual(target['ua']['pki_dir'], config['targets'][1]['ua'].get('pki_dir'))
            endpoint = target['ua']['endpoint']
            store.record(SECOND, 'ua_endpoints', ('ok', None, 1, {'endpoint': endpoint, 'endpoints': [{
                'security_policy': readiness.POLICY_BASIC256SHA256, 'security_mode': 'SignAndEncrypt',
            }]}))
            store.record(SECOND, 'ua_session', ('ok', None, 1, {
                'endpoint': endpoint, 'session_attempted': True, 'certificate_validation': {'valid': True},
            }))
            store.record_read(SECOND, 'Tank.Level', 'ns=1;s=Tank.Level', ('ok', None, 1, {'endpoint': endpoint}),
                              2.5, 'Good')
            store.record(SECOND, 'ua_close', OK)

        with (
            patch.object(readiness, 'ping_check', return_value=OK),
            patch.object(readiness, 'tcp_check', side_effect=(REFUSED, OK)) as tcp,
            patch.object(readiness, 'snapshot_pki', return_value='test fingerprint') as pki,
            patch.object(readiness, 'read_target', side_effect=successful_protocol) as opcua,
        ):
            report = readiness.run_readiness(config, switch)
        self.assertEqual(tcp.call_count, 2)
        pki.assert_called_once()
        opcua.assert_awaited_once()
        first, second = report['readiness']['stations']
        self.assertEqual(states(first)['TCP'], 'FAIL')
        self.assertEqual(states(first)['GetEndpoints'], 'SKIPPED')
        self.assertEqual(set(states(second).values()), {'PASS'})
        self.assertFalse(report['readiness']['passed'])
        self.assertEqual(report['readiness']['samples'][0]['value'], 2.5)

    def test_local_pki_failure_is_distinct_from_discovery(self):
        path = write_config(self.directory, [target(FIRST, self.directory / 'missing-pki')])
        config, switch = readiness.readiness_settings(path, SWITCH)
        with (
            patch.object(readiness, 'ping_check', return_value=OK),
            patch.object(readiness, 'tcp_check', return_value=OK),
            patch.object(readiness, 'read_target') as opcua,
        ):
            report = readiness.run_readiness(config, switch)
        opcua.assert_not_awaited()
        results = states(report['readiness']['stations'][0])
        self.assertEqual(results['Local PKI inputs'], 'FAIL')
        self.assertEqual(results['GetEndpoints'], 'SKIPPED')
        self.assertFalse(report['readiness']['passed'])

    def test_insecure_non_process_or_non_local_target_is_rejected_before_execution(self):
        insecure = target(FIRST)
        insecure['ua']['security_policy'] = 'None'
        multiple = target(FIRST)
        multiple['ua']['nodes']['Other'] = 'ns=1;s=Tank.Other'
        for invalid in (insecure, multiple, target(FIRST, identifier='i=2256'), target('192.0.2.15'),
                        target(FIRST, identifier='srv=1;ns=1;s=Tank.Level')):
            with self.subTest(target=invalid):
                path = write_config(self.directory, [invalid])
                with self.assertRaises(ValueError):
                    readiness.readiness_settings(path, SWITCH)
        with self.assertRaises(ValueError):
            readiness.readiness_settings(self.config, FIRST)


@unittest.skipUnless(os.getenv('AQUA_TEST_OPCUA_READINESS_LOOPBACK') == '1', 'explicit isolated loopback test')
class ReadinessLoopback(unittest.TestCase):
    def test_untrusted_rejection_then_secure_read_and_private_report(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            with (directory / 'server.log').open('w+') as log, subprocess.Popen(
                [sys.executable, '-B', str(SOURCE_ROOT / 'tools/sim/opcua_server.py'),
                 '--data-dir', str(directory / 'server'), '--level', '23.5'],
                stdout=subprocess.PIPE, stderr=log, text=True,
            ) as server:
                try:
                    self.assertTrue(select.select([server.stdout], [], [], 20)[0], 'Simulator readiness timed out')
                    line = server.stdout.readline()
                    if not line:
                        log.seek(0)
                        self.fail(log.read())
                    ready = json.loads(line)
                    pki = PkiManager(directory / 'client')
                    pki.ensure_client_certificate()
                    config = write_config(directory, [target('127.0.0.1', pki.pki_dir, endpoint=ready['endpoint'],
                                                             identifier=ready['node_id'], sim=True)])
                    settings, switch = readiness.readiness_settings(config, '127.0.0.2')
                    rejected = readiness.run_readiness(settings, switch)
                    rejected_checks = states(rejected['readiness']['stations'][0])
                    self.assertEqual(rejected_checks['GetEndpoints'], 'PASS')
                    self.assertEqual(rejected_checks['Server certificate'], 'FAIL')
                    self.assertEqual(rejected_checks['Open session'], 'SKIPPED')
                    self.assertEqual(rejected_checks['Read Value'], 'SKIPPED')
                    self.assertEqual(rejected_checks['Close session'], 'SKIPPED')
                    self.assertEqual(list(pki.rejected_certs_dir.iterdir()), [])
                    self.assertEqual(list(pki.trusted_certs_dir.iterdir()), [])

                    pki.trust_certificate(Path(ready['certificate']))
                    files_before = {item: item.read_bytes() for item in pki.pki_dir.rglob('*') if item.is_file()}
                    report_file = directory / 'secure-report.json'
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        status = readiness.main(['--config', str(config), '--switch', switch, '--execute',
                                                 '--report', str(report_file)])
                    self.assertEqual(status, 0)
                    self.assertIn('Server certificate', output.getvalue())
                    self.assertEqual(stat.S_IMODE(report_file.stat().st_mode), 0o600)
                    report = json.loads(report_file.read_text())
                    self.assertTrue(report['simulated'])
                    self.assertTrue(report['readiness']['passed'])
                    self.assertEqual(set(states(report['readiness']['stations'][0]).values()), {'PASS'})
                    sample, = report['readiness']['samples']
                    self.assertEqual((sample['value'], sample['quality']), (23.5, 'Good'))
                    self.assertEqual(files_before, {item: item.read_bytes() for item in pki.pki_dir.rglob('*')
                                                    if item.is_file()})
                finally:
                    server.terminate()
                    server.wait(timeout=10)
