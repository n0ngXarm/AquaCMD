# รายงานปรับ UX ของ AQUA COMMAND native GTK4

วันที่ 2026-11-12 · งาน UX เผยแพร่บน `main` ที่ `a3a2ef4` · ฐาน UX `445e1e6`

เผยแพร่ครบ **11 commits**: 10 commits ของ UX และหนึ่ง commit บันทึกอนุญาต
งานแก้ Python compatibility ได้รับการเผยแพร่บน `main` แล้ว (3 commits: `fe0ffd9`, `f888a86`, `f14cf2e`) เมื่อ 2026-11-13

อัปเดตหลังผู้ใช้ส่งภาพอ้างอิง: รักษาหน้าตาผังสามคอลัมน์เดิม และใช้ภาพ
1920x1080 ที่มี topology ครบในการเทียบ ผลตรวจงาน UX เดิม Desktop332 / contracts116 /
UX13 tests ผ่าน พร้อม regression ของประวัติ FAIL เก่าที่จอเล็ก ดูรายละเอียดท้ายรายงาน

งานปรับ GUI/presentation เสร็จใน isolated checkout และผ่านชุดตรวจด้านล่าง
ผู้ใช้อนุญาตเผยแพร่ source ไป GitHub `main` ที่ `a3a2ef4` แล้วเมื่อ 2026-11-12
ตามบันทึกใน PROJECT_PROGRESS.md การเผยแพร่ source ไม่ใช่การติดตั้งโปรแกรม
สถานะโปรแกรมที่ไอคอนเปิดยังไม่ได้ตรวจสอบในรอบ compatibility นี้
ไม่มีการติดตั้งโปรแกรม, deployment หรือแก้ OS/service/network ในงาน UX
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
| `54bead1` | โฟกัสเข้า F2 และคืนตัวเปิดจริง, ภาพ confirmation และรายงานส่งมอบแรก |
| `9889a8d` | ย่ออายุข้อมูล F3, จัด banner จอเล็ก และ regression ประวัติ FAIL พร้อม Switch/Router |
| `a3a2ef4` | บันทึกอนุญาตเผยแพร่ UX ไป main |

11 commits ข้างต้นเผยแพร่บน `main` แล้ว ไม่มี force push หรือแก้ประวัติเดิม

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
| Desktop unittest discovery | 319 tests ผ่าน | 332 tests ผ่าน, exit 0 |
| Source contracts | 116 tests ผ่าน | 116 tests ผ่าน, exit 0 |
| UX focused suite | tests ใหม่แสดงปัญหาก่อนแก้ตาม raw logs | 13 tests ผ่าน, exit 0; เป็นส่วนหนึ่งของ 332 tests |
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

ข้อความดิบส่วนท้ายจากชุดส่งมอบแรก (ผลหลังแก้ภาพอ้างอิงอยู่ท้ายรายงาน):

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

## ตรวจซ้ำตามภาพอ้างอิงของผู้ใช้

ภาพส่งมอบแรกเลือกจอ1024และโปรไฟล์ที่มีเฉพาะ4ต้นทาง ไม่มี Switch/Router
หรือหลักฐานสถานะ ภาพก่อน/หลังเดิมทั้งคู่จึงไม่เหมาะกับการเทียบภาพอ้างอิง
ที่1920x1080และมีองค์ประกอบครบ ไม่ใช่หลักฐานว่าองค์ประกอบเหล่านี้ถูกลบจาก runtime

สร้างภาพ native GTK ที่1920x1080/1360x768/1024x600จาก disposable profile
ซึ่งมี4ต้นทาง, Switch, Router, ห้าขั้นตอนภายใน และ Relay/Telegram
รวม13การ์ด/12เส้น ใช้ documentation addresses และ evidence source=sim
ทั้งชุด มี SIMULATED ในชื่อหน้าต่างและ banner ไม่มีข้อมูลจริงจากภาพอ้างอิงลงใน source
ตัวจับภาพเฉพาะงานอยู่ `artifacts/ux-reference/reference_capture.py` และไม่ commit

การตรวจนี้พบปัญหาที่ชุดก่อนยังไม่ครอบคลุม: ประวัติ FAIL เก่า8162นาที
พร้อมข้อความเหตุผล ทำให้จอ1024มี scrollHeight459 ทั้งที่ viewport417
เพิ่ม regression แล้วตรวจ fail ก่อนแก้ (exit1) จากนั้นย่อข้อความอายุที่ซ้ำ
เป็นเช่น `8162 นาทีที่แล้ว` และให้ tooltip คง `ข้อมูลล่าสุดเมื่อ ...`
ลดเฉพาะ padding/line-height ของ banner จอเล็ก ไม่ลดขนาด font/controls
คงผล FAIL เดิม เหตุผล TIMEOUT และไม่ตีประวัติ Switch ล้มเหลวเป็น BLOCKED ปัจจุบัน
regression เดิมผ่านหลังแก้ (exit0) ไม่มีการผ่อน assertions

ภาพสุดท้ายทั้ง3ขนาดมี13การ์ด/12เส้น ไม่มีการ์ดพ้น zone/legend หรือ scroll overflow
poll_count0, notification worker หยุด, demo process ไม่มี และ evidence DB ไม่เปลี่ยน
ภาพสำหรับเทียบหน้าตาหลักคือ `artifacts/ux-reference/1920x1080-F3.png`
ไม่ใช้สีแดง/เขียวหรือเส้นจำลองนี้เป็นหลักฐานสถานะของเครื่องจริง

ผลดิบชุดล่าสุด:

```text
Ran 332 tests in 75.107s

OK
EXIT_CODE=0

Ran 116 tests in 20.649s

OK
EXIT_CODE=0

Ran 13 tests in 11.989s

OK
EXIT_CODE=0
```

F3 handoff1024x496/1360x616/1920x1009 exit0ทั้งหมด
คำสั่ง child เต็มพร้อม env ของ F3 อยู่ `artifacts/ux-reference/verification-commands.json`
และ raw output อยู่ `*-raw.txt` ใน directory เดียวกัน คำสั่ง parent ใช้
Python runtime เดิมกับ `artifacts/ux-reference/reference_capture.py --isolate`
สำหรับจับภาพ และเพิ่ม `--suite` สำหรับชุดทดสอบ โดยสร้าง HOME ชั่วคราว
และตรวจยืนยัน network namespace แยกก่อนเปิด loopback คำสั่งเต็ม/HEAD/hashes
รอบนี้อยู่ `artifacts/ux-reference/final-receipt.json`

ไฟล์แก้เพิ่มในรอบอ้างอิง: `desktop/f3_api/view.js`, `desktop/f3_api/view.css`,
`desktop/tests/test_ux_desktop_polish.py`, `desktop/UX_POLISH_REPORT.md`
และ `PROJECT_PROGRESS.md` ข้อจำกัด legacy scripts/ResourceWarning และ
รายการยังไม่ได้ตรวจสอบข้างต้นยังเหมือนเดิม งาน UX เผยแพร่ไป main แล้ว
การเผยแพร่ไม่ได้ติดตั้งหรือยืนยันการรับรองหน้างาน


## แก้ Python compatibility และความเป็นอิสระจาก hostname — 2026-11-12

งานรอบนี้เผยแพร่บน `main` เมื่อ 2026-11-13 จากฐาน `a3a2ef4`
ประกอบด้วย 3 commits: `fe0ffd9` (แก้ import/เพิ่ม regression), `f888a86` (แก้ hostname assertions),
และ `f14cf2e` (ปรับเอกสารและหลักฐาน compatibility) การเผยแพร่ UX เดิม 11 commits ยังคงเป็นข้อมูลข้างต้น

Verified on Python 3.12 + GTK4/WebKit 6.0 on a headless display: 13 UX tests pass;
full discovery 332 tests had 2 hostname-dependent failures (fixed in `f888a86`);
`Optional` import gap fixed in `fe0ffd9`.

baseline 332 tests นี้ใช้ source จาก `a3a2ef4` พร้อมเฉพาะ import ที่แก้แล้ว
เพื่อแยกปัญหา hostname ออกจาก startup crash หลังแก้ทั้งหมด full discovery
ผ่าน335 tests (332เดิม + regression AST ใหม่3) ที่ hostname ทดสอบซึ่งไม่ใช่ fedora
regression ไม่ต้องใช้ GTK ผ่าน3/3ทั้ง Python3.12และ3.14 และสำเนาไฟล์ที่เอา
Optional import ออกทำให้ regression ล้มเหลวจริง ไม่ผ่อน assertions เดิม
ก่อนแก้ import app จริงบน3.12ล้มด้วย NameError หลังแก้ import สำเร็จพร้อม asyncua

pyflakes ตรวจ desktop/*.py ทั้ง38ไฟล์ พบ Optionalหนึ่งจุดและ serializationสองจุด
ใน app.py จึงเติม import จาก dependency เดิมตามขอบเขตการแก้ undefined names
หลังแก้เหลือ undefined names0 ส่วน67 warningsอื่นคงเดิม ไม่แก้ unused imports/locals
literal local-user ยังคงเป็น negative assertion เพื่อป้องกันการใช้ username
ส่วน test_f3_local.py มีข้อกำหนดให้มี non-loopback interface จึงเตรียม interface
ทดสอบใน namespace โดยไม่เปลี่ยน test หรือ interface ของเครื่องหลัก

การตรวจGUIใช้ Python3.12.3/GTK4.14/WebKit API6.0 ใน container ชั่วคราวผ่าน xvfb-run
network ปิด ไม่มี IP/route ที่เชื่อมออกสำหรับ interface ทดสอบ ใช้ HOME/XDGชั่วคราว
Python3.14ตรวจเฉพาะ AST regression; GUIบน3.14ยังไม่ได้ตรวจสอบ
ยังมี ResourceWarning ของ unclosed event loop และ Gtk.Dialog deprecation warnings
ข้อมูลนี้ไม่ใช่การตรวจรับ Windows/WinCC/PLC/LAN/Telegramจริง

ตรวจ source contracts เพิ่มบน Python3.12 จำนวน116 tests พบ2 failuresซ้ำทั้ง baseline
และหลังแก้ในสภาพแวดล้อมเดียวกัน: readiness loopback (GetEndpoints เป็น SKIPPED)
และ MQTT fresh snapshot (collector exit1) ยังไม่ยืนยันสาเหตุและไม่แก้ backend นอกขอบเขต
รอบแรกที่ container ยังไม่มี psutil/non-loopback interface มีข้อผิดพลาด setupเพิ่ม
เก็บ raw output เดิมไว้ แล้วเติมเฉพาะสภาพแวดล้อมโดยไม่แก้ tests ก่อนรันชุดหลักผ่าน
คำสั่งเต็ม ผลดิบ และรายการ67 warnings เก็บเป็นหลักฐาน local แยกจาก public source
