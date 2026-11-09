"""Actual phase 2 HTTP/SSE with sample rows exclusively in a temporary tests/ DB."""
import json
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collector.evidence_api import EvidenceHandler, make_server
from collector.probe_once import EvidenceStore
from desktop.f3_api_view import build_html

flags = {'topology_error': False, 'stream_error': False}


class ControlledHandler(EvidenceHandler):
    def do_GET(self):
        if self.path.startswith('/api/topology') and flags['topology_error']:
            self.json_response(503, {'error': 'Controlled test API outage'})
            return
        super().do_GET()


with tempfile.TemporaryDirectory(prefix='.phase3-browser-', dir=ROOT/'tests') as temporary:
    directory = Path(temporary)
    store = EvidenceStore(directory/'data.db')
    hosts = [f'192.0.2.{number}' for number in range(11, 17)]+['198.51.100.1']
    metadata = {host: {'label': 'Test source '+host, 'zone': 'SCADA_OT', 'kind': 'wincc'} for host in hosts}
    metadata[hosts[-1]] = {'label': 'Test router', 'zone': 'EXTERNAL_WAN', 'kind': 'router'}
    (directory/'page.html').write_text(build_html(metadata))

    def record(host, check='tcp', result='ok', source='real', error=None):
        return store.record(host, check, (result, error, 0.35, {'test': 'sample row in temporary tests DB'}), source=source)

    record(hosts[0], result='TIMEOUT', error='timed out <img src=x onerror=alert(1)>')
    record(hosts[1])
    record(hosts[2], check='ua_session')
    record(hosts[3], check='ua_read', source='sim')
    old = record(hosts[4], result='REFUSED', error='connection refused')
    record(hosts[-1], result='REFUSED', error='connection refused')
    store.connection.execute('UPDATE probe_evidence SET ts=? WHERE id=?',
                             ((datetime.now(timezone.utc)-timedelta(seconds=70)).isoformat(), old['id']))
    store.connection.commit()

    def start(port=0):
        server = make_server(store.path, hosts=hosts, port=port)
        server.RequestHandlerClass = ControlledHandler
        original = server.reader.after

        def after(cursor):
            if flags['stream_error']:
                raise sqlite3.OperationalError('Controlled test stream failure')
            return original(cursor)

        server.reader.after = after
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        return server, worker

    server, worker = start()
    port = server.server_port
    print(json.dumps({'ready': True, 'url': f'http://127.0.0.1:{port}', 'html': str(directory/'page.html')}), flush=True)
    try:
        for line in sys.stdin:
            command = json.loads(line)
            answer = {'request': command['request'], 'ok': True}
            try:
                action = command['action']
                if action == 'insert':
                    answer['row'] = record(command.get('host', hosts[0]), command.get('check', 'tcp'),
                                           command.get('result', 'ok'), command.get('source', 'real'), command.get('error'))
                elif action == 'snapshot':
                    answer['topology'] = server.reader.topology()
                    answer['rows'] = [dict(row) for row in store.connection.execute('SELECT * FROM probe_evidence ORDER BY id')]
                elif action == 'topology_error':
                    flags['topology_error'] = bool(command['value'])
                elif action == 'stream_error':
                    flags['stream_error'] = bool(command['value'])
                elif action == 'stop_api':
                    server.stop_event.set();server.shutdown();server.server_close();worker.join(timeout=3)
                elif action == 'start_api':
                    server, worker = start(port)
                elif action == 'age':
                    store.connection.execute('UPDATE probe_evidence SET ts=?',
                        ((datetime.now(timezone.utc)-timedelta(seconds=70)).isoformat(),))
                    store.connection.commit()
                elif action == 'many':
                    for number in range(30, 70):
                        record(f'192.0.2.{number}', result='TIMEOUT', error='controlled timeout')
                elif action == 'quit':
                    print(json.dumps(answer), flush=True)
                    break
                else:
                    raise ValueError('Unknown test action')
            except Exception as error:
                answer.update(ok=False, error=type(error).__name__+': '+str(error))
            print(json.dumps(answer), flush=True)
    finally:
        server.stop_event.set();server.shutdown();server.server_close();worker.join(timeout=3)
        store.close()
