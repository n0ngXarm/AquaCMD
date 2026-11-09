# อ่าน AGENTS.md ก่อน — เฟส 2: API/SSE ไม่มี UI

เพิ่มเฟส 2 ต่อจาก Probe CLI เดิม ใช้ Python standard library ไม่มี dependencies เพิ่ม
และไม่มีการเปิด listener/collector อัตโนมัติจากไอคอน GTK

## เริ่มแบบ explicit

รันจากรากโปรเจกต์จริง Config/DB ใช้ที่ส่วนตัวเดิม เลือกไฟล์อื่นด้วย `--config`/`--db`:

```bash
python -m collector.probe_once
python -m collector.evidence_api --port 0
```

คำสั่งแรกตรวจ targets ใน config จริงและ migrate DB เดิมแบบ transaction โดยเพิ่ม
`source TEXT NOT NULL DEFAULT 'real' CHECK(source IN ('real','sim'))` แถวเดิมคงข้อมูล/id
และได้ source real Target ต้องมี `sim: true` เป็น boolean จึงบันทึกแถวของ target นั้น
เป็น sim; การใช้ loopback ไม่เปลี่ยน provenance เอง NIC/route inventory ของ OS เป็น real

API stdout แสดง URL/port ที่ bind จริง เช่น `{"listen":"http://127.0.0.1:...","db":"..."}`
ใช้ port ที่ได้ในคำสั่งด้านล่าง หากกำหนด port เองแล้วใช้ไม่ได้ โปรแกรมแจ้ง error จริง
กด Ctrl+C เพื่อปิด ไม่มี system service หรือ autostart ในเฟสนี้

```bash
curl -sS http://127.0.0.1:PORT/api/topology
curl -sS 'http://127.0.0.1:PORT/api/evidence?host=HOST&limit=20'
curl -N http://127.0.0.1:PORT/api/stream
```

API เปิด SQLite ด้วย URI mode=ro และ query_only ไม่ migrate, สร้าง DB หรือบันทึกข้อมูล
หาก DB หาย/อ่านไม่ได้หรือ timestamp ไม่ถูกต้อง คืน error 503 พร้อมสาเหตุจริง ไม่คืน
success/counters เก่าจาก cache รองรับ GET เท่านั้น ไม่เปิด CORS และรับเฉพาะ local origin

## สถานะจากฟังก์ชันเดียว

`derive_state(rows, now)` ไม่ทำ I/O และเป็นจุดเดียวที่คำนวณสถานะ โหนดมาจาก target
config รวมกับ host ที่มี target check จริงใน DB ไม่มีแถวให้ state UNKNOWN และ
source/last_check_ts เป็น null Config เป็นรายการเป้าหมาย ไม่ใช่หลักฐานว่าเชื่อมต่อสำเร็จ

- ลำดับหลักฐานใช้ id ซึ่งเป็น SQLite rowid; source ใช้ค่าที่บันทึกในแถวล่าสุด ไม่รวม
  ผล real/sim เข้าด้วยกัน
- แถวล่าสุดอายุเกิน 60 วินาทีเป็น STALE; อายุเท่ากับ 60 วินาทียังอยู่ในช่วง freshness
- failure ใหม่ตัดความสำเร็จเก่าเป็น UNREACHABLE และ reason คง error จริง (ถ้า error
  ว่าง ใช้ result ที่บันทึก) route/ping success ไม่ล้าง transport failure
- หลัง failure ส่งเสริมได้เฉพาะความสำเร็จใหม่จริงที่ยังไม่เกิน 60 วินาที:
  tcp → TCP_OPEN, ua_session → UA_OK, ua_read → READ_OK ใช้ระดับสูงสุดที่ยังมีหลักฐาน
- route/ping/GetEndpoints success อย่างเดียวไม่ยืนยัน TCP session, UA session หรือ read
  จึงยังไม่ส่งเสริมระดับเหล่านี้ ความสำเร็จเก่าที่เกิน TTL ไม่ถูกทำให้สดด้วย route ใหม่
- reason ของ failure ก่อนการ recovery ไม่ถูกนำมาแสดงเป็นเหตุล้มเหลวปัจจุบันหลัง recovery

Topology คืน `nodes[{host,state,reason,last_check_ts,source}]`, `counters`,
`last_event_id` และ `generated_at` (เวลาเตรียม response ไม่ใช่เวลา telemetry)
ไม่มีการอ่าน NIC/network หรือ probe เมื่อ GET API

## ความหมาย counters (SQL ใน read transaction เดียวกับ snapshot)

| ชื่อ | SQL ที่นับ | ความหมาย |
|---|---|---|
| remote_hosts | COUNT(DISTINCT host) ของ route/ping/tcp/ua_endpoints/ua_session/ua_read | จำนวน host ที่เคยตรวจ รวมผลล้มเหลว ไม่ใช่ host ที่พร้อมใช้งาน |
| ua_sessions | COUNT(*) ที่ check=ua_session และ result=ok | หลักฐานสร้าง session สำเร็จสะสม ไม่ใช่ session ที่ยังเปิด |
| read_receipts | COUNT(*) ที่ check=ua_read และ result=ok | หลักฐานอ่านสำเร็จสะสม |
| committed_rows | COUNT(*) ทั้งตาราง | ทุกแถวที่ commit รวม local inventory และผลล้มเหลว |

ตัวเลขรวมมีทั้ง real/sim ตาม provenance ของแถว ศูนย์ได้จาก SQL จริง ไม่ใช่ placeholder
API evidence คืนแถวดิบเรียง id ล่าสุดก่อน `detail` คงเป็นข้อความ JSON เดิม
limit default 100, ช่วง 1–1000; host filter เป็น bound SQL parameter

## SSE

`/api/stream` ส่ง `id: ROWID`, `event: evidence`, `data: RAW_ROW_JSON` หนึ่ง event
ต่อแถวใหม่ที่ commit ติดตามทุก 500ms หากมี backlog จะส่งต่อเป็น batch ตามลำดับ
ไม่มีแถวใหม่ = ไม่มี body bytes, heartbeat หรือ event สร้างขึ้นเอง

การเชื่อมต่อใหม่เริ่มจาก MAX(rowid) ณ ขณะเชื่อมต่อ ไม่ replay ประวัติ หากมี header
Last-Event-ID จะส่งเฉพาะแถวหลัง cursor นั้น ไม่ส่งซ้ำภายในการเชื่อมต่อเดียว
หาก transport/DB ขัดข้อง stream ปิดและบันทึก error แยก ไม่ปลอมเป็น evidence event

## ตรวจสอบ

```bash
python3 -B -m unittest discover -s tests -p 'test*phase*.py' -v
bash scripts/no_fake_check.sh
```

แถวตัวอย่างอยู่ tests/ และ temporary DB เท่านั้น Tests ทดสอบ HTTP/SSE บน loopback
จริง ไม่เขียนแถวทดสอบลง DB หน้างาน API ยังอ่านประวัติ target checks ทั้งหมดเพื่อให้
derive_state ตัดสินจากบริบทครบ การทดสอบโหลด/retention ระยะยาวยังไม่ได้ตรวจสอบ
เฟส 3–5, UI, OPC UA และ Telegram ยังไม่เริ่มในงานนี้
