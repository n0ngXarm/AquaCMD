"""Real GTK launcher smoke. Captures only a masked password; never dumps widget text."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parents[1] / "desktop")]
from lab_config import PRIVATE
from lab_desktop import build_window
from lab_owner_manage import running
from native_verify import capture, spin
from gi.repository import Gio, Gtk


def main():
    before = running()
    application = Gtk.Application(application_id="org.aquacommand.HybridLab.LauncherSmoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.register(None)
    url = json.loads((PRIVATE / "state.json").read_text())["url"]
    window = build_window(application, url)
    window.present()
    spin(0.5)
    assert 500 <= window.get_width() <= 600 and window.get_height() < 500
    child = window.get_child().get_first_child()
    passwords = []
    while child:
        if isinstance(child, Gtk.PasswordEntry):
            passwords.append(child)
        child = child.get_next_sibling()
    assert len(passwords) == 1 and passwords[0].get_editable() is False
    capture(window, ROOT.parents[3] / "evidence/screenshots/lab-launcher.png")
    size = [window.get_width(), window.get_height()]
    window.close()
    spin()
    assert running() == before and before
    result = {"result": "PASS", "actual_size": size, "password_masked": True, "existing_owner_unchanged": True}
    (ROOT.parents[3] / "evidence/launcher-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
