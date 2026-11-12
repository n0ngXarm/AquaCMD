"""Capture the active GTK4 application using a disposable, labelled test profile only."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'desktop'), str(Path(__file__).parent)]
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
import app
from collector.probe_once import EvidenceStore
from wincc_catalog_fixture import write_catalog


def wait(predicate, seconds=15):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for _ in range(80):
            if not context.pending():
                break
            context.iteration(False)
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('GTK test capture timed out')


def settle(seconds=.2):
    end = time.monotonic() + seconds
    wait(lambda: time.monotonic() >= end)


def javascript(web, expression):
    result = {}
    def completed(view, task, *_):
        try:
            result['value'] = json.loads(view.evaluate_javascript_finish(task).to_string())
        except Exception as error:
            result['error'] = error
    web.evaluate_javascript('JSON.stringify(' + expression + ')', -1, None, None, None, completed, None)
    wait(lambda: bool(result))
    if 'error' in result:
        raise result['error']
    return result['value']


def capture(window, destination):
    settle()
    paintable = Gtk.WidgetPaintable.new(window)
    def frame():
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        if node is None:
            return False
        assert window.get_renderer().render_texture(node, None).save_to_png(str(destination))
        return True
    wait(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('AQUA_UX_TEST_PROFILE') != '1' or not str(Path.home()).startswith('/tmp/aqua-native-ux-'):
        raise SystemExit('This harness requires an explicitly disposable test HOME')
    args.out.mkdir(parents=True, exist_ok=True)
    config = app.CONFIG_DIR
    config.mkdir(parents=True, exist_ok=True)
    targets = [{'host': f'127.0.0.{i}', 'port': 4840} for i in range(11, 15)]
    (config / 'probe_targets.json').write_text(json.dumps({'targets': targets, 'ping_timeout_s': .1, 'tcp_timeout_s': .1}))
    (config / 'network_topology.json').write_text(json.dumps({'devices': [
        {'configured_ip': target['host'], 'type': 'wincc', 'alias': f'LAB Source {i}'}
        for i, target in enumerate(targets, 1)]}))
    db = Path.home() / '.local/share/aqua-command/probe/data.db'
    store = EvidenceStore(db)
    store.connection.close()
    before = db.read_bytes()
    catalog = write_catalog(Path.home() / 'lab-catalog.txt')
    metrics = dict(hostname='SIMULATED LAB WORKSTATION', os_name='SIMULATED test profile', kernel='SIMULATED',
                   arch='SIMULATED', cpu_model='SIMULATED', cpu_cores=1, cpu_load='SIMULATED',
                   ram_total_gb=0, ram_used_gb=0, ram_avail_gb=0, ram_pct=0,
                   disk_total_gb=0, disk_used_gb=0, disk_avail_gb=0, disk_pct=0,
                   ip_lan='127.0.0.1 (SIMULATED)', uptime_str='SIMULATED')
    application = Gtk.Application(application_id='org.aqua.ux.capture', flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.register(None)
    records = []
    confirmation_screenshots = []
    with patch('app.DEFAULT_WINCC_EXPORT', catalog), patch('app.read_real_machine_data', return_value=metrics), \
            patch('f3_api_view.read_linux_snapshot', return_value={'state':'UNKNOWN','interfaces':{}}):
        for width, height in ((1024,600), (1360,768), (1920,1080)):
            window = app.AquaWinCCWindow(application)
            window.set_title('AQUA COMMAND · SIMULATED TEST PROFILE')
            window.set_default_size(width, height)
            window.present()
            wait(window.get_mapped)
            workspace = window.unified_workspace
            web = workspace.f1_api.web
            wait(lambda: javascript(web, "Boolean(window.F1 && document.querySelector('.table-row'))"))
            try:
                for key in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6'):
                    window.on_global_key_pressed(None, getattr(Gdk, 'KEY_' + key), 0, 0)
                    if key == 'F2':
                        wait(lambda: javascript(web, "document.getElementById('modalOverlay').open"))
                    elif key == 'F3':
                        wait(lambda: window.f3_network_view.api_url or window.f3_network_view.error.get_visible())
                        if window.f3_network_view.api_url:
                            wait(lambda: javascript(window.f3_network_view.web, "Boolean(document.querySelector('[data-n]'))"))
                    settle(1.0)
                    file = f'{width}x{height}-{key}.png'
                    capture(window, args.out / file)
                    actual = [window.get_width(), window.get_height()]
                    assert actual == [width, height], ('Actual GTK allocation differs', actual, width, height)
                    record = {'requested':[width,height], 'actual':actual, 'page':key, 'screenshot':file}
                    record['native'] = {'active_nav':[name for name, button in window.nav_btns.items() if button.get_active()],
                                        'footer_height':window.alarm_text.get_parent().get_height(),
                                        'footer_selection':list(window.alarm_text.get_selection_bounds())}
                    if key == 'F1':
                        record['f1_geometry'] = javascript(web, '''(()=>{const box=document.getElementById('tableViewport').getBoundingClientRect();return {
                          viewport:{top:box.top,bottom:box.bottom,height:box.height},
                          visible_rows:[...document.querySelectorAll('.table-row')].filter(row=>{const b=row.getBoundingClientRect();return b.top>=box.top&&b.bottom<=box.bottom}).length,
                          web_height:innerHeight};})()''')
                    if key == 'F3' and window.f3_network_view.api_url:
                        geometry = javascript(window.f3_network_view.web, '''({
                          width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,
                          legendTop:document.getElementById('legend').getBoundingClientRect().top,
                          cards:[...document.querySelectorAll('.node')].map(node=>({bottom:node.getBoundingClientRect().bottom,zoneBottom:node.closest('.zone').getBoundingClientRect().bottom}))
                        })''')
                        assert geometry['scrollWidth'] <= geometry['width'] and geometry['scrollHeight'] <= geometry['height'], geometry
                        assert all(card['bottom'] <= min(card['zoneBottom'], geometry['legendTop']) for card in geometry['cards']), geometry
                        record['f3_geometry'] = geometry
                    records.append(record)
                    if key == 'F2':
                        javascript(web, "(window.F1.setMode('monitoring'), true)")
                if args.out.name == 'ux-after' and width == 1360:
                    window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0)
                    dialog = window._close_dialog
                    wait(dialog.get_mapped)
                    file = 'confirm-close-1360.png'
                    capture(dialog, args.out / file)
                    confirmation_screenshots.append(file)
                    dialog.response(Gtk.ResponseType.CANCEL)
                    view = window.f3_network_view
                    path = view._telegram_demo_config
                    previous = path.read_bytes() if path.exists() else None
                    path.write_text(json.dumps({'enabled': True, 'bot_token':'123:synthetic-ui-only', 'chat_id':'synthetic-chat-123456'}))
                    try:
                        window.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
                        wait(lambda: bool(view.api_url))
                        with patch.object(view, '_open_demo') as start:
                            view._confirm_demo()
                            confirmation = view._demo_confirmation
                            wait(confirmation.get_mapped)
                            file = 'confirm-simulated-telegram-1360.png'
                            capture(confirmation, args.out / file)
                            confirmation_screenshots.append(file)
                            confirmation.response(Gtk.ResponseType.CANCEL)
                            start.assert_not_called()
                    finally:
                        if previous is None: path.unlink()
                        else: path.write_bytes(previous)
                telemetry = window.polling_engine.get_telemetry()
                assert telemetry['state'] == 'STOPPED' and telemetry['poll_count'] == 0
                assert not window.notification_worker.running
                assert db.read_bytes() == before
            finally:
                if getattr(window, '_close_dialog', None):
                    window._close_dialog.response(Gtk.ResponseType.CANCEL)
                # Explicit harness teardown is allowed only after its idle assertions.
                window._close_confirmed = True
                window.on_close_request()
                workspace.f1_api.web.terminate_web_process()
                window.destroy()
                settle()
    application.quit()
    (args.out / 'native-layout.json').write_text(json.dumps(records, indent=2))
    print(json.dumps({'screenshots':len(records), 'confirmation_screenshots':confirmation_screenshots, 'data':'SIMULATED test profile only', 'poll_count':0,
                      'notification_worker_running':False, 'evidence_db_unchanged':True, 'records':records}), flush=True)


if __name__ == '__main__':
    main()
