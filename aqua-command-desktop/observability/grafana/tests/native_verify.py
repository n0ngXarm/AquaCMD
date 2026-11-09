"""Actual GTK F1-F8/geometry check using a temporary profile and real owner objects."""
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "desktop"))
sys.path.insert(0, str(ROOT))
from lab_config import PRIVATE
from lab_owner import guard, network_audit


def spin(seconds=0.25):
    from gi.repository import GLib
    end = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.005)


def oversized(widget, maximum, route="root"):
    from gi.repository import Gtk
    result = []
    minimum = widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
    if minimum > maximum:
        result.append({"path": route, "minimum": minimum, "actual": widget.get_width(), "class": type(widget).__name__})
    child, index = widget.get_first_child(), 0
    while child:
        result.extend(oversized(child, maximum, route + "/" + str(index)))
        child, index = child.get_next_sibling(), index + 1
    return result


def capture(window, path):
    from gi.repository import Gtk
    paintable = Gtk.WidgetPaintable.new(window)
    spin()
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    node = snapshot.to_node()
    assert node is not None
    assert window.get_renderer().render_texture(node, None).save_to_png(str(path))


def horizontal_overflow(widget, window):
    result = []
    if not widget.get_mapped():
        return result
    success, bounds = widget.compute_bounds(window)
    if success and (bounds.get_x() < -2 or bounds.get_x() + bounds.get_width() > window.get_width() + 2):
        result.append({"class": type(widget).__name__, "x": bounds.get_x(), "width": bounds.get_width()})
    child = widget.get_first_child()
    while child:
        result.extend(horizontal_overflow(child, window))
        child = child.get_next_sibling()
    return result


def main():
    sys.addaudithook(guard)
    output = PRIVATE / "native-screenshots"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aqua-hybrid-native-") as folder:
        profile = Path(folder)
        for name, content in (("key", secrets.token_bytes(32)), ("token", secrets.token_urlsafe(36).encode())):
            (profile / name).write_bytes(content)
            (profile / name).chmod(0o600)
        url = json.loads((PRIVATE / "state.json").read_text())["url"]
        config = profile / "owner.json"
        config.write_text(json.dumps({"enabled": True, "grafana_url": url, "socket_path": str(profile / "api.sock"),
            "id_key_file": str(PRIVATE / "id-key"), "projection_token_file": str(profile / "token")}))
        config.chmod(0o600)
        with patch.object(Path, "home", return_value=profile), patch.dict(os.environ, {"AQUA_OBSERVABILITY_CONFIG": str(config)}):
            import app
            from gi.repository import Gdk, Gio, Gtk
            application = Gtk.Application(application_id="org.aquacommand.HybridLayout", flags=Gio.ApplicationFlags.NON_UNIQUE)
            application.register(None)
            results = []
            window = None
            try:
                for width, height in ((1366, 768), (1600, 900), (1920, 1080)):
                    window = app.AquaWinCCWindow(application)
                    window.switch_to_tab("network")
                    window.set_default_size(width, height)
                    monitors = window.get_display().get_monitors()
                    target_monitor = max((monitors.get_item(i) for i in range(monitors.get_n_items())),
                        key=lambda monitor: monitor.get_geometry().width * monitor.get_geometry().height)
                    window.fullscreen_on_monitor(target_monitor)
                    window.present()
                    spin(0.5)
                    window.unfullscreen()
                    window.set_default_size(width, height)
                    spin(0.8)
                    assert window.hybrid_ui and window.hybrid_ui.bridge
                    capture(window, output / f"native-f3-{width}.png")
                    row = {"requested": [width, height], "actual": [window.get_width(), window.get_height()],
                        "oversized": oversized(window.get_child(), width), "bridge": window.hybrid_ui.bridge.state}
                    display = window.get_display()
                    monitors = display.get_monitors()
                    row["display"] = {"backend": type(display).__name__, "name": display.get_name(), "monitors": [
                        {"width": monitors.get_item(i).get_geometry().width, "height": monitors.get_item(i).get_geometry().height}
                        for i in range(monitors.get_n_items())]}
                    results.append(row)
                    (PRIVATE / "native-results.json").write_text(json.dumps(results, indent=2))
                    assert row["actual"][0] == width, row
                    assert row["actual"][1] == height or height == 1080 and row["actual"][1] == 1048, row
                    row["pages"] = []
                    for key, page in ((Gdk.KEY_F1, "overview"), (Gdk.KEY_F2, "overview"), (Gdk.KEY_F3, "network"),
                                      (Gdk.KEY_F4, "machine"), (Gdk.KEY_F5, "tags"), (Gdk.KEY_F6, "alarms")):
                        window.on_global_key_pressed(None, key, 0, 0)
                        spin(0.35)
                        assert window.stack.get_visible_child_name() == page
                        visible = window.stack.get_visible_child()
                        measured = {"key": Gdk.keyval_name(key), "page": page, "window_width": window.get_width(),
                            "page_minimum": visible.measure(Gtk.Orientation.HORIZONTAL, -1)[0]}
                        row["pages"].append(measured)
                        (PRIVATE / "native-results.json").write_text(json.dumps(results, indent=2))
                        if measured["window_width"] > width or measured["page_minimum"] > width:
                            measured["oversized"] = oversized(visible, width)
                            (PRIVATE / "native-results.json").write_text(json.dumps(results, indent=2))
                            raise AssertionError(measured)
                        capture(window, output / f"native-{Gdk.keyval_name(key).lower()}-{width}.png")
                        if key in (Gdk.KEY_F1, Gdk.KEY_F2):
                            measured["context_overflow"] = horizontal_overflow(window.unified_workspace.right_col, window)
                            (PRIVATE / "native-results.json").write_text(json.dumps(results, indent=2))
                            assert not measured["context_overflow"], measured
                    window.switch_to_tab("network")
                    if width != 1920:
                        window.close()
                        spin()
                        window = None
                trend = window.tags_page_grid.get_child_at(5, 1)
                assert trend.get_label() == "Trend"
                with patch("observability.ui.Gio.AppInfo.launch_default_for_uri") as launch:
                    trend.emit("clicked")
                    launch.assert_called_once()
                link = launch.call_args.args[0]
                tag_id = parse_qs(urlsplit(link).query)["var-tag"][0]
                assert tag_id == window.hybrid_ui.bridge.projection.contract.identity("tag", window.scanned_tags[0]["name"])
                assert window.scanned_tags[0]["name"] not in link
                (PRIVATE / "native-link.json").write_text(json.dumps({"url": link, "tag_id": tag_id}))
                window.on_global_key_pressed(None, Gdk.KEY_F7, 0, 0)
                assert window.hybrid_ui.bridge.projection.refresh_events[-1]["network_probe"] is False
                before = window.polling_engine.get_telemetry()["state"]
                window.on_global_key_pressed(None, Gdk.KEY_F8, 0, 0)
                spin()
                assert window.hybrid_ui.bridge.state == "STOPPED"
                assert window.polling_engine.get_telemetry()["state"] == before == "STOPPED"
                assert network_audit["blocked_external_attempts"] == 0, network_audit
                print(json.dumps({"result": "PASS", "layouts": results, "navigation": "F1-F8", "network_audit": network_audit}, indent=2))
            finally:
                if window:
                    window.close()
                    spin()


if __name__ == "__main__":
    main()
