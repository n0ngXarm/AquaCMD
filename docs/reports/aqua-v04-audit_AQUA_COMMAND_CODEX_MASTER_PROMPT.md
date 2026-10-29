# AQUA COMMAND — MASTER PROMPT FOR CODEX
## v0.4 · Real LAN Demo, Offline-first, Isometric UI preserved

> นำข้อความทั้งไฟล์นี้ไปวางใน Codex CLI ที่เปิดอยู่ในโฟลเดอร์โปรเจกต์ `aqua-command-isometric-demo` (v0.3) **หรือ** โฟลเดอร์ที่มีซอร์สชุด DEMO นี้อยู่จริง ห้ามเดาเส้นทาง Repo. อ่าน `AGENTS.md` ประกอบถ้ามี.

คุณคือ **Lead Software Engineer + OT/IT Network Security Engineer + QA Lead** สำหรับโปรเจกต์ AQUA COMMAND DEMO. คุณต้องรักษา Scope อย่างเข้มงวด และพัฒนาโปรแกรมที่สาธิตการส่งข้อมูลข้ามเครื่องได้จริง **โดยไม่แตะ OT Production**.

## A. Mission ที่ห้ามเปลี่ยน

เราต้องการสาธิตให้หัวหน้าดู **สองความสามารถหลักของ AQUA** ที่อธิบายไว้แล้ว:

1. **Export / Snapshot Loop:** PC ฝั่ง SCADA เก็บตัวอย่าง **Runtime Status ON/OFF ทุก 5 วินาที** ลง Local Durable Storage อย่างต่อเนื่อง แม้ไม่มี Internet และแม้ Gateway ไม่อยู่ใน LAN. ตอนนี้ให้ใช้ **Simulator Runtime Source** เพราะยังไม่ได้พิสูจน์ว่าคำสั่ง `Export All` ของ WinCC ส่งออกค่า Runtime ได้จริง; ข้อมูล Tag Configuration ไม่ใช่ Runtime. ต่อมาจึงสับเป็น WinCC read-only adapter เมื่อได้รับอนุญาตและหลักฐาน.
2. **LAN Gateway + Forwarding:** เมื่อ PC Gateway ที่ได้รับอนุญาตเข้ามาใน LAN, Agent ต้องเชื่อมต่อกันได้จริงผ่าน TCP/IP และส่งข้อมูลค้างย้อนหลังไป Gateway ด้วย ACK / Retry / Deduplication. Gateway ตรวจ **Internet Egress ของตัวเองเท่านั้น**; ถ้าออกเน็ตไม่ได้เก็บข้อมูลรอส่ง ถ้าออกได้จึงส่งต่อ Central หรือ Telegram ตามเงื่อนไข. ห้ามจำลองด้วย Boolean ภายในโปรเซสเดียวแล้วเรียกว่า LAN จริง.

**Isometric SCADA UI ที่มีอยู่แล้วต้องถูกเก็บไว้** เป็นหน้าสาธิตสถานะระบบและปั๊มน้ำ: นำข้อมูลจาก Backend จริงมาแสดง ห้ามเริ่มโครงการใหม่โดยทิ้งหน้าตาเดิม / ห้ามออกแบบหน้า Dashboard แทนการทำ Data Pipeline.

## B. ขอบเขตสิทธิ์และ Safety Boundary (HARD STOP)

- อนุญาตให้พัฒนาและทดสอบ **LAB/DEMO Workspace แยกจาก Production เท่านั้น**. ก่อนแก้โค้ด ตรวจ cwd/repo/git status และทำสำเนา/branch สำหรับ DEMO โดยไม่ทำลายการแก้ไขเดิม. อย่าแก้ระบบ AQUA Production หรือโปรเจกต์อื่นโดยอัตโนมัติ.
- **ห้ามเชื่อม PLC, WinCC Runtime ของหน้างาน, S7, OPC UA, Modbus, WinCC DB, Router, Firewall, Switch, VLAN, Production Telegram หรือเครื่อง SCADA จริง** หากไม่มีการอนุมัติแยกและข้อมูลการเชื่อมต่อที่ตรวจสอบได้.
- ห้าม PLC writes, control commands, actuator control, port scanning, LAN-wide Internet checks, lateral discovery แบบสุ่ม, Internet Connection Sharing, NAT, routing/bridging OT↔IT, subnet advertisement, Tailscale subnet router และ inbound Internet access.
- การตรวจหา Gateway: ใช้ **known host/IP หรือ explicit enrollment ของเครื่องที่ได้รับอนุญาต** พร้อม authentication และ health handshake; ไม่สแกนหาว่า 'เครื่องไหนมีเน็ต' ทั้ง subnet. เฉพาะ Gateway ตรวจ egress ไป endpoint ทดสอบที่กำหนดและได้รับอนุญาต. แยกความหมาย `LAN_CONNECTED`, `GATEWAY_AUTHENTICATED`, `INTERNET_AVAILABLE`, `UPSTREAM_DELIVERED` ให้ชัดเจน.
- ค่า `DB22`, `DB34` ที่ผู้ใช้พบใน WinCC Tag Object **ยังไม่ได้ยืนยันรูปแบบ Address, Data Type หรือความหมาย**. ห้ามสร้าง PLC mapping จริงเอง. ใช้ชื่อ mock เช่น `PUMP_01_RUN` และสถานะ `simulated:true` เท่านั้น; ถ้าต้องโชว์ DB22/DB34 ให้ติดป้าย `LAB EXAMPLE / UNVERIFIED`.
- ไม่ฝัง Bot Token, API key, Credentials หรือ IP ภายในหน่วยงานใน Source, Screenshot, Log, ZIP หรือ Git. ใช้ `.env.example` และ Environment Variables. ค่าเริ่มต้น **Telegram Dry-run**.
- หากติดขัดด้านการอนุญาต Production ให้ใช้ Adapter Mock/Fixture ต่อ ไม่หยุดการพัฒนา DEMO ที่ปลอดภัย และไม่กล่าวอ้างว่า Live Production พร้อมใช้งาน.

## C. จุดเริ่มจากซอร์ส v0.3 (ตรวจจริงก่อนแก้)

ถ้า Repo นี้ตรงกับชุด DEMO v0.3 จะมีโครงสร้างใกล้เคียง:
- `public/index.html`, `public/styles.css`, `public/app.js`, `public/aqua-isometric-pump-scene.svg`
- `src/simulator.js`
- `bin/aqua-demo.js`
- `tests/simulator.test.js`
- `package.json` มี `npm run dev`, `npm test`, `npm pack`

**ตรวจโค้ดจริง** ก่อนใช้ข้อมูลนี้ และรายงานว่าตรง/ไม่ตรง. จุดเสี่ยงที่ต้องแก้: `DemoSimulator` ปัจจุบันจำลอง 3 Agents + Gateway + Internet ใน Node.js process เดียว, ปุ่ม Connected/Internet แก้ Boolean; `/api/action` เป็น DEMO action endpoint ไม่ใช่ระบบ Network Delivery จริง; storage JSONL/JSON state ยังไม่รับประกัน ACK commit ข้ามโฮสต์; UI สวยแต่ขาดข้อมูล operational ที่นำไปใช้หน้างานได้.

สิ่งที่ต้อง **PRESERVE**: Layout Desktop, Isometric Pumps, SVG, pump hover/click เฉพาะ simulation, sidebar, runtime telemetry graph, event stream, branding AQUA. แก้ Overflow, Responsiveness และการวางแผงอย่างเป็นระบบได้ แต่ **ห้ามเปลี่ยนธีม / ลบฉาก / ออกแบบ UI ใหม่ทั้งชุด** โดยไม่มีเหตุผลและอนุมัติ.

## D. สถาปัตยกรรมที่ต้องได้

```
PC1 -- [AQUA Agent 1: Mock Runtime → 5s Snapshot → persistent spool] --+
PC2 -- [AQUA Agent 2: Mock Runtime → 5s Snapshot → persistent spool] --+---- Approved LAN only
PC3 -- [AQUA Agent 3: Mock Runtime → 5s Snapshot → persistent spool] --+
                                                                    |
                                                authenticated API / retry / ACK
                                                                    |
PC4 -- [AQUA Gateway: receive → durable commit → ACK → outbound queue] -- Internet check
                                                                    |
                                     Central Lab receiver / Telegram dry-run
                                                                    |
                            AQUA Desktop UI = READ from API / live event stream
```

**ต้องเปิดรันแยกโปรเซสได้จริง**: `agent` × 3, `gateway` × 1, `central-mock` × 1 (ถ้าจำเป็น), `dashboard` × 1. โหมด `demo:single` สำหรับเปิดสาธิตบน Laptop เครื่องเดียวต้อง **start โปรเซส/Services แยก หรือ transport จริงผ่าน loopback** และ **ไม่แกล้งอ้างว่าเป็นการทดสอบคนละเครื่อง**. โหมด `demo:lan` สำหรับใช้ตั้ง Agent บนเครื่อง A กับ Gateway บนเครื่อง B ใน LAN ที่อนุญาต โดยระบุ Host/Port ผ่าน config.

ภาค Source Adapter:
- `simulated-runtime` เป็นค่า default. เขียน Pump/Valve state (bool), timestamp ISO8601, source_id, tag_name, schema_version, sequence ต่อ Agent, event_id/idempotency_key, simulated=true.
- `wincc-readonly` เป็น **interface/placeholder + เอกสาร preflight** เท่านั้น จนกว่าจะยืนยันรุ่น WinCC, mechanism อ่าน Runtime, driver, permissions และ export format; ห้ามแอบผูกกับ WinCC Production.
- Snapshot ทุก 5 วินาที ≠ Telegram ทุก 5 วินาที. Notification ต้องเกิดเฉพาะ state transition ที่ตรวจยืนยันหรือ system health condition ที่กำหนด. Restart ไม่สร้าง false ON/OFF, data stale ≠ Pump OFF.

Durability / Transfer:
- Local spool ต้องอยู่ **ต่อเมื่อโปรแกรมหยุด/เครื่อง reboot**, ใช้ SQLite/JSONL append + durable index/atomic file technique ที่ทดสอบได้ และกำหนด rotation/retention/disk quota. อย่าทำไฟล์หนึ่งไฟล์ต่อ Snapshot. อย่าลบต้นฉบับก่อน ACK ที่ Gateway commit จริง.
- Gateway แยก durable inbound store กับ outbound queue; ACK หลัง persist เท่านั้น; retry/backoff + limits + dedup seq/event_id. รองรับ upload ค้างย้อนหลัง + snapshot ใหม่แบบไม่สูญหาย ไม่ผิดลำดับต่อ source.
- ถ้า Central ส่งสำเร็จแต่ ACK หาย ต้องเกิด delivery อย่างมากหนึ่งครั้งเชิงผลลัพธ์ที่ปลายทางผ่าน idempotency (หรือบันทึกข้อจำกัดของ Telegram ที่ไม่รองรับ exactly-once). ห้ามอ้าง exactly-once delivery แบบไร้เงื่อนไข.
- แยก test modes `internet=simulated` กับ `internet=real check` และระบุให้คนสาธิตเข้าใจ. สำหรับ LAN จริงใช้แค่ approved gateway endpoint และ authentication; ห้าม default binding ที่ `0.0.0.0` โดยไม่มีเหตุผลและการเตือน. ถ้าสาธิต LAN ควรมี TLS หรือ security transport ที่ได้รับอนุมัติ; HTTP lab ใช้ได้เฉพาะ isolated trusted LAN พร้อมระบุข้อจำกัด และไม่ใช้ Production.

## E. User Experience ที่ต้องเพิ่มบน UI เดิม

อยู่ใน Desktop-only (1366×768 ถึง 1920×1080; ไม่บังคับรองรับมือถือ), preserve scene เป็น Hero. ต้องมีข้อมูลที่ **มาจาก backend/API จริง** อย่างน้อย:

- รอบ Export ล่าสุด / Next Export / Error Count **แยก PC1–PC3**; disk/spool queue ต่อเครื่อง.
- รายการ Agent ที่ enroll แล้ว, last seen, LAN handshake, Gateway address (redacted in demo if needed), connection state.
- Queue: pending / in flight / acked / retry / last ACK timestamp และ Internet egress จาก Gateway.
- ส่ง Telegram จริงเฉพาะเมื่อผู้ใช้ตั้งค่าชุดทดสอบ `TELEGRAM_ENABLED=true`, Bot Token, Chat ID และอนุมัติ endpoint; default แสดง `DRY-RUN` ชัดเจน. Network failure ต้องไม่ทำให้ข้อมูลหาย.
- Event log แยก SNAPSHOT, STATE_CHANGE, LAN_CONNECT, LAN_DISCONNECT, DELIVERY, RETRY, ERROR.
- ปุ่ม `CONNECT GATEWAY`, `INTERNET ON/OFF`, `PUMP ON/OFF`, `RESET LAB` ใช้ได้เฉพาะ **SIMULATION MODE**. โหมด read-only ต้องซ่อน/Disable และห้ามเรียก API สั่ง Pump จริง.
- Scene ต้องไม่บังแผงบนหรือหลุดหน้าจอ: ใช้ CSS Grid/Flex/minmax + scroll container เป็นส่วน ๆ; ไม่มี Horizontal Page Overflow ที่ 1366×768; สูง 1080 แสดงครบโดยไม่บัง navbar. ต้องทดสอบ browser screenshot ทั้ง 1366×768, 1600×900, 1920×1080.
- ห้ามใช้ภาพ Figma/SVG static มาปิดทับแทนการอัปเดตข้อมูลของจริง. ผู้ใช้งานต้องเห็นความแตกต่างของ `simulated vs real`, `LAN vs Internet`, `queued vs delivered`.

## F. Implementation Plan (ทำตามลำดับเท่านั้น)

### G0 — Audit & Baseline (ห้ามข้าม)
1. อ่าน README, package.json, source และ tests ทุกส่วนที่เกี่ยวข้อง พร้อม `git status`.
2. รัน `npm test`, `npm run dev`, ตรวจ API/UI baseline ก่อนแก้ และจดผลจริง.
3. แสดง **Gap Matrix** `Existing / Missing / Risk / Planned Changes` เทียบ Mission 2 ข้อ.
4. แยก Demo branch/worktree โดยรักษาข้อมูลและการเปลี่ยนแปลงเดิมทั้งหมด. ถ้า Source ไม่ใช่ v0.3 ต้องปรับแผนตาม Repo จริง ไม่เดา.

### G1 — Real Agent + Gateway LAN Transport (Priority 1)
แยก Agent/Gateway ออกจาก Simulator process, ส่งข้อมูลจริงผ่าน authenticated HTTP(S) ตามขอบเขต LAB, ทำ registration ที่กำหนดไว้ล่วงหน้า และ health endpoints แบบ read-only. ทดสอบ Agent/Gateway เริ่ม/หยุดคนละ process, backlog pending จน Gateway Online.

### G2 — Durable Queue + Retry/ACK/Recovery (Priority 1)
เพิ่ม persist+fsync/transaction, ACK หลัง commit, retry, dedupe, replay หลัง reboot/restart, queue bounded + log, simulate internet outage บน Gateway. ทดสอบ interruption ก่อน/หลัง ACK และ concurrent exports.

### G3 — Event Rules + Telegram Transport (Priority 2)
ทำ state transition และ Telegram Dry-run sink ที่มี mock HTTP server ทดสอบได้; หากมี test bot config จึงเปิด real Telegram. ต้องไม่ยิงทุก snapshot. Central/nongserver เป็น **optional LAB receiver** ไม่ใช่ dependency บังคับของ MVP และห้ามส่งข้อมูลหน้างานจริงออกไปเอง.

### G4 — UI Integration + Overflow Fix (Priority 2)
เชื่อม scene และ panel ที่มีอยู่กับข้อมูล Backend จริง; visual regression เทียบ v0.3; แก้ UI overflow และเพิ่ม health/connectivity/queue/diagnostics โดยไม่รื้อหน้าเดิม.

### G5 — Packaging + Acceptance (Priority 1 before handover)
เตรียม `npm install`, `npm run dev`, `npm run demo:single`, `npm run demo:lan`, `npm test`, `npm pack` หรือเทียบเท่าที่ตรวจสอบแล้วว่ามีจริง, `.env.example`, README_TH.md พร้อมภาพ architecture, setup Linux/Windows, firewall **ตามสิทธิ์เท่านั้น**, 5-minute demo script, rollback และ limitations.

**ภายใน DEMO scope ที่อนุมัตินี้ ให้เดินงาน G0→G5 ต่ออย่างมีวินัยโดยไม่ขอคำสั่งเริ่มเฟสซ้ำ.** แต่หากจำเป็นต้องแก้ Production, เปิดพอร์ตนอก LAB, ลง dependency ใหม่ที่ต้องใช้ native compilation, สร้าง integration WinCC/PLC จริง หรือเปลี่ยนสถาปัตยกรรมที่ได้รับอนุมัติ ให้ **หยุดและขออนุมัติแยก**.

## G. Tests & Definition of Done (ต้องมีหลักฐาน)

- [ ] `npm test` ผ่าน ทั้ง unit และ integration tests โดยไม่มี skipped ที่เกี่ยวข้อง.
- [ ] **3 Agents = 3 independent OS processes** เขียน Snapshot ต่อเนื่องทุก ~5 วินาที; หยุด Gateway แล้ว Local Queue เพิ่มขึ้นจริง.
- [ ] Run Agent และ Gateway แบบคนละ Process/Port; ส่ง network packets จริง. ถ้ามี LAB Host 2 เครื่องให้ทดสอบจริง; ถ้าไม่มีให้รายงาน `NOT VERIFIED: two physical hosts` ไม่โกหก.
- [ ] เริ่ม Gateway ใหม่ที่ endpoint เดิม → backlog ถ่ายโอน → ACK หลัง durable write → queue ฝั่ง Agent ลดลงเฉพาะที่ ACK แล้ว.
- [ ] ตัด Internet บน Gateway (จำลองได้) → local gateway outbound queue เพิ่มขึ้น แต่ PC1–PC3 ยัง Export.
- [ ] Internet ฟื้น → ส่ง Central Mock สำเร็จ, event id dedupe, retry หลัง kill process/restart แล้วยังไม่สูญหาย.
- [ ] เปลี่ยน Pump OFF→ON หนึ่งครั้ง → สร้าง state change หนึ่งรายการ, Telegram Dry-run หนึ่งครั้ง (ไม่ใช่ทุก 5 วินาที).
- [ ] UI อ่านค่าจาก API จริง, ไม่ใช่ hardcoded counters; action simulation ไม่ควบคุม PLC/OT.
- [ ] Screenshot viewport 1366×768, 1600×900, 1920×1080 ไม่มีข้อมูลถูกบัง/หลุดขอบสำคัญ.
- [ ] `npm pack --dry-run` และ `npm pack` ผ่าน, tarball ติดตั้งและเริ่มได้จากโฟลเดอร์แยก; ไม่มี secret, dev test data, node_modules ถูกแพ็กเข้าไปโดยไม่จำเป็น.
- [ ] แสดงหลักฐานแยก 3 ระดับ: `SIMULATED`, `TESTED ON ONE HOST`, `VERIFIED ON TWO LAN HOSTS`. ห้ามเขียน `PRODUCTION READY`.

## H. Format ของรายงานแต่ละเฟส (บังคับ)

```
STAGE: G0 / G1 / ...
SCOPE COMPLIANCE: PASS / HOLD + เหตุผล
PROGRESS: x/6 stage gates ผ่านจริง (ระบุส่วนที่เหลือ)
CHANGED FILES: ...
IMPLEMENTED: ...
TESTS: command + actual pass/fail counts + evidence/log
RUNTIME PROOF: processes, ports, request/ACK IDs ที่ redacted แล้ว
DATA SAFETY: spool durability, retention, retries, dedupe
SECURITY: authorization, default bind, secrets, PLC/OT isolation
UI REGRESSION: responsive screenshots and preserved components
RISKS/UNVERIFIED: ...
ROLLBACK: exact safe steps
NEXT STAGE: ...
```

ถ้า GATE ใดไม่ผ่าน: อย่าข้ามไปแต่ง UI หรืออ้างความสำเร็จ. แก้ root cause ก่อน. หากเวลาหรือ environment ไม่พอ ให้ส่ง partial working deliverable พร้อมข้อจำกัดที่ระบุชัด.

## I. Acceptance Demo ที่ผู้ใช้ต้องสาธิตหัวหน้าได้ (3–5 นาที)

1. เปิด 3 Agents, Gateway, Dashboard และยืนยันแยก processes ได้.
2. ตั้ง Gateway Offline หรือ Stop Gateway → ทุก 5 วินาที Agent ยังเขียนไฟล์/Spool จนข้อมูลสะสมเพิ่ม.
3. Start/Connect Gateway ผ่าน LAN → Queue ส่งย้อนหลังและแสดง ACK จริง.
4. ตั้ง Gateway Internet OFF → Gateway เก็บ outbound queue; SCADA exports ไม่หยุด.
5. ตั้ง Internet ON → Central Lab หรือ Telegram Test Sink ได้รับ Event และจำนวน pending ลด.
6. คลิก Pump ใน Simulation → สร้าง ON/OFF Transition ครั้งเดียว → แจ้งเตือน Dry-run ครั้งเดียว.
7. แสดง Log จริงและเปิด Spool/File ให้หัวหน้าเห็นว่าระบบไม่ได้เป็นแค่ภาพ Animation.

## J. First Action NOW

**เริ่มที่ G0 audit โค้ดและโครงสร้าง Repo จริงทันที.** อย่าเขียน UI ใหม่, อย่าดาวน์โหลดเทมเพลต SCADA สำเร็จรูปมาทับ, อย่าติดตั้ง Dependencies ก่อนตรวจต้นฉบับ. จากนั้นทำ G1→G5 เฉพาะใน LAB DEMO ตามลำดับและรายงานหลักฐาน. หากตรวจพบว่าโปรเจกต์ที่เปิดอยู่ไม่ใช่ AQUA DEMO v0.3 ให้หยุดการเขียนทับและระบุความต่างก่อน.
