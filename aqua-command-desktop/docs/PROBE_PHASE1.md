# อ่าน AGENTS.md ก่อน — เฟส 1: Probe CLI เท่านั้น

จุดเข้าใช้งานจากรากโปรเจกต์คือ `python -m collector.probe_once` implementation อยู่
`src/collector/probe_once.py` ใช้ Python standard library, `ip` และ `ping` ไม่มี UI,
API listener, OPC UA client, Task Engine หรือ Telegram sender ในเฟสนี้

โปรแกรมอ่าน config ส่วนตัว `~/.config/aqua-command/probe_targets.json` และเก็บ DB ที่
`~/.local/share/aqua-command/probe/data.db` เลือกไฟล์อื่นได้ด้วย `--config` และ `--db`
ไม่ใช้ฐานข้อมูลของ GTK และไม่บรรจุข้อมูลหน้างาน/config ส่วนตัวลง source หรือแพ็กเกจ

โครงสร้าง config: `targets` เป็นรายการ object ที่มี `host` (IPv4 numeric) และ `port`
พร้อม `ping_timeout_s`, `tcp_timeout_s` ที่ระบุชัด ไม่ทำ DNS discovery หรือ subnet sweep
IP ที่ตรวจจริงมาจาก config เท่านั้น ไม่มี IP เป้าหมายฝังใน implementation

แต่ละรอบบันทึก `ip -j addr`, `ip -j route` ก่อน แล้วตรวจ `ip -j route get HOST`,
ping หนึ่งแพ็กเก็ต และ TCP connect หนึ่งครั้งตามลำดับของแต่ละ host การมี default route
ถือว่ามี route แม้เป้าหมายอยู่คนละ subnet ไม่ได้ยืนยันว่า host หรือ service ตอบ

ทุกแถวอยู่ใน `probe_evidence(id, host, check, result, error, latency_ms, ts, detail)`
`check` ถูก quote ใน SQL เพราะเป็น keyword ของ SQLite; `detail` เก็บ stdout/stderr,
argv/return code และ errno ที่เกิดขึ้นจริง Latency มาจาก monotonic clock ไม่ใช่เลข timeout
ที่ใส่แทนค่าที่วัดได้

`ok` เกิดจากการตรวจสำเร็จจริงเท่านั้น ผลล้มเหลวเก็บ TIMEOUT/NO_ROUTE/REFUSED/
UNREACHABLE/ERROR พร้อมเหตุผลจริง สิทธิ์ socket/เครื่องมือ OS ไม่พร้อมเป็น ERROR
ไม่กล่าวหาว่าอุปกรณ์ปลายทางเสีย โค้ดไม่ส่ง application payload หรือคำสั่ง PLC/WinCC

Exit 0 ของ CLI หมายถึงเก็บผลและ commit ครบ ไม่ได้หมายความว่าทุก host reachable
ผลล้มเหลวเป็นข้อมูลที่ต้องเก็บเช่นเดียวกับผลสำเร็จ Config/DB ผิดพลาดทำให้ CLI exit 1

ตรวจ syntax, OS-error handling, config validation, DB persistence และจริง TCP loopback:

```bash
python3 -B -m unittest discover -s tests -p test_probe_once_phase1.py -v
bash scripts/no_fake_check.sh
```

ตัวรับ TCP สำหรับทดสอบอยู่ `tools/sim/tcp_accept_server.py` เป็นโปรเซสแยกและพิมพ์
SIMULATED ชัดเจน ทดสอบกับ DB ชั่วคราวเท่านั้น ไม่ปนกับหลักฐาน 6 IP จริง
Scanner grep runtime ใน `src/`, `server/` (เมื่อมี) และ package entry `collector/`
ข้อจำกัด: grep ตรวจ token ที่ห้ามได้ แต่ไม่แทนการตรวจ logic/ผล runtime จริง

เฟส 2–5 ยังไม่ได้ตรวจสอบ/ยังไม่ได้เริ่มในงานนี้ ไม่อ้าง transport-open ว่าเป็น UA session,
read receipt, tag quality, pump state หรือผลส่ง Telegram
