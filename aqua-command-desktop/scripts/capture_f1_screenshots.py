#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_f1_screenshots.py — Captures native GTK4 screenshots of unified F1 Tag Overview
Generates deliverables:
  - f1_tag_overview_1366x768.png
  - f1_tag_overview_1920x1080.png
  - f1_task_manager_dialog_1366x768.png
"""

import os
import sys
import time
from pathlib import Path

desktop_dir = Path(__file__).resolve().parent.parent / 'desktop'
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk

from app import AquaWinCCWindow

out_dir = Path(__file__).resolve().parent.parent.parent / 'docs' / 'screenshots' / 'f1_overview'
out_dir.mkdir(parents=True, exist_ok=True)

app = Gtk.Application.new("org.aqua.command.screenshot.f1", 0)
app.register(None)

ctx = GLib.MainContext.default()

def spin(duration=0.2):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.01)

def snap_widget(widget, filepath):
    paintable = Gtk.WidgetPaintable.new(widget)
    w = widget.get_width()
    h = widget.get_height()
    if w <= 0 or h <= 0:
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

    deadline = time.monotonic() + 3.0
    node = None
    while node is None and time.monotonic() < deadline:
        spin(0.05)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, w, h)
        node = snapshot.to_node()
        if node is None:
            widget.queue_draw()

    if node is None:
        raise RuntimeError(f"Failed to generate render node for widget {widget}")

    renderer = widget.get_renderer()
    if renderer is None:
        native = widget.get_native()
        surface = native.get_surface() if native else None
        renderer = surface.get_renderer() if surface else None

    if renderer is None:
        raise RuntimeError("No renderer found for widget")

    texture = renderer.render_texture(node, None)
    if not texture.save_to_png(str(filepath)):
        raise RuntimeError(f"Failed saving PNG to {filepath}")
    print(f"Captured: {filepath.name} ({w}x{h})")

def capture_all():
    print("Capturing 1366x768...")
    win1366 = AquaWinCCWindow(app)
    win1366.set_default_size(1366, 768)
    win1366.set_size_request(1366, 768)
    win1366.present()
    spin(0.5)

    # Overview is default tab (F1)
    win1366.switch_to_tab('overview')
    spin(0.6)
    snap_widget(win1366, out_dir / "f1_tag_overview_1366x768.png")

    # Open WebKit Task Manager Dialog (F2) for TASK-02 (with assigned tags)
    if hasattr(win1366, 'unified_workspace') and win1366.unified_workspace.f1_api:
        win1366.unified_workspace.f1_api.open_task_dialog('TASK-02')
    else:
        win1366.activate_workspace_mode('task_manager')
    spin(0.8)
    # When F1ApiView is active, Task Manager is rendered inside the WebKit workspace
    snap_widget(win1366, out_dir / "f1_task_manager_dialog_1366x768.png")

    # Close modal and return to monitoring (F1 -> F2 -> Close -> F1 lifecycle)
    win1366.activate_workspace_mode('monitoring')
    spin(0.5)

    print("Capturing 1920x1080...")
    win1366.set_default_size(1920, 1080)
    win1366.set_size_request(1920, 1080)
    spin(0.8)
    snap_widget(win1366, out_dir / "f1_tag_overview_1920x1080.png")

    win1366.close()
    spin(0.2)

if __name__ == '__main__':
    capture_all()
    print("All F1 screenshots captured successfully!")
