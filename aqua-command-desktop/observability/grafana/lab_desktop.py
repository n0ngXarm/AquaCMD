"""Icon entrypoint for the existing isolated Lab; no terminal or global service needed."""
import json
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from lab_config import PRIVATE
from lab_control import main as containers
from lab_owner_manage import main as owner


def build_window(application, url=None):
    window = Gtk.ApplicationWindow(application=application, title="AQUA COMMAND Hybrid Lab")
    window.set_default_size(540, 340)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, "set_margin_" + side)(24)
    window.set_child(box)
    title = Gtk.Label(label="AQUA COMMAND · Hybrid Lab", xalign=0)
    title.add_css_class("title-2")
    box.append(title)
    message = Gtk.Label(xalign=0, wrap=True)
    message.set_text("เปิดหน้าต่าง AQUA COMMAND LAB แล้ว\nGrafana ใช้บัญชี Viewer ด้านล่าง ข้อมูลอุปกรณ์ที่ยังไม่ตรวจจะเป็น UNKNOWN และไม่มีข้อมูลย้อนหลังที่สร้างขึ้นแทน" if url else "เปิด Lab ไม่สำเร็จ โปรดดู Diagnostics ของชุดส่งตรวจ")
    box.append(message)
    if url:
        from observability.integration import private_file
        username = Gtk.Entry(text="aqua-viewer", editable=False)
        username.set_tooltip_text("ชื่อผู้ใช้ Grafana Lab · Viewer")
        box.append(username)
        password = Gtk.PasswordEntry(editable=False, show_peek_icon=True)
        password.set_text(private_file(PRIVATE / "viewer-password"))
        password.set_tooltip_text("รหัสผ่านของ Grafana Lab · กดรูปตาเมื่อพร้อมเข้าสู่ระบบ")
        box.append(password)
        button = Gtk.Button(label="เปิด Grafana · F3")
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(url + "/d/aqua-f3?timezone=utc", None))
        box.append(button)
    close = Gtk.Button(label="ปิดหน้าต่างนี้")
    close.connect("clicked", lambda *_: window.close())
    box.append(close)
    return window


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
    url = None
    try:
        containers("start")
        owner("start")
        url = json.loads((PRIVATE / "state.json").read_text())["url"]
    except Exception:
        pass
    application = Gtk.Application(application_id="org.aquacommand.HybridLab.Launcher", flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.connect("activate", lambda app: build_window(app, url).present())
    application.run([])


if __name__ == "__main__":
    main()
