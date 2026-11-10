"""Read one allowlisted telemetry snapshot from HTTPS, MQTT or an OPC DA Gateway without issuing controls."""
import argparse
from contextlib import closing, suppress
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import monotonic, sleep
from urllib.parse import urlsplit

from .evidence_api import read_connection, detail
from .probe_once import EvidenceStore

MAX_BYTES = 65536
CONFIG_NAME = 'telemetry_source.json'
DB_NAME = 'telemetry-evidence.db'
READ_ERRORS = (OSError, ValueError, TypeError, RecursionError, OverflowError, http.client.HTTPException,
               sqlite3.Error, subprocess.TimeoutExpired)


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    if len(data) > MAX_BYTES:
        raise ValueError('JSON exceeds 64 KiB')
    return json.loads(data, object_pairs_hook=unique)


def load_config(path):
    with path.open('rb') as config:
        return validate_config(strict_json(config.read(MAX_BYTES + 1)))


def validate_config(source):
    if not isinstance(source, dict):
        raise ValueError('Expected a JSON configuration object')
    transport = source.get('transport')
    specific = {
        'rest': {'url', 'ca_file', 'token_file'},
        'mqtt': {'url', 'ca_file', 'topic', 'client_cert', 'client_key'},
        'opcda': {'gateway_db'},
    }
    if transport not in ('rest', 'mqtt', 'opcda'):
        raise ValueError('Select REST, MQTT or OPC DA')
    if set(source) - ({'transport', 'source_id', 'tags', 'timeout_s', 'lab'} | specific[transport]):
        raise ValueError('Unexpected configuration field')
    name = source.get('source_id')
    url = source.get('url')
    tags = source.get('tags')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', name):
        raise ValueError('Invalid source_id')
    if not isinstance(tags, list) or not 1 <= len(tags) <= 100 or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 256 for tag in tags) or len(set(tags)) != len(tags):
        raise ValueError('Supply 1–100 unique exact Tag names')
    timeout, lab = source.get('timeout_s', 5), source.get('lab', False)
    if type(timeout) is not int or not 1 <= timeout <= 15 or type(lab) is not bool:
        raise ValueError('Invalid timeout_s or lab flag')
    if transport == 'opcda':
        db = source.get('gateway_db')
        if not isinstance(db, str) or not Path(db).is_absolute() or Path(db).name != 'aqua.sqlite3':
            raise ValueError('Select the absolute path to the Gateway aqua.sqlite3 file')
        if name not in ('PC-01', 'PC-02', 'PC-03'):
            raise ValueError('Select the Windows Reader source PC-01, PC-02 or PC-03')
        identity = [transport, name, str(Path(db).resolve()), sorted(tags), lab]
        binding = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        return {**source, 'binding': binding, 'timeout_s': timeout, 'lab': lab}
    if not isinstance(url, str) or not url or any(character.isspace() or ord(character) < 32 for character in url):
        raise ValueError('Invalid source URL')
    uri = urlsplit(url)
    secure, plain = ('https', 'http') if transport == 'rest' else ('mqtts', 'mqtt')
    if not uri.hostname or uri.username is not None or uri.fragment or uri.query or uri.port == 0:
        raise ValueError('Supply an explicit URL without credentials, query, or fragment')
    if lab and uri.hostname != '127.0.0.1':
        raise ValueError('LAB requires explicit IPv4 loopback')
    if uri.scheme != secure and not (lab and uri.scheme == plain):
        raise ValueError('TLS is required outside LAB')
    if transport == 'mqtt':
        topic = source.get('topic')
        if uri.path not in ('', '/') or not isinstance(topic, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', topic):
            raise ValueError('MQTT requires an exact topic without wildcards')
        if ('client_cert' in source) != ('client_key' in source):
            raise ValueError('Supply the MQTT client certificate and key together')
    for key in ('token_file', 'ca_file', 'client_cert', 'client_key'):
        if key in source:
            if uri.scheme != secure or not isinstance(source[key], str) or not Path(source[key]).is_absolute():
                raise ValueError('Credentials and certificate files require TLS and absolute paths')
    identity = [transport, name, url, sorted(tags), source.get('topic'), lab]
    binding = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    return {**source, 'uri': uri, 'binding': binding, 'timeout_s': timeout, 'lab': lab}


def save_config(path, source):
    validate_config(source)
    encoded = json.dumps(source, ensure_ascii=False, indent=2)
    if len(encoded.encode('utf-8')) > MAX_BYTES:
        raise ValueError('JSON exceeds 64 KiB')
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            temporary.replace(path)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()


def rest_payload(source):
    uri = source['uri']
    headers = {'Accept': 'application/json'}
    if 'token_file' in source:
        token_file = Path(source['token_file'])
        with token_file.open('rb') as handle:
            token = handle.read(4097).decode('ascii').strip()
        if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', token):
            raise ValueError('Invalid bearer token file')
        headers['Authorization'] = 'Bearer ' + token
    options = {'timeout': source['timeout_s']}
    if uri.scheme == 'https':
        connection = http.client.HTTPSConnection(uri.hostname, uri.port, **options,
            context=ssl.create_default_context(cafile=source.get('ca_file')))
    else:
        connection = http.client.HTTPConnection(uri.hostname, uri.port, **options)
    with closing(connection):
        connection.request('GET', uri.path or '/', headers=headers)
        with connection.getresponse() as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/json':
                raise ValueError(f'REST did not return a JSON snapshot (HTTP {response.status})')
            return response.read(MAX_BYTES + 1)


def mqtt_payload(source):
    uri = source['uri']
    timeout = source['timeout_s']
    with TemporaryDirectory(prefix='aqua-mqtt-') as temporary:
        # An explicit empty options file prevents ambient defaults from selecting other topics.
        options = Path(temporary) / 'options'
        options.touch()
        args = ['mosquitto_sub', '-o', str(options), '-h', uri.hostname, '-p',
                str(uri.port or (8883 if uri.scheme == 'mqtts' else 1883)),
                '-t', source['topic'], '-q', '1', '-R', '-C', '1', '-W', str(timeout),
                '-V', 'mqttv5', '-D', 'connect', 'maximum-packet-size', str(MAX_BYTES),
                '-N', '-F', '%x']
        if uri.scheme == 'mqtts':
            args += ['--cafile', source['ca_file']] if 'ca_file' in source else ['--tls-use-os-certs']
            if 'client_cert' in source:
                args += ['--cert', source['client_cert'], '--key', source['client_key']]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=timeout + 2, check=False)
        if result.returncode:
            raise ValueError(f'MQTT did not deliver a fresh snapshot (exit {result.returncode})')
        if len(result.stdout) > MAX_BYTES * 2:
            raise ValueError('MQTT snapshot exceeds 64 KiB')
        return bytes.fromhex(result.stdout.decode('ascii'))


def opcda_payload(source):
    uri = Path(source['gateway_db']).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=0.5)) as gateway:
        row = gateway.execute(
            "SELECT payload, digest FROM records WHERE source=? AND kind='SNAPSHOT' ORDER BY seq DESC LIMIT 1",
            (source['source_id'],)).fetchone()
    if not row:
        raise ValueError('ยังไม่มี snapshot จาก Windows Reader รหัสนี้ใน Gateway')
    payload, digest = row
    raw = payload.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Gateway snapshot digest mismatch')
    event = strict_json(raw)
    if not isinstance(event, dict) or event.get('schema') != 'aqua.runtime.v3' or (
            event.get('source_adapter') != 'wincc-opc-da' or event.get('simulated') is not False or
            event.get('source_id') != source['source_id'] or event.get('kind') != 'SNAPSHOT' or
            event.get('observed_at') != event.get('read_at')):
        raise ValueError('หลักฐานล่าสุดของแหล่งนี้ไม่ได้มาจาก Windows OPC DA Reader')
    observations, pumps = event.get('observations'), event.get('values')
    if not isinstance(observations, dict) or not isinstance(pumps, dict):
        raise ValueError('Invalid OPC DA observation')
    values = {}
    for tag in source['tags']:
        item = observations.get(tag)
        if not isinstance(item, dict):
            raise ValueError(f'Gateway snapshot has no configured Tag: {tag}')
        quality, code, error = item.get('quality'), item.get('quality_code'), item.get('read_error')
        value = item.get('raw_value') if item.get('value_type') == 'analog' else pumps.get(tag)
        stamp = item.get('source_timestamp')
        if quality == 'GOOD':
            if type(code) is not int or code & 0xc0 != 0xc0 or type(error) is not int or error != 0:
                raise ValueError('Contradictory GOOD quality in Gateway snapshot')
            if item.get('value_type') == 'analog':
                if type(value) not in (float, int) or pumps.get(tag) is not None:
                    raise ValueError('Invalid OPC DA Analog value')
                value = float(value)
            elif type(value) is not bool or item.get('raw_value') != int(value):
                raise ValueError('Invalid OPC DA pump value')
        else:
            value = None
            quality = 'BAD' if quality == 'BAD' else 'UNCERTAIN'
        values[tag] = {'value': value, 'quality': quality, 'observed_at': stamp}
    return json.dumps({'observed_at': event.get('read_at'), 'values': values}, ensure_ascii=False).encode()


def source_time(observed, now):
    if not isinstance(observed, str) or 'T' not in observed:
        raise ValueError('Expected an ISO 8601 timestamp with offset')
    stamp = datetime.fromisoformat(observed)
    if stamp.tzinfo is None or stamp > now:
        raise ValueError('Timestamp is missing its offset or is in the future')
    return stamp.astimezone(timezone.utc)


def decode_snapshot(payload, tags, now, *, per_tag_time=False):
    body = strict_json(payload)
    if not isinstance(body, dict) or set(body) != {'observed_at', 'values'}:
        raise ValueError('Expected observed_at and values')
    stamp = source_time(body['observed_at'], now)
    values = body['values']
    if not isinstance(values, dict) or set(values) != set(tags):
        raise ValueError('Snapshot must match the configured Tag allowlist exactly')
    fields = {'value', 'quality', 'observed_at'} if per_tag_time else {'value', 'quality'}
    for reading in values.values():
        if not isinstance(reading, dict) or set(reading) != fields:
            raise ValueError('Each Tag requires value and quality')
        if per_tag_time and reading['observed_at'] is not None:
            reading['observed_at'] = source_time(reading['observed_at'], now).isoformat()
        value = reading['value']
        quality = reading['quality']
        if quality not in ('GOOD', 'BAD', 'UNCERTAIN'):
            raise ValueError('Unsupported quality')
        if value is None and quality != 'GOOD':
            continue
        if type(value) not in (bool, int, float) or (
                type(value) is int and abs(value) > 9007199254740991) or (
                type(value) is float and not math.isfinite(value)):
            raise ValueError('Expected a Boolean or finite number')
    return {'observed_at': stamp.astimezone(timezone.utc).isoformat(), 'values': values}


def latest(connection, source):
    row = connection.execute(
        'SELECT detail FROM probe_evidence WHERE host=? AND "check"=? AND source=? ORDER BY id DESC LIMIT 1',
        (source['binding'], source['transport'] + '_read', 'sim' if source['lab'] else 'real')).fetchone()
    return detail(row) if row else None


def save_snapshot(db_path, source, snapshot, elapsed_ms):
    with closing(EvidenceStore(db_path)) as evidence, evidence.connection:
        evidence.connection.execute('BEGIN IMMEDIATE')
        previous = latest(evidence.connection, source)
        if previous:
            current_time = datetime.fromisoformat(snapshot['observed_at'])
            previous_time = datetime.fromisoformat(previous['observed_at'])
            if current_time <= previous_time:
                if current_time == previous_time and json.dumps(snapshot['values'], sort_keys=True) != json.dumps(
                        previous['values'], sort_keys=True):
                    raise ValueError('Conflicting values for an existing source timestamp')
                return False
        evidence.record(source['binding'], source['transport'] + '_read',
                        ('ok', None, elapsed_ms, {**snapshot, 'source_id': source['source_id']}),
                        'sim' if source['lab'] else 'real', commit=False)
        return True


def read_snapshot(db_path, source):
    with read_connection(db_path) as connection:
        return latest(connection, source)


def collect_once(config_path, source):
    acquire = {'rest': rest_payload, 'mqtt': mqtt_payload, 'opcda': opcda_payload}[source['transport']]
    start = monotonic()
    payload = acquire(source)
    elapsed_ms = (monotonic() - start) * 1000
    snapshot = decode_snapshot(payload, source['tags'], datetime.now(timezone.utc),
                               per_tag_time=source['transport'] == 'opcda')
    saved = save_snapshot(config_path.parent / DB_NAME, source, snapshot, elapsed_ms)
    print(f'{source["transport"].upper()} {"SIMULATED " if source["lab"] else ""}'
          f'{"recorded" if saved else "duplicate or older snapshot ignored"} · {len(snapshot["values"])} Tag(s)',
          flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--read', action='store_true', help='Explicitly authorize a request or subscription')
    parser.add_argument('--interval', type=int, metavar='SECONDS', help='Repeat until stopped, waiting 5–600 seconds between attempts')
    args = parser.parse_args(argv)
    if args.interval is not None and (not args.read or not 5 <= args.interval <= 600):
        parser.error('--interval requires --read and 5–600 seconds')
    try:
        source = load_config(args.config)
        if not args.read:
            print('Configuration valid. No connection opened.')
            return 0
        if args.interval is None:
            collect_once(args.config, source)
            return 0
        while True:
            try:
                collect_once(args.config, source)
            except READ_ERRORS as error:
                print(f'Telemetry attempt failed: {error}', file=sys.stderr)
            sleep(args.interval)
            if load_config(args.config) != source:
                raise ValueError('Configuration changed; restart the collector to authorize the new source')
    except READ_ERRORS as error:
        print(f'Telemetry stopped: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
