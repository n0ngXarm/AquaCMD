# Hybrid Lab operations

คำสั่งในเอกสารนี้ใช้เฉพาะ isolated Lab ที่สร้างไว้แล้ว จาก `aqua-command-desktop`
ผู้ใช้ทั่วไปเปิดผ่านไอคอน Desktop; คำสั่งด้านล่างสำหรับผู้ดูแล Lab

## Health และการกู้คืน

```bash
python3 observability/grafana/lab_control.py status
python3 observability/grafana/lab_owner_manage.py status
python3 observability/grafana/tests/lab_verify.py aqua-f3 aqua-f4 aqua-f1 aqua-f2 aqua-diagnostics
```

อ่าน URL และ container IDs จาก private receipt เท่านั้น
`status` ตรวจ ownership label; owner manager ตรวจ PID/cwd/cmdline และปฏิเสธ PID ที่ถูกนำไปใช้ใหม่
เมนู **Grafana → ตรวจสถานะ Grafana** ใน GTK ตรวจ loopback health ใน background
Grafana down ใช้หน้า native ต่อได้; producer ไม่ต้องเรียก Grafana เพื่อเก็บข้อมูล
source down ต้องแสดง query ERROR/NO DATA ไม่มี measurement fallback
frozen producer ต้องลดเป็น STALE ตาม TTL; first CPU/rate sample และ counter reset เป็น NULL

สำหรับ Lab นี้เท่านั้น หลังตรวจ ownership แล้ว:

```bash
python3 observability/grafana/lab_control.py start
python3 observability/grafana/lab_owner_manage.py start
```

การ restart ในการทดสอบที่ผ่านมาแตะเฉพาะสอง container และ owner ของ Lab นี้
ไม่มีระบบ auto-upgrade; `--pull=never` ใช้ images ที่ตรวจ digest แล้ว

## ปิด/disable

ปิดเฉพาะ consumer โดย core owner ยังอยู่:

```bash
python3 observability/grafana/lab_control.py stop
```

จบการทดลองทั้งหมด:

```bash
python3 observability/grafana/lab_owner_manage.py stop
python3 observability/grafana/lab_control.py stop
```

สำหรับ checkout ที่เปิด opt-in ไว้ ให้เลิกกำหนด `AQUA_OBSERVABILITY_CONFIG`
หรือเปลี่ยน `enabled` เป็น `false` ใน private config แล้วเปิดโปรแกรมใหม่
default-disabled path ไม่เปิด socket/observability threads
ไม่ต้องเปลี่ยน PKI, Tasks, Tag mapping, SQLite schema หรือ credentials ของแอป
การปิด GTK ยังคงใช้ close handler เดิม; bridge cleanup เพิ่มเฉพาะ optional resources ของตัวเอง
F8 ไม่ถูกเปลี่ยนให้เป็นคำสั่งหยุด Grafana container

ถ้าต้องถอน Lab ออก ให้ stop ตามด้านบนก่อน สำรองหลักฐานและ private secrets ตามนโยบาย
จากนั้นลบเฉพาะ container IDs ใน `private/state.json` ที่ยังมี
`io.aquacommand.lab=hybrid-20261105`, internal network ชื่อเดียวใน receipt,
checkout/artifact ของ Lab และไอคอน **AQUA COMMAND Hybrid Lab.desktop** เท่านั้น
อย่าใช้ container/image prune หรือ reset repository และอย่าลบไอคอน AQUA COMMAND เดิม
ขั้นตอนลบจริงยังไม่ได้ดำเนินการในงานนี้

## Backup / restore

แยก source bundle กับ private state; private backup มี secrets ต้อง mode0600 และห้ามเข้า Git
source bundle ใช้ exact increment patch/manifest ที่ส่งมอบ พร้อม baseline archive ของ current tree
อย่าใช้ `git diff HEAD` อย่างเดียว เพราะมี pre-existing dirty F3/app/workspace changes

สำรอง Grafana DB แบบ consistent โดย stop consumer ก่อน (owner/core ไม่ต้องหยุด):

```bash
python3 observability/grafana/lab_control.py stop
umask 077
tar -czf observability/grafana/private/lab-backup.tgz -C observability/grafana private/data private/provisioning private/admin-password private/grafana-key private/id-key private/projection-token private/mcp-token private/viewer-password
python3 observability/grafana/lab_control.py start
```

ชื่อ backup ต้องไม่ชนไฟล์ที่ต้องเก็บ; ใช้ชื่อใหม่ทุกครั้ง
archive นี้ไม่รวม application SQLite/profile, browser cookies, screenshots หรือ socket/PID receipts
อย่าเปิดเผย key/password หรือแนบ private backup ใน review
เก็บ `id-key` เพื่อให้ opaque Tag context เดิมยังตรงกัน; เก็บ `grafana-key` คู่กับ Grafana DB

Restore เฉพาะ Lab เดิมที่หยุดแล้วและตรวจ ownership:

1. สำรอง current private state อีกชุด; ตรวจ archive ว่ามีเฉพาะ paths ที่ระบุ ไม่มี absolute/parent traversal
2. คืน data/provisioning/secrets ใน worktree ของ Lab เดิม ภายใต้ owner เดิมและ private0700/files0600
3. ห้ามคืน `owner-running.json`, stale socket path หรือ container IDs ของเครื่องอื่น
4. ใช้ pinned images/plugin ชุดเดียวกับ backup; ใช้ lifecycle `start` เพื่อสร้าง owner config/socket ที่ถูกต้อง
5. เปิด owner แล้วตรวจ health, plugin signature, Viewer403, MCP และ actual panel queries
6. ถ้าไม่ผ่าน ให้ stop Lab และคืน private backup ก่อนหน้า; ห้ามแก้ runtime DB เพื่อให้ dashboard ผ่าน

**NOT TESTED:** archive restore บนเครื่องใหม่และ disaster recovery เต็มรูปแบบ
failure/restart/recovery ของ Lab ปัจจุบันทดสอบจริงแล้ว; ไม่ใช่หลักฐาน restore หรือ 24/7 stability

## Dashboard / dependency rollback

Dashboard JSON อยู่ใน `dashboards/`; Grafana provisioning เป็น read-only source of truth
ก่อนแก้ให้สำรองไฟล์ที่ deploy อยู่และ hashes; build scripts สร้าง JSON ที่มี UID คงที่
คืน JSON/provisioning จาก bundle ก่อนหน้าทั้งชุด แล้วตรวจ `validate_dashboards.py`
รอ provisioning reload หรือ restart เฉพาะ owned Grafana ของ Lab แล้วตรวจ API/Browser อีกครั้ง
rollback ครั้งแรกของ Hybrid increment นี้คือ disable integration; ไม่แทนที่ existing dirty source ด้วย HEAD

เปลี่ยน Grafana/plugin/MCP โดย pin release+digest/checksum ใหม่และทดสอบ signature/queries/failure/GUI ก่อน
ห้ามแก้ image tag ให้เป็น `latest` หรือเปิด auto plugin install
ถ้า downgrade Grafana DB ให้ restore DB+grafana-key ที่สำรองก่อน upgrade
ไม่มีการทดสอบ downgrade/migration ข้ามเวอร์ชันในงานนี้
