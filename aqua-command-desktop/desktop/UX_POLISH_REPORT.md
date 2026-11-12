# รายงานปรับ UX ของ AQUA COMMAND native GTK4

วันที่ 2026-11-12 · สาขา local `ux/desktop-polish` · ฐาน `445e1e6`

งานปรับ GUI/presentation เสร็จใน isolated checkout และผ่านชุดตรวจด้านล่าง
โปรแกรมที่ไอคอนเดิมเปิดยังเป็น canonical `main` ที่ `445e1e6`
ไม่มีการติดตั้ง dependency/โปรแกรม, push, merge, deployment หรือแก้ OS/service/network
ไม่แก้ backend, collector, schema, DB code, config, private runtime profile หรือ Windows reader
การตรวจ GUI ใช้ disposable test profile ที่ระบุ SIMULATED และ network namespace
ที่มี loopback เท่านั้น ไม่มีการอ่าน PLC/WinCC หรือส่ง Telegram จริง

## Commit ที่ส่งมอบ

| Commit | ผลที่เปลี่ยน |
| --- | --- |
| `2afcabe` | ยืนยันก่อนปิดผ่าน F8/ปุ่ม/หน้าต่าง โฟกัสเริ่มที่ยกเลิก เก็บ cleanup เดิมและแยกปุ่มออก |
| `f722eb7` | ป้าย/tooltip คีย์ลัดและสถานะเลือกของ Task ขณะ dialog เปิด |
| `f7a0953` | เพิ่มขนาดตัวอักษร/controls, ปรับ contrast และ F3 สำหรับพื้นที่สั้น |
| `2ddefd8` | ป้ายภาษาไทย, status คัดลอกได้พร้อม tooltip เต็ม, แสดง auto-refresh state เดิม |
| `546c424` | ยืนยัน SIMULATED Telegram พร้อม chat ที่ปิดบัง และเหตุผลเมื่อปุ่มใช้ไม่ได้ |
| `5458cc0` | คำอธิบายหน้าว่าง/รอ, ปุ่มไป F5/F6 ผ่าน handler เดิม, อายุข้อมูลและเหตุผลจริง |
| `084f5e4` | accessible labels, Tab เข้าถึงแถว F1 และ reduced-motion ครบขึ้น |
| `0a72d8f` | แก้ F3 card ล้นในหน้าต่าง native จริงและความสูงกลุ่ม F1 พร้อม regression |
| commit ที่แนบรายงานนี้ | โฟกัสเข้า F2 และคืนตัวเปิดจริง, ภาพ confirmation และรายงานผลสุดท้าย |

ทุก commit อยู่บนสาขา local เท่านั้น ไม่มีการแก้ประวัติเดิม

## ผลตามรายการที่ขอ

1. เพิ่มหน้าต่างยืนยันก่อนปิดโดยใช้รูปแบบ Gtk.Dialog เดิม โฟกัสที่ยกเลิก
   และเรียก cleanup เดิมหลังยืนยัน แยกปุ่มปิดไว้ขวาสุด
2. แสดง F1–F9 ที่ปุ่ม/tooltip ตามหน้าที่จริง ตั้งค่าระบุ F6/Ctrl+,
   ปุ่ม Task มีสถานะ active ระหว่าง dialog เปิด ใช้ชื่อ ตั้งค่า โดยเก็บ key `alarms`
3. secondary text อย่างน้อย 10pt, body/table อย่างน้อย 10.5pt และ control 36px
   หน้าต่างขั้นต่ำ 1024x600 ในพื้นที่สั้น F3 ลด spacing/คำอธิบายรอง
   เก็บสถานะ ผลตรวจ อายุ และ READ ONLY ไว้ รายละเอียดเต็มยังเปิดดู/อ่าน tooltip ได้
4. ปรับคำปุ่ม/ข้อความแสดงผลเป็นภาษาไทยและเอา emoji ตกแต่งออก
   เก็บ enum/log ที่เป็นสัญญาการทำงาน status ribbon เลือกคัดลอกและอ่าน tooltip เต็มได้
   แสดงเปิด/ปิดและช่วงเวลาของการรีเฟรชเดิมโดยไม่เปลี่ยน worker/timing
5. ตรวจ code แล้ว demo เดิมเรียก simulator แยก process และส่งจริงได้ผ่าน F6
   จึงเพิ่ม confirmation ที่บอกเนื้อหา SIMULATED/หนึ่งข้อความ/ปลายทางที่ปิดบัง
   โฟกัสที่ยกเลิก และต้องยืนยันใหม่หาก config เปลี่ยน ไม่มี config ที่ใช้ได้จะปิดปุ่มพร้อมเหตุผล
   tests ดัก `_open_demo` และใช้ข้อมูลสังเคราะห์เฉพาะ test โดยไม่เริ่ม demo หรือส่ง
6. หน้าว่าง/รออธิบายเหตุผลและมี action ไป F5/F6 ด้วย handler เดิม
   แสดงอายุจาก timestamp ที่มีอยู่และเหตุผล backend จริงพร้อมคำอธิบายไทย
   ไม่สร้าง TIMEOUT/NO_ROUTE ขึ้นเอง ไม่เปลี่ยน FAIL เป็น success และไม่ให้ STALE ทับผลเดิม
7. เพิ่ม accessible labels ให้ icon-only controls/แถว Tab และตรวจทางคีย์บอร์ด
   แก้ F2 ให้โฟกัสเข้า WebKit dialog และคืนตัวเปิดจริงเมื่อปิด
   fallback Task/Inspector คืนตัวเปิดจริงด้วย เก็บข้อความ/สัญลักษณ์คู่กับสี

## ผลก่อนและหลัง

| การตรวจ | ก่อนแก้ | ผลสุดท้าย |
| --- | --- | --- |
| Desktop unittest discovery | 319 tests ผ่าน | 331 tests ผ่าน, exit 0 |
| Source contracts | 116 tests ผ่าน | 116 tests ผ่าน, exit 0 |
| UX focused suite | tests ใหม่แสดงปัญหาก่อนแก้ตาม raw logs | 12 tests ผ่าน, exit 0; เป็นส่วนหนึ่งของ 331 tests |
| F3 standalone 1024x496 | ไม่ผ่าน: viewport สูง 457, scrollHeight 499 | ผ่าน, exit 0 |
| F3 standalone 1360x616 / 1920x1009 | ผ่านทั้งสองขนาด | ผ่านทั้งสองขนาด, exit 0 |
| Full native F1–F6 | 18ภาพ; ขอ 1024x600 แต่ได้จริง 1024x700 จาก min-height เดิม | 18ภาพ ขนาดจริงตรง 1024x600/1360x768/1920x1080 |
| F3 card bounds ใน native window | capture/regression พบล้นที่ 1024x600 และ 1360x768 หลังเจ็ด commit แรก | cards อยู่ใน zone และเหนือ legend ครบ3ขนาด ไม่มี scroll overflow |
| F2 keyboard focus | regression ไม่ผ่าน: โฟกัสค้างที่ Gtk.ToggleButton | regression และชุดรวมผ่าน: เข้า WebView แล้วคืน opener |
| Legacy `desktop/ui_test.py`, `desktop/layout_test.py` | exit 1: import `AquaWindow` ไม่ได้ | ไม่แก้ legacy scripts; ข้อจำกัด baseline ยังอยู่ |

ภาพสุดท้ายเพิ่ม confirmation อีก2ภาพ: `confirm-close-1360.png` และ
`confirm-simulated-telegram-1360.png` ทั้งสองกดยกเลิก ใน capture ตรวจว่า
polling STOPPED, poll_count=0, notification worker ไม่ทำงาน และ evidence DB ไม่เปลี่ยน
F3 WebView จริงมีขนาด 1024x417, 1360x585 และ 1920x897 ตามลำดับ

รอบกลาง 323 tests เคยไม่ผ่าน polling timing assertion หนึ่งรายการที่รอคงที่ 0.4s
รัน test เดิมแบบแคบผ่าน และชุดสุดท้าย 331 tests ผ่าน โดยไม่แก้ polling implementation
หรือผ่อน test นั้น เก็บ raw output ของรอบที่ไม่ผ่านไว้ด้วย

## Contrast ที่วัดจริง

| คู่สี | ก่อน | หลัง |
| --- | ---: | ---: |
| GTK disabled Task action | 3.499:1 | 7.978:1 |
| GTK running status | 3.518:1 | 5.091:1 |
| GTK catalog badge | 4.091:1 | 5.773:1 |
| WebKit faint | 3.526:1 | 6.991:1 |

วัดทั้งหมด12คู่สี หลังแก้ผ่าน 4.5:1 ทุกคู่ ค่าต่ำสุด4.743:1
นี่เป็นการวัดคู่สี foreground/background ใน CSS ไม่ใช่การตรวจทุกพิกเซล/ทุกสถานะ
ข้อมูลเต็มอยู่ `artifacts/ux-before/contrast-raw.json` และ
`artifacts/ux-after/contrast-raw.json` จาก repository root ของ isolated checkout

## ข้อที่มีอยู่แล้วและงานที่ข้าม

- F1 มี ArrowUp/Down, Enter, Space และ Esc อยู่ก่อน จึงไม่ได้เพิ่มกลไกเหล่านี้ใหม่ทั้งหมด
- F1/F3 มี reduced-motion อยู่ก่อน และ F3 คืนโฟกัส/Esc อยู่แล้ว
  commit accessibility เพิ่มความครอบคลุมและ labels ส่วน F2 native focus เป็นข้อผิดพลาดที่พิสูจน์/แก้เพิ่ม
- `btn_top_f2` เป็น fallback และไม่ปรากฏซ้ำใน active F1ApiView path
  ปรับชื่อให้สอดคล้องกันโดยไม่เปลี่ยนโครงสร้างหน้า
- ไม่ทำ optional theme switch เพราะต้องเกี่ยวข้องกับ private settings handling นอกขอบเขต
- งาน standalone web ที่เริ่มผิดเป้าหมายถูกยกเลิกและลบ isolated checkout
  โดย canonical web source ไม่เปลี่ยน งานส่งมอบนี้เป็น native GTK4

## คำสั่งและ raw output

คำสั่งที่ใช้จริงพร้อม absolute executable, arguments และ exit code อยู่ใน local artifacts:

- `artifacts/ux-before/baseline-commands.json` และ `ux-before/ux-commands.json`
- `artifacts/ux-after/ux-commands.json`
- `artifacts/ux-after/final-receipt.json` บันทึก parent command, HEAD และ hashes หลัง commit

ไฟล์เหล่านี้ไม่ commit เพราะ raw logs มี workstation paths ส่วนคำสั่งด้านล่างแสดง
arguments เดียวกันโดยย่อเฉพาะตำแหน่ง Python runtime เป็น `<PYTHON_RUNTIME>`
รัน child commands จาก `aqua-command-desktop/`; คำสั่ง parent รันจาก repository root
และสร้าง temporary HOME/headless display ใน network namespace ของการทดสอบ:

```text
unshare --user --map-root-user --net <PYTHON_RUNTIME> -B aqua-command-desktop/desktop/tests/ux_run.py --stage after --capture --focused --checks
<PYTHON_RUNTIME> -B -m unittest test_ux_desktop_polish -v
<PYTHON_RUNTIME> -B -m unittest discover -s desktop/tests -v
<PYTHON_RUNTIME> -B -m unittest discover -s tests -v
F3_TEST_SIZE=1024x496 <PYTHON_RUNTIME> -B tests/f3_handoff_native.py
F3_TEST_SIZE=1360x616 <PYTHON_RUNTIME> -B tests/f3_handoff_native.py
F3_TEST_SIZE=1920x1009 <PYTHON_RUNTIME> -B tests/f3_handoff_native.py
python3 -B aqua-command-desktop/desktop/tests/ux_contrast.py
bash aqua-command-desktop/scripts/no_fake_check.sh
python3 scripts/privacy_preflight.py
git diff --check 445e1e6
git diff --exit-code 445e1e6 -- aqua-command backend config windows-reader aqua-command-desktop/backend aqua-command-desktop/collector aqua-command-desktop/config aqua-command-desktop/windows-reader
```

ข้อความดิบส่วนท้ายจากชุดสุดท้าย (ไฟล์เต็มเก็บใน artifacts):

```text
Ran 331 tests in 74.149s

OK
EXIT_CODE=0

Ran 116 tests in 20.504s

OK
EXIT_CODE=0

Ran 12 tests in 8.107s

OK
EXIT_CODE=0
```

```text
native-capture exit 0
ux-focused exit 0
desktop-tests exit 0
source-contracts exit 0
f3-handoff-1024x496 exit 0
f3-handoff-1360x616 exit 0
f3-handoff-1920x1009 exit 0
no_fake_check: PASS
```

privacy preflight ไม่พบ findings ใน current tracked tree; ไม่ได้ใช้ private catalog comparison
และ history clearance เป็น NOT_EVALUATED ส่วน diff whitespace และ protected-path checks
exit0 โดยไม่มี output เก็บ output รอบท้ายใน `artifacts/ux-after/final-guards-raw.txt`

raw results ก่อนแก้และ regressions อยู่ `artifacts/ux-before/`
ผลสุดท้ายอยู่ `artifacts/ux-after/` ชื่อ `desktop-tests-raw.txt`,
`source-contracts-raw.txt`, `ux-focused-raw.txt`, `f3-handoff-*-raw.txt`,
`native-capture-raw.txt`, `native-layout.json` และภาพ `*-F1.png` ถึง `*-F6.png`
ผลหลังเจ็ด commit แรกยังเก็บแยกไว้ใน `artifacts/ux-gemini/`

## ไฟล์ที่เปลี่ยนเทียบฐาน

ทุก path ด้านล่างเริ่มจาก `aqua-command-desktop/`:

```text
PROJECT_PROGRESS.md
desktop/UX_POLISH_REPORT.md
desktop/app.py
desktop/f1_api/formal-theme.css
desktop/f1_api/index.html
desktop/f1_api/view.css
desktop/f1_api/view.js
desktop/f1_api_view.py
desktop/f1_style.css
desktop/f2_style.css
desktop/f3_api/index.html
desktop/f3_api/view.css
desktop/f3_api/view.js
desktop/f3_api_view.py
desktop/style.css
desktop/tests/test_f3_active_reconciliation.py
desktop/tests/test_f3_network_topology.py
desktop/tests/test_ux_desktop_polish.py
desktop/tests/ux_contrast.py
desktop/tests/ux_native_capture.py
desktop/tests/ux_run.py
desktop/workspace.py
desktop/workspace_style.css
```

tests lifecycle เดิมยังคง assertions ด้าน cleanup/safety และยืนยัน close dialog ก่อน teardown
ภาพ/DB/test profiles/raw logs อยู่ใน artifacts ที่ไม่ commit

## ยังไม่ได้ตรวจสอบ

Windows, WinCC/OPC/PLC จริง, LAN จริง, Telegram จริง, screen reader interoperability,
ทุก theme/font scaling และทุกคู่สี/ทุกสถานะของ UI ยังไม่ได้ตรวจสอบ
GTK accessibility bus warning ทำให้ไม่อ้างว่าผ่าน screen reader
ชุด desktop ยังมี ResourceWarning ของ unclosed event loop แม้ exit0
legacy UI/layout scripts ที่ import class เก่ายังไม่ผ่านตั้งแต่ baseline
ไม่มีผลรับรอง production/field acceptance จากงานนี้
