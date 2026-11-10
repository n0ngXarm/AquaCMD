# F3 "ผังการสื่อสาร" (Network Topology & Communication Pipeline)

เอกสารสรุปสถาปัตยกรรมและการทำงานของหน้า F3 ในโปรแกรม AQUA COMMAND (WinCC V8.1 SCADA & Task Manager)

---

## 1. โครงสร้างไฟล์

```text
aqua-command-desktop/
├── desktop/
│   ├── f3_api_view.py       # GTK4 WebKit6 Controller โหลดหน้า F3 และควบคุม loopback API
│   ├── f3_projection.py     # Presentation Adapter แปลง SQLite evidence เป็น F3 contract
│   ├── f3_handoff.py        # Core mapping logic และการตรวจ Task groups
│   ├── f1_api/formal-theme.css # ธีมสว่างและมืดที่ F1/F3 ใช้ร่วมกัน
│   └── f3_api/
│       ├── detect.mjs       # โมดูลฟังก์ชัน detect() กฎสถานะ 6 ระดับ (Node & Browser)
│       ├── index.html       # ผัง 3 โซน (OT LAN, Dual-Homed Collector, External WAN)
│       ├── view.css         # การจัดวาง F3 ใช้สีจากธีมและรองรับ prefers-reduced-motion
│       ├── view.js          # จัดการ dynamic SVG, จุดวิ่ง, วงคลื่น, popup รายละเอียด
│       └── fonts_embedded.css # @font-face base64 ฟอนต์ IBM Plex Sans Thai และ Mono
├── fonts/
│   ├── IBMPlexSansThai-Regular.woff2
│   ├── IBMPlexSansThai-Medium.woff2
│   ├── IBMPlexSansThai-SemiBold.woff2
│   ├── IBMPlexMono-Regular.woff2
│   ├── IBMPlexMono-Medium.woff2
│   ├── OFL.txt              # SIL Open Font License v1.1
│   └── fonts.css            # CSS อ้างอิงฟอนต์ในเครื่อง
└── tests/
    ├── f3_handoff_detect.mjs # Unit tests สำหรับ detect() ครบทั้ง 14 เคส
    └── test_f3_*.py         # สวีตทดสอบสัญญาระบบ, สคีมา, และ WebKit integration
```

---

## 2. การแมปคอลัมน์จากฐานข้อมูล `probe_evidence` (Adapter Mapping)

ตารางฐานข้อมูล SQLite ในเครื่อง (`~/.local/share/aqua-command/probe/data.db`):
```sql
CREATE TABLE probe_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    "check" TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT,
    latency_ms REAL NOT NULL,
    ts TEXT NOT NULL,
    detail TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'real' CHECK (source IN ('real','sim'))
);
```

การแมปไปยัง F3 Node JSON Schema (`GET /api/f3/evidence`):
| คอลัมน์ใน SQLite | ฟิลด์ใน F3 JSON | หมายเหตุ / กฎการแปลง |
|---|---|---|
| `host` | `node.id` / `label` | ไอพีของแหล่งหลักฐานและชื่ออุปกรณ์จากไฟล์ตั้งค่า |
| `result` | `last.ok` | `result == 'ok'` แปลงเป็น `true`, ค่าอื่น (timeout, fail) แปลงเป็น `false` |
| `ts` | `last.ts` | เวลาในรูปแบบ ISO-8601 UTC |
| `check` | `last.method` | วิธีตรวจ เช่น `ua_read`, `ua_session`, `ua_endpoints`, `ping`, `arp` โดยกล่อง SQLite ใช้ `sqlite_readback` เมื่ออ่านหลักฐานที่บันทึกแล้วกลับมา |
| `detail` / `error` | `last.detail` | ข้อความรายละเอียด เช่น ค่า RTT, ข้อผิดพลาด, หรือจำนวน Tag ที่อ่านได้ |
| `source` | `last.source` | `'real'` หรือ `'sim'` (แยกแยะข้อมูลจริงกับข้อมูลจำลอง) |
| `tag_samples` (ตารางรอง) | `last.task_groups` | ตรวจสอบ Tag ที่อ่านได้ว่าตรงกับ Task เฝ้าระวังใดใน F2 |

`GET /api/stream` ส่ง SSE ชื่อ `evidence` พร้อมรหัสแถวที่ SQLite บันทึกแล้ว F3 ตรวจรหัสและแหล่งที่มาก่อนแสดงจุดวิ่ง ส่วนสถานะและอายุหลักฐานอัปเดตจาก `/api/f3/evidence` ทุกประมาณ 2 วินาที

---

## 3. กฎสถานะ 6 ระดับ (`detect()`)

ลำดับความสำคัญของสีเส้นเมื่อปลายสองด้านมีสถานะต่างกัน:
`FAIL` > `BLOCKED` > `STALE` > `UNVERIFIED` > `NOT_BUILT` > `OK`

1. **NOT_BUILT (`– ยังไม่สร้าง`)**: ฟังก์ชันถูกประกาศว่ายังไม่สร้างในระบบ
2. **UNVERIFIED (`? ยังไม่ตรวจ`)**: มีการคอนฟิกโหนดไว้แต่ยังไม่เคยมีบันทึกหลักฐานในตาราง
3. **FAIL (`✕ ไม่ตอบ`)**: หลักฐานล่าสุดมีค่า `ok = false` หากหลักฐานหมดอายุ F3 ระบุว่าเป็นผลตรวจเดิม
4. **BLOCKED (`⊘ ทางผ่านล่ม`)**: สวิตช์ทางผ่านที่ตั้งค่าไว้มีหลักฐานการตรวจล่าสุดเป็น `FAIL` และยังไม่หมดอายุ โหนด SCADA ที่ผ่านสวิตช์นั้นแสดง `BLOCKED`
5. **STALE (`◔ ข้อมูลเก่า`)**: หลักฐานล่าสุด `ok = true` แต่เวลาเก่ากว่า `stale_ms` (60 วินาที) หรือเวลาเครื่องเพี้ยน
6. **OK (`✓ ปกติ`)**: หลักฐานล่าสุด `ok = true` และอายุไม่เกิน 60 วินาที

---

## 4. วิธีรันชุดทดสอบ (How to Run Tests)

```bash
# 1. ทดสอบตรรกะ detect() ด้วย Node.js (ผ่านครบ 14 เคสตาม detect.test-cases.json)
node --test tests/f3_handoff_detect.mjs

# 2. ทดสอบสัญญา F3 API View, Evidence, และ Projection ด้วย Python
PYTHONPATH=.:src python3 -m unittest discover -s tests -p 'test_f3*.py'

# 3. ทดสอบการตรวจจับ No Fake Data
bash scripts/no_fake_check.sh
```

---

## 5. วิธีเปิดโหมด Demo (จำลองสถานการณ์)

- **ทดลองใน Desktop** ใช้ปุ่ม **จำลองและส่ง Telegram** เพื่อเริ่ม `tools/sim/f3_demo.py` แยกโปรเซส ตัวจำลองฟังที่ loopback เก็บหลักฐานในฐานข้อมูลชั่วคราว และแสดงป้าย `SIMULATED` ปุ่มนี้อาจส่งข้อความทดสอบจริงเมื่อมีการตั้งค่า Telegram จึงใช้เมื่อได้รับอนุญาตให้ส่งแล้วเท่านั้น
- **ตรวจโดยไม่ส่ง Telegram** ใช้ `env -u F3_TEST_TELEGRAM_CONFIG F3_TEST_DEMO=1 python3 -B tests/f3_handoff_native.py` ในเซสชัน GTK ที่แยกจากระบบจริง เทสต์ใช้ค่าตั้งชั่วคราวและตรวจสถานะเมื่อไม่มีค่าตั้ง Telegram
- **โหมดใช้งานจริง** อ่านเฉพาะฐานข้อมูลหลักของเครื่อง การส่ง `?demo=1` ให้ API ไม่สามารถเปลี่ยนแหล่งข้อมูลเป็นโหมดจำลองได้
