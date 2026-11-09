# กฎเหล็ก (ห้ามละเมิด)

1. ห้ามมี mock, fake, faker, Math.random หรือตัวเลข/สถานะที่แต่งขึ้นในโค้ดที่รันจริง (`src/`, `server/`) ข้อมูลทุกตัวต้องมาจากตาราง `probe_evidence` เท่านั้น
2. ไม่มีหลักฐาน = UNKNOWN ตรวจแล้วล้มเหลว = บันทึกสาเหตุจริง (TIMEOUT / NO_ROUTE / REFUSED / CERT_ERROR) ห้ามแปลงเป็นสำเร็จ และห้ามใช้ subnet ต่างกันแทนผลตรวจ route จริง
3. ตัวเลข Remote hosts, UA sessions, Read receipts และ rows ต้อง COUNT จาก DB ห้ามนับในหน้าเว็บ
4. อนุภาคเกิดจาก event ของแถวที่เพิ่ง INSERT เข้า `probe_evidence` เท่านั้น ไม่มี event = ไม่มีอนุภาค ห้ามวนลูปสร้างข้อมูลจราจรเอง
5. ทั้งหมด read-only ต่อ PLC/WinCC ห้ามเขียนค่า สั่งงาน หรือเรียก method ที่เปลี่ยนระบบอุตสาหกรรม
6. ตัวจำลองสำหรับเทสต์ต้องอยู่ `tools/sim/` และทำงานเป็นโปรเซสแยก UI ต้องแสดง SIMULATED เมื่อ source เป็น sim ข้อมูลทดสอบ/แถวตัวอย่างอยู่ใน `tests/` เท่านั้น ห้ามปนเป็นข้อมูล runtime จริง
7. จบทุกงานต้องแปะรายการไฟล์ที่แก้ คำสั่งที่รันจริง และ output ดิบ ถ้ายังไม่ได้ทดสอบต้องเขียน "ยังไม่ได้ตรวจสอบ" ห้ามเดาว่าผ่าน และต้องรัน `scripts/no_fake_check.sh` ก่อนจบงานทุกครั้ง

## Phase 4 ที่ผู้ใช้อนุญาตหลัง phase3.1 ผ่าน

- Phase3.1 ผ่านและติดตั้งแล้ว ผู้ใช้อนุญาตต่อ phase4 ทันที: อ่าน OPC UA เฉพาะ endpoint/IP/port/NodeId ที่ตั้งไว้แบบ read-only และทดสอบ simulator แยก process ไม่ใช่การเปิด OPC DA/เขียนค่าหน้างาน
- เก็บ GetEndpoints/session/read/certificate metadata จาก protocol จริง; tag_samples และ ua_read ต้อง commit atomically พร้อม evidence_id/quality/source/timestamps ห้ามใช้ค่าเก่าเป็นค่าปัจจุบันเมื่อ fail หรือ binding เปลี่ยน
- ใช้ PKI เดิมสำหรับ Basic256Sha256; None ต้องตั้งชัดเจนและแสดงว่าไม่ยืนยัน secure channel ไม่มี auto-trust/fallback และไม่มี credentials ใน URL
- `collector.run` เป็นคำสั่งเริ่มเอง; --loop ต้องมี interval_s ไม่เริ่มจาก F3/API/การเปิดไอคอน การเปิด F3 อ่าน DB เท่านั้น
- อ่าน ip_forward จาก /proc และแสดงเตือนเมื่อ1 ห้ามเปลี่ยนค่า OS; แยก observer ของ NIC/route/forwarding ให้ตรงจริง
- tools/sim/opcua_server.py และ set_level.py จำกัด127.0.0.1:4850 ต้อง sim:true ตัวอย่าง/DB/keys ทดสอบอยู่testsหรือprivate data ห้ามนำ simulator rows/target ไปปะปน DB หน้างาน
- ไม่เริ่ม phase5/Telegram ในงานนี้ ไม่เพิ่ม dependency/service/network change/commit/push

## คำสั่งล่าสุด — Phase 3.1 และ Phase 4 หลังผ่าน (2026-11-06)

- ผู้ใช้ให้แก้ 6 รายการ phase3.1 และเมื่อผ่านให้ต่อ phase4 ทันที ไม่ต้องถามยืนยันเฟสอีก
- สีหลักแสดงผลตรวจที่มีหลักฐาน; freshness/STALE และอายุเป็นคนละฟิลด์ ห้าม STALE ทับผลสำเร็จหรือล้มเหลวเดิม
- SQLite state OBSERVED_LOCAL พร้อม COUNT(*)/MAX(ts) จาก DB; Remote hosts ตรวจแล้ว/ตอบสนองจาก SQL; ส่วนยังไม่ได้สร้าง NOT_BUILT
- Router ใช้ ICMP/ARP เท่านั้น ห้าม TCP4840 สำหรับ router; อนุญาต DNS resolve + certificate-verified TLS api.telegram.org:443 โดยไม่มี HTTP หรือข้อความ
- Fedora ต้องแสดง local_nic/IP/CIDR/route ต่อ OT จาก DB และเทียบ subnet จริง ห้ามใช้ subnet ต่างกันอนุมาน NO_ROUTE/อุปกรณ์เสียหรือใช้ route ยืนยันสาย OT
- Edge ต้องมีคู่ actor/target และ evidence_id เท่านั้น ไม่มีหลักฐานห้ามสร้าง fan-line/Telegram delivery; arrowhead และป้ายอายุแยกชัด
- Phase4: OPC UA client read-only, GetEndpoints/session/read configured NodeIds, tag_samples อ้างอิง evidence_id, ip_forward จาก OS และเตือนเมื่อ1, loop ตาม interval config; ตัวจำลอง asyncua tools/sim/ แยก process/127.0.0.1:4850/configsim:true, UI SIMULATED
- การอนุญาตนี้ไม่รวม PLC/WinCC write, OS network/service เปลี่ยนแปลง, Telegram send หรือเฟส5 ห้ามติดตั้ง dependency โดยไม่อนุมัติ

## ลำดับงานที่ผู้ใช้กำหนด — 2026-11-06

- ทุกเฟสเริ่มด้วย "อ่าน AGENTS.md ก่อน" ทำทีละเฟส และต้องผ่านเกณฑ์เฟสก่อนหน้าก่อนเริ่มเฟสถัดไป
- เฟส 1–3 ผ่านแล้ว; ปัจจุบัน phase3.1 แก้ backend/frontend ตามคำสั่งล่าสุด และต่อ phase4 เมื่อผ่าน
- ผู้ใช้อนุญาต SVG/WebView + API ภายในเครื่องในไอคอนเดิมไว้แล้ว; ใช้เพื่อ F3 เท่านั้น ไม่มีเว็บไซต์หรือไอคอน Review ใหม่
- เฟส 4 read-only OPC UA/ตัวจำลองแยกโปรเซส และเฟส 5 Task/Outbox/Telegram เป็นข้อกำหนดของงานถัดไป ไม่ใช่สิทธิ์ให้ข้ามเกณฑ์
- เลขพอร์ต/timeout, schema, enum และ error classification ที่กำหนดการทำงานไม่ใช่ค่าตรวจวัด การใส่ค่าเหล่านี้ในโค้ดต้องไม่สร้างผลสำเร็จหรือ telemetry ขึ้นเอง
- เก็บ IP หน้างาน/config/DB/credentials ในพื้นที่ส่วนตัวนอก source และนอกแพ็กเกจ รักษาโปรแกรมที่ไอคอนเดิมเปิดและข้อมูลตั้งค่าเดิม
- targeted read-only route/ping/TCP จำกัด 6 IP ที่ผู้ใช้ระบุและพอร์ต 4840; เฟส 3 อนุญาต probe_once ตามเกณฑ์ยืนยันสี/เหตุผล/อนุภาคจริง ไม่ใช่การ sweep, OPC UA read, write หรือ Telegram send
- เฟส 3 ให้ frontend เป็นเจ้าของ API เดิมบน 127.0.0.1 เมื่อผู้ใช้เข้า F3 และปิดเมื่อออก/ปิดหน้าต่าง API อ่าน DB แบบ read-only ไม่เริ่ม collector เอง; เปิด GTK ที่ F1 ไม่เปิด listener
- ทุกค่า state/reason/last_check_ts/source/counters ใน F3 มาจาก API เท่านั้น metadata config เดิมใช้ชื่อ/role/zoneเพื่อจัดวาง ไม่มีการนำ observed/state จาก config มายืนยันผลตรวจ

## ขอบเขตเดิม (คงไว้เมื่อไม่ขัดกับคำสั่งผู้ใช้ล่าสุด)

# AQUA native desktop scope

User-authorized rebuild: native desktop frontend and RPM delivery, not a website. Continue the existing read-only CSV/SQLite/authenticated-LAN backend. No browser/webview, no UI HTTP listener, no website deployment. GTK4 frontend talks to the private owned Node host over stdin/stdout.

WinCC/PLC access remains strictly READ ONLY. No tag writes, PLC commands, reverse-control channel, scans, routing/NAT/bridge/firewall changes, production access or actual Telegram sends during development. Local AQUA spool/config/export writes are allowed only in owned storage outside the source. Retain cursor/ACK/dedup/quality safeguards. Default idle: no child process, source access, fixture generation, egress probe or transfer on opening. Runtime is unavailable without an approved read channel; never substitute CSV/LAB silently. LAB fixture requires explicit selection. Capture and transfer approvals are separate, default off and reset on process restart. Remembered scope only skips the dialog after a manual start click. Telegram dry-run and loopback transport only in this increment. Real CSV input is explicitly selected and stays byte-for-byte unchanged.

This repository is public: no original SCADA samples, infrastructure addresses, credentials, generated enrollment, runtime databases, workstation paths or plant-specific tag names in commits/packages. Use generic LAB tags; import actual tag names only into private local configuration at runtime. No fabricated WinCC/Windows/physical-LAN verification claim.

Build and test on Linux first; create a real RPM and test its installed payload. .exe is not claimed built/tested on Linux. Existing web assets are regression fixtures only; exclude them and their entry points from the RPM.

## Actual-use increment authorized after G2

The user now requests actual runtime development instead of simulation and confirms OPC DA exists but has NOT been officially enabled/approved. Develop real Windows-local OPC DA read-only client and explicit authenticated HTTPS deployed roles; this supersedes the prior increment's loopback-only implementation scope, not the ban on production access/config changes. Do not activate/connect OPC DA, enable WinCC services, change network settings or send real Telegram messages in development. Windows client must require operator confirmation of prior organizational authorization and explicit manual start; readiness only reads registration. No simulation in normal installed workflow. Keep legacy simulation solely in explicitly gated developer tests. Never claim Windows/WinCC/physical-LAN acceptance from Linux tests.
