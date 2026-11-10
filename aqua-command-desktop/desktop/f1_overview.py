"""
f1_overview.py — AQUA COMMAND F1 Industrial Precision Master-Detail Station Explorer
Implements:
  - Section B: F1 Page Heading ("ภาพรวมสถานีสูบน้ำ", "Industrial Station Overview")
  - Section C: 4 KPI Summary Metrics Cards (Registered Tags, Tag Groups, OPC UA Session, Live Signals)
  - Section D: Equipment Group Explorer (Left ~28%, 10 Catalog Groups, selection state, keyboard navigation)
  - Section E: Technical Equipment View (Upper Right ~72%, Cairo Vector Blueprints for all equipment classes)
  - Section F: Equipment Metrics (Catalog tags, live stream status, signal quality)
  - Section G: Signal & Tag Inspector (Signal List Table & Properties Sheet modes with Search & Filter)
"""
import math
import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import cairo

# -----------------------------------------------------------------------------
# Equipment Groups Definitions (All 10 WinCC Catalog Groups)
# -----------------------------------------------------------------------------
EQUIPMENT_GROUPS_DEF = {
    '__ALL__': {
        'name_en': 'All Equipment Groups & Signals',
        'short_en': 'All Groups',
        'desc_th': 'รวมสัญญาณทั้งหมดทุกกลุ่มอุปกรณ์ในระบบ SCADA',
        'eq_class': 'all_groups',
        'icon_name': 'view-grid-symbolic',
        'db_ref': 'Multiple S7 DBs',
        'spec_summary': 'Comprehensive Station Catalog'
    },
    'High_VSD': {
        'name_en': 'High-Pressure Inverter Pumps',
        'short_en': 'Inverter Pumps',
        'desc_th': 'ปั๊มสูบส่งน้ำแรงสูง VSD (CTM13–17)',
        'eq_class': 'vsd_pump',
        'icon_name': 'network-server-symbolic',
        'db_ref': 'DB62 / DB64',
        'spec_summary': '160 kW Inverter VSD · PN16'
    },
    'High1_PT1PT': {
        'name_en': 'Ping River Raw Water Intake Pumps',
        'short_en': 'Raw Water Intake',
        'desc_th': 'สถานีสูบน้ำดิบแม่น้ำปิง (PT1_P1–P4)',
        'eq_class': 'raw_water_pump',
        'icon_name': 'weather-showers-symbolic',
        'db_ref': 'DB60',
        'spec_summary': '1,800 m³/h · Motor 110 kW'
    },
    'High_Analog': {
        'name_en': 'Process Instrumentation Transmitters',
        'short_en': 'Process Sensors',
        'desc_th': 'เครื่องวัดความดัน อัตราการไหล และระดับ',
        'eq_class': 'analog_sensor',
        'icon_name': 'utilities-system-monitor-symbolic',
        'db_ref': 'DB61',
        'spec_summary': '4-20mA 2-Wire Isolated · ±0.075%'
    },
    'High_Valve': {
        'name_en': 'Motorized Butterfly Valves & Penstocks',
        'short_en': 'Actuated Valves',
        'desc_th': 'วาล์วปีกผีเสื้อไฟฟ้า (BVEC1–4)',
        'eq_class': 'motorized_valve',
        'icon_name': 'input-dialpad-symbolic',
        'db_ref': 'DB62',
        'spec_summary': 'DN600 PN16 Wafer · 380V Actuator'
    },
    'High_DPM': {
        'name_en': 'Digital Power Multimeters (Energy Meters)',
        'short_en': 'Power Meters',
        'desc_th': 'มิเตอร์วัดกำลังไฟฟ้าดิจิทัล (DPM1–6)',
        'eq_class': 'power_meter',
        'icon_name': 'battery-symbolic',
        'db_ref': 'DB61 / Modbus',
        'spec_summary': '3P4W 380/220V 50Hz · Class 0.5S'
    },
    'High1_Sound': {
        'name_en': 'Acoustic / Annunciator Alarm Horns',
        'short_en': 'Alarm Horns',
        'desc_th': 'ไซเรนและสัญญาณเสียงแจ้งเตือนสถานีแรงต่ำ',
        'eq_class': 'analog_sensor',
        'icon_name': 'audio-volume-high-symbolic',
        'db_ref': 'DB60',
        'spec_summary': '24V DC Industrial Siren'
    },
    'High1_Totalize_Flow': {
        'name_en': 'Intake Cumulative Flow Totalizers',
        'short_en': 'Flow Totalizers',
        'desc_th': 'มิเตอร์คำนวณปริมาณน้ำดิบสะสมรวม',
        'eq_class': 'analog_sensor',
        'icon_name': 'view-list-symbolic',
        'db_ref': 'DB60 / DB61',
        'spec_summary': 'High-Resolution Pulse Totalizer'
    },
    'Temp_High_Alarm': {
        'name_en': 'Motor Winding & Bearing Thermal Alarms',
        'short_en': 'Thermal Interlocks',
        'desc_th': 'สัญญาณเตือนอุณหภูมิมอเตอร์และแบริ่งสูง',
        'eq_class': 'analog_sensor',
        'icon_name': 'dialog-warning-symbolic',
        'db_ref': 'DB62',
        'spec_summary': 'PT100 RTD Interlock Threshold'
    },
    'Timer_Of_Start_Second_CTM': {
        'name_en': 'Staggered Pump Start Sequencing Timers',
        'short_en': 'Sequencing Timers',
        'desc_th': 'ไทม์เมอร์หน่วงเวลาสตาร์ทปั๊ม CTM สลับลูก',
        'eq_class': 'vsd_pump',
        'icon_name': 'preferences-system-time-symbolic',
        'db_ref': 'DB62',
        'spec_summary': 'Siemens S7 Timer S_ODT'
    },
    'Default': {
        'name_en': 'System Supervisory & Internal Tags',
        'short_en': 'Internal Tags',
        'desc_th': 'แท็กควบคุมระบบและพารามิเตอร์ภายใน',
        'eq_class': 'analog_sensor',
        'icon_name': 'applications-system-symbolic',
        'db_ref': 'Internal',
        'spec_summary': 'SCADA Runtime System Tag'
    }
}

DATA_TYPE_MAPPING = {
    'Floating-point number 32-bit IEEE 754': 'Real',
    'Binary Tag': 'Bool',
    'Signed 32-bit value': 'DInt',
    'Unsigned 32-bit value': 'DWord',
    'Unsigned 16-bit value': 'Word',
    'Signed 16-bit value': 'Int',
    'Real': 'Real',
    'Bool': 'Bool'
}

def format_data_type(raw_type):
    return DATA_TYPE_MAPPING.get(raw_type, raw_type)


# -----------------------------------------------------------------------------
# Cairo Vector Blueprints for Technical Equipment View
# -----------------------------------------------------------------------------
def draw_blueprint_grid(cr, w, h):
    """Draws an industrial dark blueprint canvas with restrained engineering coordinates."""
    # Main dark inset surface (#101D2D)
    cr.set_source_rgb(0.063, 0.114, 0.176)
    cr.rectangle(0, 0, w, h)
    cr.fill()

    # Subtle minor grid lines (#2B3C50 / alpha 0.35)
    cr.set_source_rgba(0.169, 0.235, 0.314, 0.35)
    cr.set_line_width(0.7)
    step = 20
    for x in range(0, int(w), step):
        cr.move_to(x + 0.5, 0)
        cr.line_to(x + 0.5, h)
        cr.stroke()
    for y in range(0, int(h), step):
        cr.move_to(0, y + 0.5)
        cr.line_to(w, y + 0.5)
        cr.stroke()

    # Major grid lines every 100px (#2B3C50 / alpha 0.65)
    cr.set_source_rgba(0.169, 0.235, 0.314, 0.65)
    cr.set_line_width(1.0)
    for x in range(0, int(w), 100):
        cr.move_to(x + 0.5, 0)
        cr.line_to(x + 0.5, h)
        cr.stroke()
    for y in range(0, int(h), 100):
        cr.move_to(0, y + 0.5)
        cr.line_to(w, y + 0.5)
        cr.stroke()

    # Outer border (#2B3C50)
    cr.set_source_rgb(0.169, 0.235, 0.314)
    cr.set_line_width(1.0)
    cr.rectangle(0.5, 0.5, w - 1.0, h - 1.0)
    cr.stroke()


def draw_spec_badge(cr, w, line1, line2, line3):
    """Draws an illustrative blueprint watermark in top-right corner."""
    box_w = 260
    cr.set_source_rgba(0.047, 0.078, 0.125, 0.88)
    cr.rectangle(w - box_w - 12, 10, box_w, 54)
    cr.fill_preserve()
    cr.set_source_rgb(0.169, 0.235, 0.314)
    cr.set_line_width(1.0)
    cr.stroke()

    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(9.0)
    cr.set_source_rgb(0.56, 0.65, 0.74)
    cr.move_to(w - box_w - 2, 24)
    cr.show_text("EQUIPMENT ARCHETYPE · BLUEPRINT")
    cr.set_font_size(9.5)
    cr.set_source_rgb(0.92, 0.95, 0.97)
    cr.move_to(w - box_w - 2, 39)
    cr.show_text(line1)
    cr.set_font_size(9.0)
    cr.set_source_rgb(0.30, 0.57, 0.80)
    cr.move_to(w - box_w - 2, 53)
    cr.show_text(line3)


def draw_vsd_pump_vector(cr, w, h):
    draw_blueprint_grid(cr, w, h)
    cx, cy = w / 2.0 - 40, h / 2.0 - 5

    # Centerline (dashed)
    cr.set_source_rgba(0.51, 0.61, 0.70, 0.4)
    cr.set_dash([8, 4, 2, 4])
    cr.set_line_width(0.8)
    cr.move_to(30, cy + 20)
    cr.line_to(w - 30, cy + 20)
    cr.stroke()
    cr.set_dash([])

    # Baseplate
    cr.set_source_rgb(0.11, 0.18, 0.27)
    cr.rectangle(cx - 190, cy + 55, 380, 16)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.5)
    cr.stroke()

    # Anchor bolts
    for bx in [cx - 170, cx - 70, cx + 70, cx + 170]:
        cr.set_source_rgb(0.69, 0.76, 0.84)
        cr.rectangle(bx - 4, cy + 50, 8, 5)
        cr.stroke()
        cr.move_to(bx, cy + 45)
        cr.line_to(bx, cy + 50)
        cr.stroke()

    # Motor Section (Right side)
    mx = cx + 25
    my = cy - 25
    mw, mh = 140, 75

    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(mx, my, mw, mh)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Cooling Fins
    cr.set_source_rgba(0.31, 0.54, 0.76, 0.6)
    cr.set_line_width(1.0)
    for fx in range(int(mx + 15), int(mx + mw - 15), 10):
        cr.move_to(fx, my)
        cr.line_to(fx, my + mh)
        cr.stroke()

    # Motor Rear Fan Cowl
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.arc(mx + mw, my + mh / 2.0, mh / 2.0, -math.pi / 2, math.pi / 2)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Terminal Box (Top)
    cr.set_source_rgb(0.12, 0.20, 0.30)
    cr.rectangle(mx + 35, my - 22, 50, 22)
    cr.fill_preserve()
    cr.set_source_rgb(0.94, 0.96, 0.99)
    cr.set_line_width(1.4)
    cr.stroke()
    cr.rectangle(mx + 50, my - 28, 20, 6)
    cr.stroke()

    # Motor Feet
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.rectangle(mx + 10, my + mh, 25, 5)
    cr.stroke()
    cr.rectangle(mx + mw - 35, my + mh, 25, 5)
    cr.stroke()

    # Coupling Guard (Center)
    cpx = cx - 25
    cr.set_source_rgb(0.10, 0.17, 0.26)
    cr.rectangle(cpx, cy - 10, 50, 55)
    cr.fill_preserve()
    cr.set_source_rgb(0.51, 0.61, 0.70)
    cr.set_line_width(1.2)
    cr.stroke()
    for gx in range(int(cpx + 10), int(cpx + 45), 8):
        cr.move_to(gx, cy - 5)
        cr.line_to(gx, cy + 40)
        cr.stroke()

    # Pump Volute Casing (Left side)
    px = cx - 110
    py = cy + 15
    pr = 48

    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.arc(px, py, pr, 0, 2 * math.pi)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(2.0)
    cr.stroke()

    # Impeller inner circle (dashed)
    cr.set_dash([4, 3])
    cr.set_source_rgba(0.69, 0.76, 0.84, 0.7)
    cr.arc(px, py, pr * 0.65, 0, 2 * math.pi)
    cr.stroke()
    cr.arc(px, py, 8, 0, 2 * math.pi)
    cr.stroke()
    cr.set_dash([])

    # Suction Flange (Left inlet)
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(px - pr - 35, py - 20, 35, 40)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.6)
    cr.stroke()
    cr.rectangle(px - pr - 43, py - 26, 8, 52)
    cr.stroke()

    # Discharge Flange (Top outlet)
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(px - 18, py - pr - 32, 36, 32)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.6)
    cr.stroke()
    cr.rectangle(px - 24, py - pr - 40, 48, 8)
    cr.stroke()

    # Flow arrows
    cr.set_source_rgb(0.26, 0.73, 0.58) # Green #42B995
    cr.set_line_width(2.0)
    cr.move_to(px - pr - 65, py)
    cr.line_to(px - pr - 47, py)
    cr.stroke()
    cr.move_to(px - pr - 53, py - 5)
    cr.line_to(px - pr - 47, py)
    cr.line_to(px - pr - 53, py + 5)
    cr.stroke()

    cr.move_to(px, py - pr - 44)
    cr.line_to(px, py - pr - 62)
    cr.stroke()
    cr.move_to(px - 5, py - pr - 56)
    cr.line_to(px, py - pr - 62)
    cr.line_to(px + 5, py - pr - 56)
    cr.stroke()

    # Annotations
    cr.set_source_rgb(0.69, 0.76, 0.84)
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(10.0)
    cr.move_to(px - 45, py - pr - 46)
    cr.show_text("DN250 DISCHARGE")
    cr.move_to(px - pr - 120, py + 30)
    cr.show_text("DN300 INTAKE")
    cr.move_to(mx + 15, my - 32)
    cr.show_text("3-PHASE MOTOR / VSD DRIVE")

    draw_spec_badge(cr, w, "EQUIPMENT: HIGH_VSD (PUMPS 13-17)", "DRIVE: 160 kW INVERTER VSD", "RATED HEAD: 48m · PN16 DB62")


def draw_raw_water_pump_vector(cr, w, h):
    draw_blueprint_grid(cr, w, h)
    cx, cy = w / 2.0 - 40, h / 2.0 - 5

    # Center vertical line (dashed)
    cr.set_source_rgba(0.51, 0.61, 0.70, 0.4)
    cr.set_dash([8, 4, 2, 4])
    cr.set_line_width(0.8)
    cr.move_to(cx, 15)
    cr.line_to(cx, h - 15)
    cr.stroke()
    cr.set_dash([])

    # Vertical Column and Base Floor
    cr.set_source_rgb(0.11, 0.18, 0.27)
    cr.rectangle(cx - 110, cy + 20, 220, 14)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.5)
    cr.stroke()

    # Concrete floor pattern
    cr.set_source_rgba(0.51, 0.61, 0.70, 0.3)
    for x in range(int(cx - 100), int(cx + 100), 12):
        cr.move_to(x, cy + 34)
        cr.line_to(x + 8, cy + 42)
        cr.stroke()

    # Vertical Motor Head (Top)
    mot_w, mot_h = 70, 80
    mot_y = cy - 70
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - mot_w / 2, mot_y, mot_w, mot_h)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Vertical cooling fins
    cr.set_source_rgba(0.31, 0.54, 0.76, 0.5)
    cr.set_line_width(1.0)
    for fx in range(int(cx - mot_w / 2 + 8), int(cx + mot_w / 2 - 5), 8):
        cr.move_to(fx, mot_y + 8)
        cr.line_to(fx, mot_y + mot_h - 8)
        cr.stroke()

    # Top Cap & Eye Bolt
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.arc(cx, mot_y, 14, -math.pi, 0)
    cr.stroke()
    cr.arc(cx, mot_y - 12, 6, 0, 2 * math.pi)
    cr.stroke()

    # Discharge Head Elbow (To Right)
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx, cy - 10, 95, 30)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.6)
    cr.stroke()
    cr.rectangle(cx + 95, cy - 15, 8, 40)
    cr.stroke()

    # Submerged Column Tube (Downwards)
    col_w = 48
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - col_w / 2, cy + 34, col_w, 60)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.6)
    cr.stroke()

    # Pump Bowl and Suction Bellmouth
    cr.move_to(cx - col_w / 2, cy + 94)
    cr.line_to(cx - 38, cy + 104)
    cr.line_to(cx + 38, cy + 104)
    cr.line_to(cx + col_w / 2, cy + 94)
    cr.close_path()
    cr.fill_preserve()
    cr.stroke()

    # River Water Line
    cr.set_source_rgba(0.26, 0.73, 0.58, 0.8)
    cr.set_dash([6, 3])
    cr.move_to(cx - 150, cy + 70)
    cr.line_to(cx + 150, cy + 70)
    cr.stroke()
    cr.set_dash([])

    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(9.5)
    cr.move_to(cx - 150, cy + 65)
    cr.show_text("PING RIVER LOW DATUM")

    # Flow arrows
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.set_line_width(2.0)
    cr.move_to(cx, cy + 115)
    cr.line_to(cx, cy + 106)
    cr.stroke()
    cr.move_to(cx + 107, cy + 5)
    cr.line_to(cx + 128, cy + 5)
    cr.stroke()
    cr.move_to(cx + 122, cy)
    cr.line_to(cx + 128, cy + 5)
    cr.line_to(cx + 122, cy + 10)
    cr.stroke()

    draw_spec_badge(cr, w, "EQUIPMENT: HIGH1_PT1PT (RAW PUMPS)", "FLOW: 1,800 m³/h · MOTOR 110kW", "INTAKE: PING RIVER / DB60")


def draw_analog_sensor_vector(cr, w, h):
    draw_blueprint_grid(cr, w, h)
    cx, cy = w / 2.0 - 40, h / 2.0 + 10

    # Process Pipe Section (Horizontal)
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - 160, cy + 20, 320, 45)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Pipe flanges
    cr.rectangle(cx - 168, cy + 14, 8, 57)
    cr.stroke()
    cr.rectangle(cx + 160, cy + 14, 8, 57)
    cr.stroke()

    # Flow direction inside pipe
    cr.set_source_rgba(0.26, 0.73, 0.58, 0.8)
    cr.set_line_width(2.0)
    cr.move_to(cx - 110, cy + 42)
    cr.line_to(cx - 70, cy + 42)
    cr.stroke()
    cr.move_to(cx - 78, cy + 37)
    cr.line_to(cx - 70, cy + 42)
    cr.line_to(cx - 78, cy + 47)
    cr.stroke()

    # Sensor tapping boss & neck
    cr.set_source_rgb(0.12, 0.20, 0.30)
    cr.rectangle(cx - 12, cy - 20, 24, 40)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.5)
    cr.stroke()

    # 3-Valve Manifold block
    cr.rectangle(cx - 22, cy - 36, 44, 16)
    cr.fill_preserve()
    cr.stroke()

    # Transmitter Housing (Round body)
    tr_r = 38
    tr_y = cy - 82
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.arc(cx, tr_y, tr_r, 0, 2 * math.pi)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(2.0)
    cr.stroke()

    # Digital LCD Display Window
    cr.set_source_rgb(0.04, 0.08, 0.14)
    cr.rectangle(cx - 24, tr_y - 15, 48, 30)
    cr.fill_preserve()
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.set_line_width(1.2)
    cr.stroke()

    # Display Readout Text
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(10.0)
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.move_to(cx - 18, tr_y + 2)
    cr.show_text("2.48")
    cr.set_font_size(7.0)
    cr.move_to(cx - 16, tr_y + 11)
    cr.show_text("bar / PV")

    # Cable conduit gland (Right)
    cr.set_source_rgb(0.51, 0.61, 0.70)
    cr.rectangle(cx + tr_r, tr_y - 8, 14, 16)
    cr.stroke()
    cr.set_line_width(1.5)
    cr.move_to(cx + tr_r + 14, tr_y)
    cr.curve_to(cx + tr_r + 35, tr_y - 10, cx + tr_r + 45, tr_y + 25, cx + tr_r + 65, tr_y + 20)
    cr.stroke()

    cr.set_source_rgb(0.69, 0.76, 0.84)
    cr.set_font_size(9.0)
    cr.move_to(cx + tr_r + 70, tr_y + 23)
    cr.show_text("4-20mA LOOP (PLC AI DB61)")

    draw_spec_badge(cr, w, "INSTRUMENT: HIGH_ANALOG (PT/FT/LT)", "LOOP: 4-20mA 2-WIRE ISOLATED", "ACCURACY: ±0.075% FS · DB61")


def draw_motorized_valve_vector(cr, w, h):
    draw_blueprint_grid(cr, w, h)
    cx, cy = w / 2.0 - 40, h - 35

    # Pipe Line (Horizontal)
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - 160, cy - 20, 320, 40)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Flanges Left & Right
    cr.rectangle(cx - 168, cy - 26, 8, 52)
    cr.stroke()
    cr.rectangle(cx + 160, cy - 26, 8, 52)
    cr.stroke()

    # Valve Waist Flanges
    cr.rectangle(cx - 25, cy - 26, 8, 52)
    cr.stroke()
    cr.rectangle(cx + 17, cy - 26, 8, 52)
    cr.stroke()

    # Butterfly Disc Outline in center
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.set_line_width(2.0)
    cr.move_to(cx - 10, cy - 18)
    cr.line_to(cx + 10, cy + 18)
    cr.stroke()
    cr.arc(cx, cy, 5, 0, 2 * math.pi)
    cr.fill()

    # Valve Stem (Vertical)
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.rectangle(cx - 6, cy - 42, 12, 24)
    cr.fill_preserve()
    cr.stroke()

    # Electric Actuator Gearbox
    act_w, act_h = 68, 44
    act_y = cy - 86
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - act_w / 2, act_y, act_w, act_h)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(1.8)
    cr.stroke()

    # Manual Declutch Handwheel
    cr.set_source_rgb(0.51, 0.61, 0.70)
    cr.arc(cx + act_w / 2 + 15, act_y + 12, 14, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to(cx + act_w / 2, act_y + 12)
    cr.line_to(cx + act_w / 2 + 15, act_y + 12)
    cr.stroke()

    # Position Indicator Dial
    cr.set_source_rgb(0.04, 0.08, 0.14)
    cr.arc(cx - 8, act_y + 20, 11, 0, 2 * math.pi)
    cr.fill_preserve()
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.stroke()
    cr.move_to(cx - 8, act_y + 20)
    cr.line_to(cx - 2, act_y + 14)
    cr.stroke()

    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(8.5)
    cr.set_source_rgb(0.69, 0.76, 0.84)
    cr.move_to(cx - 80, act_y + 20)
    cr.show_text("POS: OPEN/CLOSE")
    cr.move_to(cx - 80, act_y + 32)
    cr.show_text("TORQUE SWITCH: OK")

    draw_spec_badge(cr, w, "EQUIPMENT: HIGH_VALVE (BVEC1-4)", "ACTUATOR: 380V 3-PHASE REVERSIBLE", "BODY: DN600 PN16 WAFER / DB62")


def draw_power_meter_vector(cr, w, h):
    draw_blueprint_grid(cr, w, h)
    cx, cy = w / 2.0 - 40, h / 2.0

    pw, ph = 160, 160
    cr.set_source_rgb(0.08, 0.14, 0.22)
    cr.rectangle(cx - pw / 2, cy - ph / 2, pw, ph)
    cr.fill_preserve()
    cr.set_source_rgb(0.31, 0.54, 0.76)
    cr.set_line_width(2.0)
    cr.stroke()

    cr.rectangle(cx - pw / 2 + 8, cy - ph / 2 + 8, pw - 16, ph - 16)
    cr.stroke()

    dw, dh = 124, 76
    cr.set_source_rgb(0.03, 0.06, 0.10)
    cr.rectangle(cx - dw / 2, cy - ph / 2 + 18, dw, dh)
    cr.fill_preserve()
    cr.set_source_rgb(0.16, 0.25, 0.35)
    cr.stroke()

    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_source_rgb(0.26, 0.73, 0.58)
    cr.set_font_size(10.0)
    cr.move_to(cx - dw / 2 + 8, cy - ph / 2 + 36)
    cr.show_text("U: 382.4 V")
    cr.move_to(cx - dw / 2 + 8, cy - ph / 2 + 52)
    cr.show_text("I: 245.1 A")
    cr.move_to(cx - dw / 2 + 8, cy - ph / 2 + 68)
    cr.show_text("P: 158.2 kW")
    cr.move_to(cx - dw / 2 + 8, cy - ph / 2 + 84)
    cr.set_source_rgb(0.51, 0.61, 0.70)
    cr.show_text("PF: 0.94   f: 50.0 Hz")

    btn_y = cy + ph / 2 - 28
    for i, bx in enumerate([cx - 48, cx - 16, cx + 16, cx + 48]):
        cr.set_source_rgb(0.12, 0.20, 0.30)
        cr.rectangle(bx - 10, btn_y, 20, 12)
        cr.fill_preserve()
        cr.set_source_rgb(0.31, 0.54, 0.76)
        cr.stroke()
        cr.set_font_size(7.0)
        cr.set_source_rgb(0.69, 0.76, 0.84)
        lbl = ["V/A", "P/Q", "E", "SET"][i]
        cr.move_to(bx - 6, btn_y + 9)
        cr.show_text(lbl)

    cr.set_source_rgb(0.51, 0.61, 0.70)
    cr.rectangle(cx - pw / 2 - 45, cy - 20, 35, 40)
    cr.stroke()
    cr.set_font_size(8.0)
    cr.move_to(cx - pw / 2 - 40, cy + 3)
    cr.show_text("RS-485")

    draw_spec_badge(cr, w, "EQUIPMENT: HIGH_DPM (POWER METERS)", "SYSTEM: 3P4W 380/220V 50Hz", "CLASS: 0.5S · MODBUS RTU / DB61")


def render_equipment_blueprint(cr, w, h, eq_class):
    """Router for drawing vector illustrations based on equipment class."""
    if eq_class == 'vsd_pump':
        draw_vsd_pump_vector(cr, w, h)
    elif eq_class == 'raw_water_pump':
        draw_raw_water_pump_vector(cr, w, h)
    elif eq_class == 'analog_sensor':
        draw_analog_sensor_vector(cr, w, h)
    elif eq_class == 'motorized_valve':
        draw_motorized_valve_vector(cr, w, h)
    elif eq_class == 'power_meter':
        draw_power_meter_vector(cr, w, h)
    else:
        draw_vsd_pump_vector(cr, w, h)


# -----------------------------------------------------------------------------
# F1 Master-Detail Station Explorer Component
# -----------------------------------------------------------------------------
class F1StationExplorerView:
    def __init__(self, owner):
        self.owner = owner
        self.groups_data = {}        # {grp_key: [tags...]}
        self.all_tags = []           # all catalog tags
        self.ordered_group_keys = [] # list of group keys
        self.selected_group_key = '__ALL__'
        self.selected_tag = None
        self.inspector_mode = 'list' # 'list' or 'properties'
        self.search_query = ''

        # Root container
        self.root_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.root_widget.set_margin_start(12)
        self.root_widget.set_margin_end(12)
        self.root_widget.set_margin_top(6)
        self.root_widget.set_margin_bottom(6)
        self.root_widget.set_hexpand(True)
        self.root_widget.set_vexpand(True)

        self.build_ui()

    def build_ui(self):
        # 1. Section B: F1 Page Heading Bar
        head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        head_box.add_css_class('f1-heading-bar')
        self.root_widget.append(head_box)

        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_vbox.set_hexpand(True)
        head_box.append(title_vbox)

        page_title = Gtk.Label(label="ภาพรวมสถานีสูบน้ำ")
        page_title.add_css_class('f1-page-title')
        page_title.set_xalign(0.0)
        title_vbox.append(page_title)

        page_subtitle = Gtk.Label(label="Industrial Station Overview · Station Explorer Master-Detail Workspace")
        page_subtitle.add_css_class('f1-page-subtitle')
        page_subtitle.set_xalign(0.0)
        title_vbox.append(page_subtitle)

        # Rescan quick button
        btn_refresh = Gtk.Button(label="รีเฟรชคลัง Tag")
        btn_refresh.add_css_class('f1-action-btn')
        btn_refresh.add_css_class('f1-btn-refresh')
        btn_refresh.connect('clicked', lambda _: self.owner.trigger_rescan())
        head_box.append(btn_refresh)

        # 2. Section C: 4 KPI Summary Metrics Cards
        kpi_grid = Gtk.Grid(column_spacing=10, row_spacing=0)
        kpi_grid.set_hexpand(True)
        self.root_widget.append(kpi_grid)

        self.kpi_widgets = {}
        kpi_defs = [
            ('registered_tags', 'Registered Tags', 'คลัง Tag ในระบบ', '—', 'Verified Catalog', 'f1-badge-verified'),
            ('tag_groups', 'Tag Groups', 'กลุ่มอุปกรณ์ทั้งหมด', '—', 'Active Schema', 'f1-badge-accent'),
            ('opc_session', 'OPC UA Session', 'สถานะการเชื่อมต่อสด', 'Standby', 'Not Observed', 'f1-badge-neutral'),
            ('live_quality', 'Live Signals / Quality', 'คุณภาพสัญญาณปัจจุบัน', '—', 'Zero Mock', 'f1-badge-neutral')
        ]

        for col, (key, title_en, desc_th, val_init, badge_txt, badge_cls) in enumerate(kpi_defs):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.add_css_class('f1-kpi-card')
            card.set_hexpand(True)

            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            card.append(top_row)

            lbl_t = Gtk.Label(label=title_en)
            lbl_t.add_css_class('f1-kpi-title')
            lbl_t.set_hexpand(True)
            lbl_t.set_xalign(0.0)
            top_row.append(lbl_t)

            lbl_badge = Gtk.Label(label=badge_txt)
            lbl_badge.add_css_class(badge_cls)
            top_row.append(lbl_badge)

            lbl_val = Gtk.Label(label=val_init)
            lbl_val.add_css_class('f1-kpi-value')
            lbl_val.set_xalign(0.0)
            card.append(lbl_val)

            lbl_desc = Gtk.Label(label=desc_th)
            lbl_desc.add_css_class('f1-kpi-desc')
            lbl_desc.set_xalign(0.0)
            card.append(lbl_desc)

            kpi_grid.attach(card, col, 0, 1, 1)
            self.kpi_widgets[key] = {
                'value': lbl_val,
                'badge': lbl_badge,
                'desc': lbl_desc
            }

        # 3. Master-Detail Workstation Paned Layout (Section D + E + F + G)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_hexpand(True)
        self.paned.set_vexpand(True)
        self.paned.set_position(340) # ~25% width for left equipment explorer
        self.root_widget.append(self.paned)

        # ---------------------------------------------------------------------
        # LEFT PANE (Section D: Equipment Explorer ~25%)
        # ---------------------------------------------------------------------
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left_box.add_css_class('f1-surface-panel')
        left_box.set_size_request(300, -1)
        self.paned.set_start_child(left_box)

        # Left Header
        left_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left_hdr.add_css_class('f1-panel-header')
        left_hdr.set_margin_start(6)
        left_hdr.set_margin_end(6)
        left_hdr.set_margin_top(4)
        left_hdr.set_margin_bottom(2)
        left_box.append(left_hdr)

        lbl_explorer = Gtk.Label(label="กลุ่มอุปกรณ์ (Equipment Explorer)")
        lbl_explorer.add_css_class('f1-panel-title')
        lbl_explorer.set_hexpand(True)
        lbl_explorer.set_xalign(0.0)
        lbl_explorer.set_ellipsize(Pango.EllipsizeMode.END)
        left_hdr.append(lbl_explorer)

        self.lbl_group_count_pill = Gtk.Label(label="10 กลุ่ม")
        self.lbl_group_count_pill.add_css_class('f1-badge-accent')
        left_hdr.append(self.lbl_group_count_pill)

        # Left Scrolled Group List
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        left_scroll.set_hexpand(True)
        left_scroll.set_vexpand(True)
        left_box.append(left_scroll)

        self.group_listbox = Gtk.ListBox()
        self.group_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.group_listbox.add_css_class('f1-group-list')
        self.group_listbox.connect('row-selected', self.on_group_row_selected)
        left_scroll.set_child(self.group_listbox)

        # ---------------------------------------------------------------------
        # RIGHT PANE (Upper Group Header + Lower Signal Table & Inspector)
        # ---------------------------------------------------------------------
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.set_hexpand(True)
        right_box.set_vexpand(True)
        self.paned.set_end_child(right_box)

        # Upper Card: Group Summary & Scope Information
        upper_panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        upper_panel.add_css_class('f1-surface-panel')
        upper_panel.add_css_class('f1-group-header-card')
        upper_panel.set_margin_start(2)
        upper_panel.set_margin_end(2)
        right_box.append(upper_panel)

        self.lbl_current_group_code = Gtk.Label(label="ทั้งหมด (All Groups)")
        self.lbl_current_group_code.add_css_class('f1-group-code-pill')
        upper_panel.append(self.lbl_current_group_code)

        title_v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_v.set_hexpand(True)
        upper_panel.append(title_v)

        self.lbl_group_name_en = Gtk.Label(label="All Equipment Groups & Signals")
        self.lbl_group_name_en.add_css_class('f1-group-title-en')
        self.lbl_group_name_en.set_xalign(0.0)
        title_v.append(self.lbl_group_name_en)

        self.lbl_group_desc_th = Gtk.Label(label="รวมสัญญาณทั้งหมดทุกกลุ่มอุปกรณ์ในระบบ SCADA")
        self.lbl_group_desc_th.add_css_class('f1-group-desc-th')
        self.lbl_group_desc_th.set_xalign(0.0)
        title_v.append(self.lbl_group_desc_th)

        # Right badges (Tag count & verification status)
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        upper_panel.append(status_box)

        self.lbl_group_tag_count_pill = Gtk.Label(label="0 Tags")
        self.lbl_group_tag_count_pill.add_css_class('f1-badge-accent')
        status_box.append(self.lbl_group_tag_count_pill)

        self.lbl_observation_status_pill = Gtk.Label(label="Catalog Verified")
        self.lbl_observation_status_pill.add_css_class('f1-badge-verified')
        status_box.append(self.lbl_observation_status_pill)

        # ---------------------------------------------------------------------
        # Lower Card: Section G — Signal & Tag Inspector
        # ---------------------------------------------------------------------
        lower_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lower_panel.add_css_class('f1-surface-panel')
        lower_panel.set_vexpand(True)
        lower_panel.set_margin_start(2)
        lower_panel.set_margin_end(2)
        right_box.append(lower_panel)

        # Inspector Toolbar
        insp_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        insp_toolbar.add_css_class('f1-panel-header')
        insp_toolbar.set_margin_start(6)
        insp_toolbar.set_margin_end(6)
        insp_toolbar.set_margin_top(2)
        lower_panel.append(insp_toolbar)

        # Mode Switcher Tabs
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        mode_box.add_css_class('f1-mode-switcher')
        insp_toolbar.append(mode_box)

        self.btn_mode_list = Gtk.ToggleButton(label="ตารางสัญญาณ (Signal List)")
        self.btn_mode_list.add_css_class('f1-mode-btn')
        self.btn_mode_list.set_active(True)
        self.btn_mode_list.connect('toggled', self.on_mode_list_toggled)
        mode_box.append(self.btn_mode_list)

        self.btn_mode_props = Gtk.ToggleButton(label="คุณสมบัติ Tag (Properties)")
        self.btn_mode_props.add_css_class('f1-mode-btn')
        self.btn_mode_props.set_group(self.btn_mode_list)
        self.btn_mode_props.connect('toggled', self.on_mode_props_toggled)
        mode_box.append(self.btn_mode_props)

        # Tag Search Entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.add_css_class('f1-search-entry')
        self.search_entry.set_placeholder_text("ค้นหา Tag Name, Addr, หรือคำอธิบาย...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect('search-changed', self.on_search_changed)
        insp_toolbar.append(self.search_entry)

        self.lbl_tag_table_count = Gtk.Label(label="แสดง 0 / 0 Tags")
        self.lbl_tag_table_count.add_css_class('f1-caption-mono')
        insp_toolbar.append(self.lbl_tag_table_count)

        # Inspector Stack (List vs Properties)
        self.inspector_stack = Gtk.Stack()
        self.inspector_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.inspector_stack.set_vexpand(True)
        self.inspector_stack.set_hexpand(True)
        lower_panel.append(self.inspector_stack)

        # --- Sub-page 1: Signal List Table ---
        table_scroll = Gtk.ScrolledWindow()
        table_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        table_scroll.set_vexpand(True)
        table_scroll.set_hexpand(True)

        self.tags_grid = Gtk.Grid(column_spacing=0, row_spacing=0)
        self.tags_grid.add_css_class('f1-data-table')
        self.tags_grid.set_hexpand(True)
        table_scroll.set_child(self.tags_grid)
        self.inspector_stack.add_named(table_scroll, 'list')

        # --- Sub-page 2: Properties Sheet ---
        props_scroll = Gtk.ScrolledWindow()
        props_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        props_scroll.set_vexpand(True)
        props_scroll.set_hexpand(True)

        self.props_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.props_container.add_css_class('f1-props-box')
        props_scroll.set_child(self.props_container)
        self.inspector_stack.add_named(props_scroll, 'properties')

        self.render_empty_properties()

    def create_metric_item(self, parent, label_txt, val_txt):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        b.add_css_class('f1-metric-tile')
        b.set_hexpand(True)
        l = Gtk.Label(label=label_txt)
        l.add_css_class('f1-metric-title')
        l.set_xalign(0.0)
        b.append(l)
        v = Gtk.Label(label=val_txt)
        v.add_css_class('f1-metric-val')
        v.set_xalign(0.0)
        b.append(v)
        parent.append(b)
        return v

    # -------------------------------------------------------------------------
    # Master Group Selection & Update
    # -------------------------------------------------------------------------
    def update_catalog_data(self, tags):
        """Processes raw scanned tags and dynamically organizes groups."""
        self.all_tags = list(tags)
        self.groups_data = {}
        for t in tags:
            g = t.get('group', 'Default').strip() or 'Default'
            if g not in self.groups_data:
                self.groups_data[g] = []
            self.groups_data[g].append(t)

        # Sort group keys: Known defined groups first by importance, then remaining groups
        known_order = [
            'High_VSD', 'High1_PT1PT', 'High_Analog', 'High_Valve', 'High_DPM',
            'High1_Sound', 'High1_Totalize_Flow', 'Temp_High_Alarm',
            'Timer_Of_Start_Second_CTM', 'Default'
        ]
        self.ordered_group_keys = [k for k in known_order if k in self.groups_data]
        for k in sorted(self.groups_data.keys()):
            if k not in self.ordered_group_keys:
                self.ordered_group_keys.append(k)

        # Update KPI Summary Cards (Section C)
        total_tags = len(tags)
        total_groups = len(self.groups_data)
        self.kpi_widgets['registered_tags']['value'].set_text(f"{total_tags:,} Tags")
        self.kpi_widgets['tag_groups']['value'].set_text(f"{total_groups} Groups")
        self.lbl_group_count_pill.set_text(f"{total_groups} กลุ่ม")

        # Repopulate Equipment Explorer (Section D)
        while self.group_listbox.get_first_child():
            self.group_listbox.remove(self.group_listbox.get_first_child())

        if not tags:
            self.render_empty_state()
            return

        # 1. First Row: All Groups (Virtual Filter)
        all_row = Gtk.ListBoxRow()
        all_row.grp_key = '__ALL__'
        all_row.add_css_class('f1-group-row')

        all_row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        all_row_box.add_css_class('f1-group-row-box')
        all_row.set_child(all_row_box)

        all_top_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        all_top_line.set_hexpand(True)
        all_row_box.append(all_top_line)

        all_icon = Gtk.Image.new_from_icon_name('view-grid-symbolic')
        all_icon.set_icon_size(Gtk.IconSize.NORMAL)
        all_icon.add_css_class('f1-group-icon')
        all_top_line.append(all_icon)

        all_code_lbl = Gtk.Label(label="ทั้งหมด (All Groups)")
        all_code_lbl.add_css_class('f1-group-row-code')
        all_code_lbl.set_hexpand(True)
        all_code_lbl.set_xalign(0.0)
        all_code_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        all_code_lbl.set_tooltip_text("ทั้งหมด (All Groups) — Virtual Filter")
        all_top_line.append(all_code_lbl)

        all_count_pill = Gtk.Label(label=f"{total_tags} tags")
        all_count_pill.add_css_class('f1-count-pill')
        all_top_line.append(all_count_pill)

        all_desc_lbl = Gtk.Label(label="รวมสัญญาณทั้งหมดในสถานีสูบน้ำ · All station tags")
        all_desc_lbl.add_css_class('f1-group-row-desc')
        all_desc_lbl.set_xalign(0.0)
        all_desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        all_desc_lbl.set_tooltip_text("รวมสัญญาณทั้งหมดในสถานีสูบน้ำ · All station tags")
        all_row_box.append(all_desc_lbl)

        self.group_listbox.append(all_row)

        # 2. Subsequent Rows: 10 Actual Equipment Groups
        rows_by_key = {'__ALL__': all_row}
        for grp_key in self.ordered_group_keys:
            def_item = EQUIPMENT_GROUPS_DEF.get(grp_key, {
                'name_en': grp_key,
                'desc_th': f'กลุ่มอุปกรณ์ {grp_key}',
                'eq_class': 'analog_sensor',
                'icon_name': 'applications-system-symbolic',
                'db_ref': 'Unassigned',
                'spec_summary': 'Standard SCADA Component'
            })
            tag_count = len(self.groups_data[grp_key])

            row = Gtk.ListBoxRow()
            row.grp_key = grp_key
            row.add_css_class('f1-group-row')

            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row_box.add_css_class('f1-group-row-box')
            row.set_child(row_box)

            # Line 1: Icon + Group Key + Tag Count Pill
            top_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            top_line.set_hexpand(True)
            row_box.append(top_line)

            icon = Gtk.Image.new_from_icon_name(def_item.get('icon_name', 'applications-system-symbolic'))
            icon.set_icon_size(Gtk.IconSize.NORMAL)
            icon.add_css_class('f1-group-icon')
            top_line.append(icon)

            code_lbl = Gtk.Label(label=grp_key)
            code_lbl.add_css_class('f1-group-row-code')
            code_lbl.set_hexpand(True)
            code_lbl.set_xalign(0.0)
            code_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            code_lbl.set_tooltip_text(grp_key)
            top_line.append(code_lbl)

            count_pill = Gtk.Label(label=f"{tag_count} tags")
            count_pill.add_css_class('f1-count-pill')
            top_line.append(count_pill)

            # Line 2: Concise Description (Short EN · Thai description)
            short_en = def_item.get('short_en', def_item.get('name_en', grp_key))
            desc_text = f"{short_en} · {def_item.get('desc_th', '')}"
            desc_lbl = Gtk.Label(label=desc_text)
            desc_lbl.add_css_class('f1-group-row-desc')
            desc_lbl.set_xalign(0.0)
            desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            desc_lbl.set_tooltip_text(desc_text)
            row_box.append(desc_lbl)

            self.group_listbox.append(row)
            rows_by_key[grp_key] = row

        # Select target row: preserve previous selection if exists, else default to All Groups
        target_key = getattr(self, 'selected_group_key', '__ALL__')
        selected_row = rows_by_key.get(target_key, all_row)
        self.group_listbox.select_row(selected_row)
        self.on_group_row_selected(self.group_listbox, selected_row)

    def on_group_row_selected(self, listbox, row):
        if row is None:
            return
        self.selected_group_key = getattr(row, 'grp_key', '__ALL__')
        self.selected_tag = None
        if hasattr(self, 'search_entry') and self.search_entry.get_text():
            self.search_entry.set_text('')
        self.search_query = ''
        self.update_right_panel()

    def update_right_panel(self):
        """Updates Group Info Header & Signal Inspector for the selected group."""
        grp_key = self.selected_group_key
        is_all = (grp_key == '__ALL__')

        if is_all:
            def_item = EQUIPMENT_GROUPS_DEF.get('__ALL__', {
                'name_en': 'All Equipment Groups & Signals',
                'desc_th': 'รวมสัญญาณทั้งหมดทุกกลุ่มอุปกรณ์ในระบบ SCADA'
            })
            tags_in_scope = getattr(self, 'all_tags', [])
            tag_count = len(tags_in_scope)
            self.lbl_current_group_code.set_text("ทั้งหมด (All Groups)")
            self.lbl_group_name_en.set_text(def_item['name_en'])
            self.lbl_group_desc_th.set_text(def_item['desc_th'])
            self.lbl_group_tag_count_pill.set_text(f"{tag_count} Tags")
            self.set_observation_status("Catalog Verified", is_verified=True)
        else:
            def_item = EQUIPMENT_GROUPS_DEF.get(grp_key, {
                'name_en': grp_key,
                'desc_th': f'กลุ่มอุปกรณ์ {grp_key}'
            })
            tags_in_scope = self.groups_data.get(grp_key, [])
            tag_count = len(tags_in_scope)
            self.lbl_current_group_code.set_text(grp_key)
            self.lbl_group_name_en.set_text(def_item['name_en'])
            self.lbl_group_desc_th.set_text(def_item['desc_th'])
            self.lbl_group_tag_count_pill.set_text(f"{tag_count} Tags")
            self.set_observation_status("Catalog Verified", is_verified=True)

        # Render Tag List in Inspector
        self.render_tags_table()

    def set_observation_status(self, text, is_verified=True):
        self.lbl_observation_status_pill.set_text(text)
        self.lbl_observation_status_pill.remove_css_class('f1-badge-neutral')
        self.lbl_observation_status_pill.remove_css_class('f1-badge-verified')
        if is_verified:
            self.lbl_observation_status_pill.add_css_class('f1-badge-verified')
        else:
            self.lbl_observation_status_pill.add_css_class('f1-badge-neutral')

    # -------------------------------------------------------------------------
    # Signal List Table (Section G - Mode 1)
    # -------------------------------------------------------------------------
    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        if self.search_query:
            self.search_entry.add_css_class('f1-search-active')
        else:
            self.search_entry.remove_css_class('f1-search-active')
        self.render_tags_table()

    def on_mode_list_toggled(self, btn):
        if btn.get_active():
            self.inspector_mode = 'list'
            self.inspector_stack.set_visible_child_name('list')

    def on_mode_props_toggled(self, btn):
        if btn.get_active():
            self.inspector_mode = 'properties'
            self.inspector_stack.set_visible_child_name('properties')
            if self.selected_tag:
                self.render_tag_properties(self.selected_tag)
            else:
                self.render_empty_properties()

    def render_tags_table(self):
        """Builds clean, dense, comfortable technical rows for tags in scope."""
        while self.tags_grid.get_first_child():
            self.tags_grid.remove(self.tags_grid.get_first_child())

        self.row_cells_by_tag = {}

        is_all = (self.selected_group_key == '__ALL__')
        if is_all:
            tags_in_scope = getattr(self, 'all_tags', [])
            headers = [
                ("TAG NAME / IDENTIFIER", 260, True),
                ("GROUP", 130, False),
                ("DATA TYPE", 85, False),
                ("PLC ADDRESS / DB", 125, False),
                ("LIVE VALUE", 85, False),
                ("QUALITY", 105, False),
                ("LAST OBSERVED", 95, False)
            ]
        else:
            tags_in_scope = self.groups_data.get(self.selected_group_key, [])
            headers = [
                ("TAG NAME / IDENTIFIER", 320, True),
                ("DATA TYPE", 95, False),
                ("PLC ADDRESS / DB", 145, False),
                ("LIVE VALUE", 95, False),
                ("QUALITY", 120, False),
                ("LAST OBSERVED", 110, False)
            ]

        for col, (name, min_w, hexpand) in enumerate(headers):
            th = Gtk.Label(label=name)
            th.add_css_class('f1-table-th')
            th.set_xalign(0.0)
            th.set_size_request(min_w, -1)
            if hexpand:
                th.set_hexpand(True)
            self.tags_grid.attach(th, col, 0, 1, 1)

        query = self.search_query
        filtered_tags = []
        for t in tags_in_scope:
            if not query:
                filtered_tags.append(t)
            else:
                search_blob = f"{t.get('name','')} {t.get('group','')} {t.get('addr','')} {t.get('comment','')} {t.get('type','')}".lower()
                if query in search_blob:
                    filtered_tags.append(t)

        self.lbl_tag_table_count.set_text(f"แสดง {len(filtered_tags)} / {len(tags_in_scope)} Tags")

        if not filtered_tags:
            empty_lbl = Gtk.Label(label="ไม่พบสัญญาณที่ตรงกับคำค้นหา หรือกลุ่มนี้ยังไม่มีข้อมูล Tag")
            empty_lbl.add_css_class('f1-table-empty')
            empty_lbl.set_xalign(0.0)
            self.tags_grid.attach(empty_lbl, 0, 1, len(headers), 1)
            return

        # Render rows
        for row_idx, t in enumerate(filtered_tags, start=1):
            is_selected = (self.selected_tag and self.selected_tag.get('name') == t['name'])
            row_css = 'f1-table-row-selected' if is_selected else 'f1-table-row'
            row_cells = []

            col_idx = 0

            # 1. Tag Name
            name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name_box.add_css_class(row_css)
            name_box.add_css_class('f1-table-cell-name')
            name_box.set_hexpand(True)
            name_box.set_size_request(headers[0][1], -1)

            name_btn = Gtk.Button()
            btn_lbl = Gtk.Label(label=t['name'])
            btn_lbl.set_xalign(0.0)
            btn_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            name_btn.set_child(btn_lbl)
            name_btn.set_halign(Gtk.Align.START)
            name_btn.add_css_class('f1-tag-link-btn')
            name_btn.set_tooltip_text(f"คลิกดูคุณสมบัติ: {t['name']}")
            name_btn.connect('clicked', lambda _, tag_obj=t: self.inspect_tag(tag_obj))
            name_box.append(name_btn)

            comment_txt = t.get('comment', '').strip()
            if comment_txt:
                c_lbl = Gtk.Label(label=comment_txt)
                c_lbl.add_css_class('f1-caption-subtle')
                c_lbl.set_xalign(0.0)
                c_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                c_lbl.set_tooltip_text(comment_txt)
                name_box.append(c_lbl)

            self.tags_grid.attach(name_box, col_idx, row_idx, 1, 1)
            row_cells.append(name_box)
            col_idx += 1

            # (Optional) GROUP Column when is_all
            if is_all:
                grp_lbl = Gtk.Label(label=t.get('group', 'Default'))
                grp_lbl.add_css_class('f1-table-cell-mono')
                grp_lbl.add_css_class(row_css)
                grp_lbl.set_xalign(0.0)
                grp_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                grp_lbl.set_tooltip_text(t.get('group', 'Default'))
                grp_lbl.set_size_request(headers[col_idx][1], -1)
                self.tags_grid.attach(grp_lbl, col_idx, row_idx, 1, 1)
                row_cells.append(grp_lbl)
                col_idx += 1

            # 2. Data Type
            raw_type = t.get('type', 'Real')
            clean_type = format_data_type(raw_type)
            dtype_lbl = Gtk.Label(label=clean_type)
            dtype_lbl.add_css_class('f1-table-cell')
            dtype_lbl.add_css_class(row_css)
            dtype_lbl.set_xalign(0.0)
            dtype_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            dtype_lbl.set_tooltip_text(f"Raw DataType: {raw_type}")
            dtype_lbl.set_size_request(headers[col_idx][1], -1)
            self.tags_grid.attach(dtype_lbl, col_idx, row_idx, 1, 1)
            row_cells.append(dtype_lbl)
            col_idx += 1

            # 3. PLC Address
            addr_lbl = Gtk.Label(label=t.get('addr', 'Internal'))
            addr_lbl.add_css_class('f1-table-cell-mono')
            addr_lbl.add_css_class(row_css)
            addr_lbl.set_xalign(0.0)
            addr_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            addr_lbl.set_tooltip_text(t.get('addr', 'Internal'))
            addr_lbl.set_size_request(headers[col_idx][1], -1)
            self.tags_grid.attach(addr_lbl, col_idx, row_idx, 1, 1)
            row_cells.append(addr_lbl)
            col_idx += 1

            # 4. Live Value
            val_lbl = Gtk.Label(label="—")
            val_lbl.add_css_class('f1-table-cell-mono')
            val_lbl.add_css_class(row_css)
            val_lbl.set_xalign(0.0)
            val_lbl.set_size_request(headers[col_idx][1], -1)
            self.tags_grid.attach(val_lbl, col_idx, row_idx, 1, 1)
            row_cells.append(val_lbl)
            col_idx += 1

            # 5. Quality (V1.3: Neutral subtle monospace, zero noisy badges)
            q_lbl = Gtk.Label(label="Not Observed")
            q_lbl.add_css_class('f1-table-cell-muted')
            q_lbl.add_css_class(row_css)
            q_lbl.set_xalign(0.0)
            q_lbl.set_size_request(headers[col_idx][1], -1)
            self.tags_grid.attach(q_lbl, col_idx, row_idx, 1, 1)
            row_cells.append(q_lbl)
            col_idx += 1

            # 6. Last Observed
            time_lbl = Gtk.Label(label="—")
            time_lbl.add_css_class('f1-table-cell-muted')
            time_lbl.add_css_class(row_css)
            time_lbl.set_xalign(0.0)
            time_lbl.set_size_request(headers[col_idx][1], -1)
            self.tags_grid.attach(time_lbl, col_idx, row_idx, 1, 1)
            row_cells.append(time_lbl)

            self.row_cells_by_tag[t['name']] = row_cells

            # Row interaction: Full-row hover and click gestures
            self.attach_row_events(row_cells, t)

    def attach_row_events(self, cells, tag_obj):
        tag_name = tag_obj['name']

        def on_enter(ctrl, x, y):
            is_sel = (self.selected_tag and self.selected_tag.get('name') == tag_name)
            if not is_sel:
                for c in cells:
                    c.add_css_class('f1-table-row-hover')

        def on_leave(ctrl):
            for c in cells:
                c.remove_css_class('f1-table-row-hover')

        def on_pressed(gesture, n_press, x, y):
            if n_press == 1:
                self.select_tag(tag_obj)
            elif n_press >= 2:
                self.inspect_tag(tag_obj)

        for c in cells:
            motion = Gtk.EventControllerMotion()
            motion.connect('enter', on_enter)
            motion.connect('leave', on_leave)
            c.add_controller(motion)

            click = Gtk.GestureClick()
            click.connect('pressed', on_pressed)
            c.add_controller(click)

    def select_tag(self, tag_obj):
        old_tag_name = self.selected_tag.get('name') if self.selected_tag else None
        new_tag_name = tag_obj.get('name')

        if old_tag_name and old_tag_name in self.row_cells_by_tag:
            for c in self.row_cells_by_tag[old_tag_name]:
                c.remove_css_class('f1-table-row-selected')
                c.add_css_class('f1-table-row')

        self.selected_tag = tag_obj

        if new_tag_name and new_tag_name in self.row_cells_by_tag:
            for c in self.row_cells_by_tag[new_tag_name]:
                c.remove_css_class('f1-table-row')
                c.remove_css_class('f1-table-row-hover')
                c.add_css_class('f1-table-row-selected')

        self.render_tag_properties(tag_obj)

    def inspect_tag(self, tag_obj):
        self.select_tag(tag_obj)
        self.btn_mode_props.set_active(True)
        self.inspector_stack.set_visible_child_name('properties')

    def on_tag_clicked(self, tag_obj):
        self.inspect_tag(tag_obj)

    # -------------------------------------------------------------------------
    # Properties Sheet (Section G - Mode 2)
    # -------------------------------------------------------------------------
    def render_empty_properties(self):
        while self.props_container.get_first_child():
            self.props_container.remove(self.props_container.get_first_child())

        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty_box.set_margin_top(40)
        empty_box.set_halign(Gtk.Align.CENTER)
        self.props_container.append(empty_box)

        lbl = Gtk.Label(label="เลือก Tag จากตาราง Signal List เพื่อตรวจสอบคุณสมบัติทางเทคนิค")
        lbl.add_css_class('f1-page-subtitle')
        empty_box.append(lbl)

        btn = Gtk.Button(label="กลับไปที่ตารางสัญญาณ (Signal List)")
        btn.add_css_class('f1-action-btn')
        btn.connect('clicked', lambda _: self.btn_mode_list.set_active(True))
        empty_box.append(btn)

    def render_tag_properties(self, tag):
        while self.props_container.get_first_child():
            self.props_container.remove(self.props_container.get_first_child())

        # Header bar for selected tag
        head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head_box.add_css_class('f1-panel-header')
        self.props_container.append(head_box)

        t_name = Gtk.Label(label=tag.get('name', 'UNKNOWN_TAG'))
        t_name.add_css_class('f1-group-code-pill')
        head_box.append(t_name)

        t_type = Gtk.Label(label=format_data_type(tag.get('type', 'Real')))
        t_type.add_css_class('f1-badge-accent')
        head_box.append(t_type)

        t_addr = Gtk.Label(label=f"PLC: {tag.get('addr', 'Internal')}")
        t_addr.add_css_class('f1-badge-neutral')
        head_box.append(t_addr)

        btn_back = Gtk.Button(label="กลับสู่ตารางสัญญาณ")
        btn_back.add_css_class('f1-action-btn')
        btn_back.set_hexpand(True)
        btn_back.set_halign(Gtk.Align.END)
        btn_back.connect('clicked', lambda _: self.btn_mode_list.set_active(True))
        head_box.append(btn_back)

        comment_txt = tag.get('comment', '').strip()
        if comment_txt:
            c_lbl = Gtk.Label(label=comment_txt)
            c_lbl.add_css_class('f1-group-desc-th')
            c_lbl.set_xalign(0.0)
            self.props_container.append(c_lbl)

        # Technical Grid (Compact 2-column)
        grid = Gtk.Grid(column_spacing=16, row_spacing=6)
        grid.add_css_class('f1-card-inner')
        self.props_container.append(grid)

        props = [
            ("Group / System:", f"{tag.get('group', 'Default')} ({EQUIPMENT_GROUPS_DEF.get(tag.get('group'), {}).get('name_en', '')})"),
            ("Data Type / Format:", f"{format_data_type(tag.get('type', 'Real'))} ({tag.get('type', 'Real')})"),
            ("Connection:", tag.get('conn', 'High1 (S7-300/400 ISO-on-TCP)')),
            ("S7 PLC Offset:", tag.get('addr', 'Internal / Not Mapped')),
            ("Quality Code:", "0x00000000 · Not Observed (Zero Mock)"),
            ("Live Telemetry:", "— (ยังไม่ได้เชื่อมต่อ Live OPC UA Session)"),
            ("Engineering Note:", "โครงสร้าง Tag ได้รับการยืนยันจาก Export all.txt")
        ]

        for row_idx, (prop_lbl, prop_val) in enumerate(props):
            lbl_k = Gtk.Label(label=prop_lbl)
            lbl_k.add_css_class('f1-metric-title')
            lbl_k.set_xalign(0.0)
            grid.attach(lbl_k, 0, row_idx, 1, 1)

            lbl_v = Gtk.Label(label=prop_val)
            lbl_v.add_css_class('f1-prop-value-mono')
            lbl_v.set_xalign(0.0)
            lbl_v.set_selectable(True)
            grid.attach(lbl_v, 1, row_idx, 1, 1)

    def render_empty_state(self):
        """Displays empty state when no tags are loaded in catalog."""
        self.kpi_widgets['registered_tags']['value'].set_text("0 Tags")
        self.kpi_widgets['tag_groups']['value'].set_text("0 Groups")
        self.lbl_current_group_code.set_text("No Catalog")
        self.lbl_group_name_en.set_text("ยังไม่ได้นำเข้าคลัง Tag WinCC")
        self.lbl_group_desc_th.set_text("กดรีเฟรชคลัง Tag เพื่อโหลด Export all.txt")
        self.lbl_group_tag_count_pill.set_text("0 Tags")
        self.set_observation_status("Not Observed", is_verified=False)
        self.render_tags_table()
