#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — UNIFIED MONITORING & TASK WORKSPACE V2
Professional Presentation Layer with High-Contrast Dark Surfaces & 20/48/32 Layout

Architecture:
- Top Header: SCADA Status Bar & Compact Scan Operations Toolbar
- 3-Column Interactive Layout:
    1. Left Column (~20%, 270–380px): Shared Equipment Group Explorer (All Groups + 10 Catalog Groups)
    2. Center Column (~48%, 650–920px): Shared Searchable Tag Catalog with Checkboxes & Filter Banner
    3. Right Column (~32%, 430–620px): Contextual Panel switched via F1 / F2:
        - Mode F1: Tag Properties & Technical Grid Inspector (with Collapse/Expand support)
        - Mode F2: 3-Section Task Configurator (Details, Actions, Assigned Tags, Sticky Save)
- Bottom Navigation: F1 (Monitoring), F2 (Task Mode), F3-F6, F7 (Scan In-Place), F8 (Exit)
"""

import os
import sys
import json
import time
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

def format_data_type(raw_type):
    return DATA_TYPE_MAPPING.get(raw_type, raw_type or "Real")

# Group Display Metadata (Catalog-Driven & Factual)
GROUP_METADATA = {
    "All": ("ทุกกลุ่มอุปกรณ์ (All Groups)", "รวมสัญญาณทั้งหมด 457 รายการในระบบ SCADA"),
    "High_VSD": ("ปั๊มน้ำแรงดันสูง VSD", "ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ"),
    "High_Valve": ("วาล์วท่อส่งแรงดันสูง", "วาล์วควบคุมการจ่ายน้ำแรงดันสูง"),
    "High1_PT1PT": ("เซนเซอร์วัดแรงดัน PT", "เพรชเชอร์ทรานสมิตเตอร์วัดแรงดันน้ำ"),
    "High_Analog": ("สัญญาณอนาล็อกแรงดันสูง", "เซนเซอร์วัดสัญญาณอนาล็อกทางวิศวกรรม"),
    "High_DPM": ("ดิจิทัลเพาเวอร์มิเตอร์ DPM", "ระบบวัดกำลังไฟฟ้าและพลังงาน"),
    "High1_Sound": ("ระบบตรวจวัดเสียงและความสั่น", "ระบบตรวจสอบความผิดปกติทางกล"),
    "High1_Totalize_Flow": ("มาตรวัดปริมาตรน้ำสะสม", "มิเตอร์วัดปริมาตรน้ำและอัตราการไหล"),
    "Temp_High_Alarm": ("สัญญาณเตือนอุณหภูมิสูง", "ระบบเฝ้าระวังอุณหภูมิปั๊มและมอเตอร์"),
    "Timer_Of_Start_Second_CTM": ("ตัวจับเวลาสตาร์ทปั๊ม", "ระบบกำหนดลำดับเวลาสตาร์ทเครื่องสูบ"),
    "Default": ("ค่าเริ่มต้นระบบ (Default)", "สัญญาณระบบพื้นฐานที่ยังไม่ได้จัดกลุ่ม")
}

# Task Cycle Options
CYCLE_OPTIONS = [
    (1, "1 วินาที (High Priority)"),
    (5, "5 วินาที (มาตรฐาน WinCC V8.1)"),
    (10, "10 วินาที (General Monitoring)"),
    (30, "30 วินาที (Slow Sampling)"),
    (60, "60 วินาที (Hourly Batch)")
]


class AquaUnifiedWorkspaceView:
    """
    AQUA COMMAND Unified Monitoring & Task Workspace V2
    Professional UI Pass: High Contrast, 20/48/32 Proportions, WCAG AA Compliance
    """

    def __init__(self, owner, root_box):
        self.owner = owner
        self.root_box = root_box

        # State Variables
        self.current_workspace_mode = 'monitoring'  # 'monitoring' (F1) or 'task_manager' (F2)
        self.selected_group_key = "High_VSD"
        self.search_query = ""
        self.selected_catalog_tags = set()  # set of tag names selected in library
        self.has_unsaved_changes = False
        self.selected_task_index = getattr(self.owner, 'current_task_idx', 0)
        self.inspector_collapsed = False

        self.catalog_tags_cache = []
        self.group_counts = {}
        self.currently_filtered_tags = []
        self.selected_inspector_tag = None

        # Widget references
        self.group_list_items = {}
        self.catalog_checkboxes = {}
        self.task_selector_updating = False

        # Build UI
        self.build_ui()

    # =========================================================================
    # ROOT UI CONSTRUCTION
    # =========================================================================

    def build_ui(self):
        """Constructs Root Layout: Scan Toolbar Top + 20/48/32 3-Column Paned View"""
        while True:
            first = self.root_box.get_first_child()
            if not first:
                break
            self.root_box.remove(first)

        # 1. Top Compact Unified Workspace Toolbar
        self.build_top_header()

        # 2. Main 3-Column Workspace Paned (Proportion Target: 20% / 48% / 32%)
        self.main_hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_hpaned.set_hexpand(True)
        self.main_hpaned.set_vexpand(True)
        self.main_hpaned.set_position(275)  # Left Column ~20% of 1366
        self.root_box.append(self.main_hpaned)

        # Column 1: Equipment Group Explorer (Left ~20%)
        self.left_col = self.build_left_group_explorer()
        self.left_col.set_size_request(240, -1)
        self.main_hpaned.set_start_child(self.left_col)

        # Sub Paned (Center ~48% + Right ~32% = 80% remaining)
        self.sub_hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.sub_hpaned.set_hexpand(True)
        self.sub_hpaned.set_vexpand(True)
        self.sub_hpaned.set_position(655)  # Center ~48% of 1366
        self.main_hpaned.set_end_child(self.sub_hpaned)

        # Column 2: Shared Searchable Tag Catalog (Center ~48%)
        self.center_col = self.build_center_tag_catalog()
        self.center_col.set_size_request(450, -1)
        self.sub_hpaned.set_start_child(self.center_col)

        # Column 3: Context Panel (Right ~32%)
        self.right_col = self.build_right_context_panel()
        self.right_col.set_size_request(330, -1)
        self.sub_hpaned.set_end_child(self.right_col)

        # 3. Synchronize Initial Data
        self.sync_catalog_data()
        self.refresh_group_explorer()
        self.render_catalog_table()
        self.load_current_task_to_ui()

    def update_layout_proportions(self, width=1366):
        """Sets responsive 20% / 48% / 32% split according to target resolution"""
        left_w = int(width * 0.20)
        center_w = int(width * 0.48)
        self.main_hpaned.set_position(left_w)
        self.sub_hpaned.set_position(center_w)

    # =========================================================================
    # 1. TOP COMPACT TOOLBAR
    # =========================================================================

    def build_top_header(self):
        self.top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.top_box.add_css_class('workspace-top-ribbon')
        self.root_box.append(self.top_box)

        # Workspace Brand Title
        brand_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.top_box.append(brand_vbox)

        lbl_brand = Gtk.Label(label="AQUA COMMAND · UNIFIED WORKSPACE")
        lbl_brand.add_css_class('workspace-brand-title')
        lbl_brand.set_xalign(0.0)
        brand_vbox.append(lbl_brand)

        lbl_sub = Gtk.Label(label="Station Monitoring & Task Studio · Single Source of Truth")
        lbl_sub.add_css_class('workspace-subtitle')
        lbl_sub.set_xalign(0.0)
        brand_vbox.append(lbl_sub)

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1.set_margin_start(4)
        sep1.set_margin_end(4)
        self.top_box.append(sep1)

        # Scan Toolbar Controls
        self.btn_scan_once = Gtk.Button(label="🔍 สแกนทันที 1 ครั้ง (F7)")
        self.btn_scan_once.add_css_class('f2-btn-scan-once')
        self.btn_scan_once.connect('clicked', lambda _: self.owner.trigger_rescan())
        self.top_box.append(self.btn_scan_once)

        is_running = getattr(self.owner, 'auto_scan_active', False)
        self.btn_auto_scan = Gtk.Button(label="⏹ หยุด Auto Scan" if is_running else "▶ เริ่ม Auto Scan")
        self.btn_auto_scan.add_css_class('f2-btn-auto-stop' if is_running else 'f2-btn-auto-start')
        self.btn_auto_scan.connect('clicked', self.on_toggle_auto_scan)
        self.top_box.append(self.btn_auto_scan)
        self.owner.btn_auto_scan = self.btn_auto_scan

        lbl_int = Gtk.Label(label="รอบ: 5s")
        lbl_int.add_css_class('f2-scan-label')
        self.top_box.append(lbl_int)

        self.badge_scan_status = Gtk.Label(label="Ready · Standby")
        self.badge_scan_status.add_css_class('f2-scan-status-idle')
        self.top_box.append(self.badge_scan_status)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.top_box.append(spacer)

        # Mode Indicator / Switcher in Top Bar
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.top_box.append(mode_box)

        lbl_m = Gtk.Label(label="โหมดทำงาน:")
        lbl_m.add_css_class('workspace-subtitle')
        mode_box.append(lbl_m)

        self.btn_top_f1 = Gtk.Button(label="👁 F1 ตรวจสอบ (Inspector)")
        self.btn_top_f1.add_css_class('workspace-mode-btn-active')
        self.btn_top_f1.connect('clicked', lambda _: self.set_workspace_mode('monitoring'))
        mode_box.append(self.btn_top_f1)

        self.btn_top_f2 = Gtk.Button(label="⚙️ F2 จัดการ Task (Config)")
        self.btn_top_f2.add_css_class('workspace-mode-btn-inactive')
        self.btn_top_f2.connect('clicked', lambda _: self.set_workspace_mode('task_manager'))
        mode_box.append(self.btn_top_f2)

        # Factual Network Badges
        lan_b = Gtk.Label(label="🟢 LAN: 192.168.1.14")
        lan_b.add_css_class('badge-active')
        self.top_box.append(lan_b)

        wan_b = Gtk.Label(label="🟢 WAN: 192.168.100.177")
        wan_b.add_css_class('badge-active')
        self.top_box.append(wan_b)

    # =========================================================================
    # 2. COLUMN 1: SHARED EQUIPMENT GROUP EXPLORER (LEFT ~20%)
    # =========================================================================

    def build_left_group_explorer(self):
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.add_css_class('workspace-col-panel')

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr.add_css_class('f1-panel-header')
        left_box.append(hdr)

        lbl_title = Gtk.Label(label="กลุ่มอุปกรณ์ (Equipment Groups)")
        lbl_title.add_css_class('f1-panel-title')
        lbl_title.set_hexpand(True)
        lbl_title.set_xalign(0.0)
        hdr.append(lbl_title)

        self.lbl_group_count_badge = Gtk.Label(label="10 กลุ่ม")
        self.lbl_group_count_badge.add_css_class('f1-badge-accent')
        hdr.append(self.lbl_group_count_badge)

        # Scrolled List
        self.group_scroll = Gtk.ScrolledWindow()
        self.group_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.group_scroll.set_hexpand(True)
        self.group_scroll.set_vexpand(True)
        self.group_scroll.add_css_class('f1-group-scroll')
        left_box.append(self.group_scroll)

        self.group_listbox = Gtk.ListBox()
        self.group_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.group_listbox.add_css_class('f1-group-list')
        self.group_listbox.connect('row-selected', self.on_group_row_selected)
        self.group_scroll.set_child(self.group_listbox)

        return left_box

    def refresh_group_explorer(self):
        """Populates Equipment Groups list from dynamic catalog tags"""
        while self.group_listbox.get_first_child():
            self.group_listbox.remove(self.group_listbox.get_first_child())

        groups_in_cat = sorted(list(set(t['group'] for t in self.catalog_tags_cache)))
        self.lbl_group_count_badge.set_text(f"{len(groups_in_cat)} กลุ่ม")

        display_groups = ["All"] + [g for g in groups_in_cat if g != 'Default']
        if 'Default' in groups_in_cat:
            display_groups.append('Default')

        self.group_row_widgets = {}
        target_row = None

        for g_key in display_groups:
            meta = GROUP_METADATA.get(g_key, (g_key, "กลุ่มอุปกรณ์ SCADA"))
            count = self.group_counts.get(g_key, 0)

            row = Gtk.ListBoxRow()
            row._group_key = g_key
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_box.set_margin_start(6)
            row_box.set_margin_end(6)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)
            row.set_child(row_box)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            vbox.set_hexpand(True)
            row_box.append(vbox)

            lbl_gname = Gtk.Label(label=meta[0])
            lbl_gname.set_xalign(0.0)
            lbl_gname.add_css_class('f2-group-name')
            vbox.append(lbl_gname)

            lbl_gdesc = Gtk.Label(label=meta[1])
            lbl_gdesc.set_xalign(0.0)
            lbl_gdesc.add_css_class('f2-group-desc')
            lbl_gdesc.set_ellipsize(Pango.EllipsizeMode.END)
            vbox.append(lbl_gdesc)

            cnt_pill = Gtk.Label(label=f"{count}")
            cnt_pill.add_css_class('f2-group-count')
            row_box.append(cnt_pill)

            self.group_listbox.append(row)
            self.group_row_widgets[g_key] = row
            if g_key == self.selected_group_key:
                target_row = row

        if target_row:
            self.group_listbox.select_row(target_row)

    def on_group_row_selected(self, listbox, row):
        if row and hasattr(row, '_group_key'):
            self.on_select_group(row._group_key)

    def on_select_group(self, group_key):
        self.selected_group_key = group_key
        meta = GROUP_METADATA.get(group_key, (group_key, "ระบบ SCADA"))
        self.lbl_catalog_title.set_text(f"คลัง Tag: {meta[0]}")
        self.lbl_catalog_sub.set_text(meta[1])

        # Filter banner for single-tag group Default
        if group_key == 'Default':
            self.filter_banner_box.set_visible(True)
            self.lbl_filter_banner.set_text("📌 กำลังแสดงเฉพาะกลุ่ม: Default (1 รายการ · WinCC Unassigned Tag)")
        else:
            self.filter_banner_box.set_visible(False)

        self.render_catalog_table()

    # =========================================================================
    # 3. COLUMN 2: SHARED SEARCHABLE TAG CATALOG (CENTER ~48%)
    # =========================================================================

    def build_center_tag_catalog(self):
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        center_box.add_css_class('workspace-col-panel')

        # Top Group Summary Header
        summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        summary_box.add_css_class('f2-table-header-box')
        center_box.append(summary_box)

        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_vbox.set_hexpand(True)
        summary_box.append(title_vbox)

        self.lbl_catalog_title = Gtk.Label(label="คลัง Tag: ปั๊มน้ำแรงดันสูง VSD")
        self.lbl_catalog_title.add_css_class('f2-catalog-title')
        self.lbl_catalog_title.set_xalign(0.0)
        title_vbox.append(self.lbl_catalog_title)

        self.lbl_catalog_sub = Gtk.Label(label="ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ")
        self.lbl_catalog_sub.add_css_class('f2-catalog-subtitle')
        self.lbl_catalog_sub.set_xalign(0.0)
        title_vbox.append(self.lbl_catalog_sub)

        # Selection Badge
        self.lbl_sel_badge = Gtk.Label(label="ยังไม่ได้เลือก Tag")
        self.lbl_sel_badge.add_css_class('f2-sel-badge-idle')
        summary_box.append(self.lbl_sel_badge)

        # Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        center_box.append(search_box)

        self.entry_search = Gtk.SearchEntry()
        self.entry_search.set_hexpand(True)
        self.entry_search.add_css_class('workspace-search')
        self.entry_search.set_placeholder_text("🔍 ค้นหา Tag Name / Equipment Group / Data Type / S7 Address...")
        self.entry_search.connect('search-changed', self.on_search_changed)
        search_box.append(self.entry_search)

        # Active Filter Banner
        self.filter_banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filter_banner_box.add_css_class('workspace-filter-banner')
        self.filter_banner_box.set_visible(False)
        center_box.append(self.filter_banner_box)

        self.lbl_filter_banner = Gtk.Label(label="")
        self.lbl_filter_banner.set_xalign(0.0)
        self.lbl_filter_banner.set_hexpand(True)
        self.lbl_filter_banner.add_css_class('f2-filter-label')
        self.filter_banner_box.append(self.lbl_filter_banner)

        btn_clear_f = Gtk.Button(label="แสดงทุกกลุ่ม (All)")
        btn_clear_f.add_css_class('f2-btn-clear-filter')
        btn_clear_f.connect('clicked', lambda _: self.on_select_group("All"))
        self.filter_banner_box.append(btn_clear_f)

        # Table Column Headers (High Contrast WCAG Certified)
        col_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        col_hdr.add_css_class('f2-table-header-row')
        center_box.append(col_hdr)

        lbl_c0 = Gtk.Label(label="เลือก")
        lbl_c0.set_size_request(42, -1)
        lbl_c0.add_css_class('f2-col-header')
        col_hdr.append(lbl_c0)

        lbl_c1 = Gtk.Label(label="Tag Name (ชื่อสัญญาณ)")
        lbl_c1.set_hexpand(True)
        lbl_c1.set_xalign(0.0)
        lbl_c1.add_css_class('f2-col-header')
        col_hdr.append(lbl_c1)

        lbl_c2 = Gtk.Label(label="กลุ่มอุปกรณ์")
        lbl_c2.set_size_request(110, -1)
        lbl_c2.set_xalign(0.0)
        lbl_c2.add_css_class('f2-col-header')
        col_hdr.append(lbl_c2)

        lbl_c3 = Gtk.Label(label="Data Type")
        lbl_c3.set_size_request(80, -1)
        lbl_c3.set_xalign(0.0)
        lbl_c3.add_css_class('f2-col-header')
        col_hdr.append(lbl_c3)

        lbl_c4 = Gtk.Label(label="สถานะตรวจวัด")
        lbl_c4.set_size_request(140, -1)
        lbl_c4.set_xalign(0.0)
        lbl_c4.add_css_class('f2-col-header')
        col_hdr.append(lbl_c4)

        # Scrolled Table Body (Dark Background Scoped)
        tbl_scroll = Gtk.ScrolledWindow()
        tbl_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        tbl_scroll.set_hexpand(True)
        tbl_scroll.set_vexpand(True)
        tbl_scroll.add_css_class('workspace-table-scroll')
        center_box.append(tbl_scroll)

        self.catalog_listbox = Gtk.ListBox()
        self.catalog_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.catalog_listbox.add_css_class('f2-table-list')
        self.catalog_listbox.connect('row-selected', self.on_catalog_row_selected)
        tbl_scroll.set_child(self.catalog_listbox)

        # Bottom Action Dock Bar
        self.dock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.dock_box.add_css_class('workspace-dock-bar')
        center_box.append(self.dock_box)

        # F2 Mode Controls
        self.btn_add_selected = Gtk.Button(label="➕ เพิ่ม Tag ที่เลือกเข้าสู่ Task (0 รายการ)")
        self.btn_add_selected.add_css_class('f2-btn-add-selected')
        self.btn_add_selected.set_hexpand(True)
        self.btn_add_selected.connect('clicked', lambda _: self.on_add_selected_to_task())
        self.dock_box.append(self.btn_add_selected)

        self.btn_clear_sel = Gtk.Button(label="ล้างการเลือก")
        self.btn_clear_sel.add_css_class('f2-btn-clear-selection')
        self.btn_clear_sel.connect('clicked', lambda _: self.on_clear_selection())
        self.dock_box.append(self.btn_clear_sel)

        # F1 Mode Guidance
        self.lbl_dock_guide = Gtk.Label(label="👁 โหมดตรวจสอบ: คลิกแถวสัญญาณเพื่อดู Engineering Properties ทางขวา")
        self.lbl_dock_guide.add_css_class('workspace-subtitle')
        self.lbl_dock_guide.set_hexpand(True)
        self.lbl_dock_guide.set_xalign(0.0)
        self.lbl_dock_guide.set_visible(False)
        self.dock_box.append(self.lbl_dock_guide)

        # Inspector Collapse Button (F1)
        self.btn_collapse_inspector = Gtk.Button(label="◀ ยุบ Inspector")
        self.btn_collapse_inspector.add_css_class('f2-btn-collapse')
        self.btn_collapse_inspector.connect('clicked', self.toggle_inspector_collapse)
        self.dock_box.append(self.btn_collapse_inspector)

        return center_box

    def toggle_inspector_collapse(self, _=None):
        self.inspector_collapsed = not self.inspector_collapsed
        if self.inspector_collapsed:
            self.right_col.set_visible(False)
            self.btn_collapse_inspector.set_label("▶ แสดง Inspector (F1)")
            self.btn_collapse_inspector.set_tooltip_text("ขยายแผงคุณสมบัติสัญญาณ")
        else:
            self.right_col.set_visible(True)
            self.btn_collapse_inspector.set_label("◀ ยุบ Inspector")
            self.btn_collapse_inspector.set_tooltip_text("ยุบแผงคุณสมบัติสัญญาณเพื่อให้ตารางขยายเต็มพื้นที่")

    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.render_catalog_table()

    def render_catalog_table(self):
        """Filters and renders Tag rows into catalog_listbox with high contrast"""
        while self.catalog_listbox.get_first_child():
            self.catalog_listbox.remove(self.catalog_listbox.get_first_child())

        # Filter by group and search query
        filtered = []
        for t in self.catalog_tags_cache:
            if self.selected_group_key != "All" and t.get('group', 'Default') != self.selected_group_key:
                continue
            if self.search_query:
                combined = f"{t.get('name', '')} {t.get('group', '')} {t.get('type', '')} {t.get('addr', '')}".lower()
                if self.search_query not in combined:
                    continue
            filtered.append(t)

        self.currently_filtered_tags = filtered

        first_row = None
        for idx, tag in enumerate(filtered):
            row = Gtk.ListBoxRow()
            row._tag_data = tag
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row_box.set_margin_start(6)
            row_box.set_margin_end(6)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)
            row.set_child(row_box)

            # Checkbox
            chk = Gtk.CheckButton()
            chk.set_size_request(42, -1)
            tag_name = tag.get('name', '')
            chk.set_active(tag_name in self.selected_catalog_tags)
            chk.connect('toggled', self.make_chk_callback(tag_name))
            row_box.append(chk)

            # Tag Name (Monospace, Bright White #F8FAFC)
            t_name = Gtk.Label(label=tag_name)
            t_name.set_hexpand(True)
            t_name.set_xalign(0.0)
            t_name.add_css_class('f2-tag-name-label')
            t_name.set_ellipsize(Pango.EllipsizeMode.END)
            row_box.append(t_name)

            # Group
            t_grp = Gtk.Label(label=tag.get('group', 'Default'))
            t_grp.set_size_request(110, -1)
            t_grp.set_xalign(0.0)
            t_grp.add_css_class('f2-tag-group-label')
            row_box.append(t_grp)

            # Type
            t_type = Gtk.Label(label=format_data_type(tag.get('type', 'Real')))
            t_type.set_size_request(80, -1)
            t_type.set_xalign(0.0)
            t_type.add_css_class('f2-tag-type-badge')
            row_box.append(t_type)

            # Observation Status (Factual: Standby, not raw 0x00 mock)
            t_qual = Gtk.Label(label="Not Observed (Standby)")
            t_qual.set_size_request(140, -1)
            t_qual.set_xalign(0.0)
            t_qual.add_css_class('f2-tag-quality-idle')
            row_box.append(t_qual)

            self.catalog_listbox.append(row)
            if idx == 0:
                first_row = row

        if first_row and not self.selected_inspector_tag:
            self.catalog_listbox.select_row(first_row)
            self.on_catalog_row_selected(self.catalog_listbox, first_row)

        self.update_selection_badges()

    def make_chk_callback(self, tag_name):
        def cb(button):
            if button.get_active():
                self.selected_catalog_tags.add(tag_name)
            else:
                self.selected_catalog_tags.discard(tag_name)
            self.update_selection_badges()
        return cb

    def update_selection_badges(self):
        n = len(self.selected_catalog_tags)
        if n > 0:
            self.lbl_sel_badge.set_text(f"เลือกอยู่ {n} รายการ")
            self.lbl_sel_badge.remove_css_class('f2-sel-badge-idle')
            self.lbl_sel_badge.add_css_class('f2-sel-badge-active')
            self.btn_add_selected.set_label(f"➕ เพิ่ม Tag ที่เลือกเข้าสู่ Task ({n} รายการ)")
        else:
            self.lbl_sel_badge.set_text("ยังไม่ได้เลือก Tag")
            self.lbl_sel_badge.remove_css_class('f2-sel-badge-active')
            self.lbl_sel_badge.add_css_class('f2-sel-badge-idle')
            self.btn_add_selected.set_label("➕ เพิ่ม Tag ที่เลือกเข้าสู่ Task (0 รายการ)")

    def on_clear_selection(self):
        self.selected_catalog_tags.clear()
        self.render_catalog_table()

    def on_catalog_row_selected(self, listbox, row):
        if row and hasattr(row, '_tag_data'):
            self.selected_inspector_tag = row._tag_data
            self.render_inspector_tag(self.selected_inspector_tag)

    # =========================================================================
    # 4. COLUMN 3: CONTEXT PANEL (RIGHT ~32%)
    # =========================================================================

    def build_right_context_panel(self):
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.add_css_class('workspace-col-panel')

        # Header with Mode Switcher
        mode_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mode_hdr.add_css_class('f1-panel-header')
        right_box.append(mode_hdr)

        lbl_hdr_title = Gtk.Label(label="Context Panel")
        lbl_hdr_title.add_css_class('f1-panel-title')
        lbl_hdr_title.set_hexpand(True)
        lbl_hdr_title.set_xalign(0.0)
        mode_hdr.append(lbl_hdr_title)

        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_box.add_css_class('f1-mode-switcher')
        mode_hdr.append(tab_box)

        self.btn_tab_f1 = Gtk.ToggleButton(label="F1 Inspector")
        self.btn_tab_f1.add_css_class('f1-mode-btn')
        self.btn_tab_f1.set_active(True)
        self.btn_tab_f1.connect('toggled', lambda btn: self.set_workspace_mode('monitoring') if btn.get_active() else None)
        tab_box.append(self.btn_tab_f1)

        self.btn_tab_f2 = Gtk.ToggleButton(label="F2 Task Config")
        self.btn_tab_f2.add_css_class('f1-mode-btn')
        self.btn_tab_f2.set_group(self.btn_tab_f1)
        self.btn_tab_f2.connect('toggled', lambda btn: self.set_workspace_mode('task_manager') if btn.get_active() else None)
        tab_box.append(self.btn_tab_f2)

        # Context Stack
        self.context_stack = Gtk.Stack()
        self.context_stack.set_hexpand(True)
        self.context_stack.set_vexpand(True)
        right_box.append(self.context_stack)

        # Sub-view 1: Inspector (F1)
        self.inspector_scroll = self.build_inspector_view()
        self.context_stack.add_named(self.inspector_scroll, 'monitoring')

        # Sub-view 2: Task Configurator (F2)
        self.task_config_scroll = self.build_task_config_view()
        self.context_stack.add_named(self.task_config_scroll, 'task_manager')

        self.context_stack.set_visible_child_name('monitoring')
        return right_box

    def set_workspace_mode(self, mode_name):
        """Switches Context Panel between 'monitoring' (F1) and 'task_manager' (F2)"""
        self.current_workspace_mode = mode_name
        self.context_stack.set_visible_child_name(mode_name)

        is_m = (mode_name == 'monitoring')
        self.btn_top_f1.set_css_classes(['workspace-mode-btn-active' if is_m else 'workspace-mode-btn-inactive'])
        self.btn_top_f2.set_css_classes(['workspace-mode-btn-inactive' if is_m else 'workspace-mode-btn-active'])

        if is_m:
            if not self.btn_tab_f1.get_active():
                self.btn_tab_f1.set_active(True)
            self.btn_add_selected.set_visible(False)
            self.btn_clear_sel.set_visible(False)
            self.lbl_dock_guide.set_visible(True)
            self.btn_collapse_inspector.set_visible(True)
        else:
            if not self.btn_tab_f2.get_active():
                self.btn_tab_f2.set_active(True)
            self.btn_add_selected.set_visible(True)
            self.btn_clear_sel.set_visible(True)
            self.lbl_dock_guide.set_visible(False)
            self.btn_collapse_inspector.set_visible(False)
            # Ensure panel is visible in task mode
            if self.inspector_collapsed:
                self.toggle_inspector_collapse()

        # Sync bottom function keys on owner if present
        if hasattr(self.owner, 'nav_btns'):
            if is_m and 'overview' in self.owner.nav_btns:
                self.owner.nav_btns['overview'].set_active(True)
            elif not is_m and 'tasks' in self.owner.nav_btns:
                self.owner.nav_btns['tasks'].set_active(True)

    # -------------------------------------------------------------------------
    # SUB-VIEW: F1 INSPECTOR (HIGH CONTRAST & STRUCTURED)
    # -------------------------------------------------------------------------

    def build_inspector_view(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.inspector_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.inspector_vbox.set_margin_start(4)
        self.inspector_vbox.set_margin_end(4)
        scrolled.set_child(self.inspector_vbox)

        # Empty State Placeholder
        self.empty_inspector_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.empty_inspector_box.add_css_class('workspace-empty-inspector')
        self.empty_inspector_box.set_visible(False)
        self.inspector_vbox.append(self.empty_inspector_box)

        lbl_emp_icon = Gtk.Label(label="👁 โหมดตรวจสอบคุณสมบัติสัญญาณ (Tag Inspector)")
        lbl_emp_icon.add_css_class('workspace-empty-title')
        self.empty_inspector_box.append(lbl_emp_icon)

        lbl_emp_sub = Gtk.Label(label="กรุณาคลิกเลือกสัญญาณในตาราง Tag Catalog เพื่อตรวจสอบข้อมูลทางวิศวกรรม")
        lbl_emp_sub.add_css_class('workspace-empty-sub')
        self.empty_inspector_box.append(lbl_emp_sub)

        # Active Inspector Content Box
        self.active_inspector_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.inspector_vbox.append(self.active_inspector_box)

        # Tag Header Pill
        self.insp_hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.active_inspector_box.append(self.insp_hdr_box)

        self.insp_lbl_name = Gtk.Label(label="High_VSD_01_Speed_Feedback")
        self.insp_lbl_name.add_css_class('f1-group-code-pill')
        self.insp_lbl_name.set_selectable(True)
        self.insp_hdr_box.append(self.insp_lbl_name)

        self.insp_lbl_type = Gtk.Label(label="Float")
        self.insp_lbl_type.add_css_class('f1-badge-accent')
        self.insp_hdr_box.append(self.insp_lbl_type)

        self.insp_lbl_addr = Gtk.Label(label="PLC: DB13.DBD0")
        self.insp_lbl_addr.add_css_class('f1-badge-neutral')
        self.insp_hdr_box.append(self.insp_lbl_addr)

        # Comment
        self.insp_lbl_comment = Gtk.Label(label="สัญญาณความเร็วรอบปั๊มน้ำแรงดันสูง VSD ชุดที่ 1")
        self.insp_lbl_comment.add_css_class('f1-group-desc-th')
        self.insp_lbl_comment.set_xalign(0.0)
        self.active_inspector_box.append(self.insp_lbl_comment)

        # Technical Grid 1: ข้อมูลการระบุสัญญาณ
        grid_frame1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        grid_frame1.add_css_class('workspace-inspector-grid')
        self.active_inspector_box.append(grid_frame1)

        t1 = Gtk.Label(label="1. ข้อมูลการระบุสัญญาณ (Identification)")
        t1.add_css_class('f2-section-title')
        t1.set_xalign(0.0)
        grid_frame1.append(t1)

        self.insp_grid1 = Gtk.Grid(column_spacing=12, row_spacing=6)
        grid_frame1.append(self.insp_grid1)

        self.insp_grid_values = {}
        spec_keys1 = [
            ("group", "กลุ่มอุปกรณ์ (Group):"),
            ("type", "ประเภทข้อมูล (Data Type):"),
            ("conn", "การเชื่อมต่อ (Connection):"),
            ("addr", "S7 PLC Offset:")
        ]
        for r_idx, (k, title) in enumerate(spec_keys1):
            lbl_k = Gtk.Label(label=title)
            lbl_k.add_css_class('workspace-inspector-key')
            lbl_k.set_xalign(0.0)
            self.insp_grid1.attach(lbl_k, 0, r_idx, 1, 1)

            lbl_v = Gtk.Label(label="—")
            lbl_v.add_css_class('workspace-inspector-val')
            lbl_v.set_xalign(0.0)
            lbl_v.set_selectable(True)
            self.insp_grid1.attach(lbl_v, 1, r_idx, 1, 1)
            self.insp_grid_values[k] = lbl_v

        # Technical Grid 2: สถานะการตรวจวัด
        grid_frame2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        grid_frame2.add_css_class('workspace-inspector-grid')
        self.active_inspector_box.append(grid_frame2)

        t2 = Gtk.Label(label="2. สถานะสัญญาณและการตรวจวัด (Observation)")
        t2.add_css_class('f2-section-title')
        t2.set_xalign(0.0)
        grid_frame2.append(t2)

        self.insp_grid2 = Gtk.Grid(column_spacing=12, row_spacing=6)
        grid_frame2.append(self.insp_grid2)

        spec_keys2 = [
            ("source", "แหล่งข้อมูล (Source):"),
            ("quality", "คุณภาพสัญญาณ (Quality):"),
            ("live_val", "ค่าล่าสุด (Live Value):"),
            ("last_obs", "ตรวจวัดล่าสุด (Last Seen):")
        ]
        for r_idx, (k, title) in enumerate(spec_keys2):
            lbl_k = Gtk.Label(label=title)
            lbl_k.add_css_class('workspace-inspector-key')
            lbl_k.set_xalign(0.0)
            self.insp_grid2.attach(lbl_k, 0, r_idx, 1, 1)

            lbl_v = Gtk.Label(label="—")
            lbl_v.add_css_class('workspace-inspector-val')
            lbl_v.set_xalign(0.0)
            lbl_v.set_selectable(True)
            self.insp_grid2.attach(lbl_v, 1, r_idx, 1, 1)
            self.insp_grid_values[k] = lbl_v

        # Quick Actions Card
        action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        action_card.add_css_class('f2-action-card')
        self.active_inspector_box.append(action_card)

        lbl_act = Gtk.Label(label="การดำเนินการกับสัญญาณนี้ (Quick Actions)")
        lbl_act.add_css_class('f2-action-card-title')
        lbl_act.set_xalign(0.0)
        action_card.append(lbl_act)

        btn_add_to_cur_task = Gtk.Button(label="➕ นำ Tag นี้เพิ่มเข้าสู่ Task ปัจจุบัน (F2)")
        btn_add_to_cur_task.add_css_class('f2-btn-add-selected')
        btn_add_to_cur_task.connect('clicked', lambda _: self.on_add_single_tag_to_task())
        action_card.append(btn_add_to_cur_task)

        btn_open_f6 = Gtk.Button(label="⚙️ ตั้งค่าการเชื่อมต่อ WinCC OPC UA (F6)")
        btn_open_f6.add_css_class('f2-btn-clear-selection')
        btn_open_f6.connect('clicked', lambda _: self.owner.switch_to_tab('alarms'))
        action_card.append(btn_open_f6)

        return scrolled

    def render_inspector_tag(self, tag):
        if not tag:
            self.empty_inspector_box.set_visible(True)
            self.active_inspector_box.set_visible(False)
            return

        self.empty_inspector_box.set_visible(False)
        self.active_inspector_box.set_visible(True)

        self.insp_lbl_name.set_text(tag.get('name', 'UNKNOWN'))
        self.insp_lbl_type.set_text(format_data_type(tag.get('type', 'Real')))
        self.insp_lbl_addr.set_text(f"PLC: {tag.get('addr', 'Internal')}")

        comment = tag.get('comment', '').strip() or "สัญญาณควบคุมและสถานะการทำงานของสถานีสูบน้ำ"
        self.insp_lbl_comment.set_text(comment)

        grp_name = tag.get('group', 'Default')
        meta = GROUP_METADATA.get(grp_name, ('', ''))[0]
        self.insp_grid_values['group'].set_text(f"{grp_name} ({meta})")
        self.insp_grid_values['type'].set_text(f"{format_data_type(tag.get('type', 'Real'))} ({tag.get('type', 'Real')})")
        self.insp_grid_values['conn'].set_text(tag.get('conn', 'High1 (S7-300/400 ISO-on-TCP)'))
        self.insp_grid_values['addr'].set_text(tag.get('addr', 'Internal / Not Mapped'))

        self.insp_grid_values['source'].set_text("WinCC Tag Management Export (Export all.txt)")
        self.insp_grid_values['quality'].set_text("Not Observed (Standby · Zero Mock)")
        self.insp_grid_values['live_val'].set_text("— (ยังไม่ได้เชื่อมต่อ Live Session)")
        self.insp_grid_values['last_obs'].set_text("— (ไม่มีประวัติการอ่านสด)")

    def on_add_single_tag_to_task(self):
        if not self.selected_inspector_tag:
            return
        tn = self.selected_inspector_tag.get('name')
        if not tn:
            return
        tasks = getattr(self.owner, 'tasks', [])
        if 0 <= self.selected_task_index < len(tasks):
            cur_task = tasks[self.selected_task_index]
            cur_tags = cur_task.setdefault('tags', [])
            if tn not in cur_tags:
                cur_tags.append(tn)
                self.has_unsaved_changes = True
                self.render_assigned_tags_table(cur_task)
                self.update_dirty_status()
                # Switch to F2 so user sees the addition
                self.set_workspace_mode('task_manager')

    # -------------------------------------------------------------------------
    # SUB-VIEW: F2 TASK CONFIGURATOR (3 BALANCED SECTIONS)
    # -------------------------------------------------------------------------

    def build_task_config_view(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.task_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.task_vbox.set_margin_start(2)
        self.task_vbox.set_margin_end(2)
        scrolled.set_child(self.task_vbox)

        # SECTION 1: ข้อมูลและการระบุตัวตนของ Task
        sec1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sec1.add_css_class('f2-section-card')
        self.task_vbox.append(sec1)

        s1_title = Gtk.Label(label="1. ข้อมูลและการระบุตัวตนของ Task")
        s1_title.add_css_class('f2-section-title')
        s1_title.set_xalign(0.0)
        sec1.append(s1_title)

        # Task Selector + Create New
        sel_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sec1.append(sel_row)

        lbl_s = Gtk.Label(label="เลือก Task:")
        lbl_s.add_css_class('f2-form-label')
        sel_row.append(lbl_s)

        self.task_selector_combo = Gtk.DropDown()
        self.task_selector_combo.set_size_request(220, -1)
        self.task_selector_combo.connect('notify::selected', self.on_task_selector_changed)
        sel_row.append(self.task_selector_combo)

        btn_new = Gtk.Button(label="➕ สร้าง Task")
        btn_new.add_css_class('f2-btn-new-task')
        btn_new.connect('clicked', lambda _: self.on_create_new_task())
        sel_row.append(btn_new)

        # Grid Details
        grid1 = Gtk.Grid(column_spacing=8, row_spacing=6)
        sec1.append(grid1)

        # Task ID
        lbl_id = Gtk.Label(label="Task ID:")
        lbl_id.add_css_class('f2-form-label')
        lbl_id.set_xalign(0.0)
        grid1.attach(lbl_id, 0, 0, 1, 1)

        self.lbl_task_id_val = Gtk.Label(label="TASK-01")
        self.lbl_task_id_val.add_css_class('f2-task-id-pill')
        self.lbl_task_id_val.set_xalign(0.0)
        grid1.attach(self.lbl_task_id_val, 1, 0, 1, 1)

        # Task Name
        lbl_name = Gtk.Label(label="ชื่อ Task:")
        lbl_name.add_css_class('f2-form-label')
        lbl_name.set_xalign(0.0)
        grid1.attach(lbl_name, 0, 1, 1, 1)

        self.entry_task_name = Gtk.Entry()
        self.entry_task_name.set_size_request(280, -1)
        self.entry_task_name.connect('changed', self.on_task_field_changed)
        grid1.attach(self.entry_task_name, 1, 1, 1, 1)

        # Task Cycle
        lbl_cy = Gtk.Label(label="รอบตรวจสอบ:")
        lbl_cy.add_css_class('f2-form-label')
        lbl_cy.set_xalign(0.0)
        grid1.attach(lbl_cy, 0, 2, 1, 1)

        cycle_list = Gtk.StringList.new([c[1] for c in CYCLE_OPTIONS])
        self.combo_cycle = Gtk.DropDown.new(cycle_list, None)
        self.combo_cycle.set_selected(1)  # 5s
        self.combo_cycle.set_size_request(240, -1)
        self.combo_cycle.connect('notify::selected', self.on_task_field_changed)
        grid1.attach(self.combo_cycle, 1, 2, 1, 1)

        # Status badge
        lbl_st = Gtk.Label(label="สถานะ Task:")
        lbl_st.add_css_class('f2-form-label')
        lbl_st.set_xalign(0.0)
        grid1.attach(lbl_st, 0, 3, 1, 1)

        self.lbl_task_state_badge = Gtk.Label(label="พร้อมทำงาน")
        self.lbl_task_state_badge.add_css_class('f2-task-status-ready')
        self.lbl_task_state_badge.set_xalign(0.0)
        grid1.attach(self.lbl_task_state_badge, 1, 3, 1, 1)

        # SECTION 2: การทำงานเมื่อตรวจพบสัญญาณ (Task Actions)
        sec2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sec2.add_css_class('f2-section-card')
        self.task_vbox.append(sec2)

        s2_title = Gtk.Label(label="2. การทำงานเมื่อตรวจพบสัญญาณ (Task Actions)")
        s2_title.add_css_class('f2-section-title')
        s2_title.set_xalign(0.0)
        sec2.append(s2_title)

        lbl_s2_sub = Gtk.Label(label="เมื่อ Task ทำงาน ให้ระบบทำอะไร?:")
        lbl_s2_sub.add_css_class('f2-action-subtitle')
        lbl_s2_sub.set_xalign(0.0)
        sec2.append(lbl_s2_sub)

        self.chk_action_log = Gtk.CheckButton(label="บันทึกข้อมูลประวัติ (Local CSV / SQLite Archive)")
        self.chk_action_log.set_active(True)
        self.chk_action_log.connect('toggled', self.on_task_field_changed)
        sec2.append(self.chk_action_log)

        tg_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sec2.append(tg_row)

        self.chk_action_notify = Gtk.CheckButton(label="ส่งแจ้งเตือนผ่าน Telegram Bot")
        self.chk_action_notify.set_active(True)
        self.chk_action_notify.connect('toggled', self.on_task_field_changed)
        tg_row.append(self.chk_action_notify)

        lbl_f6_hint = Gtk.Label(label="(⚙️ ต้องตั้งค่า Token & Chat ID ที่ F6 ก่อนใช้งาน)")
        lbl_f6_hint.add_css_class('f2-action-hint')
        tg_row.append(lbl_f6_hint)

        self.chk_task_enabled = Gtk.CheckButton(label="เปิดใช้งาน Task นี้ (Enable Task)")
        self.chk_task_enabled.set_active(True)
        self.chk_task_enabled.connect('toggled', self.on_task_field_changed)
        sec2.append(self.chk_task_enabled)

        # SECTION 3: สัญญาณที่ถูกผูกกับ Task (Assigned Tags)
        sec3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sec3.add_css_class('f2-section-card')
        self.task_vbox.append(sec3)

        self.lbl_assigned_title = Gtk.Label(label="3. สัญญาณที่ถูกผูกกับ Task (0 รายการ)")
        self.lbl_assigned_title.add_css_class('f2-section-title')
        self.lbl_assigned_title.set_xalign(0.0)
        sec3.append(self.lbl_assigned_title)

        as_scroll = Gtk.ScrolledWindow()
        as_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        as_scroll.set_propagate_natural_height(True)
        as_scroll.set_max_content_height(160)
        as_scroll.add_css_class('f2-assigned-scroll')
        sec3.append(as_scroll)

        self.assigned_listbox = Gtk.ListBox()
        self.assigned_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.assigned_listbox.add_css_class('f2-assigned-list')
        as_scroll.set_child(self.assigned_listbox)

        # STICKY BOTTOM SAVE TASK BAR
        save_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_bar.add_css_class('f2-save-dock-bar')
        self.task_vbox.append(save_bar)

        self.lbl_save_status = Gtk.Label(label="พร้อมใช้งาน · ข้อมูลได้รับการบันทึกแล้ว")
        self.lbl_save_status.add_css_class('f2-save-status-clean')
        self.lbl_save_status.set_hexpand(True)
        self.lbl_save_status.set_xalign(0.0)
        save_bar.append(self.lbl_save_status)

        self.btn_save_task = Gtk.Button(label="💾 บันทึก Task (Save Task)")
        self.btn_save_task.add_css_class('f2-btn-save-task')
        self.btn_save_task.connect('clicked', lambda _: self.on_save_task())
        save_bar.append(self.btn_save_task)

        return scrolled

    # -------------------------------------------------------------------------
    # TASK OPERATIONS & PERSISTENCE
    # -------------------------------------------------------------------------

    def load_current_task_to_ui(self):
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks:
            return

        if self.selected_task_index >= len(tasks):
            self.selected_task_index = 0

        # Update combo list
        self.task_selector_updating = True
        str_items = [f"{t.get('id', 'TASK')} — {t.get('name', '')[:25]}" for t in tasks]
        self.task_selector_combo.set_model(Gtk.StringList.new(str_items))
        self.task_selector_combo.set_selected(self.selected_task_index)
        self.task_selector_updating = False

        task = tasks[self.selected_task_index]
        self.lbl_task_id_val.set_text(task.get('id', f'TASK-{self.selected_task_index+1:02d}'))
        self.entry_task_name.set_text(task.get('name', ''))

        cycle_sec = task.get('cycle_sec', 5)
        cycle_idx = 1
        for i, (sec, _) in enumerate(CYCLE_OPTIONS):
            if sec == cycle_sec:
                cycle_idx = i
                break
        self.combo_cycle.set_selected(cycle_idx)

        self.chk_action_log.set_active(task.get('action_log', True))
        self.chk_action_notify.set_active(task.get('action_notify', True))
        self.chk_task_enabled.set_active(task.get('active', True))

        self.render_assigned_tags_table(task)
        self.has_unsaved_changes = False
        self.update_dirty_status()

    def render_assigned_tags_table(self, task):
        while self.assigned_listbox.get_first_child():
            self.assigned_listbox.remove(self.assigned_listbox.get_first_child())

        assigned = task.get('tags', [])
        self.lbl_assigned_title.set_text(f"3. สัญญาณที่ถูกผูกกับ Task ({len(assigned)} รายการ)")

        if len(assigned) > 0:
            self.lbl_task_state_badge.set_text(f"พร้อมทำงาน · มี {len(assigned)} Tags")
            self.lbl_task_state_badge.remove_css_class('f2-scan-status-idle')
            self.lbl_task_state_badge.add_css_class('f2-task-status-ready')
        else:
            self.lbl_task_state_badge.set_text("ยังไม่มี Tag ผูกกับ Task")
            self.lbl_task_state_badge.remove_css_class('f2-task-status-ready')
            self.lbl_task_state_badge.add_css_class('f2-scan-status-idle')

        for tn in assigned:
            tag_info = next((t for t in self.catalog_tags_cache if t['name'] == tn), {'name': tn, 'group': 'Unknown', 'type': 'Float'})

            row = Gtk.ListBoxRow()
            rbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            rbox.set_margin_start(4)
            rbox.set_margin_end(4)
            rbox.set_margin_top(3)
            rbox.set_margin_bottom(3)
            row.set_child(rbox)

            lbl_n = Gtk.Label(label=tn)
            lbl_n.set_hexpand(True)
            lbl_n.set_xalign(0.0)
            lbl_n.add_css_class('f2-tag-name-label')
            lbl_n.set_ellipsize(Pango.EllipsizeMode.END)
            rbox.append(lbl_n)

            lbl_g = Gtk.Label(label=tag_info.get('group', 'Unknown'))
            lbl_g.add_css_class('f2-tag-group-label')
            rbox.append(lbl_g)

            lbl_tp = Gtk.Label(label=format_data_type(tag_info.get('type', 'Real')))
            lbl_tp.add_css_class('f2-tag-type-badge')
            rbox.append(lbl_tp)

            lbl_q = Gtk.Label(label="Not Observed")
            lbl_q.add_css_class('f2-tag-quality-idle')
            rbox.append(lbl_q)

            btn_del = Gtk.Button(label="✕")
            btn_del.add_css_class('f2-btn-remove-tag')
            btn_del.connect('clicked', self.make_delete_callback(tn))
            rbox.append(btn_del)

            self.assigned_listbox.append(row)

    def make_delete_callback(self, tag_name):
        def cb(button):
            tasks = getattr(self.owner, 'tasks', [])
            if 0 <= self.selected_task_index < len(tasks):
                cur_task = tasks[self.selected_task_index]
                if tag_name in cur_task.get('tags', []):
                    cur_task['tags'].remove(tag_name)
                    self.has_unsaved_changes = True
                    self.render_assigned_tags_table(cur_task)
                    self.update_dirty_status()
        return cb

    def on_add_selected_to_task(self):
        if not self.selected_catalog_tags:
            return
        tasks = getattr(self.owner, 'tasks', [])
        if not tasks:
            return
        cur_task = tasks[self.selected_task_index]
        cur_tags = cur_task.setdefault('tags', [])

        added_count = 0
        for tn in self.selected_catalog_tags:
            if tn not in cur_tags:
                cur_tags.append(tn)
                added_count += 1

        if added_count > 0:
            self.has_unsaved_changes = True
            self.render_assigned_tags_table(cur_task)
            self.update_dirty_status()
            self.selected_catalog_tags.clear()
            self.render_catalog_table()

    def on_task_field_changed(self, *args):
        if self.task_selector_updating:
            return
        self.has_unsaved_changes = True
        self.update_dirty_status()

    def update_dirty_status(self):
        if self.has_unsaved_changes:
            self.lbl_save_status.set_text("⚠️ มีข้อมูลที่ยังไม่ได้บันทึก (Unsaved Changes)")
            self.lbl_save_status.remove_css_class('f2-save-status-clean')
            self.lbl_save_status.add_css_class('f2-save-status-dirty')
        else:
            self.lbl_save_status.set_text("พร้อมใช้งาน · ข้อมูลได้รับการบันทึกแล้ว")
            self.lbl_save_status.remove_css_class('f2-save-status-dirty')
            self.lbl_save_status.add_css_class('f2-save-status-clean')

    def on_task_selector_changed(self, drop_down, param_spec):
        if self.task_selector_updating:
            return
        new_idx = drop_down.get_selected()
        self.switch_to_task(new_idx)

    def switch_to_task(self, idx):
        tasks = getattr(self.owner, 'tasks', [])
        if 0 <= idx < len(tasks):
            if self.has_unsaved_changes:
                self.on_save_task()  # Auto-save safeguard before switching
            self.selected_task_index = idx
            self.owner.current_task_idx = idx
            self.load_current_task_to_ui()

    def on_save_task(self):
        tasks = getattr(self.owner, 'tasks', [])
        if not (0 <= self.selected_task_index < len(tasks)):
            return

        cur_task = tasks[self.selected_task_index]
        cur_task['name'] = self.entry_task_name.get_text().strip() or f"Task {self.selected_task_index+1}"

        cycle_idx = self.combo_cycle.get_selected()
        cur_task['cycle_sec'] = CYCLE_OPTIONS[cycle_idx][0] if 0 <= cycle_idx < len(CYCLE_OPTIONS) else 5

        cur_task['action_log'] = self.chk_action_log.get_active()
        cur_task['action_notify'] = self.chk_action_notify.get_active()
        cur_task['active'] = self.chk_task_enabled.get_active()

        # Atomic JSON Save to TASKS_CONFIG_FILE
        saved = self.owner.save_tasks() if hasattr(self.owner, 'save_tasks') else False
        self.has_unsaved_changes = False
        self.update_dirty_status()

        # Update combo title
        self.task_selector_updating = True
        str_items = [f"{t.get('id', 'TASK')} — {t.get('name', '')[:25]}" for t in tasks]
        self.task_selector_combo.set_model(Gtk.StringList.new(str_items))
        self.task_selector_combo.set_selected(self.selected_task_index)
        self.task_selector_updating = False

    def on_create_new_task(self):
        tasks = getattr(self.owner, 'tasks', [])
        if self.has_unsaved_changes:
            self.on_save_task()

        new_id_num = len(tasks) + 1
        new_task = {
            "id": f"TASK-{new_id_num:02d}",
            "name": f"Task เฝ้าระวังใหม่ TASK-{new_id_num:02d}",
            "cycle_sec": 5,
            "action_log": True,
            "action_notify": True,
            "active": True,
            "tags": [],
            "scan_count": 0,
            "log_count": 0,
            "alert_count": 0
        }
        tasks.append(new_task)
        self.selected_task_index = len(tasks) - 1
        self.owner.current_task_idx = self.selected_task_index
        self.on_save_task()
        self.load_current_task_to_ui()

    def on_toggle_auto_scan(self, button):
        if hasattr(self.owner, 'auto_scan_active'):
            self.owner.auto_scan_active = not self.owner.auto_scan_active
            is_running = self.owner.auto_scan_active
            self.btn_auto_scan.set_label("⏹ หยุด Auto Scan" if is_running else "▶ เริ่ม Auto Scan")
            if is_running:
                self.btn_auto_scan.remove_css_class('f2-btn-auto-start')
                self.btn_auto_scan.add_css_class('f2-btn-auto-stop')
                self.badge_scan_status.set_text("Scanning...")
                self.badge_scan_status.remove_css_class('f2-scan-status-idle')
                self.badge_scan_status.add_css_class('f2-scan-status-running')
            else:
                self.btn_auto_scan.remove_css_class('f2-btn-auto-stop')
                self.btn_auto_scan.add_css_class('f2-btn-auto-start')
                self.badge_scan_status.set_text("Ready · Standby")
                self.badge_scan_status.remove_css_class('f2-scan-status-running')
                self.badge_scan_status.add_css_class('f2-scan-status-idle')

    def sync_catalog_data(self):
        """Synchronizes 457 tags from owner.scanned_tags"""
        self.catalog_tags_cache = getattr(self.owner, 'scanned_tags', [])
        self.group_counts = {"All": len(self.catalog_tags_cache)}
        for t in self.catalog_tags_cache:
            g = t.get('group', 'Default')
            self.group_counts[g] = self.group_counts.get(g, 0) + 1
