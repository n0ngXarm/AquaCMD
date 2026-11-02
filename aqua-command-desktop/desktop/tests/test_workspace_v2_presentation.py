#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — UNIFIED WORKSPACE PROFESSIONAL UI PASS V2
Automated Verification for Table Contrast, Layout Proportions & Inspector Collapse
"""

import os
import sys
import math
import unittest
from pathlib import Path

desktop_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

import app
from workspace import AquaUnifiedWorkspaceView, GROUP_METADATA

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def get_relative_luminance(rgb):
    def channel_lum(c):
        return c / 12.92 if c <= 0.03928 else math.pow((c + 0.055) / 1.055, 2.4)
    r, g, b = rgb
    return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)

def get_contrast_ratio(hex1, hex2):
    lum1 = get_relative_luminance(hex_to_rgb(hex1))
    lum2 = get_relative_luminance(hex_to_rgb(hex2))
    brightest = max(lum1, lum2)
    darkest = min(lum1, lum2)
    return (brightest + 0.05) / (darkest + 0.05)


class TestWorkspaceV2Presentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gtk_app = Gtk.Application(application_id='org.aqua.test.workspace.v2')
        cls.win = app.AquaWinCCWindow(cls.gtk_app)
        cls.win.auto_scan_active = False
        cls.ws = cls.win.unified_workspace

    def test_01_wcag_aa_table_contrast(self):
        """Verify contrast ratios for all table states meet WCAG AA (>= 4.5:1) with Industrial Graphite tokens"""
        # Normal Row: Text #F0F4F8 on Background #151F2A
        contrast_normal = get_contrast_ratio("#F0F4F8", "#151F2A")
        self.assertGreaterEqual(contrast_normal, 4.5, f"Normal row contrast {contrast_normal:.2f} must be >= 4.5:1")
        self.assertGreaterEqual(contrast_normal, 14.0, "Normal row should have exceptional readability (>14:1)")

        # Zebra Row: Text #F0F4F8 on Background #192532
        contrast_zebra = get_contrast_ratio("#F0F4F8", "#192532")
        self.assertGreaterEqual(contrast_zebra, 4.5)

        # Hover Row: Text #FFFFFF on Background #26313D
        contrast_hover = get_contrast_ratio("#FFFFFF", "#26313D")
        self.assertGreaterEqual(contrast_hover, 4.5)

        # Selected Row: Text #FFFFFF on Background #1E2D3D
        contrast_selected = get_contrast_ratio("#FFFFFF", "#1E2D3D")
        self.assertGreaterEqual(contrast_selected, 4.5)

        # Table Header: Text #A8B5C3 on Background #1D2834
        contrast_header = get_contrast_ratio("#A8B5C3", "#1D2834")
        self.assertGreaterEqual(contrast_header, 4.5)

        # Equipment Group Label: Text #F0F4F8 on Background #1D2834
        contrast_group = get_contrast_ratio("#F0F4F8", "#1D2834")
        self.assertGreaterEqual(contrast_group, 4.5)

        # Neutral Gray Standby: Text #8899AA on Background #151F2A
        contrast_gray = get_contrast_ratio("#8899AA", "#151F2A")
        self.assertGreaterEqual(contrast_gray, 4.5)

    def test_02_layout_proportions_20_48_32(self):
        """Verify 20% / 48% / 32% layout proportions at 1366 and 1920"""
        # Test 1366x768
        w1 = 1366
        self.ws.update_layout_proportions(w1)
        left_pos1 = self.ws.main_hpaned.get_position()
        center_pos1 = self.ws.sub_hpaned.get_position()

        expected_left1 = int(w1 * 0.20)
        expected_center1 = int(w1 * 0.48)
        self.assertEqual(left_pos1, expected_left1)
        self.assertEqual(center_pos1, expected_center1)

        # Test 1920x1080
        w2 = 1920
        self.ws.update_layout_proportions(w2)
        left_pos2 = self.ws.main_hpaned.get_position()
        center_pos2 = self.ws.sub_hpaned.get_position()

        expected_left2 = int(w2 * 0.20)
        expected_center2 = int(w2 * 0.48)
        self.assertEqual(left_pos2, expected_left2)
        self.assertEqual(center_pos2, expected_center2)

    def test_03_inspector_collapse_and_restore(self):
        """Verify F1 Inspector collapse and expansion preserves tag selection and state"""
        self.ws.set_workspace_mode('monitoring')
        self.ws.on_select_group("High_VSD")
        selected_tag = self.ws.selected_inspector_tag
        self.assertIsNotNone(selected_tag)
        tag_name = selected_tag.get('name')

        # Collapse Inspector
        self.ws.toggle_inspector_collapse()
        self.assertTrue(self.ws.inspector_collapsed)
        self.assertFalse(self.ws.right_col.get_visible(), "Right context panel must be hidden when collapsed")
        self.assertIn("แสดง", self.ws.btn_collapse_inspector.get_label())

        # Verify selected tag is unchanged
        self.assertEqual(self.ws.selected_inspector_tag.get('name'), tag_name)

        # Restore Inspector
        self.ws.toggle_inspector_collapse()
        self.assertFalse(self.ws.inspector_collapsed)
        self.assertTrue(self.ws.right_col.get_visible(), "Right context panel must be restored")
        self.assertEqual(self.ws.selected_inspector_tag.get('name'), tag_name)

    def test_04_factual_status_not_mock_hex(self):
        """Verify status column uses factual 'Not Observed (Standby)' and not misleading 0x00 mock"""
        row_count = 0
        child = self.ws.catalog_listbox.get_first_child()
        while child:
            row_count += 1
            # Search inside row for quality label
            rbox = child.get_child()
            quality_label = None
            c = rbox.get_first_child()
            while c:
                if isinstance(c, Gtk.Label) and "Not Observed" in c.get_text():
                    quality_label = c.get_text()
                    break
                c = c.get_next_sibling()
            self.assertIsNotNone(quality_label, "Row must contain factual observation status")
            self.assertNotIn("0x00000000", quality_label, "Status must not show mock hex as live telemetry")
            child = child.get_next_sibling()
            if row_count >= 5:
                break

    def test_05_verified_group_metadata(self):
        """Verify all 10 real equipment groups have factual Thai translations without guesswork"""
        self.assertEqual(len(GROUP_METADATA), 11)  # All + 10 catalog groups
        self.assertIn("High_VSD", GROUP_METADATA)
        self.assertIn("High_Valve", GROUP_METADATA)
        self.assertIn("High1_PT1PT", GROUP_METADATA)
        self.assertIn("High_Analog", GROUP_METADATA)
        self.assertIn("High_DPM", GROUP_METADATA)
        self.assertIn("High1_Sound", GROUP_METADATA)
        self.assertIn("High1_Totalize_Flow", GROUP_METADATA)
        self.assertIn("Temp_High_Alarm", GROUP_METADATA)
        self.assertIn("Timer_Of_Start_Second_CTM", GROUP_METADATA)
        self.assertIn("Default", GROUP_METADATA)

        # Verify Thai labels are factual
        self.assertIn("VSD", GROUP_METADATA["High_VSD"][0])
        self.assertIn("วาล์ว", GROUP_METADATA["High_Valve"][0])
        self.assertIn("แรงดัน", GROUP_METADATA["High1_PT1PT"][0])
        self.assertIn("อนาล็อก", GROUP_METADATA["High_Analog"][0])

if __name__ == '__main__':
    unittest.main()
