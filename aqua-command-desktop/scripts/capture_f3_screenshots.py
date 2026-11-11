#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_f3_screenshots.py — Captures native GTK4 screenshots of reconstructed F3 tab
Generates all deliverables required by Phase 10:
  - f3_live_diagram_1366x768.png
  - f3_live_diagram_1920x1080.png
  - f3_inspector_open_1366x768.png
  - f3_device_settings_dialog_1366x768.png
  - f3_ot_authorization_dialog_1366x768.png
  - f3_device_details_dialog_1366x768.png
  - f3_device_cards_1366x768.png
  - f3_device_cards_1920x1080.png
  - Animation sequence frames (f3_anim_frame_01.png to 03.png)
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
from f3_network import (
    DeviceDetailsDialog,
    DeviceSettingsDialog,
    OTAuthorizationDialog,
    OpcUaState,
    ConnectionState
)

out_dir = Path(__file__).resolve().parent.parent.parent / 'docs' / 'screenshots' / 'f3_network'
out_dir.mkdir(parents=True, exist_ok=True)

app = Gtk.Application.new("org.aqua.command.screenshot.f3", 0)
app.register(None)

ctx = GLib.MainContext.default()

def spin(duration=0.1):
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

    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, w, h)
    node = snapshot.to_node()
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
    # 1. Capture at 1366x768
    win1366 = AquaWinCCWindow(app)
    win1366.set_default_size(1366, 768)
    win1366.set_size_request(1366, 768)
    win1366.present()
    spin(0.3)
    win1366.switch_to_tab('network')
    spin(0.3)

    f3_view = win1366.f3_network_view

    # Select PC1 and ensure Inspector is open
    f3_view.select_device("PC1")
    f3_view.toggle_inspector(True)
    spin(0.2)
    snap_widget(win1366, out_dir / "f3_inspector_open_1366x768.png")
    snap_widget(win1366, out_dir / "f3_live_diagram_1366x768.png")
    snap_widget(win1366, out_dir / "f3_device_cards_1366x768.png")
    snap_widget(win1366, out_dir / "f3_topology_1366x768.png")
    snap_widget(win1366, out_dir / "f3_ip_table_1366x768.png")

    # Capture Modals
    # A. Device Settings Dialog
    pc1_dev = f3_view.store.devices["PC1"]
    dlg_settings = DeviceSettingsDialog(win1366, pc1_dev, f3_view.store)
    dlg_settings.present()
    spin(0.3)
    snap_widget(dlg_settings, out_dir / "f3_device_settings_dialog_1366x768.png")
    dlg_settings.close()
    spin(0.1)

    # B. OT Authorization Dialog
    dlg_auth = OTAuthorizationDialog(win1366, "PC1 · SCADA Workstation", "192.0.2.11", None)
    dlg_auth.present()
    spin(0.3)
    snap_widget(dlg_auth, out_dir / "f3_ot_authorization_dialog_1366x768.png")
    dlg_auth.close()
    spin(0.1)

    # C. Device Details Dialog
    pc4_card = f3_view.cards["PC4"]
    dlg_details = DeviceDetailsDialog(win1366, pc4_card.device_meta, pc4_card.status_data, f3_view.local_state)
    dlg_details.present()
    spin(0.3)
    snap_widget(dlg_details, out_dir / "f3_device_details_dialog_1366x768.png")
    dlg_details.close()
    spin(0.1)

    # D. Animation Evidence Sequence
    # Simulate active OPC UA link on PC1 to get moving beads
    f3_view.store.update_device("PC1", {
        "opcua_state": OpcUaState.CONNECTED,
        "reachability": "REACHABLE"
    })
    for frame_idx in range(1, 4):
        f3_view.canvas.anim_tick_count += 5
        f3_view.canvas.queue_draw()
        spin(0.15)
        snap_widget(win1366, out_dir / f"f3_anim_frame_0{frame_idx}.png")

    win1366.close()
    spin(0.1)

    # 2. Capture at 1920x1080
    win1920 = AquaWinCCWindow(app)
    win1920.set_default_size(1920, 1080)
    win1920.set_size_request(1920, 1080)
    win1920.present()
    spin(0.3)
    win1920.switch_to_tab('network')
    spin(0.3)

    snap_widget(win1920, out_dir / "f3_live_diagram_1920x1080.png")
    snap_widget(win1920, out_dir / "f3_device_cards_1920x1080.png")
    snap_widget(win1920, out_dir / "f3_topology_1920x1080.png")
    snap_widget(win1920, out_dir / "f3_ip_table_1920x1080.png")

    win1920.close()
    spin(0.1)

if __name__ == '__main__':
    print('Starting capture of all F3 screenshots and animation evidence...')
    capture_all()
    print('All captures completed successfully!')
