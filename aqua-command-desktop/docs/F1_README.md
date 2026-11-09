# F1 "ภาพรวม Tag & จัดการ Task" (Unified Tag Overview & Task Manager)

เอกสารสรุปสถาปัตยกรรม, การแปลงคอลัมน์จาก Siemens WinCC Export, การทำงานของ WebKit Bridge และการทดสอบของหน้า F1 ในโปรแกรม AQUA COMMAND (WinCC V8.1 SCADA & Task Manager)

---

## 1. โครงสร้างไฟล์และการจัดวาง

```text
aqua-command-desktop/
├── desktop/
│   ├── f1_api_view.py       # GTK4 WebKit6 Controller พร้อม Secure Bridge Allowlist
│   ├── workspace.py         # AquaUnifiedWorkspaceView จัดการการเชื่อมต่อ F1/F2
│   ├── app.py               # Main GTK App & WinCC Export Parser (33 คอลัมน์)
│   └── f1_api/
│       ├── index.html       # Single-page UI ตามมาตรฐาน CSP (default-src 'none')
│       ├── view.css         # สไตล์ตาราง (แถวสูง >= 44px, ไร้สี hex นอก formal-theme.css)
│       ├── view.js          # คีย์บอร์ด, Shift+Click, 1-Click +Task, Undo Toast, Search
│       ├── formal-theme.css # ชุดตัวแปรสีทางการของระบบ (Light/Dark WCAG AA)
│       └── fonts_embedded.css # @font-face base64 ฟอนต์ IBM Plex Sans Thai และ Mono
├── docs/
│   ├── F1_README.md         # เอกสารนี้
│   └── tags/
│       └── Export all.txt   # แคตตาล็อก Tag จริงของ WinCC V8.1 (457 Tags, 10 กลุ่ม, 33 คอลัมน์)
└── desktop/tests/
    ├── test_wincc_parser.py # Unit tests สำหรับ Parser 33 คอลัมน์, UTF-16 LE, UTF-8 BOM
    ├── test_f1_api_view.py  # Contract tests สำหรับ WebKit Bridge, CSP, ปลอด hex color, Allowlist
    └── test_workspace_production.py # Integration tests หน้าต่าง F1/F2 และระบบ Task
```

---

## 2. การแมปคอลัมน์จาก `Export all.txt` (33 คอลัมน์จริง)

ไฟล์ Export มาตรฐานจาก Siemens WinCC V8.1 Tag Management ประกอบด้วย 33 คอลัมน์ ระบบได้ทำการแยกฟิลด์ที่ UI ใช้งานออกจาก Raw Metadata เพื่อคงความครบถ้วนของข้อมูลทางวิศวกรรม 100%:

| ลำดับ | Technical Header (บรรทัด 2) | Human Header (บรรทัด 3) | การใช้งานในระบบ AQUA COMMAND |
|:---:|---|---|---|
| 0 | `[NAME][100][1]` | Name | `name`: ชื่อ Tag หลัก (เช่น `BVEC1PT.AUTO_C`) |
| 1 | `[COMMENT][211][1]` | Comment | `comment`: คำอธิบายสัญญาณภาษาไทย/อังกฤษ |
| 2 | `[TYPE][101][1]` | Data type | `type`: ชนิดข้อมูล (Binary Tag, Float, Word, etc.) |
| 3 | `[LENGTH][105][1]` | Length | `length`: ขนาดความยาวข้อมูล |
| 4 | `[FORMAT][106][1]` | Format adaptation | `fmt`: การปรับแต่งฟอร์แมตสัญญาณ |
| 5 | `[CONNECTION][102][1]` | Connection | `conn`: ชื่อการเชื่อมต่อ S7 Connection |
| 6 | `[GROUP][104][1]` | Group | `group`: กลุ่มอุปกรณ์ (10 กลุ่ม เช่น `High_VSD`, `High_Valve`) |
| 7 | `[ADDRPARAMS][108][1]` | Address | `addr`: ที่อยู่ PLC / S7 Offset (เช่น `DB62,D108.3`) |
| 8 | `[SCALEVALID][112][2]` | Linear scaling | `raw_metadata['Linear scaling']` |
| 9 | `[SCALEPARAM1][113][1]` | AS value range from | `raw_metadata['AS value range from']` |
| 10 | `[SCALEPARAM2][114][1]` | AS value range to | `raw_metadata['AS value range to']` |
| 11 | `[SCALEPARAM3][115][1]` | OS value range from | `raw_metadata['OS value range from']` |
| 12 | `[SCALEPARAM4][116][1]` | OS value range to | `raw_metadata['OS value range to']` |
| 13 | `[MINLIMIT][117][1]` | Low limit | `raw_metadata['Low limit']` |
| 14 | `[MAXLIMIT][118][1]` | High limit | `raw_metadata['High limit']` |
| 15 | `[STARTVALUE][119][1]` | Start value | `raw_metadata['Start value']` |
| 16 | `[SUBSTVALUE][120][1]` | Substitute value | `raw_metadata['Substitute value']` |
| 17 | `[SUBSTVALUE_ON_MINLIMIT][121][2]` | Substitute value at low limit | `raw_metadata['Substitute value at low limit']` |
| 18 | `[SUBSTVALUE_ON_MAXLIMIT][122][2]` | Substitute value at high limit | `raw_metadata['Substitute value at high limit']` |
| 19 | `[SUBSTVALUE_AS_STARTVALUE][123][2]` | Substitute value as start value | `raw_metadata['Substitute value as start value']` |
| 20 | `[SUBSTVALUE_ON_ERROR][124][2]` | Substitute value on connection errors | `raw_metadata['Substitute value on connection errors']` |
| 21 | `[UPDATEMODE][111][2]` | Computer-local | `raw_metadata['Computer-local']` |
| 22 | `[SYNCHRONIZATION][125][2]` | Synchronization | `raw_metadata['Synchronization']` |
| 23 | `[RUNTIMEPERSISTENCE][126][2]` | Runtime persistence | `raw_metadata['Runtime persistence']` |
| 24 | `[PLCVARIABLENAME][209][1]` | AS tag name | `raw_metadata['AS tag name']` |
| 25 | `[PLCBLOCKNAME][210][1]` | Name space | `raw_metadata['Name space']` |
| 26 | `[WRITEPROTECT][212][2]` | OPC write protection | `raw_metadata['OPC write protection']` |
| 27 | `[READPROTECT][213][2]` | OPC read protection | `raw_metadata['OPC read protection']` |
| 28 | `[GMPRELEVANT][214][2]` | Good Manufacturing Practices | `raw_metadata['Good Manufacturing Practices']` |
| 29 | `[CLOUDENABLED][216][2]` | WinCC Cloud | `raw_metadata['WinCC Cloud']` |
| 30 | `[CLOUDCYCLE][217][1]` | WinCC Cloud Cycle | `raw_metadata['WinCC Cloud Cycle']` |
| 31 | `[READACCESSLEVEL][219][6]` | Read authorization | `raw_metadata['Read authorization']` |
| 32 | `[WRITEACCESSLEVEL][220][6]` | Write authorization | `raw_metadata['Write authorization']` |

---

## 3. สคีมา Task และการบันทึกข้อมูล (Task Persistence)

Task จัดเก็บในไฟล์ `~/.config/aqua-command/wincc_tasks.json` โดยใช้ระบบบันทึกแบบ Atomic (`save_atomic_json`) เขียนลงไฟล์ชั่วคราว `.tmp` ก่อนสลับแทนที่ไฟล์จริง ป้องกันข้อมูลสูญหายจากกรณีไฟดับหรือระบบขัดข้อง:

```json
{
  "id": "TASK-01",
  "name": "Modified Task 0",
  "cycle_sec": 5,
  "action_log": true,
  "action_notify": true,
  "active": true,
  "tags": [
    "BVEC1PT.AUTO_C",
    "BVEC1PT.CLOSE_C"
  ],
  "scan_count": 0,
  "log_count": 0,
  "alert_count": 0
}
```

- **กฎความเข้ากันได้**: การเพิ่ม Tag เข้า Task จะ **ไม่เปิด `action_notify` หรือ `active` อัตโนมัติ** เพื่อความปลอดภัยของระบบ OT
- **การจัดการความล้มเหลว (Write Failure Rollback)**: หากเกิดข้อผิดพลาดในการบันทึก Task (เช่น ดิสก์เต็มหรือไม่มีสิทธิ์เขียน) ตัวแปร Task ในหน่วยความจำจะย้อนกลับสู่สถานะก่อนแก้ไขทันที และแจ้งเตือนผ่าน UI

---

## 4. สิ่งที่ปรับปรุงจากต้นแบบเพื่อลดความแข็งและเพิ่มความคล่องตัว

| ปัญหาในต้นแบบ | วิธีแก้ที่ดำเนินการในงาน B | เหตุผลทางวิศวกรรม / UX |
|---|---|---|
| แถวแน่น แข็ง เล็งกดยาก | ปรับความสูงแถวตาราง `min-height: 44px;` และพื้นที่กด `min-height: 40px; min-width: 40px;` | ตรงตามมาตรฐาน Touch Target และอ่านค่าสบายตาบนจอภาพโรงงาน |
| ต้องเล็งปุ่มเล็กท้ายแถว | **คลิกที่ใดก็ได้บนแถว = เปิดหน้าต่าง Inspector ทันที** | ผู้ปฏิบัติงานไม่ต้องเล็งปุ่มขนาดเล็ก สะดวกเมื่อใช้เมาส์หรือทัชสกรีน |
| เพิ่ม Tag เข้า Task ช้า | เพิ่มปุ่มด่วน **`+ Task` ในแถว** ผูกกับ Task ล่าสุดใน 1 คลิก พร้อม Undo Toast | ลดขั้นตอนจากเดิม 4-5 คลิก เหลือเพียงคลิกเดียว ไม่ต้องสลับหน้า |
| ต้องยืนยันทุกครั้ง | ใช้ **Undo Toast (มีปุ่ม "เลิกทำ")** แสดง 6 วินาที ไม่ใช้กล่องยืนยันที่ขัดจังหวะ | ความเร็วในการทำงานต่อเนื่อง (Flow State) โดยยังคงความปลอดภัย |
| เลือกหลายตัวลำบาก | รองรับ **Shift+คลิก** เพื่อเลือกช่วง และแสดง **แถบลอย Multi-Select** ด้านล่าง | จัดการ Tag ในกลุ่มเดียวกัน 10-50 ตัวได้ใน 2-3 การกระทำ |
| คีย์บอร์ดไม่คล่อง | รองรับ `/` โฟกัสค้นหา, `↑↓` เลื่อนแถว, `Enter` เปิด popup, `Space` ติ๊กเลือก, `Esc` ปิด | ใช้งานได้สมบูรณ์โดยไม่ต้องจับเมาส์ |
| การค้นหากระตุก | ค้นหาแบบกรองทันที (Instant Filtering) พร้อมไฮไลต์คำตรง `<mark>` | ผู้ใช้เห็นผลลัพธ์ทันทีที่พิมพ์ ไม่ต้องกดปุ่มค้นหา |
| แอนิเมชันรบกวน | ควบคุม Transition สั้น `<= 200ms` และปิดทั้งหมดเมื่อมี `prefers-reduced-motion` | ทำงานได้ลื่นไหล ไม่เวียนหัว และเคารพการตั้งค่าผู้ใช้ |
| สีไม่เป็นมาตรฐาน | ใช้ตัวแปรสีจาก `formal-theme.css` ครบถ้วน **ไม่มีสี hex นอกไฟล์ธีม 100%** | ผ่านเกณฑ์ Contrast WCAG AA ทั้งโหมดสว่างและมืด |

---

## 5. ความปลอดภัยของ WebKit Bridge

การสื่อสารระหว่างหน้าเว็บ WebKit กับ Python ดำเนินการผ่าน `window.webkit.messageHandlers.f1Bridge.postMessage` โดยมีมาตรการความปลอดภัยเข้มงวด:

1. **Explicit Action Allowlist**: อนุญาตเฉพาะ Action ที่กำหนดไว้:
   - `get_state`
   - `add_tag_to_task`
   - `add_tags_to_task`
   - `remove_tag_from_task`
   - `remove_tags_from_task`
   - `save_task`
   - `create_task`
   - `delete_task`
   - `undo_last_action`
   - `navigate_f6`
   - `key_event`
2. **Strict Payload Validation**: ฟังก์ชัน `validate_payload` ใน Python ตรวจสอบชนิดข้อมูล (Type Checking), ค่าที่ยอมรับได้ (เช่น `cycle_sec` ต้องอยู่ใน `1, 5, 10, 30, 60`) และปฏิเสธ Payload ที่มีโครงสร้างผิดปกติ
3. **ห้ามรัน Arbitrary Python**: ฝั่ง JavaScript ไม่สามารถเรียกเมธอดของ Python โดยตรง
4. **Read-Only SCADA**: ไม่มีโค้ดใดที่ส่งคำสั่ง Write หรือสร้าง Connection ไปยัง SCADA หรือส่ง Telegram จริงจากการทดสอบ UI

---

## 6. คำสั่งรันการทดสอบ (Verification Commands)

```bash
# 1. ทดสอบ WinCC Parser (33 คอลัมน์, 457 Tags, 10 Groups, UTF-16 LE, UTF-8 BOM)
PYTHONPATH=AquaCMD/aqua-command-desktop:AquaCMD/aqua-command-desktop/src:AquaCMD/aqua-command-desktop/desktop \
  python3 -m unittest AquaCMD/aqua-command-desktop/desktop/tests/test_wincc_parser.py

# 2. ทดสอบ WebKit Bridge Contracts (CSP, ปลอดสี hex, Payload validation, Default Not Observed, Undo)
PYTHONPATH=AquaCMD/aqua-command-desktop:AquaCMD/aqua-command-desktop/src:AquaCMD/aqua-command-desktop/desktop \
  python3 -m unittest AquaCMD/aqua-command-desktop/desktop/tests/test_f1_api_view.py

# 3. ทดสอบ Task Persistence Audit (Atomic write, Error handling)
PYTHONPATH=AquaCMD/aqua-command-desktop:AquaCMD/aqua-command-desktop/src:AquaCMD/aqua-command-desktop/desktop \
  python3 -m unittest AquaCMD/aqua-command-desktop/desktop/tests/test_task_persistence_audit.py

# 4. ทดสอบความเข้ากันได้ของระบบ Workspace เดิม (F1, F2 dialog, F6 width, 11 รายการ)
WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 \
  PYTHONPATH=AquaCMD/aqua-command-desktop:AquaCMD/aqua-command-desktop/src:AquaCMD/aqua-command-desktop/desktop \
  python3 -m unittest AquaCMD/aqua-command-desktop/desktop/tests/test_workspace_production.py
```
