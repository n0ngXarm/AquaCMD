# ผล redesign native GTK4 + WebKitGTK และ Light/Dark

บันทึกการตรวจวันที่ 13 พฤศจิกายน 2026 เผยแพร่บน `main` ที่ `10d1aa6`
ฐาน `f14cf2e` จากงาน compatibility; ไม่รวมสาม commits ของฐานในจำนวนแปด commits ของงาน redesign นี้
ขอบเขตการดำเนินงานเป็น GUI/presentation และ test harness ภายใน `desktop/` เท่านั้น
เผยแพร่บน `main` ถึง `10d1aa6` เมื่อ 2026-11-13; ไม่มีการติดตั้งแอป, ติดตั้ง dependency ในระบบผู้ใช้ หรือแก้ operational config

## พฤติกรรมที่ส่งมอบ

Light เป็นค่าเริ่มต้น และสลับ Light/Dark ระหว่างใช้งานได้จากหัวแอปหรือ F6
GTK เปลี่ยน CssProvider และ WebViews ทั้ง F1/F3 เปลี่ยน `data-theme` โดยไม่ reload หน้า
Document-start UserScript ใช้ธีมที่เลือกในการโหลดหน้าครั้งต่อไปด้วย
UI controls อยู่ตรงกัน; บันทึกเพียง `ui_prefs.json` ใน CONFIG_DIR แบบ atomic replace,
mode 0600, schema มีเฉพาะ `theme` และ fallback เมื่อไฟล์ไม่ถูกต้อง
การสลับไม่หยุด polling/tasks/notification และไม่เริ่มการอ่านหรือการส่งข้อความ
ทดสอบกับ workers ที่หยุดอยู่โดยตรวจว่าเมธอด stop ไม่ถูกเรียก; ไม่ได้ทดสอบกับงานหน้างานที่กำลังทำงานจริง

ใช้ `theme_tokens.py` เป็นแหล่ง tokens ทั้งสองธีม ตรวจ parity กับ `formal-theme.css` ทุกชื่อและค่า
สี legacy ใช้ `palette-*` เพื่อรักษาภาพใน commit ย้าย tokens แรก; components ใหม่ใช้ semantic tokens
native CSS สี่ไฟล์และ `CSS_DATA` ไม่มี raw hex/rgb ตาม lint โดยไม่มี allowlist
ปุ่ม Primary/Secondary/Ghost/Danger สูง 34px, compact 30px, radius 6px; panels 10px
ตัวอักษร body web 14px, native 10.5pt, secondary native 10pt; Thai line-height 1.5 รวม F3 จอเล็ก
สถานะ UNKNOWN/STALE/FAIL/BLOCKED/READ ONLY/SIMULATED/ยังไม่สร้าง ยังคงข้อความและความหมายเดิม

F1 ยุบ Task ที่ผูกเป็นจำนวนเฉพาะเมื่อมีข้อมูลข้างชื่อ Tag; ไม่เปลี่ยน membership ของ Task
UNKNOWN ใช้จุดและข้อความโดยไม่มีกรอบ, ชนิด Tag เป็นข้อความพร้อม tooltip,
ชื่อและกลุ่มที่ยาวมี tooltip, ปุ่มใกล้ข้อมูล และแถวปกติสูง 38px
F2 แบ่ง form/cards และช่อง label คงที่ พร้อมทางกลับไปเลือก Tag เมื่อรายการว่าง
F6 เนื้อหาอยู่กึ่งกลาง กว้างไม่เกินประมาณ 1000px ความสูงตามเนื้อหา;
หน้าจอเตี้ยใช้ scroll ตามเดิม แถวสถานะไม่ดูเหมือน input และ tabs active ชัดเจน
F3 คงโครงสร้างสามโซน ลำดับ nodes และการอ่านหลักฐานเดิม เปลี่ยนเฉพาะ presentation

## Commits ของงานนี้

- `6187aad refactor(desktop): centralize theme tokens without changing Dark visuals`
- `27118e9 feat(desktop): switch Light and Dark live with private UI preference`
- `fbbec70 feat(desktop): unify chrome and keep one active navigation tab`
- `7d68e78 feat(desktop): align native and WebKit action and widget styles`
- `24b8d50 feat(desktop): make the catalog compact and keep unknown states quiet`
- `ca87e06 feat(desktop): organize Task forms and center connection settings`
- `d4eb265 style(desktop): apply shared F3 surfaces and verify both theme fits`
- `10d1aa6 test(desktop): verify both themes and document native redesign acceptance`

## สถานะการเผยแพร่

ณ วันที่ 2026-11-13 การเปลี่ยนแปลงทั้งหมดรวม 11 commits ได้รับการเผยแพร่บน `main` ถึง `10d1aa6` (ต่อจากฐานเดิม `a3a2ef4`):

### ฐานเดิม (Base commits)
- `445e1e6`: ฐาน canonical UX เดิม
- `a3a2ef4`: เผยแพร่ UX polish 11 commits เดิม (เมื่อ 2026-11-12)

### รายการ 11 Commits ที่เผยแพร่บน main (a3a2ef4..10d1aa6)
1. `fe0ffd9 fix(desktop): import annotation and certificate serialization names` (Python compatibility)
2. `f888a86 test(desktop): compare identity with the actual OS hostname` (Python compatibility)
3. `f14cf2e docs(desktop): reconcile published UX and Python compatibility evidence` (Python compatibility)
4. `6187aad refactor(desktop): centralize theme tokens without changing Dark visuals` (Light/Dark redesign)
5. `27118e9 feat(desktop): switch Light and Dark live with private UI preference` (Light/Dark redesign)
6. `fbbec70 feat(desktop): unify chrome and keep one active navigation tab` (Light/Dark redesign)
7. `7d68e78 feat(desktop): align native and WebKit action and widget styles` (Light/Dark redesign)
8. `24b8d50 feat(desktop): make the catalog compact and keep unknown states quiet` (Light/Dark redesign)
9. `ca87e06 feat(desktop): organize Task forms and center connection settings` (Light/Dark redesign)
10. `d4eb265 style(desktop): apply shared F3 surfaces and verify both theme fits` (Light/Dark redesign)
11. `10d1aa6 test(desktop): verify both themes and document native redesign acceptance` (Light/Dark redesign)

### จำนวนการทดสอบ (Test Counts)
- Desktop tests: 353 tests ผ่าน (353 passed)
- Source contracts: 116 tests ผ่าน (116 passed)
- F3 usability & layout fit tests: ผ่าน 3 ขนาดหน้าจอ (1024x600, 1360x768, 1920x1080) ทั้ง 2 ธีม (Light และ Dark)
- WCAG AA Contrast checks: ผ่านครบทุก 134 แถว (text >= 4.5:1, non-text >= 3:1)

### รายการที่ยังคงเปิดอยู่ (Still-Open Items)
- Git history clearance (`history_clearance: NOT_EVALUATED`): การตัดสินใจของเจ้าของระบบ
- การติดตั้ง/อัปเดตโปรแกรมบนเครื่องปฏิบัติการจริง (การเผยแพร่ source บน git ไม่ใช่การติดตั้งโปรแกรม)
- การทดสอบกับ WinCC / PLC / LAN / SCADA และ Telegram จริงในภาคสนาม (ยังคงใช้โหมดจำลอง SIMULATED LAB เท่านั้น)
- การทดสอบบน Python 3.12 / 3.14 GUI บนสภาพแวดล้อมจริงของผู้ใช้

## แปดข้อที่ตรวจจากภาพ baseline

| ข้อ | ผล baseline ที่พบ | ผลหลังแก้ / หลักฐาน |
|---|---|---|
| 1 ลำดับชั้นสี | พื้น Dark คล้ายกันหลายส่วน | Light มีพื้น gray/white และ shadow; Dark แบ่ง bg/surface/surface-2 |
| 2 รูปแบบปุ่ม | รูปแบบต่างกันหลายแบบและ F6 Primary ไม่เด่น | สี่ variants + icon; status cluster เป็น icon/text ไม่เป็นปุ่ม |
| 3 GTK/WebKit ต่างกัน | Dropdown มีกรอบซ้อนและ checkbox ขาว | skin และ tokens ร่วมกัน; parsing tests ทั้งสองธีม |
| 4 F1 chips/ช่องว่าง | UNKNOWN/type มีกรอบซ้ำ, Task ว่าง, Binary Tag ถูกตัด | UNKNOWN เงียบแต่ยังอ่านได้, type เต็ม, ยุบ Task ว่าง |
| 5 footer ถูกเลือก | **ไม่ได้เกิดทุกครั้งตอนเริ่ม**; เกิดหลังเปลี่ยนไป F6 | ไม่ focus label อัตโนมัติ; regression ยังตรวจ select/copy ได้และ tooltip เต็ม |
| 6 พื้นที่แนวตั้ง | fixture เดิมเห็น 5 แถวที่ 1024×600 (ต่างจากตัวเลข 6 ในคำขอ) | หลังแก้ 9 แถว; ที่ 1360×768: 8→13; 1920×1080: 15→22; footer 38→22px |
| 7 nav ซ้ำ | F1/F2 active พร้อมกันเมื่อ Task dialog เปิด | F2 เพียงปุ่มเดียว และกลับ F1 เมื่อปิด; ตรวจทั้ง WebKit และ fallback native |
| 8 F6 | ใช้พื้นที่เต็มและมีบริเวณว่าง; status ดูคล้าย input | content อยู่กึ่งกลางตามความสูงธรรมชาติ, form/cards และ status row |

commit tokens แรก: ภาพ Dark 16/18 ตรงทุกพิกเซล อีกสองภาพ F2 ต่าง 52 และ 50 pixels
เฉพาะบริเวณ scrollbar ที่จางอยู่หลัง dialog จึงไม่อ้างว่าภาพทั้งหมดตรง 100%
ข้อมูลอยู่ `artifacts/ux-theme/token-dark/pixel-parity.json` เทียบกับ `before/`

## ผลทดสอบสุดท้าย

- Runtime: Python 3.15.2, GTK 4.24.1, WebKit 2.54.2/API 6.0 บน headless Wayland
- Full desktop discovery: **353 tests ผ่าน, exit 0** รวม UX เดิม 13, theme switch 9, token/parity/lint/contrast 5, preference 4 และ import compatibility เดิม
- Source contracts: **116 tests ผ่าน, exit 0**
- ชุดแคบหลังปรับ expectations: workspace production 11 และ UX 13 ผ่าน
- F3 fit ทั้ง Light/Dark × 1024×496, 1360×616, 1920×1009: **6/6 ผ่าน** ด้วย assertions ของ handoff เดิม ไม่ผ่อน fit checks
- ภาพ native สุดท้าย **48 ภาพ**: Light 24 + Dark 24; F1–F6 ขนาดจริงสามขนาด และ dialogs ยืนยันอีก 6 ภาพต่อธีม
- Native captures ยืนยัน header ≤56px, footer ≤32px, nav active หนึ่งปุ่ม, footer ไม่มี selection อัตโนมัติ, F1 ≥9 แถว, F6 content ≤1000px และ F3 ไม่มี scroll/card overflow
- poll_count=0, notification worker หยุด และ evidence DB ไม่เปลี่ยนตลอดการจับภาพ
- Contrast 50 text pairs และ 84 UI pairs ผ่านทุกคู่; ต่ำสุด Light 4.541/3.921 และ Dark 4.743/4.558 (text/UI)
- Final guards: no_fake_check PASS; privacy current tracked tree 534 files ไม่พบ findings; staged/base whitespace checks และ desktop-only scope ผ่าน (ผลเต็มใน final-guards.json)

RAW summary:

```text
desktop-tests
----------------------------------------------------------------------
Ran 353 tests in 98.017s

OK
/usr/lib64/python3.15/asyncio/base_events.py:763: ResourceWarning: unclosed event loop <_UnixSelectorEventLoop running=False closed=False debug=False>

EXIT_CODE=0
source-contracts
----------------------------------------------------------------------
Ran 116 tests in 24.142s

OK

EXIT_CODE=0
```

ผลก่อนแก้ที่เก็บไว้:

- Regression F1 ใหม่: fail ก่อนแก้ (`rows=7`, `rowHeight=44`, type ไม่เต็ม, UNKNOWN มี border); ผ่านหลังแก้
- UX ชุดหนึ่งพบ type 13px ต่ำกว่า font floor เดิม; ปรับเป็น 13.5px และรัน assertions เดิมผ่าน
- Full discovery ครั้งแรก 353 tests ล้ม 5 assertions: F2 ต้อง active F1, F6 ต้องเป็น icon,
  และ F6 สาม sections ต้องสูงเต็มพื้นที่ เป็น expectations เดิมที่ขัดกับ redesign ที่ผู้ใช้กำหนด
  ปรับเฉพาะ assertions เหล่านี้ให้ตรวจ single-active, shortcut/focusability และ centered/natural-height/max-width
  คงการตรวจ config/password exclusion/Telegram local-save/Task/OPC ทุกข้อไว้ และเพิ่มตรวจคืน active F1 หลังปิด dialog
- Capture รอบ layout จบ 18 ภาพ exit 0 แต่ parent ถูกยุติ exit 143 ก่อน tests ที่เหลือ; ไม่ทราบสาเหตุแน่ชัด
  เก็บภาพ/ผลไว้ และรัน tests ที่ขาดใหม่ ไม่อ้างว่า parent เดิมผ่าน

## Contrast ของสองธีม

เป็นค่าจากคู่สี CSS/tokens ที่ระบุ ไม่ใช่การรับรองทุกพิกเซลหรือทุก platform
ข้อความ 25 คู่ต่อธีม (รวม statuses บน tint, ปุ่ม normal/hover/pressed/disabled, header): เกณฑ์ 4.5:1
ขอบควบคุม/focus/grid/เส้นสถานะและกราฟ 42 คู่ต่อธีมบน bg/surface/surface-2: เกณฑ์ 3:1
เส้นแบ่งตกแต่ง `line` ไม่ใช้แทนขอบควบคุมหรือเส้นกราฟที่ต้องสื่อความหมาย
พบป้าย `.f2-pill-running` ใน Light เดิม 2.855:1 จึงเปลี่ยนไปใช้ `ok`/`ok-tint` ทั้งสองธีม

| ข้อความ / สถานะปุ่ม | Light | Dark |
|---|---:|---:|
| GTK disabled Task action | 6.760 | 7.978 |
| GTK standby label | 4.541 | 4.743 |
| GTK running status | 6.262 | 7.593 |
| GTK catalog badge | 6.034 | 8.026 |
| ink | 14.330 | 13.370 |
| mut | 6.481 | 8.504 |
| faint | 6.031 | 6.803 |
| unv | 5.310 | 7.461 |
| ok | 6.262 | 7.593 |
| fail | 6.302 | 7.257 |
| stale | 6.227 | 7.478 |
| blocked | 6.518 | 7.199 |
| nb | 5.720 | 7.436 |
| Primary | 7.142 | 8.569 |
| Primary hover | 9.606 | 10.721 |
| Secondary | 14.330 | 13.370 |
| Secondary hover | 12.130 | 8.306 |
| Secondary pressed | 12.128 | 8.736 |
| Ghost hover | 6.284 | 5.899 |
| Danger | 7.184 | 5.798 |
| Danger hover | 6.302 | 7.257 |
| Disabled | 6.031 | 6.803 |
| Header | 13.236 | 13.848 |
| Header secondary | 8.946 | 9.359 |
| F6 status | 6.481 | 8.504 |

| เส้น / ขอบควบคุม | Light | Dark |
|---|---:|---:|
| Control border on bg | 3.921 | 6.764 |
| Control border on surface | 4.417 | 5.698 |
| Control border on surface-2 | 4.110 | 4.558 |
| Focus on bg | 6.341 | 9.748 |
| Focus on surface | 7.142 | 8.211 |
| Focus on surface-2 | 6.647 | 6.568 |
| Grid on bg | 3.921 | 6.764 |
| Grid on surface | 4.417 | 5.698 |
| Grid on surface-2 | 4.110 | 4.558 |
| g1 on bg | 6.341 | 9.748 |
| g1 on surface | 7.142 | 8.211 |
| g1 on surface-2 | 6.647 | 6.568 |
| g2 on bg | 5.676 | 10.710 |
| g2 on surface | 6.393 | 9.022 |
| g2 on surface-2 | 5.949 | 7.217 |
| g3 on bg | 5.852 | 10.380 |
| g3 on surface | 6.592 | 8.744 |
| g3 on surface-2 | 6.134 | 6.995 |
| g4 on bg | 6.964 | 10.014 |
| g4 on surface | 7.844 | 8.435 |
| g4 on surface-2 | 7.300 | 6.748 |
| g5 on bg | 5.310 | 10.748 |
| g5 on surface | 5.981 | 9.053 |
| g5 on surface-2 | 5.566 | 7.242 |
| ok on bg | 6.346 | 11.095 |
| ok on surface | 7.148 | 9.346 |
| ok on surface-2 | 6.652 | 7.476 |
| fail on bg | 6.379 | 9.901 |
| fail on surface | 7.184 | 8.340 |
| fail on surface-2 | 6.686 | 6.672 |
| stale on bg | 6.056 | 11.171 |
| stale on surface | 6.821 | 9.410 |
| stale on surface-2 | 6.348 | 7.528 |
| blocked on bg | 6.417 | 9.921 |
| blocked on surface | 7.228 | 8.357 |
| blocked on surface-2 | 6.727 | 6.685 |
| unv on bg | 5.310 | 11.072 |
| unv on surface | 5.981 | 9.327 |
| unv on surface-2 | 5.566 | 7.461 |
| nb on bg | 5.808 | 10.250 |
| nb on surface | 6.541 | 8.634 |
| nb on surface-2 | 6.088 | 6.907 |

## ภาพก่อน / หลัง และคำสั่งจริง

Artifacts เป็นหลักฐานท้องถิ่น ไม่รวมใน commits:

- `artifacts/ux-theme/before/`: ก่อน redesign 18 ภาพ F1–F6 สามขนาด
- `artifacts/ux-theme/token-dark/`: token migration พร้อม pixel-parity JSON
- `artifacts/ux-theme/light/` และ `dark/`: ธีมละ 24 ภาพ รวม 48 ภาพ
- แต่ละธีมมี `{1024x600,1360x768,1920x1080}-{F1,F2,F3,F4,F5,F6}.png`
  และ `{size}-confirm-close.png`, `{size}-confirm-simulated-telegram.png`
- F2.png เป็น Task dialog ที่เปิดจริงภายใน native window; native-layout.json เก็บขนาดจริง/rows/nav/footer/ขอบเขต F3
- ทุกภาพใช้ catalog LAB 457 รายการ, machine metrics ที่ระบุ SIMULATED และ DB disposable ไม่มี telemetry หน้างาน
  Switch/Router ใช้ documentation addresses; ไม่มีการคัดลอกข้อมูลเครื่องจริงมาใน source หรือภาพ
- F3 ในภาพที่ไม่มี evidence ยังคง UNKNOWN; fixtures ที่ทดสอบ BLOCKED/FAIL อยู่ใน tests เท่านั้น
- ภาพ confirmations ถ่ายก่อนกดยกเลิก ตรวจ `_open_demo` ไม่ถูกเรียก; ไม่เริ่ม simulator หรือส่ง Telegram

Exact argv ของ interpreter ส่วนตัว, exit code และ RAW output อยู่ `ux-commands.json` กับ `*-raw.txt`
ในแต่ละ directory: `light/`, `dark/`, `spec-regression/`, `final-regression/`
ตัว harness อยู่ `desktop/tests/ux_run.py` ใช้ HOME/XDG ชั่วคราว, AQUA_UX_TEST_PROFILE=1,
headless Mutter/Wayland และ user/network namespace แยก เปิดเฉพาะ loopback ภายใน namespace
คำสั่งกลุ่มที่ใช้ (path interpreter จริงอยู่ใน manifests ไม่ฝัง path ส่วนตัวลง repository):

```sh
unshare --user --map-root-user --net "$AQUA_PYTHON" -B aqua-command-desktop/desktop/tests/ux_run.py --stage after --capture --theme light --output artifacts/ux-theme/light
unshare --user --map-root-user --net "$AQUA_PYTHON" -B aqua-command-desktop/desktop/tests/ux_run.py --stage after --capture --theme dark --output artifacts/ux-theme/dark
unshare --user --map-root-user --net "$AQUA_PYTHON" -B aqua-command-desktop/desktop/tests/ux_run.py --stage after --test test_workspace_production --focused --fit --output artifacts/ux-theme/spec-regression
unshare --user --map-root-user --net "$AQUA_PYTHON" -B aqua-command-desktop/desktop/tests/ux_run.py --stage after --regression --output artifacts/ux-theme/final-regression
python3 -B aqua-command-desktop/desktop/tests/ux_contrast.py
bash aqua-command-desktop/scripts/no_fake_check.sh
python3 scripts/privacy_preflight.py
git diff --check f14cf2e
```

## ไฟล์ที่เปลี่ยนเทียบฐาน f14cf2e

- `aqua-command-desktop/desktop/PROJECT_PROGRESS.md`
- `aqua-command-desktop/desktop/UX_THEME_REPORT.md`
- `aqua-command-desktop/desktop/app.py`
- `aqua-command-desktop/desktop/f1_api/formal-theme.css`
- `aqua-command-desktop/desktop/f1_api/index.html`
- `aqua-command-desktop/desktop/f1_api/view.css`
- `aqua-command-desktop/desktop/f1_api/view.js`
- `aqua-command-desktop/desktop/f1_api_view.py`
- `aqua-command-desktop/desktop/f1_style.css`
- `aqua-command-desktop/desktop/f2_style.css`
- `aqua-command-desktop/desktop/f3_api/index.html`
- `aqua-command-desktop/desktop/f3_api/view.css`
- `aqua-command-desktop/desktop/f3_api_view.py`
- `aqua-command-desktop/desktop/style.css`
- `aqua-command-desktop/desktop/tests/test_theme_prefs.py`
- `aqua-command-desktop/desktop/tests/test_theme_switch.py`
- `aqua-command-desktop/desktop/tests/test_theme_tokens.py`
- `aqua-command-desktop/desktop/tests/test_workspace_production.py`
- `aqua-command-desktop/desktop/tests/ux_contrast.py`
- `aqua-command-desktop/desktop/tests/ux_native_capture.py`
- `aqua-command-desktop/desktop/tests/ux_run.py`
- `aqua-command-desktop/desktop/tests/ux_theme_fit.py`
- `aqua-command-desktop/desktop/theme_prefs.py`
- `aqua-command-desktop/desktop/theme_tokens.py`
- `aqua-command-desktop/desktop/theme_web.py`
- `aqua-command-desktop/desktop/workspace_style.css`

## รายการเว้นไว้ และยังไม่ได้ตรวจสอบ

- ไม่เพิ่ม mode ตามระบบ เพราะไม่ได้ยืนยัน reliable detection ข้าม runtime โดยไม่เพิ่ม dependency; เลือก Light/Dark ชัดเจน
- ไม่มีการแก้ backend, collector, schema, DB implementation, source config, Windows reader หรือ business logic
- Python 3.15.2 + GTK 4.24.1 + WebKit 2.54.2 (API 6.0) ผ่าน native headless ในรอบนี้
  Python 3.14 GUI และ Python 3.12 GUI ของ redesign ชุดนี้: **ยังไม่ได้ตรวจสอบ**
- การเปิดผ่านไอคอน/ธีม OS/profile ของผู้ใช้จริง, interactive desktop/Windows, WinCC/PLC/LAN จริง,
  Telegram จริง และ screen reader จริง: **ยังไม่ได้ตรวจสอบ**
- ยังพบ warnings ของ accessibility bus, GTK deprecated settings/dialogs, asyncio policy และ resource/event-loop/database cleanup
  ไม่อ้างว่า screen reader ผ่านหรือ warnings ถูกแก้
- Privacy guard ตรวจ current tracked tree เท่านั้น ไม่มี private-catalog comparison และ history clearance เป็น NOT_EVALUATED
- หลักฐานการตรวจนี้ไม่ใช่ field acceptance และไม่เปลี่ยนโปรแกรมที่ติดตั้งอยู่
