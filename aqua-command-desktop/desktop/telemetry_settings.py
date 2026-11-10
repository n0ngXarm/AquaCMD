"""Manual F6 setup and lifecycle controls for the alternative F1 readers."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

from gi.repository import GLib, Gtk

from collector import telemetry


TRANSPORTS = ('opcda', 'rest', 'mqtt')
NAMES = ('OPC DA · Windows Gateway', 'REST · HTTPS', 'MQTT · TLS')
FIELD_OPTIONS = {
    'opcda': ('gateway_db',),
    'rest': ('url', 'ca_file', 'token_file'),
    'mqtt': ('url', 'topic', 'ca_file', 'client_cert', 'client_key'),
}
HELP = {
    'opcda': 'เปิด Windows Reader บนเครื่อง WinCC และอนุญาตส่งเข้า Gateway ก่อน จากนั้นเลือกไฟล์ aqua.sqlite3 ของ Gateway บนเครื่องนี้และรหัส PC ของ Reader',
    'rest': 'ระบุ URL HTTPS ของ Gateway ที่ส่ง snapshot ค่า Tag ตามรูปแบบของ AQUA COMMAND',
    'mqtt': 'ระบุ URL mqtts และ topic ที่เผยแพร่ snapshot ค่า Tag โดยใช้ชื่อ topic แบบเจาะจง',
}
CAPTIONS = {
    'source_id': 'รหัสแหล่งข้อมูล',
    'gateway_db': 'ฐานข้อมูล Gateway',
    'url': 'URL',
    'topic': 'Topic',
    'ca_file': 'ไฟล์ CA',
    'token_file': 'ไฟล์ Bearer token',
    'client_cert': 'ไฟล์ใบรับรอง client',
    'client_key': 'ไฟล์กุญแจ client',
}


class TelemetrySettings:
    def __init__(self, owner, form, actions, label, action, status):
        self.owner = owner
        self.path = Path(owner.config_dir) / telemetry.CONFIG_NAME
        self.process = None
        self.picker = None
        self.closing = False
        self.stopping = False
        self.loaded = {}
        self.transport = Gtk.DropDown.new_from_strings(NAMES)
        self.transport.update_property([Gtk.AccessibleProperty.LABEL], ['แหล่งข้อมูลสำหรับหน้าติดตามค่า'])
        form.append(self.transport)
        self.help = label('', 'f6-help')
        form.append(self.help)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        form.append(grid)
        self.entries = {}
        self.rows = {}
        for row, (key, caption) in enumerate(CAPTIONS.items()):
            name = label(caption, 'f6-field-label')
            entry = Gtk.Entry(hexpand=True)
            entry.update_property([Gtk.AccessibleProperty.LABEL], [caption])
            field = entry
            if key == 'gateway_db':
                field = Gtk.Box(spacing=8)
                field.append(entry)
                field.append(action('เลือกไฟล์…', self.choose_database))
            grid.attach(name, 0, row, 1, 1)
            grid.attach(field, 1, row, 1, 1)
            self.entries[key] = entry
            self.rows[key] = (name, field)
        form.append(label('ชื่อ Tag · หนึ่งชื่อต่อบรรทัด', 'f6-field-label'))
        self.tags = Gtk.TextView(wrap_mode=Gtk.WrapMode.CHAR)
        self.tags.update_property([Gtk.AccessibleProperty.LABEL], ['ชื่อ Tag หนึ่งชื่อต่อบรรทัด'])
        tag_scroll = Gtk.ScrolledWindow(min_content_height=96, has_frame=True)
        tag_scroll.set_child(self.tags)
        form.append(tag_scroll)
        self.lab = Gtk.CheckButton(label='LAB · ใช้ข้อมูลทดสอบ')
        form.append(self.lab)

        self.selected = status('')
        actions.append(self.selected)
        self.result = status('ยังไม่ได้เริ่มอ่าน')
        actions.append(self.result)
        self.save_button = action('บันทึกและใช้แหล่งนี้', self.save, primary=True)
        self.once_button = action('อ่านครั้งเดียว', lambda _: self.start(False))
        self.start_button = action('เริ่มอ่านตามรอบ', lambda _: self.start(True))
        self.stop_button = action('หยุดอ่าน', lambda _: self.stop())
        self.ua_button = action('กลับไปใช้ OPC UA', self.restore_ua)
        for button in (self.save_button, self.once_button, self.start_button, self.stop_button, self.ua_button):
            actions.append(button)
        self.form = form
        active = self.read_settings(self.path)
        self.transport.set_selected(TRANSPORTS.index(active['transport']) if active else 0)
        self.transport.connect('notify::selected', self.show_transport)
        self.show_transport()
        self.update_selected()
        self.update_controls()

    @staticmethod
    def read_settings(path):
        try:
            return telemetry.load_config(path)
        except (OSError, ValueError, TypeError, RecursionError):
            return {}

    def profile_path(self, method):
        return self.path.with_name(f'telemetry_{method}.json')

    def show_transport(self, *_):
        method = TRANSPORTS[self.transport.get_selected()]
        active = self.read_settings(self.path)
        self.loaded = active if active.get('transport') == method else self.read_settings(self.profile_path(method))
        self.help.set_text(HELP[method])
        for key, entry in self.entries.items():
            visible = key == 'source_id' or key in FIELD_OPTIONS[method]
            for widget in self.rows[key]:
                widget.set_visible(visible)
            entry.set_text(self.loaded.get(key, 'PC-01' if key == 'source_id' and method == 'opcda' else ''))
        self.entries['url'].set_placeholder_text(
            'https://gateway.example/snapshot' if method == 'rest' else 'mqtts://broker.example:8883')
        self.tags.get_buffer().set_text('\n'.join(self.loaded.get('tags', ())))
        self.lab.set_active(self.loaded.get('lab', False))

    def update_selected(self):
        active = self.read_settings(self.path)
        if active:
            name = NAMES[TRANSPORTS.index(active['transport'])]
            lab = ' · SIMULATED' if active['lab'] else ''
            self.selected.set_text(f'แหล่งข้อมูลที่เลือก · {name} · {active["source_id"]}{lab}')
        else:
            self.selected.set_text('แหล่งข้อมูลที่เลือก · OPC UA' if not self.path.exists() else 'ไฟล์ตั้งค่าแหล่งข้อมูลไม่ถูกต้อง')

    def update_controls(self):
        idle = self.process is None
        self.form.set_sensitive(idle)
        for button in (self.save_button, self.once_button, self.start_button, self.ua_button):
            button.set_sensitive(idle)
        self.stop_button.set_sensitive(not idle and not self.stopping)

    def choose_database(self, _):
        if self.picker is not None:
            return
        picker = Gtk.FileChooserNative.new('เลือกฐานข้อมูลของ Gateway', self.owner,
                                           Gtk.FileChooserAction.OPEN, 'เลือก', 'ยกเลิก')
        file_filter = Gtk.FileFilter()
        file_filter.set_name('Gateway aqua.sqlite3')
        file_filter.add_pattern('aqua.sqlite3')
        picker.add_filter(file_filter)

        def chosen(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file and file.get_path():
                    self.entries['gateway_db'].set_text(file.get_path())
            self.picker = None
            dialog.destroy()

        self.picker = picker
        picker.connect('response', chosen)
        picker.show()

    def save(self, *_):
        if self.process is not None:
            return False
        method = TRANSPORTS[self.transport.get_selected()]
        buffer = self.tags.get_buffer()
        tags = buffer.get_text(*buffer.get_bounds(), True)
        config = {
            'transport': method,
            'source_id': self.entries['source_id'].get_text().strip(),
            'tags': [line.strip() for line in tags.splitlines() if line.strip()],
            'timeout_s': self.loaded.get('timeout_s', 5),
            'lab': self.lab.get_active(),
        }
        for key in FIELD_OPTIONS[method]:
            value = self.entries[key].get_text().strip()
            if value:
                config[key] = value
        try:
            # Preserve a pre-existing manually configured source before switching profiles.
            active = self.read_settings(self.path)
            if active and active['transport'] != method:
                telemetry.save_config(self.profile_path(active['transport']),
                                      {k: v for k, v in active.items() if k not in ('uri', 'binding')})
            telemetry.save_config(self.profile_path(method), config)
            telemetry.save_config(self.path, config)
        except (OSError, ValueError, TypeError, RecursionError) as error:
            self.result.set_text(f'บันทึกไม่ได้ · {error}')
            return False
        self.loaded = config
        self.update_selected()
        self.result.set_text('บันทึกแล้ว · กดอ่านเมื่อพร้อม')
        return True

    def restore_ua(self, _):
        if self.process is not None:
            return
        try:
            active = self.read_settings(self.path)
            if active:
                telemetry.save_config(self.profile_path(active['transport']),
                                      {k: v for k, v in active.items() if k not in ('uri', 'binding')})
            self.path.unlink(missing_ok=True)
        except (OSError, ValueError) as error:
            self.result.set_text(f'เปลี่ยนแหล่งไม่ได้ · {error}')
            return
        self.update_selected()
        self.result.set_text('หน้าติดตามค่าใช้ OPC UA แล้ว')

    def start(self, repeat):
        if not self.save():
            return
        args = [sys.executable, '-B', '-u', '-m', 'collector.telemetry', '--config', str(self.path), '--read']
        if repeat:
            args += ['--interval', '5']
        try:
            process = subprocess.Popen(args, cwd=Path(__file__).resolve().parents[1],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace',
                                       start_new_session=os.name == 'posix')
        except OSError as error:
            self.result.set_text(f'เริ่มอ่านไม่ได้ · {error}')
            return
        self.process = process
        self.stopping = False
        self.update_controls()
        self.result.set_text('กำลังอ่านค่าจากแหล่งที่เลือก…')
        threading.Thread(target=self.watch, args=(process, repeat), daemon=True).start()

    def watch(self, process, repeat):
        with process.stdout:
            for line in process.stdout:
                GLib.idle_add(self.show_result, process, line.strip(), repeat)
        GLib.idle_add(self.finished, process, process.wait())

    def show_result(self, process, line, repeat):
        if self.process is process and not self.closing and not self.stopping:
            prefix = 'อ่านตามรอบ · ' if repeat else ''
            self.result.set_text(prefix + line[:420])
        return GLib.SOURCE_REMOVE

    def finished(self, process, status):
        if self.process is process:
            self.process = None
            if not self.closing:
                if self.stopping:
                    self.result.set_text('หยุดอ่านแล้ว · ค่าล่าสุดยังแสดงพร้อมเวลาต้นทาง')
                elif status != 0 and not self.result.get_text().startswith('Telemetry stopped:'):
                    self.result.set_text(f'ตัวอ่านหยุด · exit {status}')
                self.stopping = False
                self.update_controls()
        return GLib.SOURCE_REMOVE

    def stop(self, *, closing=False):
        self.closing = closing
        if closing and self.picker is not None:
            self.picker.destroy()
            self.picker = None
        if self.process is None or self.stopping:
            return
        self.stopping = True
        if not closing:
            self.update_controls()
            self.result.set_text('กำลังหยุดอ่าน…')
        try:
            if os.name == 'posix':
                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.terminate()
        except ProcessLookupError:
            pass
