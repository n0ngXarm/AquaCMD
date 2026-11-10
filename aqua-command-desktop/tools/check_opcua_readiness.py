"""Check one explicitly authorized OPC UA path per station without changing WinCC."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv4Network
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
from tempfile import TemporaryDirectory
import time

from asyncua import ua

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.evidence_api import detail
from collector.opcua_read import read_target
from collector.probe_once import EvidenceStore, load_settings, ping_check, tcp_check
from desktop.f3_handoff import project_f3
from desktop.opcua_pki import POLICY_BASIC256SHA256, PkiManager

FIELD_NETWORKS = tuple(map(IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))


def local_address(value):
    address = IPv4Address(value)
    if not address.is_loopback and not any(address in network for network in FIELD_NETWORKS):
        raise ValueError("Readiness requires explicit RFC 1918 IPv4 addresses or isolated loopback")
    return address


def readiness_settings(config, switch):
    """Narrow the existing collector configuration to a single, bounded pass."""
    settings = load_settings(config)
    if settings['internet'] is not None or settings['interval_s'] is not None:
        raise ValueError("Remove internet and interval_s from the readiness configuration")
    targets = settings['targets']
    if not 1 <= len(targets) <= 4:
        raise ValueError("Select one to four explicitly approved station targets")
    switch = local_address(switch)
    for target in targets:
        address = local_address(target['host'])
        if address == switch:
            raise ValueError("The switch must be different from each OPC UA station")
        simulated = target['source'] == 'sim'
        if address.is_loopback != simulated or switch.is_loopback != simulated:
            raise ValueError("Use a separate loopback switch address only for a simulated run")
        if target['port'] != (4850 if simulated else 4840):
            raise ValueError("Station TCP port must be 4840 (4850 for the loopback simulator)")
        opcua = target.get('ua')
        if not opcua or opcua['security_policy'] != 'Basic256Sha256' or len(opcua['nodes']) != 1:
            raise ValueError("Each station requires Basic256Sha256 and one approved Tag-to-NodeId mapping")
        tag, identifier = next(iter(opcua['nodes'].items()))
        node = ua.NodeId.from_string(identifier)
        if not tag.strip() or node.NamespaceIndex <= 0 or isinstance(node, ua.ExpandedNodeId) or node.to_string() != identifier:
            raise ValueError("Choose a process Tag with an exact nonstandard namespace NodeId")
    return settings, str(switch)


def snapshot_pki(original, destination, timeout):
    """Use the existing identity/trust inputs without changing the operator's PKI."""
    for relative in ('own/certs/client_cert.der', 'own/private/client_key.pem'):
        target = destination / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(target, 'xb', opener=private_opener) as output:
            output.write((original / relative).read_bytes())

    certificate = PkiManager.load_cert_from_file(destination / 'own/certs/client_cert.der')
    key = PkiManager.load_key_from_file(destination / 'own/private/client_key.pem')
    now = datetime.now(timezone.utc)
    if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc - timedelta(seconds=timeout + 1):
        raise ValueError("The existing client certificate is not valid for the discovery window")
    if not PkiManager.validate_key_pair(certificate, key):
        raise ValueError("The existing client certificate and private key do not match")

    for relative, extensions in (
        ('trusted/certs', ('.der', '.pem', '.crt')),
        ('issuers/certs', ('.der', '.pem', '.crt')),
        ('issuers/crl', ('.der', '.pem', '.crl')),
    ):
        target = destination / relative
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        for entry in (original / relative).iterdir() if (original / relative).exists() else ():
            if entry.is_file() and entry.suffix.lower() in extensions:
                (target / entry.name).write_bytes(entry.read_bytes())
    return PkiManager.cert_thumbprint(certificate)


def private_opener(path, flags):
    return os.open(path, flags, 0o600)


def stage(name, row, *, verified=None, reason=None):
    if row is None:
        return {'stage': name, 'status': 'SKIPPED', 'reason': reason or 'No attempted check'}
    passed = row['result'] == 'ok' if verified is None else verified
    return {
        'stage': name,
        'status': 'PASS' if passed else 'FAIL',
        'reason': reason or row['error'] or row['result'],
        'evidence_id': row['id'],
    }


def station_report(target, checks, switch_passed):
    tcp = checks.get('tcp')
    local_pki = checks.get('ua_pki_local')
    discovery = checks.get('ua_endpoints')
    session = checks.get('ua_session')
    read = checks.get('ua_read')
    close = checks.get('ua_close')
    blocked = 'Switch did not pass' if not switch_passed else None
    discovery_detail = detail(discovery) if discovery else {}
    offered = any(
        item['security_policy'] == POLICY_BASIC256SHA256 and item['security_mode'] == 'SignAndEncrypt'
        for item in discovery_detail.get('endpoints', [])
    )
    session_detail = detail(session) if session else {}
    session_attempted = session_detail.get('session_attempted') is True
    session_open = bool(session_attempted and session['result'] == 'ok')
    validation = session_detail.get('certificate_validation') or {}
    cert_checked = bool(validation) or (
        offered and session and session['result'] == 'CERT_ERROR' and not session_attempted
    )
    cert_valid = validation.get('valid') is True
    certificate_reason = None
    if cert_valid:
        certificate_reason = 'Trusted server certificate'
    elif cert_checked:
        certificate_reason = validation.get('error') or session['error']

    return {
        'host': target['host'],
        'tag': next(iter(target['ua']['nodes'])),
        'stages': [
            stage('TCP', tcp, reason=blocked),
            stage('Local PKI inputs', local_pki, reason='TCP did not pass' if local_pki is None else None),
            stage(
                'GetEndpoints',
                discovery,
                verified=bool(discovery and discovery['result'] == 'ok' and offered),
                reason=(
                    ('Basic256Sha256 / SignAndEncrypt offered' if offered else 'Required secure endpoint was not offered')
                    if discovery and discovery['result'] == 'ok' else
                    ('Local PKI preflight did not pass' if discovery is None else None)
                ),
            ),
            stage(
                'Server certificate', session if cert_checked else None, verified=cert_valid,
                reason=certificate_reason or 'Secure endpoint discovery did not pass',
            ),
            stage('Open session', session if session_attempted or cert_valid else None,
                  verified=session_open,
                  reason='Secure endpoint or certificate did not pass' if not (session_attempted or cert_valid) else None),
            stage('Read Value', read, reason='Session did not pass' if read is None else None),
            stage('Close session', close if session_open else None,
                  reason='No established session' if not session_open else None),
        ],
    }


def run_readiness(settings, switch):
    targets = settings['targets']
    source = targets[0]['source']
    timeout = settings['tcp_timeout_s']
    with TemporaryDirectory(prefix='aqua-opcua-readiness-') as directory:
        directory = Path(directory)
        store = EvidenceStore(directory / 'evidence.db')
        try:
            ping = store.record(switch, 'ping', ping_check(switch, settings['ping_timeout_s']), source)
            if ping['result'] == 'ok':
                for target in targets:
                    host = target['host']
                    tcp = store.record(host, 'tcp', tcp_check(host, target['port'], timeout), source)
                    if tcp['result'] != 'ok':
                        continue
                    original = Path(target['ua'].get('pki_dir', Path.home() / '.config/aqua-command/pki'))
                    destination = directory / host
                    started = time.perf_counter()
                    try:
                        fingerprint = snapshot_pki(original, destination, timeout)
                    except (OSError, ValueError, TypeError) as error:
                        elapsed = (time.perf_counter() - started) * 1000
                        store.record(host, 'ua_pki_local', ('CERT_ERROR', str(error), elapsed, {}), source)
                        continue
                    elapsed = (time.perf_counter() - started) * 1000
                    store.record(host, 'ua_pki_local', ('ok', None, elapsed, {'client_sha256': fingerprint}), source)
                    isolated = {**target, 'ua': {**target['ua'], 'pki_dir': str(destination)}}
                    asyncio.run(read_target(isolated, timeout, store, lambda _: None))
            rows = [dict(row) for row in store.connection.execute('SELECT * FROM probe_evidence ORDER BY id')]
            samples = [dict(row) for row in store.connection.execute('SELECT * FROM tag_samples ORDER BY id')]
        finally:
            store.close()

        projection_settings = {**settings, 'targets': [*targets, {'host': switch, 'kind': 'router', 'source': source}]}
        report = project_f3(store.path, projection_settings, {switch: {'kind': 'switch'}})
        switch_stage = stage('Switch ping', ping)
        stations = [
            station_report(target, {row['check']: row for row in rows if row['host'] == target['host']},
                           switch_passed=ping['result'] == 'ok')
            for target in targets
        ]
        passed = switch_stage['status'] == 'PASS' and all(
            check['status'] == 'PASS' for station in stations for check in station['stages']
        )
        report['readiness'] = {
            'passed': passed, 'switch': {'host': switch, **switch_stage}, 'stations': stations,
            'evidence': [{**row, 'detail': detail(row)} for row in rows],
            'samples': [{**sample, 'value': json.loads(sample['value'])} for sample in samples],
        }
        return report


def print_table(readiness):
    print(f"{'Target':<15} {'Stage':<19} {'Result':<7} Detail")
    print('-' * 72)
    rows = [(readiness['switch']['host'], readiness['switch'])]
    rows.extend((item['host'], check) for item in readiness['stations'] for check in item['stages'])
    for host, check in rows:
        reason = ''.join(character if character.isprintable() else ' ' for character in check['reason'])
        reason = ' '.join(reason.split())
        print(f"{host:<15} {check['stage']:<19} {check['status']:<7} {reason}")


def report_destination(path):
    path = path.parent.resolve() / path.name
    source_root = next((parent for parent in (ROOT, *ROOT.parents) if (parent / '.git').exists()), ROOT)
    if path.is_relative_to(source_root):
        raise ValueError("Store the readiness report outside the source repository")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path, help='private collector configuration')
    parser.add_argument('--switch', required=True, help='explicit IPv4 address of the approved switch')
    parser.add_argument('--report', type=Path, help='new JSON report path outside the source repository')
    parser.add_argument('--execute', action='store_true', help='explicitly authorize one read-only pass')
    options = parser.parse_args(argv)
    if options.execute and options.report is None:
        parser.error('--execute requires --report')

    try:
        settings, switch = readiness_settings(options.config, options.switch)
        if not options.execute:
            print(f"Configuration only: switch {switch}; stations " +
                  ', '.join(target['host'] for target in settings['targets']))
            print('No probes run. Use --execute with a private --report after approval.')
            return 0
        destination = report_destination(options.report)
        with open(destination, 'x', encoding='utf-8', opener=private_opener) as output:
            report = run_readiness(settings, switch)
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write('\n')
        print_table(report['readiness'])
        return 0 if report['readiness']['passed'] else 1
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Readiness stopped: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Readiness interrupted", file=sys.stderr)
        return 130


def stop(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, stop)
    sys.exit(main())
