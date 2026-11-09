# AQUA COMMAND · Grafana Hybrid Lab

ชุดส่งตรวจสำหรับ GTK4 F1–F8 ใช้ Grafana เป็น consumer แบบอ่านอย่างเดียว
สถานะ: **REVISE ก่อน commit/production** ดูผลจริงในรายงานส่งมอบ
โปรแกรมที่ติดตั้งเดิมยังไม่ได้รับการแก้ไขใน increment นี้

## เปิดใช้งานบนเครื่องพัฒนา

ดับเบิลคลิก **AQUA COMMAND Hybrid Lab** บน Desktop
ไอคอนจะเปิดเฉพาะ container และ GTK owner ที่มี receipt ของ Lab นี้
หน้าต่างช่วยเข้าสู่ระบบแสดงบัญชี `aqua-viewer` และรหัสผ่านแบบซ่อน
กดรูปตาเมื่อต้องการดูรหัสผ่าน แล้วเลือก **เปิด Grafana · F3**
ใน GTK ใช้เมนู **Grafana** เพื่อเปิด Dashboard ของแต่ละหน้าใน Browser แยก
F5 มีปุ่ม **Trend** สำหรับ Tag ที่เลือก ส่วนการตั้งค่าทั้งหมดยังอยู่ใน GTK

Lab ใช้ `AquaWinCCWindow` และ backend classes จริงจาก checkout นี้กับโปรไฟล์แยก
ไม่ได้จำลอง Observable Store และไม่ได้เริ่ม polling หรือ notification worker
ข้อมูล host เป็นค่าจาก Fedora จริง; สถานะอุปกรณ์อาจเป็น CONFIGURED/UNKNOWN
เมื่อไม่มีการอ่านที่ตรวจสอบแล้ว F1/F2 แสดง NO DATA ตามจริง
การทดสอบนี้ยังไม่ยืนยันข้อมูลจาก WinCC/PLC หรือการส่ง Telegram จริง

## การแบ่งหน้าที่

| หน้า | Grafana | GTK4 |
| --- | --- | --- |
| F1 | Live values, quality, timestamps, trends/history | เลือก Tag และตรวจรายละเอียด |
| F2 | Event timeline, thresholds, outbox, attempts/failures | สร้าง/แก้/ลบ Task, rules, enable/disable |
| F3 | Dynamic Node Graph และ Inspector แสดง provenance | Device management และ manual actions ที่ได้รับอนุญาต |
| F4 | CPU, RAM, disk/I/O, NIC, process, DB/worker metrics | Native host view สำรอง |
| F5 | ประวัติ Tag ผ่าน opaque context link | Catalog, search, filtering, NodeId mapping |
| F6 | Connection/read/certificate/delivery diagnostics | Endpoint, PKI/trust, credentials, Telegram, start/stop |
| F7 | ประวัติ local refresh และ probe receipts ที่มีอยู่ | Scan/Refresh เดิม; Grafana ไม่สร้าง probe |
| F8 | เมนูสถานะ/เปิด Grafana | Close/exit semantics เดิม |

F1/F2 ใช้พื้นที่ overview เดิมร่วมกับ task workspace ตาม navigation ของแอปเดิม
มีลิงก์ F1 และ F2 แยกในเมนู Grafana เพื่อเลือก Dashboard ให้ตรงงาน

## เส้นทางข้อมูล

`existing OPC UA reader/poller → existing store/SQLite/task/outbox → optional owner bridge`
`→ authenticated Unix socket → internal read-only proxy → Infinity backend parser → Grafana`

bridge เปิดด้วย `AQUA_OBSERVABILITY_CONFIG` เท่านั้น; ค่าเริ่มต้นปิดและไม่สร้าง socket/thread
อ่าน owner objects บน GTK thread ทุก 5 วินาที; เก็บ host samples และอ่าน SQL ใน background
เพิ่มเพียง optional endpoint/session metadata บน read receipts เดิม
ไม่มี OPC UA client, poller หรือ Telegram worker ชุดใหม่สำหรับ Grafana
browser/bridge startup failure ไม่ขัดขวาง core lifecycle

Producer เปิด `/v1/runtime/health`, `snapshot`, `graph`, `devices`, `tags`, `worker`,
`host`, `host-history`, `interfaces`, `history`, `events`, `outbox`, `attempts`, `probes`, `refresh`
ผ่าน Unix socket ที่จำกัด owner และ bearer authentication
รองรับ GET เท่านั้น; ไม่มี generic SQL/API proxy หรือ control endpoint
Grafana ไม่ได้ mount SQLite runtime DB

ประวัติรับ `window=1h|24h|7d` หรือ `from/to` แบบ epoch milliseconds ในอดีตไม่เกิน 7 วัน
ใช้ parameterized SQL, `mode=ro`, `query_only`, timeout 0.1s
คืน observations ล่าสุดไม่เกิน 2,000 rows และ events/outbox/attempts อย่างละไม่เกิน 500 rows
Tag filter ทำก่อน LIMIT; coverage ระบุ `BOUNDED_RECENT_ROWS` จึงไม่อ้างว่าได้ทุก row ตลอดช่วง
เลือกคอลัมน์ที่ปลอดภัยเท่านั้น ไม่อ่าน payload, recipient, token หรือ raw error

## ความหมายข้อมูล

- IP/endpoint ที่ตั้งค่าไว้ไม่ใช่หลักฐานว่า online; NIC carrier เป็นสถานะ local link เท่านั้น
- REACHABLE, TCP_CONNECTED, OPC_UA_CONNECTED และ READ_VERIFIED แยกกัน
- session จาก manual read ที่ปิดแล้วแสดง CLOSED แม้มี read receipt ล่าสุด
- UNKNOWN, Bad, wrong target, missing evidence และ STALE ให้ค่าปัจจุบันเป็น NULL
- Good `0` และ `false` ยังคงเป็นค่าจริง ไม่ใช้เป็น fallback ของข้อมูลหาย
- แต่ละ field ใช้ timestamp/TTL ของหลักฐานตนเอง; owner ที่ยังทำงานไม่ทำให้ read เก่าสดขึ้น
- เวลาเป็น UTC; ใช้ source/arrival timestamps และ engineering unit ของข้อมูลจริง
- catalog 457 Tags ไม่ใช่ telemetry 457 Tags
- ประวัติ schema เดิมไม่มี endpoint/session binding: แสดง `UNBOUND_LOCAL_RUNTIME`
- generic SENT ไม่ใช่ Telegram/provider ACK และไม่สร้าง source-to-delivery trace ขึ้นเอง
- ใช้ HMAC IDs และ generic labels; configured/observed IP/hostname จริงไม่ถูกเปิดเผยตาม default privacy
- Node Graph แสดง logical path มีคำอธิบายกำกับ ไม่ใช่สาย physical network และไม่มี packet animation
- SYNTHETIC acceptance ใช้ datasource/dashboard คนละ UID ไม่มี runtime route/fallback และลบทิ้งหลังทดสอบ

## Deployment และสิทธิ์

ดู [VERSION_MATRIX.md](VERSION_MATRIX.md) สำหรับ pins/digests/checksums
ใช้ rootless Podman internal network ชื่อ `aqua-hybrid-20261105`
Grafana publish เฉพาะ `127.0.0.1`; proxy ไม่ publish host port และทั้งคู่ไม่มี default route
ไฟล์ `private/state.json` เป็นแหล่ง URL/container IDs ปัจจุบัน ห้ามเดา port
source/provisioning/plugins เป็น read-only; root filesystem read-only, cap-drop ALL,
no-new-privileges, resource limits และ restart-on-failure 3 ครั้ง
ไม่มี anonymous access, embedding หรือการปิด security headers

จำเป็นต้องมี bootstrap admin เพียงบัญชีเดียวสำหรับ instance ใหม่
ผู้ใช้ทั่วไปและ MCP ใช้ Viewer; provisioning ปฏิเสธ dashboard edits (ตรวจจริงได้ HTTP 403)
MCP binary ทางการเรียกผ่าน `mcp_launch.py` ด้วย `--disable-write` และจำกัดกลุ่ม tools
token อ่านจากไฟล์ owner-only แล้วฉีดเข้า child environment ไม่มีใน argv/TOML/Git
`.codex/config.toml.example` เป็น template; config จริงถูก ignore
MCP handshake/queries ผ่านแล้ว แต่ automatic project load ใน worktree ที่ยังไม่ trusted
ยังเป็น **BLOCKED** และ tools ในแชตนี้ **NOT_ADVERTISED**; ไม่ได้เปลี่ยน global trust settings

proxy มีข้อยกเว้น `label=disable` เฉพาะ container ของ Lab เพื่อเชื่อม host Unix socket
ไม่ได้เปลี่ยน SELinux enforcing, Grafana label หรือ host policy
ต้อง review IPC policy ก่อนนำ production ไปใช้
ดู [OPERATIONS.md](OPERATIONS.md) สำหรับ health, backup/restore, rollback และ disable

## ตรวจซ้ำโดยผู้พัฒนา

จาก `aqua-command-desktop` ของ isolated checkout:

```bash
python3 observability/grafana/tests/validate_dashboards.py
python3 observability/grafana/tests/lab_verify.py aqua-f3 aqua-f4 aqua-f1 aqua-f2 aqua-diagnostics
python3 observability/grafana/tests/mcp_verify.py --calls
python3 -B -m unittest discover -s observability/grafana/tests -p test_lab_lifecycle.py -v
python3 -B -X faulthandler observability/grafana/tests/native_verify.py
node observability/grafana/tests/browser_verify.mjs
```

GUI/socket/container checks ต้องใช้สิทธิ์ตาม environment และใช้ Lab นี้เท่านั้น
Playwright ติดตั้งเฉพาะใน ignored `private/browser`; ใช้ Chrome ที่มีอยู่แล้ว
ไม่มี dependency เพิ่มใน application packaging
ผล unit tests ไม่ได้พิสูจน์ 24/7 stability หรือ field/production acceptance
