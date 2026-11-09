"""Run the actual GTK owner in a separate Lab profile, with outbound test guards.

No fake observations, alternate backend, or industrial/notification workers are started.
This launcher deliberately does not attach to or modify the installed operator profile.
"""
import ipaddress
import json
import os
import signal
import sys
import threading
from pathlib import Path
from unittest.mock import patch

from lab_config import PRIVATE, ROOT

network_audit = {"loopback_connects": 0, "blocked_external_attempts": 0}


def local(host):
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def guard(event, args):
    if event == "socket.connect" and isinstance(args[1], tuple):
        if not local(args[1][0]):
            network_audit["blocked_external_attempts"] += 1
            raise PermissionError("Lab blocks non-loopback connections")
        network_audit["loopback_connects"] += 1
    if event in ("socket.gethostbyaddr", "socket.getaddrinfo") and args[0] and not local(args[0]):
        network_audit["blocked_external_attempts"] += 1
        raise PermissionError("Lab blocks non-loopback name lookups")
    if event == "subprocess.Popen" and isinstance(args[1], (list, tuple)) and Path(str(args[1][0])).name == "ping" and not local(str(args[1][-1])):
        network_audit["blocked_external_attempts"] += 1
        raise PermissionError("Lab blocks non-loopback probes")


def main():
    sys.addaudithook(guard)
    sys.path.insert(0, str(ROOT.parents[1] / "desktop"))
    os.environ["AQUA_OBSERVABILITY_CONFIG"] = str(PRIVATE / "owner.json")
    with patch.object(Path, "home", return_value=PRIVATE / "profile"):
        import app
        from gi.repository import Gio, GLib, Gtk
        application = Gtk.Application(application_id="org.aquacommand.HybridLab", flags=Gio.ApplicationFlags.NON_UNIQUE)
        application.register(None)
        window = app.AquaWinCCWindow(application)
        window.set_title("AQUA COMMAND — HYBRID LAB · isolated profile")
        window.set_default_size(1366, 768)
        window.switch_to_tab("network")
        window.present()
        assert window.hybrid_ui and window.hybrid_ui.bridge, "Optional bridge did not start"
        loop = GLib.MainLoop()
        def receipt():
            result = {"pid": os.getpid(), "profile": "ISOLATED_LAB", "actual_owner_class": type(window).__name__,
                "bridge": window.hybrid_ui.bridge.state, "polling_state": window.polling_engine.get_telemetry()["state"],
                "threads": [t.name for t in threading.enumerate()], "network_audit": network_audit,
                "observations": len(window.opcua_store.snapshot_observations()),
                "native_size": [window.get_width(), window.get_height()]}
            (PRIVATE / "owner-running.json").write_text(json.dumps(result, indent=2))
            return True
        def close(*_):
            receipt()
            window.close()
            loop.quit()
            return False
        signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(close))
        GLib.timeout_add_seconds(5, receipt)
        receipt()
        print("Actual GTK Lab owner running; core monitoring remains STOPPED", flush=True)
        loop.run()


if __name__ == "__main__":
    main()
