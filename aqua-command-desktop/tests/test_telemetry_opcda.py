from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from collector import telemetry


def gateway_snapshot(path, now, *, source='PC-01', simulated=False, source_adapter='wincc-opc-da'):
    def observed(value, stamp, **extra):
        return {'raw_value': value, 'quality': 'GOOD', 'quality_code': 192,
                'read_error': 0, 'source_timestamp': stamp, **extra}
    event = {
        'schema': 'aqua.runtime.v3', 'source_id': source, 'source_adapter': source_adapter,
        'kind': 'SNAPSHOT', 'simulated': simulated, 'read_at': now.isoformat(), 'observed_at': now.isoformat(),
        'values': {'Tank.Level': None, 'Pump.Run': True, 'Other.Level': None},
        'observations': {
            'Tank.Level': observed(73.25, (now - timedelta(seconds=90)).isoformat(), value_type='analog'),
            'Pump.Run': observed(1, now.isoformat()),
            'Other.Level': observed(0.0, None, value_type='analog'),
        },
    }
    data = json.dumps(event)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS records(source TEXT, kind TEXT, seq INTEGER, payload TEXT, digest TEXT)')
        db.execute('INSERT INTO records VALUES(?,?,?,?,?)',
                   (source, 'SNAPSHOT', 1, data, hashlib.sha256(data.encode()).hexdigest()))


class OpcDaTelemetryTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.db = self.directory / 'aqua.sqlite3'
        self.config = self.directory / telemetry.CONFIG_NAME
        self.raw = {'transport': 'opcda', 'source_id': 'PC-01', 'gateway_db': str(self.db),
                    'tags': ['Tank.Level', 'Pump.Run', 'Other.Level'], 'lab': True}
        self.now = datetime.now(timezone.utc)

    def test_collect_preserves_per_tag_age_and_leaves_gateway_untouched(self):
        gateway_snapshot(self.db, self.now)
        before = self.db.read_bytes()
        telemetry.save_config(self.config, self.raw)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 0)
        snapshot = telemetry.read_snapshot(self.directory / telemetry.DB_NAME,
                                           telemetry.load_config(self.config))
        self.assertEqual(snapshot['values']['Tank.Level'],
                         {'value': 73.25, 'quality': 'GOOD',
                          'observed_at': (self.now - timedelta(seconds=90)).isoformat()})
        self.assertIs(snapshot['values']['Pump.Run']['value'], True)
        self.assertIsNone(snapshot['values']['Other.Level']['observed_at'])
        self.assertEqual(before, self.db.read_bytes())

    def test_missing_or_unrelated_data_fails_without_creating_evidence(self):
        telemetry.save_config(self.config, self.raw)
        self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 1)
        self.assertFalse(self.db.exists())
        gateway_snapshot(self.db, self.now, source_adapter='wincc-csv')
        self.assertEqual(telemetry.main(['--config', str(self.config), '--read']), 1)
        self.assertFalse((self.directory / telemetry.DB_NAME).exists())

    def test_corrupt_digest_or_missing_tag_is_rejected(self):
        gateway_snapshot(self.db, self.now)
        source = telemetry.validate_config({**self.raw, 'tags': ['Not.In.Archive']})
        with self.assertRaisesRegex(ValueError, 'has no configured Tag'):
            telemetry.opcda_payload(source)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE records SET digest='incorrect'")
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            telemetry.opcda_payload(telemetry.validate_config(self.raw))
