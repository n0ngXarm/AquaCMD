"""F3 presentation reads the phase 2 API; it never starts a collector or UA client."""
from html import escape
import ipaddress
import json
import re
import signal
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from collector.evidence_api import make_server
from collector.probe_once import load_settings
try:
    from .f3_local import read_linux_snapshot
    from .f3_network import F3DeviceStore
    from .f3_projection import F3Projection
except ImportError:
    from f3_local import read_linux_snapshot
    from f3_network import F3DeviceStore
    from f3_projection import F3Projection

ASSETS = Path(__file__).with_name('f3_api')
FORMAL_THEME = ASSETS.parent / 'f1_api' / 'formal-theme.css'


def load_metadata(path):
    """Only configured names/roles affect layout; observations are not imported."""
    path = Path(path)
    if not path.exists():
        return {}
    configuration = json.loads(path.read_text())
    devices = configuration.get('devices', [])
    if isinstance(devices, dict):
        devices = devices.values()
    result = {}
    for device in devices:
        if not isinstance(device, dict) or device.get('type') == 'local_host':
            continue
        try:
            address = str(ipaddress.IPv4Address(device.get('configured_ip', '')))
        except (ValueError, TypeError):
            continue
        result[address] = {'label': str(device.get('alias') or address),
                           'zone': str(device.get('network_zone') or 'SCADA_OT'),
                           'kind': str(device.get('type') or 'device')}
    return result


def build_html(metadata, *, allow_demo=True, demo=False, demo_error="", demo_status=None):
    page = (ASSETS/'index.html').read_text()
    status = demo_status or {'configured': False, 'reason': 'ตั้งค่า Telegram ใน F6 ก่อนจำลองส่งข้อความ'}
    reason = status.get('reason', '')
    attributes = 'hidden' if not allow_demo else '' if demo or status['configured'] else 'disabled aria-disabled="true"'
    attributes += ' title="' + escape(reason or 'เริ่มจำลองและส่งข้อความ SIMULATED 1 ข้อความ · ต้องยืนยันก่อน', quote=True) + '"'
    page = page.replace('__F3_DEMO_ATTR__', attributes)
    page = page.replace('__F3_DEMO_LABEL__', 'จำลองและส่ง Telegram' if demo or status['configured'] else 'Telegram ยังไม่พร้อม · ตั้งค่า F6')
    page = page.replace('__F3_DEMO_MODE__', '1' if demo else '0')
    page = page.replace('__F3_DEMO_ERROR__', escape(demo_error, quote=True))
    fonts = (ASSETS/'fonts_embedded.css').read_text() if (ASSETS/'fonts_embedded.css').exists() else ''
    theme = FORMAL_THEME.read_text(encoding='utf-8')
    page = page.replace('/*F3_CSS*/', '\n'.join((fonts, theme, (ASSETS/'view.css').read_text(encoding='utf-8'))))
    detector = (ASSETS/'detect.mjs').read_text().replace('export function detect(', 'function detect(', 1)
    page = page.replace('/*F3_JS*/', detector + '\n' + (ASSETS/'view.js').read_text())
    return page.replace('__F3_METADATA__', json.dumps(metadata, ensure_ascii=False).replace('<', '\\u003c'))


def is_api_uri(uri, origin):
    try:
        parsed, base = urlsplit(uri), urlsplit(origin)
        return parsed.scheme == base.scheme == 'http' and parsed.hostname == base.hostname == '127.0.0.1' \
            and parsed.port == base.port and parsed.username is None and parsed.password is None
    except ValueError:
        return False


class F3ApiView:
    def __init__(self, owner, db_path=None, config_path=None, *, allow_demo=True):
        self.owner = owner
        self._allow_demo = allow_demo
        self._demo_process = None
        self._demo_requested = False
        self._demo_confirmation = None
        self._live_api_url = ""
        config_dir = Path(getattr(owner, 'config_dir', None) or Path.home()/'.config/aqua-command')
        self._telegram_demo_config = config_dir / 'telegram_config.json'
        self.config_path = Path(config_path or config_dir/'probe_targets.json')
        self.db_path = Path(db_path or getattr(owner, 'probe_db_path', None) or Path.home()/'.local/share/aqua-command/probe/data.db')
        self.metadata_error = ''
        try:
            self.metadata = load_metadata(config_dir/'network_topology.json')
        except (OSError, ValueError, AttributeError, TypeError) as error:
            self.metadata = {}
            self.metadata_error = f'{type(error).__name__}: {error}'
        # Existing opt-in observability callers keep their configured inventory.
        # This object is never a source of state/counters for the F3 page.
        self.store = F3DeviceStore(config_file=config_dir/'network_topology.json')
        self.router_targets = {}
        for role, kind, zone in (('OT', 'switch', 'SCADA_OT'), ('WAN', 'router', 'EXTERNAL_WAN')):
            hosts = [host for host, meta in self.metadata.items() if (meta['kind'], meta['zone']) == (kind, zone)]
            if len(hosts) == 1:
                self.router_targets[role] = hosts[0]
        self.local_state = {'interfaces': {}, 'ip_forwarding': None}
        self.topology_data = getattr(owner, 'topology_data', {})
        self.closed = False
        self._active = False
        self._generation = 0
        self._lock = threading.Lock()
        self._server = None
        self._worker = None
        self._stop = threading.Event()
        self._local_pending = False
        self._local_requested = 0.0
        self.api_url = ''
        self.root_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root_widget.set_hexpand(True)
        self.root_widget.set_vexpand(True)
        self.canvas = self.root_widget
        self.web = None
        self.details_window = None
        self.details_text = None
        self._details_node = None
        self._details_body = ''
        self.error = Gtk.Label(label='')
        self.error.set_wrap(True)
        self.error.set_selectable(True)
        self.error.set_visible(bool(self.metadata_error))
        if self.metadata_error:
            self.error.set_text('อ่านป้ายกำกับอุปกรณ์ไม่ได้ · '+self.metadata_error)
        self.root_widget.append(self.error)
        self.settings_action = Gtk.Button(label='ตั้งค่า OPC UA · F6', halign=Gtk.Align.START)
        self.settings_action.set_tooltip_text('เปิดตั้งค่า OPC UA · F6')
        self.settings_action.connect('clicked', lambda _: self.owner.on_global_key_pressed(None, Gdk.KEY_F6, 0, 0))
        self.settings_action.set_visible(bool(self.metadata_error))
        self.root_widget.append(self.settings_action)
        self.root_widget.connect('map', self._mapped)
        self.root_widget.connect('unmap', self._unmapped)
        # Keep the passive host snapshot independent of the evidence collector.
        self.refresh_local_state()

    def _ensure_web(self):
        if self.web is not None:
            return
        session = WebKit.NetworkSession.new_ephemeral()
        session.set_proxy_settings(WebKit.NetworkProxyMode.NO_PROXY, None)
        manager = WebKit.UserContentManager()
        manager.register_script_message_handler('f3navigation', None)
        manager.connect('script-message-received::f3navigation', self._message)
        self.web = WebKit.WebView(network_session=session, user_content_manager=manager)
        self.web.set_hexpand(True)
        self.web.set_vexpand(True)
        settings = self.web.get_settings()
        for name in ('enable-webgl', 'enable-html5-database', 'enable-html5-local-storage',
                     'enable-media-stream', 'enable-developer-extras', 'enable-dns-prefetching',
                     'javascript-can-open-windows-automatically'):
            if settings.find_property(name):
                settings.set_property(name, False)
        self.web.connect('decide-policy', self._policy)
        self.web.connect('permission-request', lambda _, request: (request.deny(), True)[1])
        self.web.connect('create', lambda *_: None)
        self.web.connect('web-process-terminated', self._renderer_failed)
        self.root_widget.prepend(self.web)

    def _mapped(self, *_):
        if self.closed or self._active:
            return
        self._ensure_web()
        self.web.load_html(build_html(self.metadata, allow_demo=self._allow_demo, demo_status=self._demo_status()), None)
        self._active = True
        self._generation += 1
        generation = self._generation
        stop = self._stop = threading.Event()
        tasks = tuple(getattr(self.owner, 'tasks', ()) or ())

        def worker():
            server = None
            try:
                settings=load_settings(self.config_path)
                server=make_server(self.db_path,hosts=[target['host'] for target in settings['targets']],port=0,settings=settings)
                server.reader = F3Projection(server.reader, settings, self.metadata, task_groups=tasks,
                                             local_snapshot=lambda: self.local_state)
                with self._lock:
                    if stop.is_set():
                        server.server_close()
                        return
                    self._server = server
                GLib.idle_add(self._ready, server, generation)
                server.serve_forever(poll_interval=0.15)
            except Exception as error:
                GLib.idle_add(self._startup_failed, f'{type(error).__name__}: {error}', generation)
            finally:
                if server is not None:
                    server.stop_event.set()
                    server.server_close()
                with self._lock:
                    if self._server is server:
                        self._server = None

        self._worker = threading.Thread(target=worker, daemon=True, name='F3-read-only-API')
        self._worker.start()

    def _ready(self, server, generation):
        if self.closed or not self._active or generation != self._generation:
            return GLib.SOURCE_REMOVE
        self._live_api_url = f'http://127.0.0.1:{server.server_port}'
        if self._demo_requested:
            return GLib.SOURCE_REMOVE
        self.api_url = self._live_api_url
        self.error.set_visible(bool(self.metadata_error))
        self.settings_action.set_visible(bool(self.metadata_error))
        self.web.set_visible(True)
        self.web.load_html(build_html(self.metadata, allow_demo=self._allow_demo, demo_status=self._demo_status()), self.api_url+'/f3/')
        return GLib.SOURCE_REMOVE

    def _startup_failed(self, error, generation):
        if not self.closed and self._active and generation == self._generation:
            self.error.set_text('ไม่ได้รับข้อมูลจาก backend · '+error)
            self.error.set_visible(True)
            self.settings_action.set_visible(True)
        return GLib.SOURCE_REMOVE

    def _unmapped(self, *_):
        self._active = False
        if self._demo_confirmation is not None:
            self._demo_confirmation.response(Gtk.ResponseType.CANCEL)
        if self.details_window is not None:
            self.details_window.set_visible(False)
        self._active = False
        self._stop_demo()
        self._live_api_url = ""
        self._generation += 1
        self._stop.set()
        if not self.closed and self.web is not None:
            self.web.evaluate_javascript('window.F3?.pause()', -1, None, None, None, None, None)
        with self._lock:
            server = self._server
        if server is not None:
            server.stop_event.set()
            threading.Thread(target=server.shutdown, daemon=True, name='F3-API-stop').start()

    def _policy(self, web, decision, kind):
        if kind in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
            uri = decision.get_navigation_action().get_request().get_uri()
            if uri == 'about:blank' or is_api_uri(uri, self.api_url):
                decision.use()
            else:
                decision.ignore()
            return True
        return False

    def _message(self, manager, value):
        try:
            message = json.loads(value.to_string())
            key = message.get('key')
        except (ValueError, TypeError, AttributeError):
            return
        if message.get('action') == 'open-demo':
            if self._demo_requested:
                self._open_demo()
            else:
                self._confirm_demo()
            return
        if key in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9') and not self.closed:
            self.owner.on_global_key_pressed(None, getattr(Gdk, 'KEY_'+key), 0, 0)

    def _show_f3(self, *, port=None, demo_error=""):
        if not self._active or self.closed:
            return
        self.api_url = f'http://127.0.0.1:{port}' if port else self._live_api_url
        base = self.api_url + '/f3/' if self.api_url else None
        self.web.load_html(build_html(self.metadata, allow_demo=self._allow_demo,
                                      demo=port is not None, demo_error=demo_error, demo_status=self._demo_status()), base)

    def _demo_status(self):
        """Return only readiness, a masked destination and a reason to the presentation."""
        try:
            config = json.loads(self._telegram_demo_config.read_text())
        except (OSError, ValueError):
            config = {}
        reason = ''
        if not isinstance(config, dict) or config.get('enabled') is not True:
            reason = 'เปิดใช้งาน Telegram ใน F6 ก่อนจำลองส่งข้อความ'
        elif not isinstance(config.get('bot_token'), str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', config['bot_token'].strip()):
            reason = 'ตั้งค่า Bot Token ใน F6 ก่อนจำลองส่งข้อความ'
        elif not isinstance(config.get('chat_id'), str) or not config['chat_id'].strip():
            reason = 'ตั้งค่า Chat ID ใน F6 ก่อนจำลองส่งข้อความ'
        chat = config.get('chat_id', '') if isinstance(config, dict) else ''
        chat = chat.strip() if isinstance(chat, str) else ''
        return {'configured': not reason, 'reason': reason,
                'destination': '***' + chat[-4:] if len(chat) > 8 else '***'}

    def _confirm_demo(self):
        if self.closed or not self._active or not self._allow_demo:
            return
        status = self._demo_status()
        if not status['configured']:
            self._show_f3(demo_error=status['reason'])
            return
        if self._demo_confirmation is not None:
            self._demo_confirmation.present()
            return
        try:
            approved_config = self._telegram_demo_config.read_bytes()
        except OSError:
            self._show_f3(demo_error='อ่านการตั้งค่า Telegram ใน F6 ไม่ได้ · ยังไม่ได้เริ่มจำลอง')
            return
        parent = self.owner if isinstance(self.owner, Gtk.Window) else self.root_widget.get_root()
        if not isinstance(parent, Gtk.Window):
            return
        dialog = Gtk.MessageDialog(
            transient_for=parent, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text='จำลองและส่ง Telegram จริงหรือไม่?',
            secondary_text=(
                'จะเริ่ม OPC UA จำลองบน localhost และส่งข้อความทดสอบ 1 ข้อความไปยังแชต '
                + status['destination'] + ' ที่บันทึกไว้ใน F6\n\n'
                'ข้อความขึ้นต้น [AQUA COMMAND · SIMULATED] และ “ข้อความทดสอบจากหน้า F3” '
                'ตามด้วยระดับน้ำจำลองและกลุ่ม Task พร้อมเกณฑ์ที่เข้าเงื่อนไข '
                'เมื่ออ่านข้อมูลจำลองสำเร็จ ทั้งหมดเป็น SIMULATED ไม่ใช่ค่าจาก WinCC หน้างาน'),
        )
        cancel = dialog.add_button('ยกเลิก', Gtk.ResponseType.CANCEL)
        accept = dialog.add_button('เริ่มจำลองและส่ง', Gtk.ResponseType.ACCEPT)
        accept.add_css_class('destructive-action')
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        self._demo_confirmation = dialog

        def response(widget, choice):
            self._demo_confirmation = None
            widget.destroy()
            if choice == Gtk.ResponseType.ACCEPT:
                try:
                    unchanged = self._telegram_demo_config.read_bytes() == approved_config
                except OSError:
                    unchanged = False
                if unchanged:
                    self._open_demo()
                else:
                    self._show_f3(demo_error='การตั้งค่า Telegram เปลี่ยนไป · กรุณาตรวจ F6 และยืนยันใหม่')
            elif self.web is not None and self._active and not self.closed:
                self.web.grab_focus()
                self.web.evaluate_javascript("document.getElementById('f3-demo')?.focus()", -1, None, None, None, None, None)

        dialog.connect('response', response)
        dialog.present()
        cancel.grab_focus()

    def _open_demo(self):
        if self.closed or not self._active or not self._allow_demo:
            return
        if self._demo_requested:
            self._stop_demo()
            self._show_f3()
            return
        if self._demo_process is not None:
            return
        try:
            process = Gio.Subprocess.new(
                [sys.executable, '-B', str(ROOT / 'tools' / 'sim' / 'f3_demo.py'),
                 '--telegram-config', str(self._telegram_demo_config)],
                Gio.SubprocessFlags.STDOUT_PIPE,
            )
        except GLib.Error:
            self._show_f3(demo_error='เริ่มการจำลองไม่สำเร็จ')
            return
        self._demo_requested = True
        self._demo_process = process
        self.web.evaluate_javascript('window.F3?.startingDemo()', -1, None, None, None, None, None)
        output = Gio.DataInputStream.new(process.get_stdout_pipe())
        output.read_line_async(GLib.PRIORITY_DEFAULT, None, self._demo_ready, process)
        process.wait_async(None, self._demo_exited)

    def _demo_ready(self, output, result, process):
        if process is not self._demo_process or not self._demo_requested:
            return
        try:
            line, _ = output.read_line_finish_utf8(result)
            if line is None:
                return  # The exit callback reports the startup failure.
            port = json.loads(line)['port']
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError('Invalid demo port')
        except (GLib.Error, ValueError, TypeError, KeyError):
            self._stop_demo()
            self._show_f3(demo_error='อ่านสถานะการจำลองไม่สำเร็จ')
            return
        self._show_f3(port=port)

    def _stop_demo(self):
        if self._demo_requested and self._demo_process is not None:
            self._demo_process.send_signal(signal.SIGTERM)
        self._demo_requested = False

    def _demo_exited(self, process, result):
        process.wait_finish(result)
        self._demo_process = None
        if self._demo_requested:
            self._demo_requested = False
            self._show_f3(demo_error='การจำลองหยุดทำงาน ตรวจสอบว่าพอร์ตจำลอง 4850 ว่างแล้วลองอีกครั้ง')

    def _renderer_failed(self, *_):
        if not self.closed:
            self.error.set_text('ไม่ได้รับข้อมูลจาก backend · SVG renderer หยุดทำงาน')
            self.error.set_visible(True)
            self.web.set_visible(False)
            self._unmapped()

    def refresh_local_state(self):
        if self.closed or self._local_pending:
            return
        self._local_pending = True
        self._local_requested = time.monotonic()

        def worker():
            try:
                state = read_linux_snapshot(router_targets=self.router_targets)
            except Exception as error:
                state = {'interfaces': {}, 'state': 'UNKNOWN', 'errors': [f'{type(error).__name__}: {error}']}
            GLib.idle_add(done, state)

        def done(state):
            self._local_pending = False
            if not self.closed:
                self.local_state = state
            return GLib.SOURCE_REMOVE

        threading.Thread(target=worker, daemon=True, name='F1-local-cache').start()

    def tick_live(self):
        if time.monotonic()-self._local_requested >= 10:
            self.refresh_local_state()

    def render_ip_summary_table(self):
        if self._active and not self.closed:
            self.web.evaluate_javascript('window.F3?.refresh()', -1, None, None, None, None, None)

    def close(self):
        if self.closed:
            return
        self._unmapped()
        self.closed = True
        if self.details_window is not None:
            self.details_window.destroy()
        if self.web is not None:
            self.web.stop_loading()
            self.web.terminate_web_process()
