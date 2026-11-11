"""Actual GTK/WebKit F3 entry, dialog, navigation and read-only listener lifecycle.

All catalogs/configuration/SQLite rows are test-owned synthetic data. No field
probe, OPC UA operation or external message is performed by this harness.
"""
import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from collector.probe_once import EvidenceStore
from f3_api_view import F3ApiView


def spin_until(predicate, timeout=12):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for _ in range(60):
            if not context.pending():
                break
            context.iteration(False)
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for actual F3 lifecycle condition')


class ActiveF3ReconciliationTests(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        self.directory = Path(profile.name)
        (self.directory / 'probe_targets.json').write_text(json.dumps({
            'targets': [{'host': '127.0.0.2', 'port': 4840}],
            'ping_timeout_s': .1, 'tcp_timeout_s': .1}))
        (self.directory / 'network_topology.json').write_text(json.dumps({'devices': [{
            'device_id': 'lab-source', 'type': 'wincc', 'configured_ip': '127.0.0.2',
            'alias': 'LAB Source', 'state': 'READ_OK', 'observed_ip': '127.0.0.99'}]}))
        self.db = self.directory / 'evidence.db'
        store = EvidenceStore(self.db)
        store.connection.close()
        self.before_db = self.db.read_bytes()
        self.owner = SimpleNamespace(config_dir=self.directory, probe_db_path=self.db,
                                     tasks=[], on_global_key_pressed=Mock())
        passive = patch('f3_api_view.read_linux_snapshot', return_value={'state': 'UNKNOWN', 'interfaces': {}})
        passive.start()
        self.addCleanup(passive.stop)
        self.view = F3ApiView(self.owner, allow_demo=False)
        self.window = Gtk.Window()
        self.window.set_default_size(1366, 768)
        self.window.set_child(self.view.root_widget)
        self.addCleanup(self.close_ui)

    def close_ui(self):
        self.view.close()
        self.window.destroy()
        spin_until(lambda: self.view._worker is None or not self.view._worker.is_alive())

    def show(self):
        self.window.present()
        spin_until(lambda: bool(self.view.api_url) and self.view._server is not None)
        spin_until(lambda: self.js("Boolean(window.F3 && document.querySelector('[data-n]'))"))

    def js(self, expression):
        result = {}
        def done(web, task, *_):
            try:
                result['value'] = json.loads(web.evaluate_javascript_finish(task).to_string())
            except Exception as error:
                result['error'] = error
        script = 'JSON.stringify(' + expression + ')'
        self.view.web.evaluate_javascript(script, -1, None, None, None, done, None)
        spin_until(lambda: bool(result))
        if 'error' in result:
            raise result['error']
        return result['value']

    def test_active_dialog_is_initially_closed_reuses_selection_and_restores_focus(self):
        # G12/G13/G21: exercise the real HTML dialog rather than a legacy native popup.
        self.show()
        self.assertFalse(self.js("document.getElementById('pop').open"))
        data = self.js("""(()=>{
          const button=document.querySelector('[data-n]');
          window.__testDialog=document.getElementById('pop');
          window.__testNode=button.id;
          button.click();
          return {open:__testDialog.open, owner:__testDialog.ownerDocument===document,
                  title:document.getElementById('ptitle').textContent};
        })()""")
        self.assertTrue(data['open'])
        self.assertTrue(data['owner'])
        self.assertTrue(data['title'])
        self.assertTrue(self.js("(()=>{document.querySelector('[data-close]').click();return !__testDialog.open})()"))
        spin_until(lambda: self.js('document.activeElement.id===window.__testNode'))
        self.assertTrue(self.js("(()=>{document.getElementById(__testNode).click();return __testDialog===document.getElementById('pop') && __testDialog.open})()"))
        self.assertEqual(self.db.read_bytes(), self.before_db)

    def test_web_keyboard_navigation_and_settings_shortcut_reach_owner_only(self):
        # G14: current settings route is F6, not an invented native details toplevel.
        self.show()
        self.js("(()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'F2'}));return true})()")
        spin_until(lambda: self.owner.on_global_key_pressed.call_count == 1)
        self.assertEqual(self.owner.on_global_key_pressed.call_args.args[1], Gdk.KEY_F2)
        self.js("(()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:',',code:'Comma',ctrlKey:true}));return true})()")
        spin_until(lambda: self.owner.on_global_key_pressed.call_count == 2)
        self.assertEqual(self.owner.on_global_key_pressed.call_args.args[1], Gdk.KEY_F6)
        self.assertEqual(self.db.read_bytes(), self.before_db)

    def test_map_unmap_remap_closes_listener_and_rejects_late_ready(self):
        # G10 + listener invariant: no API until F3 is mapped; leave/close stops it.
        self.assertIsNone(self.view._server)
        self.assertIsNone(self.view._worker)
        self.show()
        server = self.view._server
        worker = self.view._worker
        generation = self.view._generation
        port = server.server_port
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass
        self.window.set_visible(False)
        spin_until(lambda: not worker.is_alive())
        self.assertIsNone(self.view._server)
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=.1)
        previous = self.view.api_url
        self.view._ready(server, generation)
        self.assertEqual(self.view.api_url, previous)
        self.show()
        self.assertIsNot(self.view._server, server)
        self.view.close()
        spin_until(lambda: not self.view._worker.is_alive())
        self.assertTrue(self.view.closed)
        self.assertFalse(self.view._active)
        self.assertEqual(self.db.read_bytes(), self.before_db)

    def test_configured_success_cannot_become_observed_page_state_or_start_remote_io(self):
        # G03/G06/G16: real page + API, configured success remains UNKNOWN.
        with patch('f3_network.RealDetectionEngine.detect_device_network') as probe, \
                patch('f3_opcua.SecureF3OpcUa.probe_sync') as session, \
                patch('f3_opcua.SecureF3OpcUa.read_sync') as read:
            self.show()
            nodes = self.js("Array.from(document.querySelectorAll('[data-n]')).map(n=>({id:n.dataset.n,state:n.dataset.state}))")
            self.assertTrue(nodes)
            self.assertTrue(all(n['state'] in ('UNVERIFIED', 'NOT_BUILT') for n in nodes))
            self.assertFalse(self.js("document.getElementById('pop').open"))
            probe.assert_not_called()
            session.assert_not_called()
            read.assert_not_called()
        self.assertEqual(self.db.read_bytes(), self.before_db)

    def test_normal_application_f3_navigation_and_owner_close_stop_listener(self):
        # Normal application entry supplements the small isolated F3 owner fixture.
        import app as desktop_app
        with patch.object(desktop_app, 'CONFIG_DIR', self.directory / 'application'), \
                patch.object(desktop_app, 'DEFAULT_WINCC_EXPORT', self.directory / 'absent.txt'):
            application = Gtk.Application(application_id='org.aqua.p1.active', flags=Gio.ApplicationFlags.NON_UNIQUE)
            application.register(None)
            win = desktop_app.AquaWinCCWindow(app=application)
            win.f3_network_view.config_path = self.directory / 'probe_targets.json'
            win.f3_network_view.db_path = self.db
            win.present()
            try:
                self.assertEqual(win.stack.get_visible_child_name(), 'overview')
                self.assertIsNone(win.f3_network_view._worker)
                win.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
                spin_until(lambda: win.f3_network_view._server is not None)
                worker = win.f3_network_view._worker
                port = win.f3_network_view._server.server_port
                win.on_global_key_pressed(None, Gdk.KEY_F1, 0, 0)
                spin_until(lambda: not worker.is_alive())
                with self.assertRaises(OSError):
                    socket.create_connection(('127.0.0.1', port), timeout=.1)
                win.on_global_key_pressed(None, Gdk.KEY_F3, 0, 0)
                spin_until(lambda: win.f3_network_view._server is not None)
                win.on_close_request()
                spin_until(lambda: not win.f3_network_view._worker.is_alive())
                self.assertTrue(win.f3_network_view.closed)
            finally:
                win.on_close_request()
                win.destroy()
                application.quit()
