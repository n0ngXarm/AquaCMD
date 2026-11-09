"""Optional external dashboard navigation. Native controls keep their ownership."""
import json
import threading
from urllib.request import urlopen

from gi.repository import Gio, GLib, Gtk
from .integration import start_optional


class DashboardUI:
    def __init__(self, owner):
        self.owner, self.bridge = owner, start_optional(owner)
        self.state = "READY" if self.bridge else "DISABLED"
        self.menu = Gtk.MenuButton(label="Grafana")
        self.menu.set_tooltip_text("เปิด Dashboard แบบอ่านอย่างเดียวในหน้าต่าง Browser แยก")
        self.menu.set_sensitive(self.bridge is not None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        for label, page in (("เปิดหน้าปัจจุบัน", None), ("F1 Monitoring", "overview"),
                ("F2 Event history", "tasks"), ("F3 Network / OPC UA", "network"),
                ("F4 Host metrics", "machine"), ("F6/F7 Diagnostics", "alarms")):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _, target=page: self.open(target))
            box.append(button)
        self.status = Gtk.Label(label="ยังไม่ได้ตรวจ Grafana" if self.bridge else "Grafana ไม่ได้เปิดใช้งาน")
        self.status.set_wrap(True)
        box.append(self.status)
        check = Gtk.Button(label="ตรวจสถานะ Grafana")
        check.connect("clicked", self.check_health)
        box.append(check)
        popover = Gtk.Popover()
        popover.set_child(box)
        self.menu.set_popover(popover)

    def open(self, page=None, tag=None):
        if self.bridge is None:
            return False
        try:
            page = page or self.owner.stack.get_visible_child_name()
            Gio.AppInfo.launch_default_for_uri(self.bridge.link(page, tag=tag), None)
            return True
        except Exception:
            self.state = "BROWSER_UNAVAILABLE"
            self.status.set_text("เปิด Browser ไม่สำเร็จ · ใช้หน้า AQUA เดิมต่อได้")
            return False

    def check_health(self, *_):
        if self.bridge is None:
            return
        self.status.set_text("กำลังตรวจ Grafana…")
        def run():
            state = "UNAVAILABLE"
            try:
                with urlopen(self.bridge.url + "/api/health", timeout=2) as response:
                    body = json.loads(response.read(8192))
                    if response.status == 200 and body.get("database") == "ok":
                        state = "AVAILABLE"
            except Exception:
                pass
            GLib.idle_add(self._health_result, state)
        threading.Thread(target=run, name="Aqua-Dashboard-Health", daemon=True).start()

    def _health_result(self, state):
        self.state = state
        self.status.set_text("Grafana พร้อมใช้งาน" if state == "AVAILABLE" else "Grafana ไม่พร้อม · ใช้หน้า AQUA เดิมต่อได้")
        return False

    def stop(self):
        if self.bridge:
            self.bridge.stop()
