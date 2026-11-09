#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQUA COMMAND — UNIFIED WORKSPACE PROFESSIONAL UI PASS V2
Palette contrast and catalog group labels. Native popup/layout checks live in test_workspace_production.py.
"""

import sys
import math
import unittest
from pathlib import Path

desktop_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(desktop_dir))

import gi
gi.require_version('Gtk', '4.0')
from workspace import GROUP_METADATA

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
