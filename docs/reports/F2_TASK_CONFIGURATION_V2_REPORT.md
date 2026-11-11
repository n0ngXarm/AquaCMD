<!-- Phase 7 public copy: historical private values redacted. Original evidence remains privately preserved. This is not a rerun or acceptance upgrade. -->
# AQUA COMMAND — F2 TASK CONFIGURATION V2 (PHASE 1) REPORT
## Industrial Precision Task Management & Monitoring Rule Editor

**Document ID:** `DOC-AC-F2-V2-PHASE1`
**Date:** 2026-11-01
**Target Environment:** Linux GTK4 (`aqua-command-desktop/desktop/app.py` & `f2_tasks.py`)
**Design Standard:** Industrial Spectrum V2 Design System
**Implementation Phase:** Phase 1 (UI & Interaction Architecture — Gate B Pending)

---

## 1. Executive Summary & Objective

ตามคำสั่งอนุมัติ **GEMINI — AQUA COMMAND F2 TASK CONFIGURATION V2 (Phase 1)** ทีมพัฒนาได้ดำเนินการยกเครื่องหน้าต่าง **F2 Task Configuration Panel** จากรูปแบบดั้งเดิม (Flat Property Form) ให้กลายเป็น **Professional Industrial Task Management & Monitoring Rule Editor** ที่มีโครงสร้างเชิงวิศวกรรม ชัดเจนทั้ง 7 ส่วน (Sections A ถึง G) สอดรับกับปรัชญา **Industrial Spectrum V2** และยังคงรักษาความเข้ากันได้แบบ 100% กับ Runtime ดั้งเดิมของ Aqua Command

### กฎเหล็ก Phase 1 ที่ปฏิบัติตามอย่างเคร่งครัด
1. **Zero Mock Data:** ไม่สร้างหรือปลอมแปลงข้อมูลสังเคราะห์ สถานะทุกจุดแสดงผลจาก Runtime State จริง (เช่น `Standby (Auto-Scan Inactive)` เมื่อระบบสแกนยังไม่เริ่ม, `Not Observed` สำหรับสัญญาณที่ยังไม่มีเซสชัน OPC UA)
2. **Phase 1 Boundary (No Premature Rule Engine Execution):** ใน Phase 1 ส่วนเงื่อนไขทริกเกอร์ (Section C: Trigger Rules) ถูกออกแบบเป็น **Phase 2 Preview (Disabled Controls)** อย่างชัดเจน พร้อมระบุ `ยังไม่รองรับใน Runtime ปัจจุบัน` และไม่มีปุ่มบันทึกที่สร้างความเข้าใจผิดแก่ผู้ปฏิบัติงาน
3. **No Breaking Changes:** ไม่แก้ไข `win_desktop.py` (Windows Companion) หรือ `AQUA Runtime 0.9` ภายนอกขอบเขตที่ได้รับอนุญาต
4. **Preserved Shell & Navigation:** รักษาสถานะ F1 Station Explorer, Top Header, Status Ribbon, และ Bottom Navigation Dock (F1–F8) ครบถ้วน
5. **Strict Local Isolation:** ไม่มีการสั่ง Git Commit หรือ Push จนกว่าจะผ่านการตรวจรับจากผู้ใช้งาน

---

## 2. โครงสร้างหน้าต่าง F2 Task Configuration V2 (Sections A — G)

```
+-------------------------------------------------------------------------------------------------------------------------+
| Top Header & Operations Toolbar: [สแกนทันที 1 ครั้ง] [เริ่ม Auto Scan] [รอบสแกนระบบ: 5s] [สร้าง Task ใหม่] [บันทึก Task]     |
+-------------------------------------------------------+-----------------------------------------------------------------+
| คลัง Tag ที่สแกนพบ (Discovered Tags Library - 457)   | A. การระบุตัวตน Task (Task Identity)                              |
| - ตัวกรองกลุ่ม (ทุกกลุ่ม + 10 กลุ่มจริง)               |    [Selector] [ID Badge: TASK-01] [Configured] [Enabled] [State]|
| - กล่องค้นหา (Search Tag Name / Addr)                 +-----------------------------------------------------------------+
| - ตาราง Tag เช็คบ็อกซ์เลือกรายการ                       | B. การตั้งค่ารอบการเฝ้าระวัง (Monitoring Settings)                |
|   [✓] Tag Name | กลุ่ม | Address | ชนิดข้อมูล          |    [Task Cycle: 5s / 10s / 30s / 60s] [Assigned Tag Count]       |
|                                                       +-----------------------------------------------------------------+
|                                                       | C. เงื่อนไขทริกเกอร์ (Trigger Rules) — [PHASE 2 PREVIEW]         |
|                                                       |    (Disabled: Binary Transitions, Analog Thresholds, Deadband)  |
|                                                       +-----------------------------------------------------------------+
|                                                       | D. การกระทำเมื่อพบเหตุการณ์ (Action Configuration)               |
|                                                       |    [✓] บันทึก Local Archive   [✓] เปิดใช้งาน Task (Enable)       |
|                                                       |    [✓] ส่งแจ้งเตือน Telegram (ลิงก์ไปตั้งค่าที่หน้า F6)          |
|                                                       +-----------------------------------------------------------------+
|                                                       | E. รายการ Tag ที่กำหนดให้กับ Task นี้ (Assigned Tags)           |
|                                                       |    Tag Name | กลุ่ม | ชนิด | สถานะ | [✕ นำออก]                  |
|                                                       +-----------------------------------------------------------------+
|                                                       | F. ตรวจสอบความถูกต้อง (Validation & Feedback)                    |
| [ปุ่ม: เพิ่ม Tag ที่เลือกเข้า Task]                    |    [ข้อความแจ้งสถานะความถูกต้อง] [Pill: Saved / Unsaved]         |
|                                                       +-----------------------------------------------------------------+
|                                                       | G. ข้อมูลสถานะการทำงานจริง (Execution Status)                    |
|                                                       |    [Status Pill] Executions: 0 | Records: 0 | Alerts: 0         |
+-------------------------------------------------------+-----------------------------------------------------------------+
| F1 ภาพรวมสถานี | F2 ตัวจัดการ Task | F3 ผังเครือข่าย | F4 ข้อมูลเครื่อง | F5 คลัง Tag | F6 OPC UA & Telegram | F7 สแกน | F8 ออก |
+-------------------------------------------------------------------------------------------------------------------------+
```

### รายละเอียดการจัดแบ่งแต่ละส่วน (Section Breakdown)
- **Section A: Task Identity**
  - Dropdown สลับ Task ได้ทันที (`[TASK-01] เฝ้าระวังแรงดันปั๊มน้ำ VSD (High_VSD)`)
  - Badge รหัส Task ประจำการ (`TASK-01`)
  - ช่องป้อนชื่อ Task ที่เชื่อมต่อ Live Validation
  - Badges แยก 3 มิติอย่างชัดเจน:
    1. *Configuration Completeness:* `Configured` (สีฟ้า `#3489E8`) เทียบกับ `Incomplete` (สีเหลือง `#EAC54F` เมื่อไม่มี Tag กำหนด)
    2. *User Intent:* `Enabled` (สีเขียว `#27B785`) เทียบกับ `Disabled` (สีเทา `#8998AA`)
    3. *Real Runtime Execution:* `Standby (Auto-Scan Inactive)` (สีเทา) เทียบกับ `Running (Active Monitoring)` (สีเขียวสด) โดยแยกขาดจาก active flag อย่างเด็ดขาด
- **Section B: Monitoring Settings**
  - ตัวเลือกรอบเวลาเฉพาะของแต่ละ Task: `1 วินาที`, `5 วินาที (มาตรฐาน WinCC V8.1)`, `10 วินาที`, `30 วินาที`, `60 วินาที`
  - ทำงานเป็นอิสระจาก Auto-Scan กลางของระบบ พร้อมคำอธิบายทางวิศวกรรม
  - Badge แสดงจำนวน Tag ที่ถูกควบคุมใน Task นี้
- **Section C: Trigger Rules (Phase 2 Preview — Disabled)**
  - กล่องแบบ Collapsible Accordion พร้อม Badge สีส้มอำพัน `PHASE 2 PREVIEW — DISABLED`
  - สรุปแนวทางการตั้งค่าทริกเกอร์ 2 โหมด:
    - *Binary (ดิจิทัล):* ตรวจจับการเปลี่ยนสถานะ 0->1 (OFF->ON), 1->0 (ON->OFF), Both
    - *Analog (แอนะล็อก):* เกณฑ์เปรียบเทียบ High Limit (> Threshold), Low Limit (< Threshold), Out of Range พร้อม Hysteresis Deadband (±0.5%) และยืนยันผล 2 ค่าต่อเนื่อง (Confirmation Samples) เพื่อป้องกัน Alarm Flapping
    - ข้อความระบุชัดเจน: *“ยังไม่รองรับใน Runtime ปัจจุบัน — ไม่มีผลต่อการทำงานจริงใน Phase 1”*
- **Section D: Action Configuration**
  - Checkbox: `บันทึกประวัติลง Local Archive (Data Logging)` (SQLite / CSV)
  - Checkbox: `เปิดใช้งาน Task นี้ (Enable Task)`
  - Checkbox: `ส่งแจ้งเตือน Telegram เมื่อเปลี่ยนสถานะ` พร้อมข้อความแจ้งสิทธิ์และปุ่มลิงก์ตรงไปยังการตั้งค่า Token/Chat ID ในหน้า F6
- **Section E: Assigned Tags (Technical Grid)**
  - ตารางแสดง Tag ที่ผูกกับ Task ประกอบด้วย: `TAG NAME`, `กลุ่ม (GROUP)`, `ชนิดข้อมูล`, `สถานะ`, และปุ่ม `✕ นำออก`
  - จัดการ Empty State อย่างประณีตเมื่อไม่มี Tag กำหนด
- **Section F: Validation & Feedback**
  - ระบบตรวจสอบกฎแบบ Realtime:
    - แจ้งเตือนเมื่อ *“ชื่อ Task ไม่สามารถเว้นว่างได้”* (แสดง Badge สีแดง `Invalid`)
    - แจ้งเตือนเมื่อ *“Task ยังไม่มี Tag ที่กำหนด”* (แสดง Badge สีส้ม `Incomplete`)
    - ยืนยันสถานะความถูกต้องและสถานะการบันทึก (`Saved` / `Unsaved Changes`)
- **Section G: Execution Status**
  - แสดงสถานะรอบการประมวลผลจริง: รันไปแล้วกี่รอบ (`Executions`), บันทึกลงฐานข้อมูลกี่แถว (`Records`), เกิดการแจ้งเตือนกี่ครั้ง (`Alerts`), และข้อผิดพลาดล่าสุด (`Last Error: None`)

---

## 3. สิ่งที่ทำงานได้จริง (Working Features) vs สิ่งที่รอ Phase 2 (Pending)

| รายการระบบ / ฟังก์ชัน | สถานะใน Phase 1 | รายละเอียดพฤติกรรม |
|---|---|---|
| **Discovered Tag Library (Left)** | **ใช้งานได้ 100%** | เลือกแสดงตามกลุ่ม 10 กลุ่มจริง + All Groups, ค้นหาแบบ Real-time, ติ๊กเลือกหลายรายการ |
| **Add Selected Tags to Task** | **ใช้งานได้ 100%** | เพิ่ม Tag ที่เลือกเข้าสู่ Task ปัจจุบัน พร้อมอัปเดตตาราง Section E ทันที ป้องกันรายการซ้ำ |
| **Remove Tag from Task** | **ใช้งานได้ 100%** | กดปุ่ม `✕ นำออก` ในแถวตารางเพื่อถอด Tag ออกจาก Task ทันที |
| **Task Creation & Switching** | **ใช้งานได้ 100%** | กดปุ่ม `+ สร้าง Task ใหม่` กำหนดรหัส ID อัตโนมัติ สลับ Task ผ่าน Dropdown ได้ลื่นไหล |
| **Task Configuration Persistence** | **ใช้งานได้ 100%** | กด `บันทึก Task (Save)` เก็บค่าลง JSON Structure และตรวจสอบ Validation |
| **Runtime Execution Decoupling** | **ใช้งานได้ 100%** | แยกสถานะ Configured / Enabled / Running อย่างถูกต้อง ไม่หลอกว่ารันเมื่อ Auto-Scan ปิดอยู่ |
| **Trigger Rule Engine Evaluation** | *รอ Phase 2 (Gate B)* | UI มีสถานะเป็น Preview Disabled Controls ชัดเจน ยังไม่มีการประเมิน Threshold ในลูป |
| **Live Telegram Dispatching** | *รอ Phase 2 (Gate B)* | มีปุ่มเปิดรับ Intent และลิงก์ไปหน้า F6 แต่ระงับการส่งข้อความยิงภายนอกจนกว่าจะมี Gate B |

---

## 4. ผลการทดสอบเชิงระบบ (Automated Test Suite Results)

ชุดทดสอบ `F2TestSuite` ดำเนินการทดสอบครอบคลุม 9 มิติ:
1. `test_01_f2_view_initialization`: ผ่าน 100% (สร้างวิดเจ็ตครบทั้ง 7 ส่วน โครงสร้างสมบูรณ์)
2. `test_02_group_filter_population`: ผ่าน 100% (พบ All Groups + 10 กลุ่มจริงจาก SCADA Catalog)
3. `test_03_task_creation_and_switching`: ผ่าน 100% (สร้าง Task 2 รายการ สลับ Selector และอัปเดต UI ตรงกัน)
4. `test_04_section_a_identity_and_badges`: ผ่าน 100% (แยก Badges 3 มิติ Configured, Enabled, Standby ถูกต้อง)
5. `test_05_add_selected_tags_to_task`: ผ่าน 100% (เลือก 2 Tags จากคลังซ้าย เพิ่มเข้า Task สำเร็จ ตาราง Section E อัปเดตทันที)
6. `test_06_remove_tag_from_task`: ผ่าน 100% (กดลบ Tag ออกจาก Task ตารางและจำนวนนับลดลงถูกต้อง)
7. `test_07_validation_live_feedback`: ผ่าน 100% (ลบชื่อ Task จนว่าง เกิด Invalid State ทันที เมื่อพิมพ์ชื่อกลับคืนสู่สถานะ Valid)
8. `test_08_auto_scan_runtime_state_toggle`: ผ่าน 100% (เมื่อเปิด Auto Scan เปลี่ยนสถานะเป็น `Running (Active Monitoring)` สีเขียวสด เมื่อปิดสลับกลับเป็น `Standby`)
9. `test_09_test_data_isolation`: ผ่าน 100% (ข้อมูลทดสอบถูกล้างออก ไม่มีการบันทึกทับ Task จริงของผู้ใช้งาน)

---

## 5. การวิเคราะห์ภาพหน้าจอเปรียบเทียบ (Visual Quality & Screenshots)

### ภาพหน้าจอหลักที่บันทึกแล้วในคลังเอกสาร:
1. [f2_configured_task_1366x768.png](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_configured_task_1366x768.png)
   - ความละเอียดมาตรฐาน 1366×768 แสดงการทำงานใน Task ที่มีการกำหนดค่าและ Tag ครบถ้วน (Section A ถึง E ปรากฏในมุมมองโดยตรง Dropdown สี Dark Theme สวยงามกลมกลืน)
2. [f2_configured_task_1920x1080.png](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_configured_task_1920x1080.png)
   - ความละเอียด Full HD 1920×1080 แสดงผลสวยงาม ช่องว่างและสัดส่วนคอลัมน์กว้างขวาง เหมาะสมกับหน้าจอ SCADA Workstation
3. [f2_running_autoscan_1366x768.png](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_running_autoscan_1366x768.png)
   - แสดงสถานะเมื่อระบบกด `เริ่ม Auto Scan` ป้าย Section A เปลี่ยนเป็น `Running (Active Monitoring)` สีเขียวสดใส (`#27B785`) พร้อมเวลาถอยหลังรอบการสแกน
4. [f2_empty_state_1366x768.png](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_empty_state_1366x768.png)
   - แสดง Empty State เมื่อเปิดโปรแกรมใหม่แบบ Zero-Mock (0 Tags)

---

## 6. ข้อเสนอทางวิศวกรรมสำหรับ Phase 2 (Gate B Recommendations)

เพื่อเตรียมความพร้อมสำหรับการเปิดประเมินเงื่อนไขทริกเกอร์จริงใน Phase 2 แนะนำสถาปัตยกรรมดังนี้:
1. **Rule Evaluation Pipeline:**
   - ประเมินค่าแยกตาม Data Type (Binary Transitions: `0->1`, `1->0`, `any_edge`; Analog Thresholds: `High`, `Low`, `Band` พร้อม deadband ±0.5%)
2. **Quality & Timestamp Guard:**
   - ปฏิเสธการประเมินทริกเกอร์หากค่า Tag มีสถานะ `Bad`, `Uncertain`, หรือเป็น Stale Data เกินกว่าอายุที่กำหนด
3. **Flapping & Chattering Suppression:**
   - กำหนดให้เงื่อนไขต้องเข้าเกณฑ์ต่อเนื่องอย่างน้อย `N samples` (เช่น 2 รอบสแกน) ก่อนเปลี่ยนสถานะเป็น ALARM
4. **Notification Cooldown & Deduplication:**
   - กำหนด Cooldown Window (เช่น 300 วินาที) สำหรับการแจ้งเตือนซ้ำ เพื่อไม่ให้เกิด Alert Storm ไปยัง Telegram
5. **Schema Migration & Backward Compatibility:**
   - ขยายโครงสร้าง Task Schema อย่างปลอดภัย โดยเพิ่มคีย์ `trigger_rules: [...]` แบบ optional โดยไม่ทำลายไฟล์คอนฟิกเดิมของผู้ใช้
