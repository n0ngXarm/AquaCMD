import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch

from collector import telemetry


def payload(stamp, value=73.25, quality='GOOD'):
    return json.dumps({'observed_at': stamp.isoformat(),
                       'values': {'Tank.Level': {'value': value, 'quality': quality}}}).encode()


class TelemetryFixture(unittest.TestCase):
    def setUp(self):
        private = TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.root = Path(private.name)
        self.config = self.root / telemetry.CONFIG_NAME
        self.db = self.root / telemetry.DB_NAME
        self.now = datetime.now(timezone.utc)

    def source(self, **updates):
        config = {'transport': 'rest', 'url': 'http://127.0.0.1:8787/latest', 'lab': True,
                  'source_id': 'lab-station', 'tags': ['Tank.Level'], **updates}
        self.config.write_text(json.dumps(config))
        return telemetry.load_config(self.config)


class TelemetryTest(TelemetryFixture):
    def test_config_only_has_no_side_effects(self):
        self.source()
        self.assertEqual(telemetry.main(['--config', str(self.config)]), 0)
        self.assertFalse(self.db.exists())

    def test_loop_stops_before_reading_a_changed_source(self):
        self.source()
        with patch.object(telemetry, 'collect_once') as collect, patch.object(
                telemetry, 'sleep', side_effect=lambda _: self.source(url='http://127.0.0.1:8081/latest')):
            status = telemetry.main(['--config', str(self.config), '--read', '--interval', '5'])
        self.assertEqual(status, 1)
        collect.assert_called_once()

    def test_invalid_configs(self):
        for options in (
                {'lab': False}, {'url': 'http://192.0.2.1/latest'}, {'tags': ['Tank.Level'] * 2},
                {'transport': 'mqtt', 'url': 'mqtt://127.0.0.1', 'topic': 'station/#'},
                {'url': 'http://user@127.0.0.1:8787/latest'},
                {'url': 'http://127.0.0.1/latest?token=hidden'},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.source(**options)

    def test_rejects_unknown_tags_nonfinite_future_and_duplicate_keys(self):
        tags = ['Tank.Level']
        cases = (payload(self.now, float('nan')), payload(self.now + timedelta(seconds=1)),
                 payload(self.now, None), payload(self.now).replace(b'Tank.Level', b'Other.Tag'),
                 b'{"observed_at": "2026-01-01T00:00:00Z", "values": {}, "values": {}}')
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                telemetry.decode_snapshot(case, tags, self.now)

    def test_record_preserves_source_time_and_ignores_replay(self):
        source = self.source()
        values = telemetry.decode_snapshot(payload(self.now, 0), source['tags'], self.now)
        self.assertTrue(telemetry.save_snapshot(self.db, source, values, 1.2))
        self.assertFalse(telemetry.save_snapshot(self.db, source, values, 1.0))
        older = telemetry.decode_snapshot(payload(self.now - timedelta(seconds=70)), source['tags'], self.now)
        self.assertFalse(telemetry.save_snapshot(self.db, source, older, 1.0))
        other = telemetry.decode_snapshot(payload(self.now, 1), source['tags'], self.now)
        with self.assertRaises(ValueError):
            telemetry.save_snapshot(self.db, source, other, 1.0)
        self.assertEqual(telemetry.read_snapshot(self.db, source)['values'], values['values'])
        self.assertEqual(telemetry.read_snapshot(self.db, source)['observed_at'], self.now.isoformat())
        other_source = self.source(url='http://127.0.0.1:8788/latest')
        self.assertIsNone(telemetry.read_snapshot(self.db, other_source))
        with telemetry.read_connection(self.db) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM probe_evidence').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT source FROM probe_evidence').fetchone()[0], 'sim')


@unittest.skipUnless(os.environ.get('AQUA_TELEMETRY_LOOPBACK_TEST'), 'run only in an isolated loopback namespace')
@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required for local TLS fixtures')
class TransportTest(TelemetryFixture):
    def certificate(self):
        cert, key = self.root / 'cert.pem', self.root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=IP:127.0.0.1', '-out', str(cert), '-keyout', str(key)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return cert, key

    def test_rest_snapshot_requires_trust_and_does_not_follow_redirect(self):
        requests = []
        data = payload(self.now)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, self.headers.get('Authorization')))
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/latest')
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        cert, key = self.certificate()
        token = self.root / 'token'
        token.write_text('fixture-token')
        with HTTPServer(('127.0.0.1', 0), Handler) as server:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            worker = Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f'https://127.0.0.1:{server.server_port}'
                self.source(url=base + '/latest')
                self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 1)
                self.assertFalse(self.db.exists())
                source = self.source(url=base + '/latest', ca_file=str(cert), token_file=str(token))
                self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 0)
                self.assertEqual(telemetry.read_snapshot(self.db, source)['values']['Tank.Level']['value'], 73.25)
                self.source(url=base + '/redirect', ca_file=str(cert))
                self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 1)
                self.assertEqual(requests, [('/latest', 'Bearer fixture-token'), ('/redirect', None)])
            finally:
                server.shutdown()
                worker.join()

    @unittest.skipUnless(all(shutil.which(cmd) for cmd in ('mosquitto', 'mosquitto_pub', 'mosquitto_sub')),
                         'Mosquitto tools required')
    def test_mqtt_exact_topic_ignores_retained_snapshot(self):
        with closing(socket.socket()) as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        cert, key = self.certificate()
        broker_config = self.root / 'broker.conf'
        user = 'user root\n' if os.geteuid() == 0 else ''
        broker_config.write_text(f'{user}listener {port} 127.0.0.1\nallow_anonymous true\n'
                                 f'certfile {cert}\nkeyfile {key}\n')
        with subprocess.Popen(['mosquitto', '-c', str(broker_config)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) as broker:
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1', port), .1):
                            break
                    except OSError:
                        time.sleep(.02)
                else:
                    self.fail('Broker did not start')
                topic = 'lab/snapshot'
                pub = ['mosquitto_pub', '-h', '127.0.0.1', '-p', str(port), '-q', '1', '--cafile', str(cert)]
                subprocess.run([*pub, '-t', topic, '-r', '-s'], input=payload(self.now, 12.5), check=True)
                source = self.source(transport='mqtt', url=f'mqtts://127.0.0.1:{port}',
                                     topic=topic, ca_file=str(cert), timeout_s=4)
                command = [sys.executable, '-B', '-m', 'collector.telemetry', '--config', str(self.config), '--read']
                with subprocess.Popen(command) as collector:
                    try:
                        for _ in range(24):
                            if collector.poll() is not None:
                                break
                            subprocess.run([*pub, '-t', 'lab/other', '-s'], input=payload(self.now, 31.0), check=True)
                            subprocess.run([*pub, '-t', topic, '-s'], input=payload(self.now, 73.25), check=True)
                            time.sleep(.12)
                        self.assertEqual(collector.wait(timeout=6), 0)
                    finally:
                        if collector.poll() is None:
                            collector.kill()
                self.assertEqual(telemetry.read_snapshot(self.db, source)['values']['Tank.Level']['value'], 73.25)
            finally:
                broker.terminate()
