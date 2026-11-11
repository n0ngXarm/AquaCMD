"""Test-only controls for actual F3 boundaries; never authorize field I/O."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch
import cairo
from gi.repository import GLib
import f3_network as f3
from f3_fixture import configure_legacy_inventory
from f3_layout import page_inventory


class HeldThread:
    started = []

    def __init__(self, target, args=(), kwargs=None, **ignored):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.started.append(self)

    def run(self):
        self.target(*self.args, **self.kwargs)


def drain():
    context = GLib.MainContext.default()
    for _ in range(300):
        if not context.pending():
            return
        context.iteration(False)
    raise AssertionError('GLib callbacks did not drain')


def new_view(case):
    profile = tempfile.TemporaryDirectory()
    case.addCleanup(profile.cleanup)
    configure_legacy_inventory(profile.name)
    owner = SimpleNamespace(config_dir=Path(profile.name), topology_data={})
    with patch.object(f3.F3NetworkTopologyView, 'refresh_local_state'):
        view = f3.F3NetworkTopologyView(owner)
    case.addCleanup(GLib.source_remove, view.canvas.anim_source_id)
    return view


def assert_all_pages_fit(case, view, width, height):
    case.assertGreater(width, 0)
    case.assertGreater(height, 0)
    devices = list(view.store.devices.values())
    seen = set()
    _, initial = page_inventory(devices, height, 0, width)
    for page in range(initial['pages']):
        # Use the same paged inventory input as the native drawing callback.
        inventory, info = page_inventory(devices, height, page, width)
        view.diagram_inventory = inventory
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        view.canvas.on_draw(view.canvas, cairo.Context(surface), width, height)
        for dev in inventory:
            x, y, w, h = view.canvas.node_rects[dev['device_id']]
            case.assertGreaterEqual(x, 0)
            case.assertGreaterEqual(y, 0)
            case.assertGreater(w, 0)
            case.assertGreaterEqual(h, 80)
            case.assertLessEqual(x + w, width)
            case.assertLessEqual(y + h, height)
            seen.add(dev['device_id'])
    case.assertEqual(seen, set(view.store.devices))
