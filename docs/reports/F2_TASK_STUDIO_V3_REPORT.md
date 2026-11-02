# AQUA COMMAND — F2 TASK STUDIO V3 REPORT
## Complete UI Rebuild & Task-First SCADA Experience

**Document ID:** `DOC-AC-F2-STUDIO-V3`  
**Date:** 2026-11-02  
**Target Environment:** Linux GTK4 (`aqua-command-desktop/desktop/app.py`, `f2_tasks.py`, `f2_style.css`)  
**Design Standard:** Industrial Spectrum V2 Design System  
**Status:** Verification & Testing 100% Passed (Awaiting User Acceptance)

---

## 1. Executive Summary & Design Transformation

ตามคำสั่งไม่อนุมัติ Layout เดิมและอนุมัติให้ Rebuild F2 ใหม่จากศูนย์ภายใต้แนวคิด **AQUA COMMAND — Task Studio** ทีมพัฒนาได้ยกเลิกโครงสร้างเก่าที่มี Tag Library ขนาดใหญ่ด้านซ้ายและฟอร์ม A–G ด้านขวาออกทั้งหมด และสร้างสถาปัตยกรรม UI ใหม่แบบ **Task-First Architecture** ที่มุ่งเน้นลำดับการทำงานที่ชัดเจน:

$$\text{เลือก Task} \longrightarrow \text{ดู Tag ที่กำหนด} \longrightarrow \text{เพิ่ม/ลบ Tag (On-Demand Picker)} \longrightarrow \text{ตั้งค่าการทำงาน} \longrightarrow \text{ตรวจสอบ} \longrightarrow \text{บันทึก}$$

### ข้อกำหนดสำคัญที่บรรลุผล 100%:
1. **ตัด Rule Builder ที่ยังไม่รองรับออกทั้งหมด:** ไม่มี Accordion เงื่อนไขทริกเกอร์ที่ใช้งานไม่ได้ในหน้านี้อีกต่อไป
2. **On-Demand Contextual Tag Picker:** ยกเลิกการแสดง Tag Library เต็มจอถาวร โดยเปลี่ยนเป็น Contextual Picker ในตัว Workspace ที่เปิดเฉพาะเมื่อผู้ใช้กด `+ เพิ่ม Tag` พร้อมระบบค้นหา ตัวกรองครบ 10 กลุ่มจริง + All Groups และระบบ Multi-select ที่คงค่าการเลือกไว้ข้ามการค้นหาและเปลี่ยนกลุ่ม
3. **ป้องกัน Tag ซ้ำ (Zero Duplicate):** ระบบตรวจสอบ Tag ที่ผูกกับ Task แล้วอย่างเข้มงวด โดยปิดการเลือกและระบุ `กำหนดแล้วใน Task นี้`
4. **แยกสถานะ Intent และ Runtime ออกจากกัน:** แยก `Enabled` (เปิดรับงาน) ออกจาก `Running` (ระบบกำลังมอนิเตอร์จริงขณะ Auto-Scan ทำงาน) อย่างเด็ดขาด
5. **Top Scan Operations Bar:** ย้ายปุ่มสแกนออกจาก Toolbar เดิมที่รก กลายเป็นแถบเครื่องมือระดับวิศวกรรมที่กะทัดรัด มองเห็นสถานะและปุ่มหยุดสแกนได้ทันทีโดยไม่ต้องเข้าเมนูลึก

---

## 2. Before / After Architecture Comparison

| มิติการออกแบบ | F2 Layout เดิม (Rejected) | F2 Task Studio V3 (New Rebuild) |
|---|---|---|
| **Layout Paradigm** | Static Split: ซ้ายเป็น Tag Catalog กว้างมาก ขวาเป็นแบบฟอร์มหัวข้อ A–G | **Master-Detail Studio:** ซ้าย Task Navigator (24%), ขวา Task Workspace (76%) |
| **User Mental Model** | ผู้ใช้สับสนว่าต้องเริ่มจาก Tag หรือ Task ข้อมูลกองรวมกัน | **Task-Centric:** โฟกัสทีละ Task จัดการ Tag, ตั้งค่า, และตรวจสอบเป็นขั้นตอน |
| **Tag Selection** | ตาราง Tag Library 457 รายการแสดงค้างอยู่ตลอดเวลา กินพื้นที่ครึ่งจอ | **Contextual On-Demand Picker:** เปิดใช้งานเฉพาะเมื่อกด `+ เพิ่ม Tag` ไม่แย่งพื้นที่ |
| **Workspace Organization** | รายการยาวแบบ Flat Scroll ตั้งแต่ A ถึง G | **3 Dedicated Tabs:** 🏷️ รายการ Tag, ⚙️ การตั้งค่า, 📋 ตรวจสอบ & บันทึก |
| **Scan Operations** | ปะปนอยู่กับ Toolbar ด้านบน รกสายตา | **Compact Scan Bar:** แถบเครื่องมือเฉพาะด้านบน สูงเพียง 38px กะทัดรัด สวยงาม |
| **Rule Builder** | แสดง Accordion Phase 2 Preview ที่กดใช้งานไม่ได้ | **Purged:** ลบออกทั้งหมดตามคำสั่ง เพื่อความชัดเจนในการใช้งานจริง |
| **Zero Mock Compliance** | แสดง Mock Tag หรือ Empty แบบเดิม | **Real Catalog & Live State:** เชื่อมต่อ 457 Tags จริง และแสดงสถานะตามจริง |

---

## 3. รายละเอียดโครงสร้างส่วนประกอบ (Component Breakdown)

```
+-------------------------------------------------------------------------------------------------------------------------------------+
| Top Scan Bar: [สแกนทันที 1 ครั้ง] [▶ เริ่ม Auto Scan] | รอบ: [5s] ระยะเวลา: [1 ชม.] | [Auto Scan: สแตนด์บาย] ⏱️ 5s | Catalog: 457 Tags  |
+-------------------------------------------+-----------------------------------------------------------------------------------------+
| Task Navigator (~24%)                     | Task Workspace (~76%)                                                                   |
| [Header: 2 Tasks]                         | [TASK-01] เฝ้าระวังแรงดันปั๊มน้ำ VSD (High_VSD)   [3 Tags] [Configured] [Enabled] [Standby] |
| [+ สร้าง Task ใหม่]                         +-----------------------------------------------------------------------------------------+
|                                           | [🏷️ รายการ Tag (Assigned Tags)]   [⚙️ การตั้งค่า (Settings)]   [📋 ตรวจสอบ & บันทึก (Review)]   |
| ┌───────────────────────────────────────┐ +-----------------------------------------------------------------------------------------+
| │ [TASK-01] เฝ้าระวังแรงดันปั๊มน้ำ VSD   │ | Tab 1: Assigned Tags View                                                               |
| │ [3 Tags] [Configured] [Enabled]       │ | - Action Row: Tag ที่กำหนดให้กับ Task นี้ (3 รายการ)            [+ เพิ่ม Tag (Add Tags)] |
| ├───────────────────────────────────────┤ | - Technical Table:                                                                    |
| │ [TASK-02] ตรวจสอบวาล์วปีกผีเสื้อไฟฟ้า │ |   TAG NAME / IDENTIFIER   | กลุ่ม (GROUP) | ชนิดข้อมูล | สถานะ | คำสั่ง (ACTION)       |
| │ [3 Tags] [Configured] [Disabled]      │ |   CTM13PT.AUTO_C          | High_VSD      | Binary Tag | Online| [✕ นำออก]             |
| └───────────────────────────────────────┘ |   CTM13PT.MODBUS_S        | High_VSD      | Binary Tag | Online| [✕ นำออก]             |
|                                           |   CTM13PT.READY_S         | High_VSD      | Binary Tag | Online| [✕ นำออก]             |
|                                           | --------------------------------------------------------------------------------------- |
|                                           | (หรือเมื่อกด [+ เพิ่ม Tag] จะสลับเป็น Contextual Tag Picker ค้นหา/กรองจาก 457 Tags ทันที)|
+-------------------------------------------+-----------------------------------------------------------------------------------------+
| F1 ภาพรวมสถานี | F2 ตัวจัดการ Task | F3 ผังเครือข่าย | F4 ข้อมูลเครื่อง | F5 คลัง Tag | F6 OPC UA & Telegram | F7 สแกน | F8 ปิดระบบ      |
+-------------------------------------------------------------------------------------------------------------------------------------+
```

### 3.1 Task Navigator (คอลัมน์ซ้าย ~24%)
- แสดงการ์ดรายการ Task ทั้งหมดในระบบแบบ Interactive
- การ์ดแต่ละใบประกอบด้วย:
  - Monospace ID Badge (เช่น `TASK-01`)
  - ชื่องาน Task (ตัดคำด้วย Ellipsize ป้องกันข้อความล้น)
  - ป้ายระบุจำนวน Tag (เช่น `3 Tags`)
  - สถานะ Completeness: `Configured` (ฟ้า) หรือ `Incomplete` (ส้มอมเหลือง)
  - สถานะการเปิดใช้งานและรันไทม์: `Enabled` (เขียวอ่อน), `Disabled` (เทา), หรือ `Running` (เขียวมรกตสด) เมื่อระบบเริ่ม Auto-Scan จริง
- ปุ่มสร้างงานใหม่ `+ สร้าง Task ใหม่` เด่นชัดด้านบนของ Navigator พร้อมระบบโฟกัสงานที่เพิ่งสร้างให้อัตโนมัติ

### 3.2 Task Workspace (พื้นที่ทำงานขวา ~76%)
- **Workspace Header:** แสดงรหัส Task, ชื่อเต็มขนาดใหญ่ (13pt Bold), จำนวน Tag, และสถานะทั้ง 3 มิติ
- **Segmented Tab Switcher:** ปุ่มสลับ 3 แท็บสไตล์วิศวกรรมอุตสาหกรรม
- **Tab 1 — รายการ Tag (Assigned Tags):**
  - แสดงตารางสัญญาณที่ผูกกับ Task นี้ พร้อมปุ่ม `✕ นำออก` แต่ละแถว
  - หาก Task ยังไม่มี Tag จะแสดง Empty State ที่สุภาพชัดเจน พร้อมปุ่มดึงดูดสายตา `+ เพิ่ม Tag เข้า Task นี้`
  - **Contextual Tag Picker (On Demand):** เมื่อกด `+ เพิ่ม Tag` หน้าต่างจะสลับเป็นโหมดเลือกสัญญาณจากคลัง 457 Tags:
    - ตัวกรองกลุ่ม SCADA ครบทุกกลุ่ม (All Groups + 10 กลุ่มจริง: `High_VSD`, `High_Valve`, `Low_Flow`, ฯลฯ)
    - กล่องค้นหา Realtime Search กรองจากชื่อ, Address, กลุ่ม, ชนิดข้อมูล
    - ปุ่มเลือกทั้งหมดในผลการค้นหา และปุ่มล้างการเลือก
    - ติ๊กเลือกได้หลายรายการพร้อมกัน (Multi-select) โดยไม่สูญหายเมื่อเปลี่ยนตัวกรอง
    - ป้องกัน Tag ซ้ำ: Tag ที่อยู่ใน Task แล้วจะถูกติ๊กค้างและปิดการแก้ไขพร้อมป้าย `กำหนดแล้วใน Task นี้`
- **Tab 2 — การตั้งค่า (Settings):**
  - ช่องแก้ไขชื่อ Task แบบ Live Update
  - ดรอปดาวน์รอบเวลาการเฝ้าระวัง: `1 วินาที`, `5 วินาที (มาตรฐาน WinCC)`, `10 วินาที`, `30 วินาที`, `60 วินาที`
  - เช็คบ็อกซ์บันทึก Local Archive (SQLite / CSV)
  - เช็คบ็อกซ์แจ้งเตือน Telegram พร้อมลิงก์ตรงไปยังหน้าตั้งค่า F6
  - เช็คบ็อกซ์เปิดใช้งาน Task (Enable Task)
- **Tab 3 — ตรวจสอบ & บันทึก (Review & Save):**
  - การ์ดสรุปพารามิเตอร์ทั้งหมดของ Task
  - ระบบตรวจสอบความถูกต้อง (Validation Engine):
    - แจ้งเตือนสีแดงหากชื่อว่างเปล่า `❌ ชื่อ Task ต้องไม่เป็นค่าว่าง`
    - แจ้งเตือนสีเหลืองหากไม่มี Tag `⚠️ Task ยังไม่มี Tag ที่กำหนด`
    - แสดงกล่องสีเขียวเมื่อสมบูรณ์ `✅ การตั้งค่าทั้งหมดถูกต้องและสมบูรณ์ พร้อมบันทึกและใช้งาน`
  - ปุ่มบันทึกขนาดใหญ่ **`💾 บันทึก Task (Save Task)`** พร้อมป้ายบอกสถานะ `Saved` หรือ `Unsaved Changes`

---

## 4. ผลการทดสอบเชิงระบบ (Automated Test Suite Results)

ชุดทดสอบอัตโนมัติ `F2StudioTestSuite` ดำเนินการทดสอบ 12 มิติ และ **ผ่านทั้งหมด 100%**:

```
>>> Starting F2 Task Studio V3 Automated Test Suite...
[PASS] Test 01: F2TaskManagerView initialization verified
[PASS] Test 02: Task Navigator selection & card mapping verified
[PASS] Test 03: Task creation & auto-focus verified
[PASS] Test 04: Assigned tags empty state verified
[PASS] Test 05: Contextual Tag Picker & Group Catalog verified (11 options)
[PASS] Test 06: Search & Multi-select in Tag Picker verified
[PASS] Test 07: Add Selected Tags & Duplicate Prevention verified
[PASS] Test 08: Remove tag from task verified
[PASS] Test 09: Settings tab & form inputs verified
[PASS] Test 10: Review tab, validation & save action verified
[PASS] Test 11: Runtime execution decoupling (Enabled vs Running) verified
[PASS] Test 12: Navigation regression across all F1-F8 pages verified
>>> ALL 12 F2 TASK STUDIO V3 TESTS PASSED 100%!
>>> Original tasks safely restored. Zero side effects.
```

---

## 5. รายการภาพหน้าจอที่บันทึกจาก GTK4 จริง

ไฟล์ภาพหน้าจอทั้งหมดถูกเรนเดอร์และบันทึกไว้ใน `docs/screenshots/f2_v3/` และ Artifact Directory:

| รูปภาพ | ลิงก์ไฟล์ | คำอธิบายรายละเอียด |
|---|---|---|
| **Tab 1: Assigned Tags** | [f2_v3_tab1_assigned_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_tab1_assigned_1366x768.png) | หน้าจอหลัก Tab 1 บนความละเอียด 1366×768 แสดง Task Navigator, Workspace Header, และตาราง Tag ที่กำหนด |
| **Contextual Tag Picker** | [f2_v3_tab1_picker_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_tab1_picker_1366x768.png) | หน้าต่างเลือก Tag ในตัว Workspace แสดงตัวกรองกลุ่ม, กล่องค้นหา, เช็คบ็อกซ์หลายรายการ, และป้ายนับ |
| **Tab 2: Settings** | [f2_v3_tab2_settings_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_tab2_settings_1366x768.png) | แบบฟอร์มตั้งค่า Task Name, รอบเวลาเฝ้าระวัง, Local Archive, และ Telegram Notification พร้อมลิงก์ F6 |
| **Tab 3: Review & Save** | [f2_v3_tab3_review_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_tab3_review_1366x768.png) | การ์ดสรุปพารามิเตอร์, Live Validation Engine (แจ้งเตือนความถูกต้อง), และปุ่มบันทึก `💾 บันทึก Task` |
| **Running Auto-Scan** | [f2_v3_running_autoscan_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_running_autoscan_1366x768.png) | สถานะเมื่อกดเริ่ม Auto-Scan ปุ่มเปลี่ยนเป็นสีแดง `⏹ หยุด Auto Scan` ป้ายเปลี่ยนเป็น `Running (Active)` สีเขียว |
| **Task Empty State** | [f2_v3_empty_state_1366x768.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_empty_state_1366x768.png) | แสดงการ์ด Empty State สุภาพเมื่อสร้าง Task ใหม่ที่ยังไม่มี Tag กำหนด พร้อมปุ่ม `+ เพิ่ม Tag เข้า Task นี้` |
| **Full HD 1080p** | [f2_v3_tab1_assigned_1920x1080.png](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f2_v3_tab1_assigned_1920x1080.png) | การเรนเดอร์บนจอ SCADA Workstation 1920×1080 สัดส่วนกว้างขวาง สวยงาม สบายตา |

---

## 6. รายการไฟล์และสรุปการเปลี่ยนแปลง (Git Summary)

- **ไฟล์ที่สร้าง/แก้ไขใน Working Tree:**
  1. [`aqua-command-desktop/desktop/f2_tasks.py`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f2_tasks.py): Rebuild presentation layer เป็น Task Studio V3 ทั้งหมด (~650 บรรทัด สะอาด เป็นระเบียบ)
  2. [`aqua-command-desktop/desktop/f2_style.css`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f2_style.css): ชุดสไตล์ Industrial Spectrum V2 tokens สำหรับ Task Studio, Navigator cards, Tab bar, Dropdowns, และ Badges
  3. [`aqua-command-desktop/desktop/app.py`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/app.py): เชื่อมต่อ `f2_style.css` และ delegate callbacks ไปยัง `F2TaskManagerView` อย่างสมบูรณ์
- **สถานะ Git:**
  - สภาพ Working Tree แยกอิสระ ปลอดภัย
  - **ไม่มีการ Commit หรือ Git Push ใดๆ** ตามกฎความปลอดภัยที่ระบุไว้
