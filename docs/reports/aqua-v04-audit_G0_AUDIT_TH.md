<!-- Phase 7 public copy: historical private values redacted. Original evidence remains privately preserved. This is not a rerun or acceptance upgrade. -->
# G0 — Audit & Baseline

STAGE: **G0**

SCOPE COMPLIANCE: **PASS** — พบ Source v0.3 จริง อ่าน Master Prompt และ AGENTS.md จาก prompt pack ครบทั้งสองไฟล์ ตรวจ source/scripts/tests ก่อนแก้ implementation ไม่มีการสร้าง UI หรือโปรเจกต์ทดแทน

PROGRESS: **1/6 stage gates ผ่านจริง**; G1–G5 ยังไม่ผ่าน

## Repository และขอบเขต

- ต้นฉบับ: `[REDACTED_HOME]/Downloads/AQUA_COMMAND_Desktop_Demo_v0.3_BUNDLE/aqua-command-isometric-demo-source/aqua-command-isometric-demo`
- `package.json`: `aqua-command-isometric-demo@0.3.0`, ESM, Node >=20, ไม่มี external dependencies
- Source เป็นโฟลเดอร์ที่แตกจาก archive ไม่ใช่ Git repository; `git status` ต้นฉบับตอบ `not a git repository`
- ทำ working copy จาก source เดิมแบบ byte-for-byte ใน `work/aqua-command-v04` โดยไม่ยก runtime `data/` เดิมมาใช้ และไม่แก้ต้นฉบับ
- Working copy มี branch `demo/v0.4-real-lan`, baseline commit `5f25be6`, tag `baseline-v0.3` เก็บ source และ scope documents ครบ
- อ่าน README ทั้งสองภาษา, package/lock, server, simulator, tests, HTML/CSS/JS ที่เกี่ยวข้อง ตรวจ asset SVG เดิมและเก็บ hash เพื่อเทียบภายหลัง

CHANGED FILES: เพิ่มสำเนาเอกสารบังคับ `AGENTS.md`, `AQUA_COMMAND_CODEX_MASTER_PROMPT.md` และรายงาน/แผนใน working copy เท่านั้น; **implementation และ public assets ยังไม่เปลี่ยน**

## Scripts และ baseline ที่รันจริง

Scripts เดิม: `dev` และ `start` → `node bin/aqua-demo.js`; `test` → `node --test tests/*.test.js`; `pack:demo` → `npm pack --pack-destination ..` ไม่มี `demo:single`/`demo:lan` ใน v0.3

ทดสอบด้วย Node **v22.23.1**, npm **10.9.8**:

- `npm test`: **4 pass, 0 fail, 0 skipped** (306.084908 ms ในรอบที่ใช้ Node runner เต็มรูปแบบ)
- `node tests/simulator.test.js`: **4 pass, 0 fail** เป็นการตรวจยืนยันตัว test bodies โดยตรงเพิ่มเติม
- `npm run dev`: เปิดสำเร็จด้วย `AQUA_HOST=127.0.0.1`, `PORT=14173`, `AQUA_DATA_DIR=.../work/g0-baseline-data` จึงไม่แตะ data เดิม
- API `/api/status`, `/api/action` และหน้า Isometric ทำงานจริงใน **simulator process เดียว**
- API baseline: เริ่ม snapshots/local backlog **198**, Gateway disconnected; หลังตั้ง Internet DOWN และ Connect Gateway ได้ source queue **0**, Gateway queue **198**, delivered **0**; หลัง Internet ON ได้ backlog **0**, delivered **198** ข้อมูลนี้เป็นผลจำลองภายในโปรเซส ไม่ใช่ LAN transfer/ACK ข้ามเครื่อง

## Gap Matrix

| Mission / ส่วน | Existing | Missing | Risk | Planned Changes |
|---|---|---|---|---|
| Export 5s | Node timer สร้าง 3 runtime JSONL ต่อรอบ | 3 independent agents, per-agent status/errors | server เดียวหยุดแล้ว exporter หยุดทั้งหมด | G1 แยก agent workers; default simulator adapter |
| Local Queue | JSON state + JSONL, rename state file | transaction/ACK ledger, corruption fail-closed, quota/retention | append ไม่ fsync; load error reset เงียบ; queue โตไม่จำกัด | G2 SQLite FULL/WAL, bounded retained data, visible storage errors |
| LAN Gateway | Boolean `gatewayConnected` และการย้าย array | real TCP/IP, enrollment, handshake/auth, known endpoint | UI CONNECT ไม่ใช่ network link จริง | G1 authenticated HTTP(S), configured endpoint, separate processes |
| ACK/retry | ฟังก์ชัน flush ใน simulator | ACK after Gateway commit, retry/backoff, replay/dedup across restart | counter success ไม่พิสูจน์ durable remote receipt | G2 fault tests ก่อน/หลัง commit/ACK, per-source ordering |
| Egress | Boolean `internetOnline`; default AVAILABLE | own-Gateway real probe, simulated/real distinction | AVAILABLE ไม่ใช่ผลตรวจ Internet | G3 fixed approved test endpoint, separate statuses, external default off |
| Notifications | pump transition dry-run ไม่ยิงทุก snapshot | durable transition dedup after retry/restart, mock HTTP sink | restart/corrupt state อาจสูญเสียประวัติ | G3 deterministic event IDs + transactional dry-run notification |
| UI เดิม | Isometric pumps/SVG, sidebar, pan/zoom, chart, events, branding | per-agent export/queue/last ACK/handshake/error diagnostics | ACTIVE ถูก hardcode; synthetic graph ใช้เวลา hardcode | G4 ผูก API ของ services จริง โดยเก็บ scene/theme/controls |
| Packaging | local npm package, no dependencies | single/LAN role scripts, enrollment docs, acceptance/rollback | existing scripts ยังสาธิตคนละเครื่องไม่ได้ | G5 test install/dev/single/lan/pack และติดตั้ง tarball ใหม่ |

## UI regression baseline

เก็บ screenshot และ DOM geometry ครบ **1366×768**, **1600×900**, **1920×1080** ก่อนแก้:

- ไม่มี horizontal page overflow ในทั้งสามขนาดที่ตรวจ
- 1366×768: เนื้อหาสูง **935 px**; ส่วนล่างต้องเลื่อนดู
- 1600×900: เนื้อหาสูง **935 px**; ส่วนล่างยังเกิน viewport
- 1920×1080: เนื้อหาสูง **1080 px**, footer อยู่ครบ
- เก็บ Isometric scene, pump interactions, sidebar, toolbar, telemetry และ event stream เป็น baseline; ยังไม่แก้ layout ใน G0

Evidence: `work/g0-evidence/api-baseline.json`, `layout-baseline.json`, source SHA-256 manifest และ `outputs/aqua-v04-audit/evidence/v03-*.png`

## Safety / unverified / rollback

DATA SAFETY: baseline data แยกจากต้นฉบับ; v0.3 ยังไม่ผ่าน durable remote ACK/recovery criteria ของ v0.4

SECURITY: เปิดเฉพาะ loopback; ไม่ใช้ `.env`/credentials เดิม ไม่เรียก PLC/WinCC/OT ไม่สแกน LAN ไม่แก้ firewall/NAT/bridge ไม่ส่ง Telegram

RISKS/UNVERIFIED: `SIMULATED` เท่านั้นใน v0.3; **NOT VERIFIED: two physical hosts**. ไม่มี TLS/auth จริงใน legacy simulator. ข้อกำหนด G1–G5 ยังไม่ถือว่าผ่านจากผล 4 legacy tests

ROLLBACK: implementation ปัจจุบันยังเป็น v0.3; ใช้ `git switch -c rollback/v03 baseline-v0.3` ใน working copy เพื่อเปิด source baseline อีก branch โดยไม่ลบ user data อย่าใช้ reset/clean ลบ data ของต้นฉบับ

NEXT STAGE: **G1** — แยก Agent/Gateway ด้วย known-endpoint authenticated transport ก่อนทำ recovery tests, event transport และเชื่อม UI ตามลำดับ
