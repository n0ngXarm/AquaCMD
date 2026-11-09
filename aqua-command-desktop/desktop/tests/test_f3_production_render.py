"""Actual Cairo pixels: no fabricated flow; committed events move and expire."""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cairo
import f3_network as f3
from f3_runtime import read_snapshot
from opcua_storage import DurableStorage
from gi.repository import GLib


class TestF3EventRendering(unittest.TestCase):
    def setUp(self):
        profile = tempfile.TemporaryDirectory()
        self.addCleanup(profile.cleanup)
        owner = SimpleNamespace(config_dir=Path(profile.name), topology_data={})
        self.storage = DurableStorage(Path(profile.name) / "runtime.db")
        self.view = f3.F3NetworkTopologyView(owner)
        self.addCleanup(GLib.source_remove, self.view.canvas.anim_source_id)

    def frame(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 450)
        with patch("socket.socket", side_effect=AssertionError("I/O in draw")), \
                patch("subprocess.run", side_effect=AssertionError("I/O in draw")), \
                patch("sqlite3.connect", side_effect=AssertionError("I/O in draw")):
            self.view.canvas.on_draw(self.view.canvas, cairo.Context(surface), 1200, 450)
        surface.flush()
        return bytes(surface.get_data())

    def test_idle_and_configured_state_have_identical_pixels_across_ticks(self):
        collector = next(iter(self.view.store.devices.values()))
        collector.update(link_status="LINK_VERIFIED", reachability="REACHABLE", opcua_state="CONNECTED")
        first = self.frame()
        self.view.canvas._on_anim_tick()
        self.assertEqual(first, self.frame())
        self.assertEqual(self.view.runtime.active(), [])

    def test_committed_sqlite_event_changes_pulse_pixels_then_expires(self):
        self.view.runtime.accept(read_snapshot(self.storage.db_path))
        with sqlite3.connect(self.storage.db_path) as conn:
            conn.execute("INSERT INTO tag_observations(tag_name, quality, arrival_timestamp) VALUES ('LAB.Level', 'GOOD', datetime('now'))")
        self.view.runtime.accept(read_snapshot(self.storage.db_path))
        first = self.frame()
        time.sleep(0.12)
        self.assertNotEqual(first, self.frame())
        self.assertEqual(self.view.runtime.active(now=time.monotonic() + 2), [])
        self.view.runtime.pulses.clear()
        idle = self.frame()
        self.view.canvas._on_anim_tick()
        self.assertEqual(idle, self.frame())

    def test_reopening_view_does_not_animate_commits_from_when_it_was_hidden(self):
        self.view.runtime.accept(read_snapshot(self.storage.db_path))
        self.view._on_observer_unmap()
        with sqlite3.connect(self.storage.db_path) as conn:
            conn.execute("INSERT INTO tag_observations(tag_name, quality, arrival_timestamp) VALUES ('LAB.Level', 'GOOD', datetime('now'))")
        self.view.runtime.accept(read_snapshot(self.storage.db_path))
        self.assertEqual(self.view.runtime.active(), [])


if __name__ == "__main__":
    unittest.main()
