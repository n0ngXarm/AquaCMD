#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — F2 TAG LIBRARY & TASK CONFIGURATOR V4
Concept: Tag -> Task -> Actions

Architecture:
- Top Bar: Compact Scan Operations Toolbar (Scan Once, Auto Scan Start/Stop, Interval, Duration, Live Countdown)
- Main Paned (Interactive 55% / 45% Split):
    - LEFT Panel (~55%): Complete Tag Library
        - Sub-column 1: Group Explorer (All Groups + 10 real Catalog groups with dynamic counts)
        - Sub-column 2: Catalog Tag Table (Search, Select All, Multi-select, Not Observed live status, Add Selected to Task)
    - RIGHT Panel (~45%): Task Configuration
        - Section 1: Task Management (Task Selector, Create New Task, Task ID, Task Name, Task Cycle, Verifiable State)
        - Section 2: Task Actions (Local Archive Logging, Telegram Alert with F6 link, Enable Task)
        - Section 3: Assigned Tags (Technical Table: Tag Name, Source Group, Type, Status [Not Observed], Remove Action)
        - Section 4: Save & Validation (Atomic JSON Persistence, Live Error/Warning Feedback, Save Task Button)
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango

# Clean Data Type Mapping
DATA_TYPE_MAPPING = {
    "Binary Tag": "Bool",
    "Floating-point number 32-bit IEEE 754": "Float",
    "Floating-point number 64-bit IEEE 754": "Double",
    "Unsigned 16-bit value": "Word",
    "Signed 16-bit value": "Int",
    "Unsigned 32-bit value": "DWord",
    "Signed 32-bit value": "DInt",
    "Boolean": "Bool",
    "Float": "Float",
    "Double": "Double",
    "Integer": "Int",
    "Word": "Word",
    "DWord": "DWord",
    "String": "String",
    "Int": "Int",
    "Bool": "Bool"
}

# Group Display Metadata (Catalog-Driven)
GROUP_METADATA = {
    "All": ("ทุกกลุ่ม (All Groups)", "รวมสัญญาณทั้งหมดในระบบ SCADA"),
    "High_VSD": ("ปั๊มน้ำแรงดันสูง VSD", "ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ"),
    "High_Soft": ("ปั๊มน้ำแรงดันสูง Soft Starter", "ระบบสูบน้ำแรงดันสูงสตาร์ทแบบนุ่มนวล"),
    "High_DOL": ("ปั๊มน้ำแรงดันสูง Direct On Line", "ระบบสูบน้ำสตาร์ทตรงแบบกระแสสูง"),
    "High_Valve": ("วาล์วท่อส่งแรงดันสูง", "วาล์วควบคุมการจ่ายน้ำแรงดันสูง"),
    "Low_VSD": ("ปั๊มน้ำแรงดันต่ำ VSD", "ระบบสูบน้ำดิบและแรงดันต่ำแบบ VSD"),
    "Low_DOL": ("ปั๊มน้ำแรงดันต่ำ Direct On Line", "ระบบสูบน้ำดิบแบบสตาร์ทตรง"),
    "Low_Valve": ("วาล์วท่อส่งแรงดันต่ำ", "วาล์วควบคุมท่อส่งน้ำแรงดันต่ำ"),
    "Low_Flow": ("มาตรวัดอัตราการไหล Flow Meter", "มิเตอร์วัดปริมาตรและอัตราการไหลของน้ำ"),
    "Chemical": ("ระบบจ่ายสารเคมีและคลอรีน", "ระบบควบคุมคุณภาพน้ำและจ่ายสารเคมี"),
    "Power": ("ระบบไฟฟ้าและหม้อแปลง MDB", "ระบบตรวจวัดแรงดันและกำลังไฟฟ้าหลัก")
}

# Task Cycle Options
CYCLE_OPTIONS = [
    (1, "1 วินาที (High Priority)"),
    (5, "5 วินาที (มาตรฐาน WinCC V8.1)"),
    (10, "10 วินาที (General Monitoring)"),
    (30, "30 วินาที (Slow Sampling)"),
    (60, "60 วินาที (Hourly Batch)")
]


class F2TaskManagerView:
    """
    AQUA COMMAND F2 Tag Library & Task Configurator V4
    Implements Tag -> Task -> Actions Architecture for Linux GTK4
    """

    def __init__(self, owner, root_box):
        self.owner = owner
        self.root_box = root_box

        # State Variables
        self.selected_task_index = getattr(self.owner, 'current_task_idx', 0)
        self.selected_group_key = "All"
        self.search_query = ""
        self.selected_catalog_tags = set()  # set of tag name strings selected in library
        self.catalog_tags_cache = []
        self.group_counts = {}
        self.has_unsaved_changes = False

        # UI References
        self.group_list_items = {}
        self.catalog_checkboxes = {}
        self.task_selector_updating = False

        # Build UI
        self.build_ui()

    # =========================================================================
    # UI ROOT CONSTRUCTION
    # =========================================================================

    def build_ui(self):
        """Constructs Root Layout: Scan Bar Top + 55/45 Split View"""
        # Clear existing children if any
        while True:
            first = self.root_box.get_first_child()
            if not first:
                break
            self.root_box.remove(first)

        # 1. Top Compact Scan Operations Toolbar
        self.build_scan_toolbar()

        # 2. Main Two-Panel Layout (Left Tag Library 55% / Right Task Config 45%)
        self.build_main_split_view()

        # 3. Synchronize Catalog & Initial Render
        self.sync_catalog_data()
        self.refresh_group_explorer()
        self.render_catalog_table()
        self.load_current_task_to_ui()

    # =========================================================================
    # 1. TOP SCAN TOOLBAR
    # =========================================================================

    def build_scan_toolbar(self):
        """Builds a compact, professional top toolbar for Scan Operations"""
        self.scan_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_bar.add_css_class('f2-scan-bar')
        self.root_box.append(self.scan_bar)

        # Scan Once Button
        self.btn_scan_once = Gtk.Button(label="🔍 สแกนทันที 1 ครั้ง (Scan Once)")
        self.btn_scan_once.add_css_class('f2-btn-scan-once')
        self.btn_scan_once.connect('clicked', lambda _: self.owner.trigger_single_scan(silent=False))
        self.scan_bar.append(self.btn_scan_once)

        # Auto Scan Toggle Button
        is_running = getattr(self.owner, 'auto_scan_active', False)
        self.btn_auto_scan = Gtk.Button(label="⏹ หยุด Auto Scan" if is_running else "▶ เริ่ม Auto Scan")
        self.btn_auto_scan.add_css_class('f2-btn-auto-stop' if is_running else 'f2-btn-auto-start')
        self.btn_auto_scan.connect('clicked', self.on_toggle_auto_scan)
        self.scan_bar.append(self.btn_auto_scan)
        self.owner.btn_auto_scan = self.btn_auto_scan

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1.add_css_class('f2-scan-sep')
        self.scan_bar.append(sep1)

        # Scan Interval Dropdown
        lbl_int = Gtk.Label(label="รอบสแกน:")
        lbl_int.add_css_class('f2-scan-label')
        self.scan_bar.append(lbl_int)

        self.interval_combo = Gtk.DropDown.new_from_strings([
            "1 วินาที", "5 วินาที (มาตรฐาน)", "10 วินาที", "30 วินาที", "60 วินาที"
        ])
        self.interval_combo.add_css_class('f2-scan-dropdown')
        self.interval_combo.set_selected(1)  # Default 5s
        self.interval_combo.connect('notify::selected', self.owner.on_scan_interval_changed)
        self.scan_bar.append(self.interval_combo)

        # Scan Duration Dropdown
        lbl_dur = Gtk.Label(label="ระยะเวลารวม:")
        lbl_dur.add_css_class('f2-scan-label')
        self.scan_bar.append(lbl_dur)

        self.duration_combo = Gtk.DropDown.new_from_strings([
            "1 ชั่วโมง (1 hr)", "รันต่อเนื่อง", "2 ชั่วโมง (2 hrs)", "8 ชั่วโมง (1 Shift)"
        ])
        self.duration_combo.add_css_class('f2-scan-dropdown')
        self.duration_combo.set_selected(0)  # Default 1 hr
        self.duration_combo.connect('notify::selected', self.owner.on_scan_duration_changed)
        self.scan_bar.append(self.duration_combo)

        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep2.add_css_class('f2-scan-sep')
        self.scan_bar.append(sep2)

        # Live Auto Scan Status Badge
        self.lbl_auto_scan_status = Gtk.Label(label="Auto Scan: สแตนด์บาย (รอเริ่ม)")
        self.lbl_auto_scan_status.add_css_class('f2-scan-status-idle')
        self.scan_bar.append(self.lbl_auto_scan_status)
        self.owner.auto_scan_badge = self.lbl_auto_scan_status

        # Countdown Label
        self.lbl_countdown = Gtk.Label(label="รอบถัดไป: 5s")
        self.lbl_countdown.add_css_class('f2-scan-countdown')
        self.scan_bar.append(self.lbl_countdown)
        self.owner.auto_scan_countdown_lbl = self.lbl_countdown

        # Remaining Time Label
        self.lbl_remaining = Gtk.Label(label="เหลือ: 1 ชม.")
        self.lbl_remaining.add_css_class('f2-scan-meta')
        self.scan_bar.append(self.lbl_remaining)
        self.owner.auto_scan_remaining_lbl = self.lbl_remaining

        # Cycles Completed Label
        self.lbl_cycles = Gtk.Label(label="สแกน: 0 รอบ")
        self.lbl_cycles.add_css_class('f2-scan-meta')
        self.scan_bar.append(self.lbl_cycles)
        self.owner.auto_scan_cycle_lbl = self.lbl_cycles

        # Last Time Label (dummy hook)
        self.lbl_last_time = Gtk.Label(label="")
        self.owner.auto_scan_last_time_lbl = self.lbl_last_time

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.scan_bar.append(spacer)

        # Catalog Count Badge
        cat_count = len(getattr(self.owner, 'scanned_tags', []))
        self.lbl_catalog_status = Gtk.Label(label=f"Catalog: {cat_count} Tags")
        self.lbl_catalog_status.add_css_class('f2-badge-catalog')
        self.scan_bar.append(self.lbl_catalog_status)

    def on_toggle_auto_scan(self, widget):
        """Toggles system auto-scan and updates scan bar & badges"""
        self.owner.toggle_auto_scan(widget)
        is_running = getattr(self.owner, 'auto_scan_active', False)
        if is_running:
            self.btn_auto_scan.set_label("⏹ หยุด Auto Scan")
            self.btn_auto_scan.remove_css_class('f2-btn-auto-start')
            self.btn_auto_scan.add_css_class('f2-btn-auto-stop')
            self.lbl_auto_scan_status.set_label("Auto Scan: ทำงาน (Active)")
            self.lbl_auto_scan_status.remove_css_class('f2-scan-status-idle')
            self.lbl_auto_scan_status.add_css_class('f2-scan-status-running')
        else:
            self.btn_auto_scan.set_label("▶ เริ่ม Auto Scan")
            self.btn_auto_scan.remove_css_class('f2-btn-auto-stop')
            self.btn_auto_scan.add_css_class('f2-btn-auto-start')
            self.lbl_auto_scan_status.set_label("Auto Scan: สแตนด์บาย (รอเริ่ม)")
            self.lbl_auto_scan_status.remove_css_class('f2-scan-status-running')
            self.lbl_auto_scan_status.add_css_class('f2-scan-status-idle')

        self.update_task_status_strip()

    # =========================================================================
    # 2. MAIN TWO-PANEL LAYOUT (LEFT 55% / RIGHT 45%)
    # =========================================================================

    def build_main_split_view(self):
        """Constructs interactive GTK4 Paned with Left Tag Library and Right Task Config"""
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_paned.set_hexpand(True)
        self.main_paned.set_vexpand(True)
        self.main_paned.set_wide_handle(True)
        self.main_paned.set_position(740)  # ~55% on 1366px screen
        self.root_box.append(self.main_paned)

        # LEFT Panel: Complete Tag Library (~55%)
        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.left_panel.add_css_class('f2-panel')
        self.left_panel.set_hexpand(True)
        self.left_panel.set_vexpand(True)
        self.left_panel.set_size_request(620, -1)
        self.main_paned.set_start_child(self.left_panel)
        self.main_paned.set_resize_start_child(True)

        # RIGHT Panel: Task Configuration (~45%)
        self.right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.right_panel.add_css_class('f2-panel')
        self.right_panel.set_hexpand(True)
        self.right_panel.set_vexpand(True)
        self.right_panel.set_size_request(450, -1)
        self.main_paned.set_end_child(self.right_panel)
        self.main_paned.set_resize_end_child(True)

        # Build Internal Panels
        self.build_left_tag_library()
        self.build_right_task_config()

    # =========================================================================
    # 3. LEFT PANEL: COMPLETE TAG LIBRARY (~55%)
    # =========================================================================

    def build_left_tag_library(self):
        """Builds Left Panel: Group Explorer Sub-panel + Catalog Tag Table"""
        # Header Row
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr.add_css_class('f2-panel-header')
        self.left_panel.append(hdr)

        lbl_title = Gtk.Label(label="คลังสัญญาณ WinCC SCADA (Tag Library)")
        lbl_title.add_css_class('f2-panel-title')
        hdr.append(lbl_title)

        self.lbl_catalog_tag_count = Gtk.Label(label="0 Tags")
        self.lbl_catalog_tag_count.add_css_class('f2-badge-blue')
        hdr.append(self.lbl_catalog_tag_count)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        hdr.append(spacer)

        self.lbl_selected_counter = Gtk.Label(label="เลือกอยู่: 0 รายการ")
        self.lbl_selected_counter.add_css_class('f2-badge-blue')
        hdr.append(self.lbl_selected_counter)

        # Sub-split: Group Selector (Left-sub) + Tag Table (Right-sub)
        sub_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sub_box.set_hexpand(True)
        sub_box.set_vexpand(True)
        self.left_panel.append(sub_box)

        # 3.1 Sub-column 1: Group Selector (~190px)
        self.build_group_selector(sub_box)

        # 3.2 Sub-column 2: Tag Table & Action Bar
        self.build_catalog_table_area(sub_box)

    def build_group_selector(self, parent_box):
        """Builds Group Explorer sidebar on the left of Tag Library"""
        grp_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        grp_container.add_css_class('f2-group-container')
        grp_container.set_size_request(190, -1)
        grp_container.set_vexpand(True)
        parent_box.append(grp_container)

        # Header
        lbl_grp_hdr = Gtk.Label(label="กลุ่มอุปกรณ์ (Groups)")
        lbl_grp_hdr.add_css_class('f2-subpanel-title')
        lbl_grp_hdr.set_xalign(0.0)
        grp_container.append(lbl_grp_hdr)

        # Scrolled List of Groups
        grp_scroll = Gtk.ScrolledWindow()
        grp_scroll.set_hexpand(True)
        grp_scroll.set_vexpand(True)
        grp_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        grp_container.append(grp_scroll)

        self.group_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.group_list_box.add_css_class('f2-group-list')
        grp_scroll.set_child(self.group_list_box)

    def refresh_group_explorer(self):
        """Populates the Group Explorer with All Groups + 10 real Catalog groups"""
        while True:
            child = self.group_list_box.get_first_child()
            if not child:
                break
            self.group_list_box.remove(child)

        self.group_list_items.clear()
        total_tags = len(self.catalog_tags_cache)
        self.lbl_catalog_tag_count.set_label(f"{total_tags} Tags")

        # Group Keys: All + Real detected groups
        groups = ["All"]
        # Find all distinct groups in catalog
        detected_groups = sorted(list(set(t.get('group', 'Other') for t in self.catalog_tags_cache)))
        groups.extend(detected_groups)

        for gkey in groups:
            meta = GROUP_METADATA.get(gkey, (gkey, f"สัญญาณกลุ่ม {gkey}"))
            title = meta[0]
            count = total_tags if gkey == "All" else sum(1 for t in self.catalog_tags_cache if t.get('group') == gkey)
            self.group_counts[gkey] = count

            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            item_box.add_css_class('f2-group-item')
            if gkey == self.selected_group_key:
                item_box.add_css_class('f2-group-item-selected')

            # Row 1: Title & Count
            r1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            item_box.append(r1)

            lbl_name = Gtk.Label(label=title)
            lbl_name.add_css_class('f2-group-title')
            lbl_name.set_hexpand(True)
            lbl_name.set_xalign(0.0)
            lbl_name.set_ellipsize(Pango.EllipsizeMode.END)
            r1.append(lbl_name)

            lbl_cnt = Gtk.Label(label=str(count))
            lbl_cnt.add_css_class('f2-group-count-badge')
            r1.append(lbl_cnt)

            # Click gesture
            click = Gtk.GestureClick()
            click.connect('released', self._make_group_click_handler(gkey))
            item_box.add_controller(click)

            self.group_list_items[gkey] = item_box
            self.group_list_box.append(item_box)

    def _make_group_click_handler(self, gkey):
        def _on_click(gesture, n_press, x, y):
            self.on_select_group(gkey)
        return _on_click

    def on_select_group(self, gkey):
        """Switches active group filter in Tag Library without losing selections"""
        self.selected_group_key = gkey
        for key, widget in self.group_list_items.items():
            if key == gkey:
                widget.add_css_class('f2-group-item-selected')
            else:
                widget.remove_css_class('f2-group-item-selected')

        self.render_catalog_table()

    def build_catalog_table_area(self, parent_box):
        """Builds Sub-column 2: Search, Filter, Table, and Add to Task Button"""
        table_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        table_container.add_css_class('f2-table-container')
        table_container.set_hexpand(True)
        table_container.set_vexpand(True)
        parent_box.append(table_container)

        # Top Bar: Search Entry + Bulk Selection
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        table_container.append(search_row)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("ค้นหา Tag Name, PLC Address, กลุ่ม...")
        self.search_entry.set_hexpand(True)
        self.search_entry.add_css_class('f2-search-input')
        self.search_entry.connect('search-changed', self.on_search_changed)
        search_row.append(self.search_entry)

        btn_select_all = Gtk.Button(label="เลือกทั้งหมดในมุมมองนี้")
        btn_select_all.add_css_class('f2-btn-neutral-sm')
        btn_select_all.connect('clicked', self.on_select_all_in_view)
        search_row.append(btn_select_all)

        btn_clear_sel = Gtk.Button(label="ล้างที่เลือก")
        btn_clear_sel.add_css_class('f2-btn-neutral-sm')
        btn_clear_sel.connect('clicked', self.on_clear_selection)
        search_row.append(btn_clear_sel)

        # Filter Notification Strip (shows actively filtering state, especially for single-tag groups)
        self.filter_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filter_banner.add_css_class('f2-filter-banner')
        self.filter_banner.set_visible(False)
        table_container.append(self.filter_banner)

        self.lbl_filter_status = Gtk.Label(label="")
        self.lbl_filter_status.add_css_class('f2-filter-label')
        self.lbl_filter_status.set_hexpand(True)
        self.lbl_filter_status.set_xalign(0.0)
        self.filter_banner.append(self.lbl_filter_status)

        self.btn_clear_filter = Gtk.Button(label="✕ แสดงทั้งหมด (All Groups)")
        self.btn_clear_filter.add_css_class('f2-btn-clear-filter')
        self.btn_clear_filter.connect('clicked', lambda _: self.on_select_group("All"))
        self.filter_banner.append(self.btn_clear_filter)

        # Scrolled Window with Catalog Grid
        self.catalog_scroll = Gtk.ScrolledWindow()
        self.catalog_scroll.set_hexpand(True)
        self.catalog_scroll.set_vexpand(True)
        self.catalog_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        table_container.append(self.catalog_scroll)

        self.catalog_grid = Gtk.Grid(column_spacing=0, row_spacing=0)
        self.catalog_scroll.set_child(self.catalog_grid)

        # Bottom Action Bar: Add Selected Tags to Task
        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom_row.add_css_class('f2-lib-bottom-bar')
        table_container.append(bottom_row)

        self.lbl_bottom_sel_info = Gtk.Label(label="เลือก Tag จากตาราง แล้วกดปุ่มเพื่อเพิ่มเข้า Task")
        self.lbl_bottom_sel_info.add_css_class('f2-table-cell-muted')
        self.lbl_bottom_sel_info.set_hexpand(True)
        self.lbl_bottom_sel_info.set_xalign(0.0)
        bottom_row.append(self.lbl_bottom_sel_info)

        self.btn_add_to_task = Gtk.Button(label="➕ เพิ่ม Tag ที่เลือกเข้าสู่ Task")
        self.btn_add_to_task.add_css_class('f2-btn-add-to-task')
        self.btn_add_to_task.connect('clicked', self.on_add_selected_tags_to_task)
        bottom_row.append(self.btn_add_to_task)

    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.render_catalog_table()

    def sync_catalog_data(self):
        """Loads verified catalog tags from scanned_tags"""
        scanned = getattr(self.owner, 'scanned_tags', [])
        self.catalog_tags_cache = scanned if scanned else []

    def render_catalog_table(self):
        """Renders catalog tags matching current group and search filters"""
        while True:
            child = self.catalog_grid.get_first_child()
            if not child:
                break
            self.catalog_grid.remove(child)

        self.catalog_checkboxes.clear()

        # Determine currently assigned tags in active task to show assigned status
        tasks = getattr(self.owner, 'tasks', [])
        assigned_in_current_task = set()
        if tasks and 0 <= self.selected_task_index < len(tasks):
            for x in tasks[self.selected_task_index].get('tags', []):
                tname = x.get('name') if isinstance(x, dict) else str(x)
                assigned_in_current_task.add(tname)

        # Filter tags
        filtered = []
        for t in self.catalog_tags_cache:
            tname = t.get('name', '')
            group = t.get('group', '')
            addr = t.get('plc_addr', '')
            dtype = t.get('type', '')

            # Group filter
            if self.selected_group_key != "All" and group != self.selected_group_key:
                continue

            # Search query filter
            if self.search_query:
                q = self.search_query
                match = (
                    q in tname.lower() or
                    q in group.lower() or
                    q in addr.lower() or
                    q in dtype.lower()
                )
                if not match:
                    continue

            filtered.append(t)

        self.currently_filtered_tags = filtered

        # Update Filter Banner Status (Prevent user confusion on single-tag groups like Default)
        total_in_catalog = len(self.catalog_tags_cache)
        count_shown = len(filtered)
        if hasattr(self, 'filter_banner'):
            if self.selected_group_key != "All" or self.search_query:
                self.filter_banner.set_visible(True)
                meta = GROUP_METADATA.get(self.selected_group_key, (self.selected_group_key,))
                grp_name = meta[0]
                if self.selected_group_key == "Default":
                    self.lbl_filter_status.set_label(
                        f"🔍 กำลังกรอง: กลุ่ม Default (แสดง {count_shown} จากทั้งหมด {total_in_catalog} Tags ในระบบ)"
                    )
                elif self.search_query:
                    self.lbl_filter_status.set_label(
                        f"🔍 ผลการค้นหา: '{self.search_query}' (พบ {count_shown} จากทั้งหมด {total_in_catalog} Tags ในระบบ)"
                    )
                else:
                    self.lbl_filter_status.set_label(
                        f"🔍 กำลังกรอง: {grp_name} (แสดง {count_shown} จากทั้งหมด {total_in_catalog} Tags ในระบบ)"
                    )
            else:
                self.filter_banner.set_visible(False)

        if not filtered:
            empty_lbl = Gtk.Label(label="ไม่พบ Tag ที่ตรงกับเงื่อนไขในกลุ่มนี้")
            empty_lbl.add_css_class('f2-table-empty')
            empty_lbl.set_xalign(0.0)
            self.catalog_grid.attach(empty_lbl, 0, 1, 6, 1)
            return

        # Table Header
        headers = [
            ("เลือก", 34),
            ("TAG NAME / IDENTIFIER", 160),
            ("กลุ่ม", 85),
            ("PLC ADDR", 75),
            ("ชนิด", 55),
            ("สถานะสด", 75)
        ]
        for col_idx, (htitle, width) in enumerate(headers):
            lbl = Gtk.Label(label=htitle)
            lbl.add_css_class('f2-table-hdr')
            lbl.set_size_request(width, 30)
            lbl.set_xalign(0.5 if col_idx == 0 else 0.0)
            self.catalog_grid.attach(lbl, col_idx, 0, 1, 1)

        for row_idx, t in enumerate(filtered, 1):
            tname = t.get('name', '')
            group = t.get('group', '—')
            addr = t.get('plc_addr', '—')
            raw_type = t.get('type', '—')
            clean_type = DATA_TYPE_MAPPING.get(raw_type, raw_type)
            is_assigned = tname in assigned_in_current_task

            # Column 0: Checkbox
            chk = Gtk.CheckButton()
            chk.add_css_class('f2-check')
            if is_assigned:
                # Already in current task: checked and disabled
                chk.set_active(True)
                chk.set_sensitive(False)
            else:
                chk.set_active(tname in self.selected_catalog_tags)
                chk.connect('toggled', self._make_chk_toggle_handler(tname))

            chk_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            chk_box.add_css_class('f2-table-row')
            chk_box.set_halign(Gtk.Align.CENTER)
            chk_box.append(chk)
            self.catalog_grid.attach(chk_box, 0, row_idx, 1, 1)
            self.catalog_checkboxes[tname] = chk

            # Column 1: Tag Name
            lbl_name = Gtk.Label(label=tname)
            lbl_name.add_css_class('f2-table-cell-mono')
            lbl_name.add_css_class('f2-table-row')
            lbl_name.set_xalign(0.0)
            lbl_name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            self.catalog_grid.attach(lbl_name, 1, row_idx, 1, 1)

            # Column 2: Group
            lbl_grp = Gtk.Label(label=group)
            lbl_grp.add_css_class('f2-table-cell-muted')
            lbl_grp.add_css_class('f2-table-row')
            lbl_grp.set_xalign(0.0)
            lbl_grp.set_ellipsize(Pango.EllipsizeMode.END)
            self.catalog_grid.attach(lbl_grp, 2, row_idx, 1, 1)

            # Column 3: PLC Address
            lbl_addr = Gtk.Label(label=addr)
            lbl_addr.add_css_class('f2-table-cell-mono')
            lbl_addr.add_css_class('f2-table-row')
            lbl_addr.set_xalign(0.0)
            lbl_addr.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            self.catalog_grid.attach(lbl_addr, 3, row_idx, 1, 1)

            # Column 4: Type
            lbl_type = Gtk.Label(label=clean_type)
            lbl_type.add_css_class('f2-table-cell-muted')
            lbl_type.add_css_class('f2-table-row')
            lbl_type.set_xalign(0.0)
            lbl_type.set_ellipsize(Pango.EllipsizeMode.END)
            self.catalog_grid.attach(lbl_type, 4, row_idx, 1, 1)

            # Column 5: Live Status (Strictly Not Observed when offline / standby)
            if is_assigned:
                lbl_st = Gtk.Label(label="ใน Task นี้")
                lbl_st.add_css_class('f2-pill-enabled')
            else:
                lbl_st = Gtk.Label(label="Not Observed")
                lbl_st.add_css_class('f2-pill-not-observed')
            lbl_st.add_css_class('f2-table-row')
            lbl_st.set_xalign(0.0)
            self.catalog_grid.attach(lbl_st, 5, row_idx, 1, 1)

    def _make_chk_toggle_handler(self, tname):
        def _on_toggled(chk):
            if chk.get_active():
                self.selected_catalog_tags.add(tname)
            else:
                self.selected_catalog_tags.discard(tname)
            self.update_selection_badges()
        return _on_toggled

    def update_selection_badges(self):
        """Updates selection counter and action button label"""
        cnt = len(self.selected_catalog_tags)
        self.lbl_selected_counter.set_label(f"เลือกอยู่: {cnt} รายการ")

        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            self.btn_add_to_task.set_sensitive(False)
            self.btn_add_to_task.set_label("➕ กรุณาสร้าง Task ก่อนเพิ่ม Tag")
            self.lbl_bottom_sel_info.set_label("ยังไม่มี Task ที่เลือก — กรุณาสร้าง Task ในฝั่งขวา")
            return

        t = tasks[self.selected_task_index]
        tid = t.get('id', f"TASK-{self.selected_task_index+1:02d}")
        self.btn_add_to_task.set_sensitive(cnt > 0)
        if cnt > 0:
            self.btn_add_to_task.set_label(f"➕ เพิ่ม {cnt} Tag เข้าสู่ [{tid}]")
            self.btn_add_to_task.remove_css_class('f2-btn-neutral')
            self.btn_add_to_task.add_css_class('f2-btn-add-to-task')
            self.lbl_bottom_sel_info.set_label(f"พร้อมนำ {cnt} สัญญาณเข้าสู่ Task {tid}")
        else:
            self.btn_add_to_task.set_label(f"➕ เพิ่ม Tag ที่เลือกเข้าสู่ [{tid}]")
            self.btn_add_to_task.remove_css_class('f2-btn-add-to-task')
            self.btn_add_to_task.add_css_class('f2-btn-neutral')
            self.lbl_bottom_sel_info.set_label("เลือก Tag จากตารางด้านบน แล้วกดปุ่มเพื่อเพิ่มเข้า Task")

    def on_select_all_in_view(self, btn):
        tasks = getattr(self.owner, 'tasks', [])
        current_assigned = set()
        if tasks and 0 <= self.selected_task_index < len(tasks):
            for x in tasks[self.selected_task_index].get('tags', []):
                tname = x.get('name') if isinstance(x, dict) else str(x)
                current_assigned.add(tname)

        for t in getattr(self, 'currently_filtered_tags', []):
            tname = t.get('name', '')
            if tname not in current_assigned:
                self.selected_catalog_tags.add(tname)

        self.update_selection_badges()
        self.render_catalog_table()

    def on_clear_selection(self, btn):
        self.selected_catalog_tags.clear()
        self.update_selection_badges()
        self.render_catalog_table()

    def on_add_selected_tags_to_task(self, btn=None):
        """Adds all checked tags to current task, ensuring NO duplicates, then updates UI"""
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            return

        t = tasks[self.selected_task_index]
        existing_tags = t.get('tags', [])
        existing_names = set()
        for x in existing_tags:
            existing_names.add(x.get('name') if isinstance(x, dict) else str(x))

        added_count = 0
        for tname in self.selected_catalog_tags:
            if tname not in existing_names:
                existing_tags.append(tname)
                existing_names.add(tname)
                added_count += 1

        t['tags'] = existing_tags
        # Save atomically
        self.owner.save_all_tasks()

        self.selected_catalog_tags.clear()
        self.update_selection_badges()
        self.render_catalog_table()
        self.render_assigned_tags()
        self.update_task_status_strip()

    # =========================================================================
    # 4. RIGHT PANEL: TASK CONFIGURATION (~45%)
    # =========================================================================

    def build_right_task_config(self):
        """Constructs unified Right Panel for Task Configuration"""
        # Header Row
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr.add_css_class('f2-panel-header')
        self.right_panel.append(hdr)

        lbl_title = Gtk.Label(label="การกำหนดค่า Task (Task Configuration)")
        lbl_title.add_css_class('f2-panel-title')
        hdr.append(lbl_title)

        self.lbl_ws_tid = Gtk.Label(label="TASK-01")
        self.lbl_ws_tid.add_css_class('f2-card-id-badge')
        hdr.append(self.lbl_ws_tid)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        hdr.append(spacer)

        self.lbl_assigned_count = Gtk.Label(label="0 Tags")
        # Do not append duplicate badge to main panel header to avoid clutter

        # Scrolled Container for Form
        self.form_scroll = Gtk.ScrolledWindow()
        self.form_scroll.set_hexpand(True)
        self.form_scroll.set_vexpand(True)
        self.form_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.right_panel.append(self.form_scroll)

        self.form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.form_box.add_css_class('f2-form-box')
        self.form_scroll.set_child(self.form_box)

        # Section 1: Task Details
        self.build_section_task_management()

        # Section 2: Task Actions
        self.build_section_task_actions()

        # Section 3: Assigned Tags
        self.build_section_assigned_tags()

        # Section 4: Save & Feedback (Pinned at bottom of right panel)
        self.build_section_save_action()

    # -------------------------------------------------------------------------
    # 4.1 Section 1: Task Details
    # -------------------------------------------------------------------------
    def build_section_task_management(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class('f2-card')
        self.form_box.append(card)

        # Card Title
        lbl_title = Gtk.Label(label="รายละเอียด Task (Task Details)")
        lbl_title.add_css_class('f2-card-title')
        lbl_title.set_xalign(0.0)
        card.append(lbl_title)

        grid = Gtk.Grid(column_spacing=10, row_spacing=4)
        card.append(grid)

        # Row 0: Task Selector + Create Button
        lbl_sel = Gtk.Label(label="เลือก Task:")
        lbl_sel.add_css_class('f2-form-label')
        lbl_sel.set_xalign(0.0)
        grid.attach(lbl_sel, 0, 0, 1, 1)

        sel_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        grid.attach(sel_row, 1, 0, 1, 1)

        self.task_selector_combo = Gtk.DropDown.new_from_strings(["(ไม่มี Task)"])
        self.task_selector_combo.add_css_class('f2-scan-dropdown')
        self.task_selector_combo.set_size_request(280, 32)
        self.task_selector_combo.set_hexpand(False)
        self.task_selector_combo.connect('notify::selected', self.on_task_selector_changed)
        sel_row.append(self.task_selector_combo)

        btn_new_task = Gtk.Button(label="+ สร้าง Task ใหม่")
        btn_new_task.add_css_class('f2-btn-create-task')
        btn_new_task.connect('clicked', self.on_create_new_task)
        sel_row.append(btn_new_task)

        # Row 1: Task ID & Status Pills (Enabled + Running)
        lbl_id = Gtk.Label(label="รหัส Task:")
        lbl_id.add_css_class('f2-form-label')
        lbl_id.set_xalign(0.0)
        grid.attach(lbl_id, 0, 1, 1, 1)

        id_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        grid.attach(id_box, 1, 1, 1, 1)

        self.lbl_task_id_badge = Gtk.Label(label="TASK-01")
        self.lbl_task_id_badge.add_css_class('f2-card-id-badge')
        id_box.append(self.lbl_task_id_badge)

        self.lbl_pill_enabled = Gtk.Label(label="Enabled")
        self.lbl_pill_enabled.add_css_class('f2-pill-enabled')
        id_box.append(self.lbl_pill_enabled)

        self.lbl_pill_runtime = Gtk.Label(label="Standby (Auto-Scan Inactive)")
        self.lbl_pill_runtime.add_css_class('f2-pill-not-observed')
        id_box.append(self.lbl_pill_runtime)

        # Row 2: Task Name (Constrained ergonomic width)
        lbl_name = Gtk.Label(label="ชื่อ Task:")
        lbl_name.add_css_class('f2-form-label')
        lbl_name.set_xalign(0.0)
        grid.attach(lbl_name, 0, 2, 1, 1)

        self.entry_task_name = Gtk.Entry()
        self.entry_task_name.add_css_class('f2-form-entry')
        self.entry_task_name.set_size_request(340, 32)
        self.entry_task_name.set_hexpand(False)
        self.entry_task_name.set_placeholder_text("ระบุชื่อ Task เพื่อสื่อสารการทำงาน")
        self.entry_task_name.connect('changed', self.on_task_name_changed)
        grid.attach(self.entry_task_name, 1, 2, 1, 1)

        # Row 3: Task Cycle
        lbl_cycle = Gtk.Label(label="รอบเวลาสแกน:")
        lbl_cycle.add_css_class('f2-form-label')
        lbl_cycle.set_xalign(0.0)
        grid.attach(lbl_cycle, 0, 3, 1, 1)

        cycle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        grid.attach(cycle_box, 1, 3, 1, 1)

        cycle_strings = [opt[1] for opt in CYCLE_OPTIONS]
        self.combo_task_cycle = Gtk.DropDown.new_from_strings(cycle_strings)
        self.combo_task_cycle.add_css_class('f2-scan-dropdown')
        self.combo_task_cycle.set_size_request(240, 32)
        self.combo_task_cycle.set_hexpand(False)
        self.combo_task_cycle.set_selected(1)  # Default 5s
        self.combo_task_cycle.connect('notify::selected', self.on_task_cycle_changed)
        cycle_box.append(self.combo_task_cycle)

        lbl_cycle_sub = Gtk.Label(label="(รอบเวลาของ Task นี้)")
        lbl_cycle_sub.add_css_class('f2-form-subtext')
        cycle_box.append(lbl_cycle_sub)

    def on_task_name_changed(self, entry):
        self.has_unsaved_changes = True
        self.update_save_status()

    def on_task_cycle_changed(self, drop_down, *args):
        self.has_unsaved_changes = True
        self.update_save_status()

    def switch_to_task(self, idx):
        """Switches active task with unsaved changes safeguard"""
        tasks = getattr(self.owner, 'tasks', [])
        if 0 <= idx < len(tasks):
            # Check for unsaved changes before switching
            if self.has_unsaved_changes and idx != self.selected_task_index:
                prev_task = tasks[self.selected_task_index]
                prev_id = prev_task.get('id', '')
                if hasattr(self.owner, 'alarm_text'):
                    self.owner.alarm_text.set_text(
                        f"⚠️ มีการเปลี่ยนแปลงใน {prev_id} ที่ยังไม่ได้บันทึก — ระบบได้จัดเก็บค่าลง Task ปัจจุบันก่อนสลับ"
                    )
                self.on_save_task()

            self.selected_task_index = idx
            self.owner.current_task_idx = idx
            self.has_unsaved_changes = False
            self.load_current_task_to_ui()
            self.render_catalog_table()  # Re-evaluate "In this Task" markers

    def on_task_selector_changed(self, drop_down, *args):
        if self.task_selector_updating:
            return
        idx = drop_down.get_selected()
        self.switch_to_task(idx)

    # -------------------------------------------------------------------------
    # 4.2 Section 2: Task Actions
    # -------------------------------------------------------------------------
    def build_section_task_actions(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class('f2-card')
        self.form_box.append(card)

        # Question Header in Thai
        lbl_title = Gtk.Label(label="เมื่อ Task ทำงาน ให้ระบบทำอะไร?")
        lbl_title.add_css_class('f2-card-title')
        lbl_title.set_xalign(0.0)
        card.append(lbl_title)

        grid = Gtk.Grid(column_spacing=10, row_spacing=3)
        card.append(grid)

        # Checkbox 1: Local Archive
        self.chk_action_log = Gtk.CheckButton(label="บันทึกข้อมูลลงเครื่อง")
        self.chk_action_log.add_css_class('f2-check-lg')
        self.chk_action_log.connect('toggled', self.on_action_toggled)
        grid.attach(self.chk_action_log, 0, 0, 1, 1)

        lbl_log_sub = Gtk.Label(label="จัดเก็บประวัติค่าสัญญาณลงฐานข้อมูล SQLite ในเครื่องเพื่อตรวจสอบย้อนหลัง")
        lbl_log_sub.add_css_class('f2-form-subtext')
        lbl_log_sub.set_xalign(0.0)
        grid.attach(lbl_log_sub, 1, 0, 1, 1)

        # Checkbox 2: Telegram Notification
        tg_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.chk_action_notify = Gtk.CheckButton(label="แจ้งเตือน Telegram")
        self.chk_action_notify.add_css_class('f2-check-lg')
        self.chk_action_notify.connect('toggled', self.on_action_toggled)
        tg_row.append(self.chk_action_notify)

        btn_f6 = Gtk.Button(label="เปิดการตั้งค่า →")
        btn_f6.add_css_class('f2-btn-link')
        btn_f6.connect('clicked', lambda _: self.owner.switch_to_tab('alarms'))
        tg_row.append(btn_f6)
        grid.attach(tg_row, 0, 1, 1, 1)

        lbl_tg_sub = Gtk.Label(label="ส่งข้อความแจ้งเตือนผ่านบอทเมื่อสัญญาณมีสถานะผิดปกติ")
        lbl_tg_sub.add_css_class('f2-form-subtext')
        lbl_tg_sub.set_xalign(0.0)
        grid.attach(lbl_tg_sub, 1, 1, 1, 1)

        # Checkbox 3: Enable Task
        self.chk_task_enabled = Gtk.CheckButton(label="เปิดใช้งาน Task")
        self.chk_task_enabled.add_css_class('f2-check-lg')
        self.chk_task_enabled.connect('toggled', self.on_action_toggled)
        grid.attach(self.chk_task_enabled, 0, 2, 1, 1)

        lbl_en_sub = Gtk.Label(label="เริ่มประมวลผล Task นี้เมื่อระบบเปิดใช้งาน Auto-Scan")
        lbl_en_sub.add_css_class('f2-form-subtext')
        lbl_en_sub.set_xalign(0.0)
        grid.attach(lbl_en_sub, 1, 2, 1, 1)

        # Safety Assurance Note
        lbl_safety = Gtk.Label(label="* การกด Save Task จะบันทึกการตั้งค่าเท่านั้น ไม่มีการส่งแจ้งเตือนหรือเริ่มสแกนทันที")
        lbl_safety.add_css_class('f2-form-subtext-alert')
        lbl_safety.set_xalign(0.0)
        card.append(lbl_safety)

    def on_action_toggled(self, chk):
        self.has_unsaved_changes = True
        self.update_task_status_strip()
        self.update_save_status()

    # -------------------------------------------------------------------------
    # 4.3 Section 3: Assigned Tags
    # -------------------------------------------------------------------------
    def build_section_assigned_tags(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class('f2-card')
        self.form_box.append(card)

        # Header Row
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        card.append(hdr)

        lbl_title = Gtk.Label(label="Tag ใน Task นี้ (Assigned Tags)")
        lbl_title.add_css_class('f2-card-title')
        lbl_title.set_hexpand(True)
        lbl_title.set_xalign(0.0)
        hdr.append(lbl_title)

        self.lbl_assigned_badge = Gtk.Label(label="0 Tags")
        self.lbl_assigned_badge.add_css_class('f2-badge-blue')
        hdr.append(self.lbl_assigned_badge)

        self.lbl_pill_cfg = Gtk.Label(label="Incomplete (0 Tags)")
        self.lbl_pill_cfg.add_css_class('f2-pill-configured')
        hdr.append(self.lbl_pill_cfg)

        # Scrolled Grid for Assigned Tags - Compact List Pattern
        self.assigned_scroll = Gtk.ScrolledWindow()
        self.assigned_scroll.set_hexpand(True)
        self.assigned_scroll.set_propagate_natural_height(True)
        self.assigned_scroll.set_max_content_height(160)
        self.assigned_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        card.append(self.assigned_scroll)

        self.assigned_grid = Gtk.Grid(column_spacing=0, row_spacing=0)
        self.assigned_scroll.set_child(self.assigned_grid)

    def render_assigned_tags(self):
        """Renders assigned tags table for current active task"""
        while True:
            child = self.assigned_grid.get_first_child()
            if not child:
                break
            self.assigned_grid.remove(child)

        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            return

        t = tasks[self.selected_task_index]
        tags = t.get('tags', [])
        self.lbl_assigned_badge.set_label(f"{len(tags)} Tags")
        self.lbl_assigned_count.set_label(f"{len(tags)} Tags")

        if not tags:
            # Short, clean, compact empty state (no large vertical waste)
            empty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            empty_box.add_css_class('f2-table-empty-box-compact')
            empty_box.set_hexpand(True)

            lbl_sub = Gtk.Label(label="📭 ยังไม่มี Tag ใน Task นี้ — เลือก Tag จากคลังฝั่งซ้ายแล้วกดปุ่ม [เพิ่ม Tag]")
            lbl_sub.add_css_class('f2-table-cell-muted')
            lbl_sub.set_xalign(0.0)
            empty_box.append(lbl_sub)

            self.assigned_grid.attach(empty_box, 0, 0, 5, 1)
            return

        # Table Header
        headers = [
            ("TAG NAME / IDENTIFIER", 160),
            ("กลุ่มต้นทาง", 85),
            ("ชนิด", 55),
            ("สถานะสด", 75),
            ("คำสั่ง", 65)
        ]
        for col_idx, (htitle, width) in enumerate(headers):
            lbl = Gtk.Label(label=htitle)
            lbl.add_css_class('f2-table-hdr')
            lbl.set_size_request(width, 28)
            lbl.set_xalign(0.0 if col_idx < 4 else 0.5)
            self.assigned_grid.attach(lbl, col_idx, 0, 1, 1)

        catalog_map = {item['name']: item for item in self.catalog_tags_cache}

        for row_idx, item in enumerate(tags, 1):
            if isinstance(item, dict):
                tname = item.get('name', '')
                group = item.get('group', '—')
                raw_type = item.get('type', '—')
            else:
                tname = str(item)
                info = catalog_map.get(tname, {})
                group = info.get('group', '—')
                raw_type = info.get('type', '—')

            clean_type = DATA_TYPE_MAPPING.get(raw_type, raw_type)

            # Column 0: Tag Name
            lbl_name = Gtk.Label(label=tname)
            lbl_name.add_css_class('f2-table-cell-mono')
            lbl_name.add_css_class('f2-table-row')
            lbl_name.set_xalign(0.0)
            lbl_name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            self.assigned_grid.attach(lbl_name, 0, row_idx, 1, 1)

            # Column 1: Source Group
            lbl_grp = Gtk.Label(label=group)
            lbl_grp.add_css_class('f2-table-cell-muted')
            lbl_grp.add_css_class('f2-table-row')
            lbl_grp.set_xalign(0.0)
            lbl_grp.set_ellipsize(Pango.EllipsizeMode.END)
            self.assigned_grid.attach(lbl_grp, 1, row_idx, 1, 1)

            # Column 2: Data Type
            lbl_type = Gtk.Label(label=clean_type)
            lbl_type.add_css_class('f2-table-cell-muted')
            lbl_type.add_css_class('f2-table-row')
            lbl_type.set_xalign(0.0)
            lbl_type.set_ellipsize(Pango.EllipsizeMode.END)
            self.assigned_grid.attach(lbl_type, 2, row_idx, 1, 1)

            # Column 3: Status (Strictly Not Observed when offline / standby)
            lbl_st = Gtk.Label(label="Not Observed")
            lbl_st.add_css_class('f2-pill-not-observed')
            lbl_st.add_css_class('f2-table-row')
            lbl_st.set_xalign(0.0)
            self.assigned_grid.attach(lbl_st, 3, row_idx, 1, 1)

            # Column 4: Remove Button
            btn_rm = Gtk.Button(label="✕ นำออก")
            btn_rm.add_css_class('f2-btn-remove')
            btn_rm.connect('clicked', self._make_remove_handler(tname))
            box_rm = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            box_rm.add_css_class('f2-table-row')
            box_rm.set_halign(Gtk.Align.CENTER)
            box_rm.append(btn_rm)
            self.assigned_grid.attach(box_rm, 4, row_idx, 1, 1)

    def _make_remove_handler(self, tname):
        def _on_remove(btn):
            self.on_remove_tag_from_task(tname)
        return _on_remove

    def on_remove_tag_from_task(self, tag_name):
        """Removes a tag from active task and saves atomically"""
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            return

        t = tasks[self.selected_task_index]
        existing = t.get('tags', [])
        new_tags = []
        for x in existing:
            x_name = x.get('name') if isinstance(x, dict) else str(x)
            if x_name != tag_name:
                new_tags.append(x)

        t['tags'] = new_tags
        self.owner.save_all_tasks()

        self.render_assigned_tags()
        self.render_catalog_table()
        self.update_task_status_strip()

    # -------------------------------------------------------------------------
    # 4.4 Section 4: Save & Feedback
    # -------------------------------------------------------------------------
    def build_section_save_action(self):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.add_css_class('f2-card-save')
        self.right_panel.append(card)

        self.lbl_save_status_pill = Gtk.Label(label="Saved (บันทึกแล้ว)")
        self.lbl_save_status_pill.add_css_class('f2-pill-enabled')
        card.append(self.lbl_save_status_pill)

        self.lbl_save_feedback = Gtk.Label(label="การตั้งค่าถูกต้องและได้รับการบันทึกเรียบร้อย")
        self.lbl_save_feedback.add_css_class('f2-table-cell-muted')
        self.lbl_save_feedback.set_hexpand(True)
        self.lbl_save_feedback.set_xalign(0.0)
        card.append(self.lbl_save_feedback)

        self.btn_save_task = Gtk.Button(label="💾 บันทึก Task (Save Task)")
        self.btn_save_task.add_css_class('f2-btn-save-task')
        self.btn_save_task.connect('clicked', lambda _: self.on_save_task())
        card.append(self.btn_save_task)

    def update_save_status(self):
        """Validates current task inputs and updates save button/status pill"""
        name = self.entry_task_name.get_text().strip()
        tasks = getattr(self.owner, 'tasks', [])
        tags_cnt = len(tasks[self.selected_task_index].get('tags', [])) if (tasks and self.selected_task_index < len(tasks)) else 0

        if not name:
            self.lbl_save_status_pill.set_label("Invalid")
            self.lbl_save_status_pill.remove_css_class('f2-pill-enabled')
            self.lbl_save_status_pill.remove_css_class('f2-pill-incomplete')
            self.lbl_save_status_pill.add_css_class('f2-pill-error')
            self.lbl_save_feedback.set_label("❌ ชื่อ Task ต้องไม่เป็นค่าว่าง")
            self.btn_save_task.set_sensitive(False)
        elif self.has_unsaved_changes:
            self.lbl_save_status_pill.set_label("Unsaved Changes")
            self.lbl_save_status_pill.remove_css_class('f2-pill-enabled')
            self.lbl_save_status_pill.remove_css_class('f2-pill-error')
            self.lbl_save_status_pill.add_css_class('f2-pill-incomplete')
            self.lbl_save_feedback.set_label("มีการแก้ไขที่ยังไม่ได้บันทึก — กดปุ่ม [บันทึก Task]")
            self.btn_save_task.set_sensitive(True)
        else:
            self.lbl_save_status_pill.set_label("Saved")
            self.lbl_save_status_pill.remove_css_class('f2-pill-incomplete')
            self.lbl_save_status_pill.remove_css_class('f2-pill-error')
            self.lbl_save_status_pill.add_css_class('f2-pill-enabled')
            self.lbl_save_feedback.set_label("การตั้งค่าล่าสุดได้รับการบันทึกเรียบร้อย")
            self.btn_save_task.set_sensitive(True)

    def on_save_task(self):
        """Saves current form values to active task dict and writes atomic JSON"""
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            return

        new_name = self.entry_task_name.get_text().strip()
        if not new_name:
            return

        t = tasks[self.selected_task_index]
        t['name'] = new_name
        c_idx = self.combo_task_cycle.get_selected()
        t['cycle_sec'] = CYCLE_OPTIONS[c_idx][0] if 0 <= c_idx < len(CYCLE_OPTIONS) else 5
        t['action_log'] = self.chk_action_log.get_active()
        t['action_notify'] = self.chk_action_notify.get_active()
        t['active'] = self.chk_task_enabled.get_active()

        # Atomic persistence
        self.owner.save_all_tasks()
        self.has_unsaved_changes = False

        self.update_task_selector_dropdown()
        self.update_task_status_strip()
        self.update_save_status()

    # =========================================================================
    # 5. DATA SYNC & LOAD TO UI
    # =========================================================================

    def update_task_selector_dropdown(self):
        """Populates the Task Selector dropdown"""
        self.task_selector_updating = True
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks:
            self.task_selector_combo.set_model(Gtk.StringList.new(["(ไม่มี Task ในระบบ)"]))
            self.task_selector_combo.set_selected(0)
            self.task_selector_updating = False
            return

        items = []
        for idx, t in enumerate(tasks):
            tid = t.get('id', f"TASK-{idx+1:02d}")
            tname = t.get('name', t.get('task_name', f"Task {tid}"))
            tname_display = (tname[:26] + '…') if len(tname) > 28 else tname
            tcount = len(t.get('tags', []))
            items.append(f"[{tid}] {tname_display} ({tcount} Tags)")

        self.task_selector_combo.set_model(Gtk.StringList.new(items))
        self.selected_task_index = max(0, min(self.selected_task_index, len(tasks) - 1))
        self.task_selector_combo.set_selected(self.selected_task_index)
        self.task_selector_updating = False

    def update_task_status_strip(self):
        """Updates Configured, Enabled, and Runtime pills based on verifiable data"""
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks or self.selected_task_index >= len(tasks):
            self.lbl_ws_tid.set_label("—")
            self.lbl_pill_cfg.set_label("Incomplete")
            self.lbl_pill_enabled.set_label("Disabled")
            self.lbl_pill_runtime.set_label("Standby")
            return

        t = tasks[self.selected_task_index]
        tid = t.get('id', f"TASK-{self.selected_task_index+1:02d}")
        tag_count = len(t.get('tags', []))
        is_active = t.get('active', True)
        is_running = getattr(self.owner, 'auto_scan_active', False)

        self.lbl_ws_tid.set_label(tid)
        if hasattr(self, 'lbl_task_id_badge'):
            self.lbl_task_id_badge.set_label(tid)

        # Completeness Pill
        if tag_count > 0:
            self.lbl_pill_cfg.set_label("Configured")
            self.lbl_pill_cfg.remove_css_class('f2-pill-incomplete')
            self.lbl_pill_cfg.add_css_class('f2-pill-configured')
        else:
            self.lbl_pill_cfg.set_label("Incomplete (0 Tags)")
            self.lbl_pill_cfg.remove_css_class('f2-pill-configured')
            self.lbl_pill_cfg.add_css_class('f2-pill-incomplete')

        # Enabled Pill
        if is_active:
            self.lbl_pill_enabled.set_label("Enabled")
            self.lbl_pill_enabled.remove_css_class('f2-pill-disabled')
            self.lbl_pill_enabled.add_css_class('f2-pill-enabled')
        else:
            self.lbl_pill_enabled.set_label("Disabled")
            self.lbl_pill_enabled.remove_css_class('f2-pill-enabled')
            self.lbl_pill_enabled.add_css_class('f2-pill-disabled')

        # Runtime Pill
        if is_running and is_active:
            self.lbl_pill_runtime.set_label("Running (Auto-Scan Active)")
            self.lbl_pill_runtime.remove_css_class('f2-pill-not-observed')
            self.lbl_pill_runtime.add_css_class('f2-pill-running')
        else:
            self.lbl_pill_runtime.set_label("Standby (Auto-Scan Inactive)")
            self.lbl_pill_runtime.remove_css_class('f2-pill-running')
            self.lbl_pill_runtime.add_css_class('f2-pill-not-observed')

    def load_current_task_to_ui(self):
        """Loads selected task data into all fields of Task Configuration"""
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks:
            self.entry_task_name.set_text("")
            self.entry_task_name.set_sensitive(False)
            self.combo_task_cycle.set_sensitive(False)
            self.chk_action_log.set_sensitive(False)
            self.chk_action_notify.set_sensitive(False)
            self.chk_task_enabled.set_sensitive(False)
            if hasattr(self, 'btn_save_task'):
                self.btn_save_task.set_sensitive(False)
            if hasattr(self, 'lbl_task_id_badge'):
                self.lbl_task_id_badge.set_label("—")
            self.render_assigned_tags()
            self.update_task_status_strip()
            self.update_selection_badges()
            self.update_save_status()
            return

        self.entry_task_name.set_sensitive(True)
        self.combo_task_cycle.set_sensitive(True)
        self.chk_action_log.set_sensitive(True)
        self.chk_action_notify.set_sensitive(True)
        self.chk_task_enabled.set_sensitive(True)
        if hasattr(self, 'btn_save_task'):
            self.btn_save_task.set_sensitive(True)

        self.selected_task_index = max(0, min(self.selected_task_index, len(tasks) - 1))
        t = tasks[self.selected_task_index]

        # Update Dropdown & ID
        self.update_task_selector_dropdown()
        self.update_task_status_strip()

        # Update Name Entry
        tname = t.get('name', t.get('task_name', ''))
        self.entry_task_name.set_text(tname)

        # Update Cycle Dropdown
        cycle_sec = t.get('cycle_sec', 5)
        matched_c = 1
        for idx, opt in enumerate(CYCLE_OPTIONS):
            if opt[0] == cycle_sec:
                matched_c = idx
                break
        self.combo_task_cycle.set_selected(matched_c)

        # Update Action Checkboxes
        self.chk_action_log.set_active(t.get('action_log', True))
        self.chk_action_notify.set_active(t.get('action_notify', True))
        self.chk_task_enabled.set_active(t.get('active', True))

        self.has_unsaved_changes = False

        # Render Assigned Tags Table
        self.render_assigned_tags()
        self.update_save_status()
        self.update_selection_badges()

    def on_create_new_task(self, btn=None):
        """Creates a brand new task, selects it, and sets focus"""
        tasks = getattr(self.owner, 'tasks', [])
        new_id = f"TASK-{len(tasks)+1:02d}"
        new_task = {
            'id': new_id,
            'name': f"Task เฝ้าระวังใหม่ {new_id}",
            'cycle_sec': 5,
            'action_log': True,
            'action_notify': True,
            'active': True,
            'tags': [],
            'scan_count': 0,
            'log_count': 0,
            'alert_count': 0
        }
        tasks.append(new_task)
        self.owner.save_all_tasks()

        self.selected_task_index = len(tasks) - 1
        self.owner.current_task_idx = self.selected_task_index
        self.load_current_task_to_ui()
        self.render_catalog_table()

    # =========================================================================
    # BACKWARD COMPATIBILITY DELEGATES (CALLED BY APP.PY)
    # =========================================================================

    def render_discovered_tags(self):
        """Called by app.py render_tags_grid()"""
        self.sync_catalog_data()
        self.refresh_group_explorer()
        self.render_catalog_table()

    def on_add_selected_tags(self, _):
        """Called by app.py add_selected_tags_to_current_task()"""
        self.on_add_selected_tags_to_task()
