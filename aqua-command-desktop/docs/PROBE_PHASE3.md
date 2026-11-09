# อ่าน AGENTS.md ก่อน — เฟส 3: F3 จาก API เท่านั้น

เปิด AQUA COMMAND จากไอคอนเดิมและเลือก F3 ไม่ต้องเปิดเว็บไซต์หรือไอคอน Review แยก
F3 ใช้ SVG ใน WebKit ที่ติดตั้งอยู่แล้ว ไม่เพิ่ม dependencies

## ข้อมูลและ lifecycle

- เมื่อเข้า F3 frontend เปิด phase2API เดิมแบบ read-only บน 127.0.0.1 และ port ที่ OS จัดให้
  เมื่อออก F3 หรือปิดหน้าต่างจะปิด API ที่ตนเป็นเจ้าของ เปิดแอปอยู่ที่ F1 ยังไม่สร้าง WebView/API
- GET `/api/topology` เป็นแหล่ง state/reason/last_check_ts/source และ counters เพียงแหล่งเดียว
  frontend โหลดใหม่เมื่อ SSE event และทุก 1.6 วินาทีเพื่อรับ TTL/ความผิดพลาดของ backend
- ไม่มีการเริ่ม collector, ping/TCP, OPC UA, Task หรือ Telegram จากการเปิด F3 หรือกดโหลดหลักฐาน
  ปุ่มโหลดหลักฐานอ่าน API อีกครั้งเท่านั้น การตรวจใหม่ยังใช้ `python -m collector.probe_once`
- API/collector/derive_state ของเฟส 2 คง implementation เดิม ไม่มี backend route/schema ใหม่ในเฟสนี้
  HTML/CSS/JS อยู่ในโปรแกรมและ load inline โดยใช้ origin ของ API เดียวกัน ไม่มี static server เพิ่ม
- ชื่อ/role/zone จาก config เดิมใช้จัดวางเท่านั้น ค่า observed/state/value ใน config ไม่เข้า F3
  ไม่อนุมาน NO_ROUTE/UNKNOWN จาก subnet เครื่องนี้ สถานะล้มเหลวมาจาก API ตามผลตรวจจริง
- ผังแบ่ง SCADA → Fedora → ฝั่งอินเทอร์เน็ต ส่วนที่ API ยังไม่มีสถานะ (client ภายในเครื่อง,
  Task Engine, SQLite health, Outbox, Telegram, มือถือ) เป็น UNKNOWN โดยแยกคำอธิบายไว้
  การมีแถวใน SQLite ไม่ใช้ยืนยันการทำ Task/ส่ง Telegram สำเร็จ

Remote hosts หมายถึง host ที่เคยมี target checks รวมผลล้มเหลว UA sessions/read receipts
เป็นหลักฐานสำเร็จสะสม ไม่ใช่ active sessions ดูสัญญา SQL เต็มใน PROBE_PHASE2.md
ตัวเลขทั้งสี่แสดงตาม API โดยตรง ไม่มี frontend COUNT หรือ placeholder ศูนย์

## SSE และอนุภาค

รับ `/api/stream` และสร้าง SVG object หนึ่งตัวต่อ rowid ใหม่ที่รับมาเท่านั้น
ตัวเดิมวิ่งออกเป็น probe น้ำเงิน เมื่อ result=ok เปลี่ยนเป็น reply เขียวอมฟ้าและย้อนกลับ
ถ้าล้มเหลวมีขาออกอย่างเดียวแล้วจางหาย ไม่มีอนุภาคต่อไป Task/Outbox โดยไม่มีหลักฐาน
เหตุการณ์ local inventory มีเส้นทางภายในเครื่อง แยกจาก target ทางเครือข่าย

อนุภาคแสดงผลตรวจที่บันทึกแล้ว ไม่ใช่ packet capture (เช่น route lookup เป็นการตรวจ OS)
ไม่มี event ใหม่ = ไม่มีอนุภาคและไม่มี RAF loop ค้าง หลัง reconnect จะเริ่ม live stream ใหม่
ไม่เปิด animation จากประวัติที่ขาดช่วง หากซ่อนหน้า/ออก F3 จะล้างอนุภาค

เคารพ `prefers-reduced-motion: reduce`: คงสีและตัวเลขจาก API แต่ไม่สร้างอนุภาค
state/source/เวลาตรวจไม่ถูกเปลี่ยนจากการเปิดหรือปิด motion

## API/SSE ขาดและ Inspector

API หรือ SSE ขาดจะแสดง "ไม่ได้รับข้อมูลจาก backend" หยุด/ล้างอนุภาค แสดง counters เป็น —
และทำเครื่องหมายข้อมูลค้าง จนกว่าทั้ง API และ SSE กลับมา การรับ API สำเร็จอย่างเดียว
ไม่ใช้กลบ SSE failure ค่า timeout ของ fetch 1.2 วินาทีรวมกับรอบโหลดทำให้ตรวจ API loss
ในหน้าที่แสดงอยู่ภายใน 5 วินาที SSE ที่เงียบโดยไม่มีแถวใหม่เป็นปกติ ไม่ใช้ความเงียบแทน failure

แต่ละการ์ดแสดงเวลาจาก last_check_ts จริงหรือยังไม่มีหลักฐาน คลิก/Enter เปิด Inspector
ที่เรียก `/api/evidence` และแสดง JSON แถวดิบเลือกคัดลอกได้ ไม่มี probe/เปลี่ยนสถานะเมื่อเลือก
source=sim ติดป้าย SIMULATED ตามแถว DB ป้ายนี้ไม่เกิดจากการใช้ loopback/config alias

การ refresh คงโหนด DOM เดิมเพื่อไม่ให้การเลือก/โฟกัสหลุด ผังแนวนอนบน desktop และสามโซน
แนวตั้งบนหน้าจอแคบ มีการเลื่อนเมื่อ inventory ใหญ่ ไม่มีการตัดโหนดออกเพื่อให้ภาพดูครบ
F1/F2/F6 ยังใช้ navigation เดิม ส่วน passive OS cache ของ F1 และ config inventory สำหรับ
observability คงอยู่แยกกัน ไม่ใช้เป็น telemetry ของ F3

## ตรวจสอบและขอบเขต

```bash
python3 -B -m unittest discover -s tests -p 'test*phase*.py' -v
bash scripts/no_fake_check.sh
```

Tests/browser fixture อยู่ tests/ และใช้ temporary DB เท่านั้น เพิ่ม scanner ให้ตรวจ
desktop/f3_api/ และ desktop/f3_api_view.py ด้วย นอกเหนือจาก runtime roots เดิม
Acceptance และภาพ native/Chrome จริงอยู่ในรายงาน phase3 ของ workspace

เฟส 4–5, UA protocol, tag samples และ Telegram delivery ยังไม่เริ่มในงานนี้
ไม่มี Windows/EXE, RPM build หรือ load/soak ระยะยาว acceptance ในเฟสนี้
