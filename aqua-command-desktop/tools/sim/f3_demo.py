"""Run real read-only OPC UA calls against a local demonstration server."""
import argparse
import asyncio
import json
import signal
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from asyncua import Server, ua

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from collector.evidence_api import make_server
from collector.opcua_read import read_target
from collector.probe_once import EvidenceStore
from desktop.f3_projection import F3Projection
from f3_demo_delivery import DemoProjection, DeliveryError, finish_delivery, queue_example, send_message

DEMO_HOST = '127.0.0.1'
DEMO_PORT = 4850


async def run(directory, telegram_config=None, *, once=False):
    fixture = json.loads((ROOT / 'tests' / 'f3_demo_fixture.json').read_text())
    station = fixture['station']
    tasks = fixture['tasks']
    tag, identifier = next(iter(station['ua']['nodes'].items()))
    endpoint = f'opc.tcp://{DEMO_HOST}:{DEMO_PORT}'
    target = {
        'host': DEMO_HOST, 'port': DEMO_PORT, 'kind': 'device', 'source': 'sim',
        'ua': {'endpoint': endpoint, 'nodes': {tag: identifier}, 'security_policy': 'None'},
    }
    switch, router = fixture['switch'], fixture['router']
    settings = {'targets': [
        target, {'host': switch, 'kind': 'device', 'source': 'sim'},
        {'host': router, 'kind': 'router', 'source': 'sim'},
    ]}
    metadata = {
        DEMO_HOST: {'label': 'OPC UA Server จำลอง', 'kind': 'wincc'},
        switch: {'label': 'LAN Switch · ผังตัวอย่าง', 'kind': 'switch'},
        router: {'label': 'Router · ผังตัวอย่าง', 'kind': 'router'},
    }
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)

    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name('AQUA COMMAND SIMULATED')
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    await server.register_namespace('urn:aquacmd:f3-demo')
    await server.nodes.objects.add_variable(ua.NodeId.from_string(identifier), tag, station['value'])
    store = EvidenceStore(directory / 'demo.db')
    api = None
    thread = None
    try:
        async with server:
            api = make_server(store.path, settings=settings)
            projection = DemoProjection if telegram_config is not None else F3Projection
            api.reader = projection(api.reader, settings, metadata, task_groups=tasks)
            thread = threading.Thread(target=api.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
            thread.start()
            print(json.dumps({'port': api.server_port}), flush=True)
            # Let F3 attach its event stream before the first OPC UA read.
            delivery_started = False
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), 3)
                except asyncio.TimeoutError:
                    rows = []
                    await read_target(target, 2, store, lambda row: rows.append(json.loads(row)))
                    if stop.is_set() or telegram_config is None or delivery_started:
                        continue
                    read = next((row for row in rows if row['check'] == 'ua_read' and row['result'] == 'ok'), None)
                    if read is None:
                        if once:
                            return 1
                        continue
                    delivery_started = True
                    text = queue_example(store, read, tasks, station['unit'])
                    if text is None:
                        if once:
                            return 1
                        continue
                    started = time.monotonic()
                    try:
                        message_id = await asyncio.to_thread(send_message, telegram_config, text)
                    except DeliveryError as error:
                        result = finish_delivery(store, read['id'], started, error=str(error))
                    else:
                        result = finish_delivery(store, read['id'], started, message_id=message_id)
                    print(json.dumps({'telegram': result['result'],
                                      'receipt': json.loads(result['detail'])}, ensure_ascii=False), file=sys.stderr)
                    if once:
                        return 0 if result['result'] == 'ok' else 1
            return 0
    finally:
        if api is not None:
            api.stop_event.set()
            if thread is not None:
                api.shutdown()
                thread.join()
            api.server_close()
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--telegram-config', type=Path)
    parser.add_argument('--once', action='store_true')
    options = parser.parse_args()
    if options.once and options.telegram_config is None:
        parser.error('--once requires --telegram-config')
    try:
        with TemporaryDirectory(prefix='aquacmd-f3-demo-') as temporary:
            raise SystemExit(asyncio.run(run(Path(temporary), options.telegram_config, once=options.once)))
    except Exception as error:
        print(f'F3 demo: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
