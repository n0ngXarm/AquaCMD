"""Exercise the real GTK wrapper against a temporary SQLite database on loopback."""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collector.probe_once import EvidenceStore
from desktop import f3_api_view
from desktop.f3_api_view import F3ApiView, GLib, Gtk, WebKit

HOSTS = [f'192.0.2.{number}' for number in range(11, 15)]
SWITCH = '192.0.2.254'
ROUTER = '198.51.100.1'
ENDPOINTS = {host: f'opc.tcp://{host}:4840' for host in HOSTS}


def until(predicate, label, seconds=12):
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError(label)


def javascript(view, expression):
    result = []

    def completed(web, task):
        try:
            result.append(web.evaluate_javascript_finish(task).to_string())
        except GLib.Error as error:
            result.append(error)

    view.web.evaluate_javascript(expression, -1, None, None, None, completed)
    until(lambda: result, f'JavaScript result: {expression}', 4)
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0]


with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as temporary:
    directory = Path(temporary)
    inventory = [{'configured_ip': host, 'type': 'wincc', 'alias': f'Station {i}'}
                 for i, host in enumerate(HOSTS, 1)]
    inventory.extend([{'configured_ip': SWITCH, 'type': 'switch', 'alias': 'LAN Switch'},
                      {'configured_ip': ROUTER, 'type': 'router', 'alias': 'Router'}])
    (directory / 'network_topology.json').write_text(json.dumps({'devices': inventory}))
    config = [{'host': host, 'port': 4840, 'ua': {'endpoint': ENDPOINTS[host], 'nodes': {'Level': 'i=2256', 'Pump': 'i=2257'}, 'security_policy': 'None'}}
              for host in HOSTS]
    config.extend({'host': host, 'kind': 'router' if host == ROUTER else 'device',
                   **({'port': 4840} if host == SWITCH else {})}
                  for host in (SWITCH, ROUTER))
    (directory / 'probe_targets.json').write_text(json.dumps(
        {'targets': config, 'ping_timeout_s': 1, 'tcp_timeout_s': 1}))
    store = EvidenceStore(directory / 'data.db')

    def record(host, check, result='ok', age=0, source='sim'):
        data = {'endpoint': ENDPOINTS.get(host)}
        row = store.record(host, check, (result, None if result == 'ok' else result, 1, data),
                           source=source, commit=False)
        if age:
            timestamp = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
            store.connection.execute('UPDATE probe_evidence SET ts=? WHERE id=?', (timestamp, row['id']))
        store.connection.commit()
        return row['id']

    for host in HOSTS:
        record(host, 'ua_read')
    record(SWITCH, 'ping')
    record(ROUTER, 'ping')
    record(HOSTS[0], 'ua_read', 'TIMEOUT', source='real')
    keys = []
    owner = SimpleNamespace(config_dir=directory, on_global_key_pressed=lambda _, key, *rest: keys.append(key),
                            tasks=[{'id': 'A', 'name': 'กลุ่มระดับน้ำ', 'tags': ['Level']},
                                   {'id': 'B', 'name': 'แจ้งเตือนระดับสูง', 'tags': ['Level']},
                                   {'id': 'C', 'name': 'ติดตามปั๊ม', 'tags': ['Pump']}])
    # The fixture writes rows directly. Mark the validated inventory as synthetic
    # without changing the collector's one-loopback-simulator rule.
    load_settings = f3_api_view.load_settings
    def fixture_settings(path):
        settings = load_settings(path)
        for target in settings['targets']:
            target['source'] = 'sim'
        return settings
    f3_api_view.load_settings = fixture_settings
    # Prevent the unrelated F1 OS inventory snapshot during this isolated UI test.
    F3ApiView.refresh_local_state = lambda self: None
    view = F3ApiView(owner, db_path=store.path)
    width, height = map(int, os.environ.get('F3_TEST_SIZE', '1240x870').split('x'))
    window = Gtk.Window(default_width=width, default_height=height)
    window.set_child(view.root_widget)
    window.present()

    def state(host):
        return javascript(view, f'document.getElementById("n-{host}")?.dataset.state ?? ""')

    def request(path, method='GET'):
        req = urllib.request.Request(view.api_url + path, method=method)
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    try:
        def ready():
            if view.error.get_visible():
                raise AssertionError(view.error.get_text())
            return view.api_url
        until(ready, 'WebKitGTK loopback API started')
        until(lambda: state(HOSTS[0]) == 'OK', 'first sample loads in native F3')
        data = request('/api/f3/evidence')
        assert data['simulated'] is True
        assert all(item['last']['source'] == 'sim' for item in data['nodes'] if item['last'])
        assert {item['id']: item['last']['ok'] for item in data['nodes'] if item['kind'] == 'scada'} == dict.fromkeys(HOSTS, True)
        for path, method, status in [('/api/f3/evidence?demo=1', 'GET', 400),
                                     ('/api/f3/evidence', 'POST', 405)]:
            try:
                request(path, method)
            except urllib.error.HTTPError as error:
                assert error.code == status
            else:
                raise AssertionError(f'{method} {path} accepted')
        print('PASS GET mapping, source segregation, demo query rejected, POST rejected', flush=True)

        if len(sys.argv) == 2:
            for theme in ('dark', 'light'):
                javascript(view, f'document.documentElement.dataset.theme = "{theme}"; "theme set"')
                saved = []
                def capture(web, result):
                    texture = web.get_snapshot_finish(result)
                    saved.append(texture.save_to_png(str(Path(sys.argv[1]) / f'gtk-{theme}.png')))
                view.web.get_snapshot(WebKit.SnapshotRegion.FULL_DOCUMENT,
                                      WebKit.SnapshotOptions.NONE, None, capture)
                until(lambda: saved, 'native screenshot written')
                assert saved[0]

        assert javascript(view, 'String(document.querySelectorAll(".rip, #pt circle").length)') == '0'
        javascript(view, """window.motionEvents = []; window.taskMotion = {};
          new MutationObserver(() => {
            for (const element of document.querySelectorAll(".rip, #pt circle")) motionEvents.push(element.dataset.evidenceId);
            for (const label of document.querySelectorAll(".packet-task")) taskMotion[label.dataset.evidenceId] = label.textContent;
          }).observe(document.querySelector("#dia"), {childList:true,subtree:true}); "ready" """)
        # Two reads on one source arrive between snapshots. Each must keep its own groups.
        pump, level = [
            store.record_read(HOSTS[0], tag, node_id, ('ok', None, 1, {'endpoint': ENDPOINTS[HOSTS[0]]}),
                              value, 'Good', source='sim')['id']
            for tag, node_id, value in [('Pump', 'i=2257', True), ('Level', 'i=2256', 62)]
        ]
        until(lambda: 'ติดตามปั๊ม' in javascript(view, f'taskMotion["{pump}"] ?? ""'), 'first read keeps its own group')
        caption = until(lambda: javascript(view, f'taskMotion["{level}"] ?? ""'), 'second read has its own groups')
        assert 'กลุ่มระดับน้ำ' in caption and 'แจ้งเตือนระดับสูง' in caption and 'ติดตามปั๊ม' not in caption
        label = javascript(view, f'document.getElementById("n-{HOSTS[0]}").querySelector(".task-groups").textContent')
        assert 'Task ที่ผูกกับ Tag' in label and 'กลุ่มระดับน้ำ' in label and 'แจ้งเตือนระดับสูง' in label
        print('PASS consecutive read particles retain separate evidence IDs and Task groups; F3 shows F2 membership', flush=True)

        failed = record(HOSTS[1], 'ua_read', 'TIMEOUT')
        until(lambda: state(HOSTS[1]) == 'FAIL', 'simulated SCADA read failure')
        until(lambda: javascript(view, f'String(motionEvents.includes("{failed}"))') == 'true', 'SSE animation has committed row id')
        print('PASS no initial animation; SCADA timeout FAIL with SSE animation bound to committed row', flush=True)

        record(SWITCH, 'ping', 'TIMEOUT')
        until(lambda: state(SWITCH) == 'FAIL', 'simulated switch timeout')
        assert all(state(host) == 'BLOCKED' for host in HOSTS)
        dimensions = json.loads(javascript(view, """JSON.stringify({
          width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
          scrollHeight: document.documentElement.scrollHeight,
          mapHeight: document.getElementById('dia').getBoundingClientRect().height,
          mapWidth: document.getElementById('dia').getBoundingClientRect().width,
          nodeFont: parseFloat(getComputedStyle(document.querySelector('.node strong')).fontSize),
          lowestCard: Math.ceil(Math.max(...[...document.querySelectorAll('.node')]
            .map(card => card.getBoundingClientRect().bottom)))
        })"""))
        assert dimensions['scrollWidth'] <= dimensions['width'], dimensions
        assert dimensions['scrollHeight'] <= dimensions['height'], dimensions
        assert dimensions['lowestCard'] <= dimensions['height'], dimensions
        if dimensions['width'] >= 1600 and dimensions['height'] >= 800:
            assert dimensions['mapHeight'] >= dimensions['height'] * .80, dimensions
            assert dimensions['mapWidth'] >= dimensions['width'] * .94, dimensions
            assert dimensions['nodeFont'] >= 17, dimensions
        print(f'PASS F3 fits without scroll even when four SCADA are BLOCKED: {dimensions}', flush=True)
        assert javascript(view, 'document.getElementById("n-opc").click(); document.getElementById("detail").textContent').find('ตรวจคุณภาพ') >= 0
        javascript(view, 'document.querySelector("[data-close]").click(); "closed"')
        print('PASS simulated switch timeout makes four SCADA nodes BLOCKED', flush=True)

        record(SWITCH, 'ping')
        record(HOSTS[0], 'ua_read', age=57)
        until(lambda: state(HOSTS[0]) == 'OK', 'fresh row after switch recovery')
        until(lambda: state(HOSTS[0]) == 'STALE', 'threshold passes with no new evidence', 9)
        assert javascript(view, f'document.getElementById("n-{HOSTS[0]}").click(); String(document.querySelector("dialog").open)') == 'true'
        assert 'probe_evidence' in javascript(view, 'document.getElementById("detail").textContent')
        assert javascript(view, 'document.querySelector("[data-close]").click(); String(document.querySelector("dialog").open)') == 'false'
        javascript(view, 'document.dispatchEvent(new KeyboardEvent("keydown", {key:"F2", bubbles:true})); "key sent"')
        until(lambda: keys, 'F2 reaches GTK owner')
        print('PASS stopped updates cross 60s threshold, details dialog and F2 bridge', flush=True)

        if os.environ.get('F3_TEST_DEMO'):
            import socket

            def field(name):
                return javascript(view, f'document.body.dataset.{name} ?? ""')

            telegram_config = os.environ.get('F3_TEST_TELEGRAM_CONFIG')
            if telegram_config:
                private_config = directory / 'telegram_config.json'
                private_config.touch(mode=0o600)
                private_config.write_bytes(Path(telegram_config).read_bytes())
            evidence_bytes = store.path.read_bytes()
            original_url = view.api_url
            click = 'document.getElementById("f3-demo").click(); "clicked"'
            javascript(view, click)
            process = until(lambda: view._demo_process, 'F3 button starts separate worker')
            until(lambda: field('demo') == '1', 'yellow simulation strip appears')
            until(lambda: view.api_url != original_url and javascript(view, 'location.origin') == view.api_url,
                  'demo WebView loaded')
            javascript(view, """document.documentElement.dataset.theme = "dark";
              window.demoMotion = {};
              new MutationObserver(() => {
                for (const label of document.querySelectorAll(".packet-task")) demoMotion[label.dataset.evidenceId] = label.textContent;
              }).observe(document.querySelector("#dia"), {childList:true,subtree:true}); "ready" """)
            expected = 'success' if telegram_config else 'error'
            until(lambda: field('signal') == expected, 'Telegram receipt or configuration error reaches F3', 22)
            assert view._demo_process is process and view.api_url != original_url
            rows = request('/api/evidence')['rows']
            read = next(row for row in rows if row['check'] == 'ua_read')
            assert read['source'] == 'sim' and read['result'] == 'ok'
            read_value = json.loads(read['detail'])
            assert read_value['value'] == 73.25 and read_value['quality'] == 'Good'
            notice = javascript(view, 'document.getElementById("f3-toast").textContent')
            assert ('Telegram ยืนยันข้อความ' if telegram_config else 'ตั้งค่า Telegram') in notice
            stages = {node['id']: node['last'] for node in request('/api/f3/evidence')['nodes']}
            assert stages['task']['ok'] and stages['outbox']['ok']
            assert stages['tg']['ok'] == bool(telegram_config)
            for stage in ('task', 'outbox', 'relay', 'tg'):
                assert stages[stage]['read_evidence_id'] == read['id']
                assert [group['name'] for group in stages[stage]['task_groups']] == [
                    'เฝ้าระวังระดับน้ำ', 'แจ้งเตือนถังพัก']
                label = javascript(view, f'document.getElementById("n-{stage}").querySelector(".task-groups").textContent')
                assert 'เฝ้าระวังระดับน้ำ' in label and 'แจ้งเตือนถังพัก' in label
            for stage in ('task', 'outbox'):
                evidence_id = stages[stage]['id']
                caption = until(lambda: javascript(view, f'demoMotion["{evidence_id}"] ?? ""'),
                                f'{stage} shows the groups while its evidence moves')
                assert 'เฝ้าระวังระดับน้ำ' in caption and 'แจ้งเตือนถังพัก' in caption
            assert javascript(view, 'String(document.documentElement.scrollWidth <= innerWidth)') == 'true'
            assert javascript(view, 'String(document.documentElement.scrollHeight <= innerHeight)') == 'true'
            if telegram_config:
                assert stages['relay']['ok']
                print('PASS Telegram acknowledgement shown in F3: ' + notice, flush=True)
            if len(sys.argv) == 2:
                saved = []
                def capture_inline(web, result):
                    texture = web.get_snapshot_finish(result)
                    saved.append(texture.save_to_png(str(Path(sys.argv[1]) / 'inline-demo.png')))
                view.web.get_snapshot(WebKit.SnapshotRegion.VISIBLE,
                                      WebKit.SnapshotOptions.NONE, None, capture_inline)
                until(lambda: saved, 'demo screenshot written')
                assert saved[0]
            javascript(view, click)
            until(lambda: view._demo_process is None, 'stop reaps demo worker')
            until(lambda: field('demo') == '0', 'live view restored')
            assert view.api_url == original_url
            assert store.path.read_bytes() == evidence_bytes
            print('PASS inline demo: yellow rail, genuine OPC UA 73.25 Good, Task/Outbox committed, Telegram status verified, parent DB untouched', flush=True)

            with socket.socket() as occupied:
                occupied.bind(('127.0.0.1', 4850))
                occupied.listen()
                javascript(view, click)
                until(lambda: field('signal') == 'error', 'occupied port raises red border')
                assert 'พอร์ตจำลอง' in javascript(view, 'document.getElementById("f3-toast").textContent')
                assert view.api_url == original_url
            print('PASS occupied loopback port: red frame and lower-left toast; live view restored', flush=True)

        window.set_child(None)
        until(lambda: view._server is None, 'unmap shuts down API')
        print('PASS GTK unmap shuts down localhost listener', flush=True)
    finally:
        view.close()
        window.close()
        store.close()

