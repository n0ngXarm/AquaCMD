# F3 จำลองถึง Telegram — 2026-11-08

เพิ่มปุ่มจำลองและส่ง Telegram ใช้ OPC UA localhost อ่าน 73.25% Good แล้ว SQLite → Task (เกณฑ์ 70%) → Outbox → Telegram แชตที่ตั้งใน F6 สูงสุดหนึ่งคำขอต่อรอบ แยกฐานข้อมูลชั่วคราว ขอบเขียวเมื่อ Telegram ตอบ message_id สีแดงเมื่อไม่สำเร็จ เวลาแต่ละขั้นมาจากการวัดจริง

ทดสอบ F3 ด้วย SQLite จำลองผ่านโดยไม่มี credentials และผล 4 เคสของการรับใบยืนยันผ่าน การทดสอบส่งไปยัง Telegram ที่ตั้งไว้หนึ่งครั้งไม่ได้รับ message_id จึงยังไม่ยืนยันว่าถึงแชต TLS diagnostic ภายหลัง timeout ไม่ส่งซ้ำ syntax/no_fake_check/git diff --check ผ่าน ยังไม่ได้ตรวจ WinCC หน้างาน

ผลดิบและรายการไฟล์: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-telegram/ สำรอง: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-telegram/before/

# จำลอง OPC UA ใน F3 เดิม — 2026-11-08

เปลี่ยนจากหน้าต่างแยกเป็นปุ่มจำลอง/หยุดใน WebView F3 เดิม โปรเซส tools/sim/f3_demo.py เปิด Server localhost:4850 และใช้ Client read-only จริง SQLite ชั่วคราว source=sim แถบเหลืองแสดงช่วงจำลอง ขอบเขียวเมื่อ UA read สำเร็จ ขอบแดงและ toast ซ้ายล่างเมื่อผิดพลาด

Native WebKitGTK 1024×496 exit 0 อ่านค่า 73.25 Good ผ่าน OPC UA จริงบน loopback, ปุ่มหยุดคืน API เดิม, DB หลักในชุดทดสอบ bytes เดิม, ทดสอบพอร์ตไม่ว่างขึ้นแดงพร้อม toast, syntax/no_fake_check/git diff --check ผ่าน ยังไม่ได้ตรวจ WinCC หน้างาน

ผลดิบและภาพ: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-inline/ สำรอง: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-inline/before/

# ปุ่มดูตัวอย่างการทำงาน F3 — 2026-11-08

เพิ่มปุ่มดูตัวอย่างการทำงานใน F3 เปิดโปรเซส GTK tools/sim/f3_demo.py แยกพร้อม SQLite ชั่วคราว ใช้ fixture tests/f3_demo_fixture.json ทั้งหมดเป็น SIMULATED เลือกอ่านสำเร็จ 73.25% Good / ดูหลักฐานเก่า / อ่านใหม่ได้ ผ่าน EvidenceStore และ SSE เดิม ไม่มีการเชื่อมต่อ OPC UA หรือส่ง Telegram ในตัวอย่าง

ทดสอบ F3_TEST_DEMO=1 F3_TEST_SIZE=1024x535 ผ่าน native GTK: เปิดได้หนึ่งโปรเซส ปิดตามเจ้าของ DB ตัวอย่างของหน้าหลักคง bytes เดิม สถานะจำลอง UNVERIFIED→OK→STALE→OK และผังไม่ต้องเลื่อน node syntax, no_fake_check และ git diff --check exit 0 ยังไม่ได้ตรวจในโปรแกรมพร้อมฐานข้อมูลหน้างาน

ไฟล์ที่ลง ผลดิบ และภาพ: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-demo/ สำรอง: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-demo/before/

# F3 ขยายตามหน้าต่าง — 2026-11-08

ผู้ใช้แจ้งว่าหน้ากะทัดรัดเล็กเกินไปเมื่อขยายโปรแกรม แก้ desktop/f3_api/view.css ให้ใช้พื้นที่จอใหญ่และขยายตัวอักษรตาม WebView เพิ่มการตรวจขนาดจอใหญ่ใน tests/f3_handoff_native.py

ที่ 1920×1009 ผังสูง 408→855 px และชื่อการ์ด 13→19 px ตรวจ 1920×1009, 1360×616 และ 1024×496 ใน WebKitGTK ด้วย SQLite จำลอง 4 สถานี ผ่านและไม่มีแถบเลื่อนแม้ขึ้น BLOCKED ทั้งสี่ รายละเอียดการทำงาน F3 ยังคงแสดงในผังและ popup no_fake_check และ git diff --check ผ่าน ยังไม่ได้ทดสอบฐานหน้างาน

ผลและภาพ: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-adaptive/ สำรอง: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-adaptive/before/

# F3 พอดีหน้าต่างและอธิบายการทำงาน — 2026-11-08

แก้ index.html/view.css/view.js เฉพาะผัง F3 และเพิ่ม regression check ใน tests/f3_handoff_native.py ผังสามโซนแสดงครบโดยไม่เลื่อนที่ขนาดที่ทดสอบ ป้ายอ่านอย่างเดียวและลำดับอ่านค่า → เก็บหลักฐาน → ประเมินเงื่อนไข → จัดคิวอยู่กลางผัง รายละเอียดเต็มเปิดจากแต่ละการ์ด

ก่อนแก้ WebKitGTK 1024×496 เอกสารสูง 1228 px (exit 1) หลังแก้ทดสอบขนาดจริง 1024×496 และ 1360×616 ผ่านทั้งแนวตั้งและแนวนอนแม้ SCADA 4 การ์ด BLOCKED ตรวจจาก checkout หลักด้วย SQLite จำลอง no_fake_check/syntax/diff check exit 0 ข้อมูลหน้างานและโปรแกรมเต็มยังไม่ได้ตรวจซ้ำ

ผลดิบและภาพ: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-fit/ สำรองก่อนแก้: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-fit/before/

# ลง F3 handoff ใน AquaCMD ที่ไอคอนใช้งาน — 2026-11-08

ผู้ใช้อนุมัติลง patch ใน checkout หลัก project_water/AquaCMD/aqua-command-desktop แล้ว ยืนยัน GNOME desktop entry เรียก launcher ที่ชี้ desktop/app.py ของ checkout นี้ ลง patch 12 ไฟล์ผ่าน git apply หลังตรวจ baseline และสำรองไฟล์เดิมพร้อม SHA-256 ตรวจ reverse patch ผ่าน

ทดสอบจาก checkout ที่ลงจริง: Node detector 14/14, frontend contract 4/4, syntax, no_fake_check และ git diff --check ผ่าน Native WebKitGTK ใช้ XDG profile/SQLite จำลองบน localhost ผ่านกรณี SSE, SCADA FAIL, Switch FAIL → 4 BLOCKED, STALE เกิน 60 วินาที, popup/F2 และปิด listener เมื่อออก F3 รัน frontend ครั้งแรกติดสิทธิ์สร้างไฟล์ชั่วคราวใน tests จึงรันซ้ำผ่านระบบอนุมัติแล้ว exit 0

เปิด Aqua Command จากไอคอนใหม่และกด F3 เพื่อดูรุ่นใหม่ ยังไม่ได้ตรวจสอบการเปิดด้วยฐานข้อมูลหน้างานหรือการเชื่อม SCADA/Telegram จริง ไม่มีการ commit/push หรือเปลี่ยน runtime config

หลักฐานและภาพ: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/outputs/f3-live-install/ สำรอง: [REDACTED_HOME]/Documents/Codex/2026-11-07/referenced-chatgpt-conversation-this-is-an/work/f3-live-install/before/

# GNOME Applications เปิดได้แล้ว — 2026-11-08

ผู้ใช้ยืนยัน "เปิดหน้าต่างแล้ว" หลังแก้ไอคอนใน GNOME Applications. Journal21:55:02 แสดง GNOME เรียก app.py ที่ Documents/Codex/... ตำแหน่งเก่า แม้ GIO ในคำสั่งทดสอบเลือก launcherใหม่แล้ว.

ลงทะเบียน desktop ID ใหม่ `org.aquacommand.AquaCMD.desktop` (ชื่อแสดง AQUA COMMAND) ให้ใช้ ~/.local/bin/aqua-command ซึ่งชี้ canonical source ใน project_water/AquaCMD. ซ่อน ID เดิม org.aquacommand.Desktop.desktop ผ่าน user override Hidden/NoDisplay และ update-desktop-database; ไม่แตะ application/backend source. Desktop shortcut ยังคงเปิดผ่าน launcherเดียวกัน.

ตรวจ desktop-file-validate ทั้ง2ไฟล์และ update-desktop-database PASS exit0; GIO เห็น AQUA COMMAND ที่ should_show เพียงรายการใหม่; gtk-launch org.aquacommand.AquaCMD exit0 และตรวจGUIprocess. ผู้ใช้กดจากApplicationsตามภาพและยืนยันเปิดหน้าต่างได้จริง. no_fake_check PASS. หลักฐาน: artifacts/aqua-gnome-menu-repair-20261108/.

# แก้ launcher หลังย้ายโปรเจกต์ — 2026-11-08

ผู้ใช้แจ้งเปิดโปรแกรมไม่ได้ พบ ~/.local/bin/aqua-command ยังชี้ Documents/Codex/.../waterlevels-desktop ที่ย้ายแล้ว พิสูจน์ก่อนแก้: เรียก launcher แล้ว Python can't open file / No such file or directory, exit2.

แก้ launcher ให้ชี้ `[REDACTED_HOME]/Documents/Work_SHCOOL/project_water/AquaCMD/aqua-command-desktop/desktop/app.py` และแก้ Exec ของไอคอน Menu/Desktop ให้เรียก launcherเดียวกัน. สำรองทั้ง3ไฟล์ใน artifacts/aqua-launch-repair-20261108/before-*. ไม่มีการแก้ application code/backend.

หลังแก้ sh -n และ desktop-file-validate ทั้ง2ไฟล์ PASS exit0; ~/.local/bin/aqua-command --help แสดง GTK help exit0; gio launch Desktop icon exit0; host pgrep ยืนยัน app.py ตำแหน่งใหม่ PID558978 ยังทำงาน. no_fake_check PASS exit0. ไม่มีfieldprobe/Telegram/dependency/commit/push.

# ย้าย AQUA COMMAND มาที่ project_water/AquaCMD แล้ว — 2026-11-08

Source หลัก: `[REDACTED_HOME]/Documents/Work_SHCOOL/project_water/AquaCMD/aqua-command-desktop`.
Repository root: `project_water/AquaCMD` (origin n0ngXarm/AquaCMD), HEAD c4daf58a85a068988963a0b0282c69e021fc9563. ใช้ Git จาก root นี้สำหรับโปรแกรม Desktop; project_water/.git เป็น waterlevels คนละ repository.

ย้ายทั้ง repository จาก Documents/Codex/.../waterlevels-desktop ด้วย directory rename รวม .git/history/uncommitted/untracked files. ตรวจ hash964ไฟล์ตรงกัน Git statusเดิมตรงกันก่อนเขียน checkpoint และ linked worktree10ชุดซ่อม reference แล้ว HEADตรงเดิม. ตำแหน่งเก่าไม่มี source หลักซ้ำ; มี AQUACMD_MOVED_TO.md ใน parent ชี้ทางใหม่.

ไอคอน Menu และ Desktop ชี้ app.py ตำแหน่งใหม่แล้ว; desktop-file-validate PASS. ตรวจหลังย้าย F3 tests13/13 PASS, no_fake_check PASS, git diff --check PASS exit0. Actual GTK4 ตำแหน่งใหม่1600x900/mainDB read-only PASS:129→129 hashเดิม config5ไฟล์เดิม ไม่มีprobe/collector/notificationเริ่ม. หลักฐานและคำสั่ง/outputดิบ: `project_water/artifacts/aqua-project-relocation-20261108/`.

Runtime config/DB ยังอยู่ ~/.config/aqua-command และ ~/.local/share/aqua-command เพื่อรักษาข้อมูลส่วนตัว แยกจาก source. ไม่ได้ commit/push/merge หรือทดสอบ SCADA/Telegramจริง. อ้างอิง ACTIVE_PROJECT.md และ AGENTS.md ที่ workspace root สำหรับการพัฒนาครั้งถัดไป.

# F3 architecture ติดตั้งในโปรแกรมไอคอนเดิมแล้ว — 2026-11-07

ผู้ใช้อนุญาต apply/restart หลังพบว่ายังเห็นหน้ารุ่นเดิม ติดตั้ง payload8ไฟล์จาก reviewed manifest หลังguard117baseline hashes และbackup ภายใน artifacts/aqua-f3-architecture-20261107/installed/before; sourceอื่นไม่เปลี่ยน ไม่มีcommit/push/merge/SCADAprobe/TGsend
Installed F3 tests13/13 PASS exit0 และno_fake_check PASS exit0; actualGTK/mainDBread-only proof PASS:129→129 hashเดิม config5ไฟล์เดิม workersSTOPPED/noNotifications. จับภาพจริงใน evidence/real/installed-f3-main.png และ installed-f3-inspector.png. ตรวจแล้ว staleไม่เป็นHealthy, sources4จากAPI, dockไม่มีrawdefault. เปิดโปรแกรมผ่าน desktop entry เดิมใหม่แล้ว เลือกF3เพื่อดูหน้าที่เปลี่ยน
หลักฐาน: artifacts/aqua-f3-architecture-20261107/installed/install-result.json, restart-result.json และ evidence/real/result.json; รายงานcandidate119testsและ3sizesอยู่README.md. Task/Outbox/Telegram evidence pipelineยังNOT_BUILT; การเชื่อมต่อหน้างานจริงยังไม่ได้ตรวจสอบ

# F3 architecture ติดตั้งในโปรแกรมไอคอนเดิมแล้ว — 2026-11-07

ผู้ใช้อนุญาต apply/restart หลังพบว่ายังเห็นหน้ารุ่นเดิม ติดตั้ง payload8ไฟล์จาก reviewed manifest หลังguard117baseline hashes และbackup ภายใน artifacts/aqua-f3-architecture-20261107/installed/before; sourceอื่นไม่เปลี่ยน ไม่มีcommit/push/merge/SCADAprobe/TGsend
Installed F3 tests13/13 PASS exit0 และno_fake_check PASS exit0; actualGTK/mainDBread-only proof PASS:129→129 hashเดิม config5ไฟล์เดิม workersSTOPPED/noNotifications. จับภาพจริงใน evidence/real/installed-f3-main.png และ installed-f3-inspector.png. ตรวจแล้ว staleไม่เป็นHealthy, sources4จากAPI, dockไม่มีrawdefault. เปิดโปรแกรมผ่าน desktop entry เดิมใหม่แล้ว เลือกF3เพื่อดูหน้าที่เปลี่ยน
หลักฐาน: artifacts/aqua-f3-architecture-20261107/installed/install-result.json, restart-result.json และ evidence/real/result.json; รายงานcandidate119testsและ3sizesอยู่README.md. Task/Outbox/Telegram evidence pipelineยังNOT_BUILT; การเชื่อมต่อหน้างานจริงยังไม่ได้ตรวจสอบ

# F3 Inspector เปิดเป็นหน้าต่าง popup — 2026-11-07

ผู้ใช้ขอให้คลิกกล่อง F3 แล้วเด้งรายละเอียดเป็นหน้าต่าง popup แทน dock ติดตั้งเฉพาะ desktop/f3_api_view.py และ desktop/f3_api/index.html/view.css/view.js หลังสำรองและตรวจ hashes ไม่มี app.py/probe/API/backend/config/dependency/phase5 เปลี่ยนแปลง

ใช้ Gtk.Window แบบ transient/nonmodal อ่านข้อความ/หลักฐานดิบจาก Inspector API เดิม ไม่มี WebView/API/collector ชุดที่สอง เปิดซ้ำใช้หน้าต่างเดิม เปลี่ยนกล่องอัปเดตข้อมูล ปิดด้วย ×/Esc และปิดตามเมื่อออกF3/parentclose; pollingไม่เปิดหน้าต่างที่ปิดแล้วและไม่เรียก present ซ้ำ ผังคงขนาดเดิม API origin policy เดิมยังบล็อก arbitrary windows

Candidate GTKจริง1366×768/1600×900/1920×1080 PASS exit0; browser20checks PASS exit0; installed UItests4/4 PASS exit0 และ actual installed/mainDB popup/read-only proof PASS exit0; no_fake_check PASS exit0 ทั้ง7backend files/testsเดิม/config5/icons2/mainDBคงbytesเดิม มีbackupในprivate/before-apply
Main DB 129→129 ไม่มีprobe/collector/TGsend การเชื่อมต่อหน้างานรอบใหม่ยังไม่ได้ตรวจสอบ; fullshared/backend suiteไม่ได้รันซ้ำในงานUIนี้ รายงาน/ไฟล์/patch/commands/outputดิบ/ภาพจริง: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-f3-popup-20261107/README.md

# F3 หน้าตาเรียบง่ายตามคำสั่งล่าสุด — 2026-11-07

เปลี่ยนเฉพาะ HTML/CSS/JS ของF3และการแสดงผล native wrapper (ซ่อนNIC/Internetpillเดิม/ปรับcaptionเฉพาะF3 คืนค่าเมื่อออก) พร้อมUItestfixture ไม่มีการเปลี่ยน app.py, probe, API backend หรือconfig

ผัง4สถานี→LAN Switch→fedora Gateway→Router/Internet→Telegram→มือถือ กล่องชื่อ>=16px+สถานะไทยบรรทัดเดียว ป้ายอายุแยก สีผลล่าสุดคงเดิมเมื่อหลักฐานเก่า ตัวเลขเหลือแถบเดียว สรุปใช้SQLAPIคำนิยามปลายทางรวมSwitch/Router ที่อยู่Routerอ่านroute_inventory/default routeจากiprouteในหลักฐานผ่านAPIเดิม ไม่fallbackconfiguredrouter ผลเน็ตใช้DNS+TLS NIC/route/ip_forward/error/msอยู่Inspector;ผังเชิงบทบาทไม่อ้างphysicalswitchhop

Installed UItests4/4 PASS0/browser19checksPASS/nativeจริง3ขนาดPASS พร้อมF1/F2/F6และrestoreheader Mainreadonlyproof:DB129→129,bytesเดิม,0probe/collector/notification/particles,defaultgateway192.168.1.1ตรงOSขณะตรวจ;no_fake_checkPASS0. Sourcebackend/config5files/icons2files/DBคงhashเดิม มีbackupก่อนแก้
ภาพจริง/คำสั่ง/outputดิบ/manifest/patch: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-f3-simple-20261107/README.md ไอคอนเดิมเปิดsourceนี้ ไม่เพิ่มfeature/dependency/subagent/commit/push/fieldprobe/TGsend

# อ่าน AGENTS.md ก่อน — Phase 4 ติดตั้งและตรวจแล้ว (2026-11-06)

เพิ่ม read-only asyncua client: GetEndpoints/session/configured NodeId read, atomic tag_samples/evidence FK, certificate metadata/PKI เดิม, startup ip_forward และคำเตือนเมื่อ1, manual loop ตาม interval config ไม่มี collector autostart จาก F3. Simulator แยก process 127.0.0.1:4850; set_level อยู่ tools/sim เท่านั้น; sourceไม่มี control calls.
Installed phase66/66 PASS exit0, observability43/43 PASS exit0, browser17 PASS, nativeจริง3ขนาด PASS. Installed-source GTK+protocol sim12.5→73.25/Good, SSE19/SVG19, serverหยุด→REFUSED/value unavailable, mainDB bytesคงเดิมระหว่างทดสอบ. ไม่มี Sim target/rows ใน private main config/DB.
Actual mainหนึ่งรอบ: DB101→129; SSE28/SVG28; old101rowsคงเดิม; tag_samples0; ip_forward=0; backendbanner90.4ms. ดู actual UA errors/SQL/API/route ในรายงาน; ไม่อ้าง WinCC/production acceptance จาก Sim.
Private probe configเพิ่มเฉพาะ UA ServerStatus i=2256 Anonymous/None ของ5targetเดิมและ interval_s5; ไม่เปลี่ยน opcua_config เดิม/4otherconfigs/2icons. Iconเดิมเปิด sourceนี้; collectorloopไม่ถูกเปิดค้าง. หลักฐาน/manifest/patch/commands/output: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase4-20261106/README.md ไม่มีdependencies/subagents/commit/push/PLCwrite/TGsend/phase5.

# อ่าน AGENTS.md ก่อน — Phase 3.1 ผ่าน (2026-11-06)

ติดตั้ง11ไฟล์ตามmanifestหลังสำรองและhashguard; SQLiteOBSERVED_LOCAL/COUNT/MAXtimestamp, ผลหลักแยกอายุSTALE, RouterICMPARPไม่มีTCPใหม่, DNS+TLSไม่มีHTTP/ข้อความ, FedoraNIC/IP/CIDR/routeและsubnetจริง, SQLchecked/responding, NOT_BUILTและevidencepairedarrows/fontcardsใหญ่.
Installedphase51/51PASS0; observability43/43PASS0;browser16checksPASS;nativeactual3sizesPASS. RealDB80→101;SSE21/SVG21;oldrows80คงเดิม;backendbanner104.2ms. Privateprobeconfigเปลี่ยนเฉพาะreviewedrouter/OTsubnet/internet;4otherconfigs/2iconsคงhashเดิม.
Source/patch/rawcommands/output/SQL/API/route/screenshots: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase3_1-20261106/README.md ผู้ใช้อนุญาตต่อPhase4หลังผ่าน;ยังไม่มีOPCUA/TGsend/PLCwrite/dependency/commit/push.

# อ่าน AGENTS.md ก่อน — เฟส 3 ผ่านเกณฑ์จริง (2026-11-06)

F3 SVG/WebView อ่าน phase2APIเท่านั้น backendเดิมhashเดิม; สถานะ/ตัวเลขSQLผ่านAPI;rawInspector/sourceSIMULATED/reducedmotion;1SVGobjectต่อSSErowid ไม่มีidletraffic APIownedเฉพาะF3และปิดเมื่อออก/ปิด เริ่มF1ยังไม่สร้างWebView/API
Actualsource phase42/42tests PASS0, observability43/43PASS0; browser15checksPASS; nativeactual1366x768/1600x900/1920x1080fullscreenPASSและassertขนาดจริง Shared87/88FAIL1baselinefixtureเดิม ซึ่งsourceก่อนติดตั้งก็6/7FAILเหมือนกัน ไม่มีskip/assertionsลด
เกณฑ์จริงหนึ่งprobe6targets/4840เดิม:DB60→80 SSE20rows/particleobjects20;SQL/API/DOMตรงกัน;backendfailurebanner136.3ms<5s;oldrows60คงเดิม;pollingSTOPPED/notificationsOFF/UAobs0. Source/config5files/icons2filesรักษาhashเดิมนอกpayload;เปิดmenuiconเดิมใหม่ PID46253
หลักฐาน/คำสั่ง/exit/outputดิบ/ภาพ: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase3-20261106/README.md เฟส4–5ยังไม่เริ่ม ไม่มีdependencies/commit/push/PLCwrite/TGsend/RPMEXEbuild/productionacceptance

# อ่าน AGENTS.md ก่อน — เฟส 2 ผ่านเกณฑ์จริง (2026-11-06)

source migration คงแถวเดิม 20 แถว; derive_state จุดเดียว; SQL counters; loopback API/SSE; tests38/38 exit0; no_fake_check exit0. รัน probe จริงสองรอบตาม6 targets/4840เดิม: DB 20 → 60 แถว; curl/SQLตรงกัน; SSE 20 events ตรงแถวใหม่ทุกตัว; ไม่มี idle bytes; ไม่ probe 70.0s แล้วทั้ง6โหนดSTALE. UI85ไฟล์hashเดิม configเดิม APIทดสอบปิดแล้ว ไม่มีservice/autostart/UA/TG/write/dependencies/commit/push เฟส3–5ยังไม่เริ่ม

หลักฐาน/คำสั่ง/exit code/outputดิบ: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase2-20261106/evidence และ [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase2-20261106/README.md

## เฟส 1 ผ่านเกณฑ์จริง — 2026-11-06

อ่าน AGENTS.md แล้ว ติดตั้ง sqlite CLI ตามที่ผู้ใช้อนุมัติ เก็บจริงหนึ่งรอบกับ6IPที่กำหนด:20แถว, NIC wlp2s0 [REDACTED_PRIVATE_IP]/24, default gateway192.168.100.1 routeทั้ง6ok;5เป้าหมาย192.168.1.x ping/TCP TIMEOUT;gateway pingok/TCP4840 REFUSED ไม่มีUA/TG/PLCwrite Test12/12และno_fake_check exit0 UI85ไฟล์hashเดิม เฟส2–5ยังไม่เริ่ม
คำสั่งจริงและoutputดิบ: [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase1-20261106/evidence (probe-once, sql-raw, sql-tcp-corrected, sql-counts, installed-tests, no-fake-final) Queryสรุปเสริมครั้งแรกquoteผิดexit1 เก็บหลักฐานเดิมไว้แล้ว แก้SQLและอ่านซ้ำเท่านั้น ไม่probeเพิ่ม

# อ่าน AGENTS.md ก่อน — ปัจจุบัน: ขั้น 0 + เฟส 1 (2026-11-06)

ผู้ใช้กำหนดให้ทำทีละเฟส CLI ใหม่อยู่ src/collector/probe_once.py และเปิดด้วย python -m collector.probe_once กฎเหล็กและ scanner ติดตั้งแล้ว หน้าจอ/API/OPC UA/Telegram ไม่ถูกแก้ในเฟสนี้ config/data อยู่นอก source แยกจาก GTK DB หลักฐานและผลรันจริงอยู่ [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-evidence-phase1-20261106 เฟส 2–5 รอเกณฑ์เฟส 1 ผ่านก่อน ตัวเลข/ผลสำเร็จต้องมาจากหลักฐานจริงเสมอ

# F3 separate details window — completed 2026-11-04

- Requested behavior: F3 device details/settings open in a separate native window; the main diagram retains its full width.
- Changed only `desktop/f3_network.py` and added `desktop/tests/test_f3_details_window.py`. Existing inspector API, manual authorization, read/probe logic and supplied tests preserved.
- Popup is created on demand, owned by the main window, reused for new selections and close/reopen, and hidden when its parent closes. Settings and authorization dialogs use the popup as their parent.
- Reproduced six failures before the popup change. Native fixture also exposed a Wayland crash when a settings window was immediately destroyed before mapping; waiting for its actual mapped state corrected that fixture. The final aggregate run passes.
- Actual-source verification: `python3 -B -X faulthandler artifacts/aqua-f3-dialog/run_isolated.py --project <this-project> --pattern 'test_f3*.py'`: 65 tests PASS, exit 0. The runner uses a temporary profile and permits loopback connections only.
- Native source layout/screenshot smoke PASS, exit 0: main windows 1366x768, 1600x900, 1920x1048; separate popup 420x660. Canvas widths before/after opening details: 1366/1366, 1600/1600, 1920/1920. Largest requested height is clamped by the desktop work area.
- Hash checks verify both payloads and 42 unchanged desktop source/style/test files. Originals and prior checkpoint backed up under `artifacts/aqua-f3-dialog/before-apply` in the working workspace. `git diff --check` PASS.
- Evidence: `f3-details-window.patch`, `patch-manifest.json`, `source-f3.log`, `source-layout.log`, screenshots and verification scripts under `[REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-f3-dialog`.
- Close/reopen the existing application to load the Python UI change. Real F3 live tag reads remain unavailable/disabled. WinCC/physical LAN/real Telegram acceptance NOT TESTED. No dependency changes, service restart, production probes, commits or pushes.

# Current F3 revision — usability correction

Date: 2026-11-04. User reported that the live F3 view was confusing and unusable.

Changed `desktop/app.py`, `desktop/f3_network.py`, and added `desktop/tests/test_f3_usability.py`:

- Diagram is the default full-height view; details start hidden and use 340px when opened. Device list is a separate full-height view with all configured devices and readable status summaries.
- Station nodes now use complete IP addresses as primary text when hostname is unknown; primary text is 13pt and nodes are 92px high. Native short-viewport drawing keeps default stations visible; larger device sets scroll. Corrected the lower-left corner arc that made device outlines look skewed/folded.
- Operator guidance, actions, and key statuses use Thai. Details actions stay visible; unavailable F3 live Tag reading and unsupported external-service probes are disabled honestly. Existing manual remote-action consent remains intact.
- Internet starts unknown and remains unverified after passive refresh instead of claiming Online/Offline without evidence.
- Existing tests and assertions preserved. No dependencies, transport, OPC UA/PLC read/write pipeline, or notification engine changes.

Verification after applying to the actual checkout:

- `python3 -B -X faulthandler -m unittest discover -s tests -p test_f3_usability.py -v` from `desktop`: PASS, 9 tests, exit 0.
- Selected isolated regression suites: PASS, 105 tests, exit 0. Covers old/new F3 tests, workspace presentation, GTK E2E, OPC UA security/polling, task/outbox and network recovery. Loopback only, temporary profiles.
- Native GTK checks: all three default stations within the viewport; details width 340px; diagram/details/device-list screenshots at widths 1366, 1600, and 1920. Desktop work area limits the tallest requested window to 1048px.
- Source hashes checked before/after patch; 40 other desktop modules/styles unchanged. Prior source versions backed up privately before applying.

Operator follow-up: close and reopen AQUA to load the new Python UI. Operator acceptance and physical WinCC/Windows/OT-LAN/real Telegram remain NOT TESTED. F3 live Tag reading remains unavailable; TCP port checks do not establish an OPC UA session.

---

# AQUA COMMAND — F3 continuation

Date: 2026-11-04
Base: `c4daf58`, branch `feature/v3-ui-task-remediation`.
Scope: finish Gemini's F3 topology/device-identity work; preserve existing user changes.

Completed:

- Fixed duplicate GTK widget ownership and animation rendering failure.
- Kept legacy/stable device IDs consistent for card selection, add/remove and configuration updates.
- Isolated DEMO observations and late callbacks from LIVE state; disabled devices do not start remote actions.
- Applied the existing manual authorization dialog to F3 remote OPC UA actions.
- Displayed observed NIC addresses/link status separately from unverified Internet/egress state.
- Preserved existing network configuration when saving device identity settings.
- Adjusted F3 header/cards/text widths and the app stack so the visible page can fit narrower screens.
- Kept original F3 assertions; isolated test config and mocked the simulated certificate test's socket.

Actual verification after applying the patch:

- `python3 -B -X faulthandler -m unittest discover -s tests -p test_f3_continuation.py -v` from `desktop`: PASS, 14 tests, exit 0.
- Isolated regression runner: PASS, 96 tests, exit 0. Covers F3, workspace presentation, GTK E2E, OPC UA security/polling, task/outbox and network recovery. Temporary profile; loopback-only network guard.
- Native GTK screenshots: PASS at requested widths 1366, 1600 and 1920. Actual heights: 768, 900 and 1048; the desktop work area limits the 1080-height request.
- SHA256 checked before applying and after installation; unrelated desktop modules unchanged.

Limits and next step:

- Physical Windows/WinCC/OT-LAN and real Telegram acceptance remain NOT TESTED.
- Existing F3 LIVE OPC UA check establishes TCP reachability only; its single-tag live reader remains unavailable. Secure reader/polling integration tests use loopback servers.
- Existing legacy test setup still emits GTK application-registration warnings; the F3 duplicate-parent warning was eliminated.
- Ready for operator review of F3. Preserve separate authorization for any future field commissioning.


## F3 desktop update — 2026-11-05
User authorized installing the reviewed F3 into the existing desktop icon target. Applied18 F3/test files with backup; production33/33 and actual-source native GTK smoke PASS. Shared runtime unchanged; existing legacy-test limitations remain documented. Desktop shortcut uses the same source as the application icon. No commit/push, network changes or industrial/Telegram connection.


## Existing app-menu source update — 2026-11-06
User clarified that only the original AQUA COMMAND application icon is used. Applied the reviewed current Hybrid/F3 source into that exact icon target, with private backups and drift/hash checks. Existing menu/Desktop icons and four runtime configuration files remain unchanged. Narrow installed-source dock contract reproduced FAIL before and PASS after; focused/shared/native results and exact commands are recorded in [REDACTED_HOME]/Documents/Work_SHCOOL/project_water/artifacts/aqua-main-app-install-20261106. No new dependencies, field actions, commit/push or Windows EXE rebuild. Legacy aggregate/shared acceptance limitations from the review remain. Windows GUI uses a separate implementation; see installation report before claiming platform parity.

## F1/F2 desktop update — 2026-11-08

F1 now shows one Tag workspace. F2 opens the Task editor over that workspace. The row Inspector, quick add with Undo, and range selection operate on the same catalog. Task settings keep the existing wincc_tasks.json format. Failed saves keep the draft and report failure. New Tasks start disabled with notifications unchecked.

Updated desktop/app.py, desktop/workspace.py, desktop/workspace_style.css and three focused test files at the existing application icon target. Previous versions were saved in the task workspace. Ran the installed-source GTK workspace, presentation and persistence suites against an isolated profile (10 passed), scripts/no_fake_check.sh (PASS), and git diff --check (exit 0). Verified the catalog against the local export (457 tags in 10 groups). Live WinCC and Telegram acceptance remain outside this update.

Evidence and controls are recorded in the Codex task outputs under f1-unify/F1_README.md. Next step is operator review from the existing icon after restarting the application.

## F1 catalog readability — 2026-11-08

The installed icon target uses a common heading/row column allocation. Tag and Task columns share spare width; long Task labels ellipsize with the full name in their tooltip. Increased label size and contrast and used Noto Sans/Noto Sans Thai with tabular digits in F1, its dialogs and the main header clock. No data-source or Task persistence changes.

The native geometry test reproduced inconsistent columns before the change. The installed source passed 7 workspace tests at 1920 px, the geometry test at 1280 px, 4 presentation/persistence tests, the no-fake scanner and the scoped Git whitespace check. Screenshots and raw logs are in this Codex task's outputs under f1-readability. Next step is operator review after reopening the existing icon. WinCC and Telegram were outside this verification.

## F1/F2 operator workflow — 2026-11-08

Single-clicking a catalog row selects/focuses it. The explicit Details button, Enter or double-click open the selected Tag details. The selection and Add to Task actions are above the table and show hidden selections. A destination is shown before saving single or bulk assignments. Tag details put observation and provenance first, with technical metadata in a disclosure and actions in a fixed footer. F2 save and return controls are also outside the scroll area. Existing Task storage, Undo, safety defaults, and read gating are retained.

The original single-click activation reproduced a focused GTK test failure. Installed-source verification passed 8 native workspace tests at 1280 px, the focused workflow test at 1920 px, 4 presentation/persistence tests, no_fake_check and the scoped whitespace check. See this Codex task's f1-simple outputs for screenshots and raw logs. Next step is operator review after reopening the existing icon. No field verification was run.

## F2 task layout and plain tag tables — 2026-11-08

F2 uses a larger window with settings to the left and an expanding assigned Tag table to the right. Only the assigned table scrolls when the list exceeds the viewport. Removing a selected row is available above the table and changes the draft until Save. F1 uses plain cells with one Details action above the table plus row double-click or Enter. Task persistence and observation sources are unchanged.

The focused test reproduced nested scrolling before the change. Installed-source verification passed nine workspace tests at 1280 px, the focused nine/sixty-Tag layout test at 1920 px, four presentation/persistence tests, no_fake_check and the scoped whitespace check. Screenshots and raw logs are in this Codex task's f2-clean outputs. Next step is operator review from the existing icon after reopening the app.

## F6 connection settings layout — 2026-11-08

F6 now has WinCC OPC UA, Telegram and History tabs. WinCC connection and automatic reading controls are separate. Username credentials are shown only for that auth mode, and the certificate disclosure opens when trust review is actionable. Telegram masks the token, distinguishes saving from sending, and reports a failed local write without replacing the active destination. Test Send stops before dispatch if saving fails.

The original single-page layout failed the focused tab test. Installed-source verification passed 10 workspace tests at 1280 px, the F6 test at 1920 px, four presentation/persistence tests, no_fake_check and the scoped whitespace check. Local profiles only. WinCC reads and Telegram sends were outside verification. Screenshots and raw logs are in this Codex task's f6-clean outputs. Next step is operator review after reopening the existing icon.

## F6 full-width workspace — 2026-11-09

Removed the centered 840 px rail and expanded the F6 header and workspace to the window. WinCC keeps the connection form on the left and automatic reading and certificate status on the right. Telegram keeps destination settings and test sending side by side. History fills the workspace. Existing settings and read/send handlers are unchanged.

The prior layout measured 812 px of content in a 1920 px window. Installed-source tests covered all three tabs at actual window widths 1052, 1280 and 1920 px, including credential fields and expanded certificate details, plus presentation/persistence checks and no_fake_check. No field connections were used. Screenshots and raw logs are in this Codex task's f6-wide outputs. Next step is operator review after reopening the existing icon.

## OPC UA field-readiness check — 2026-11-09

Checked the installed icon target with read-only inspection and a network namespace containing only loopback. The desktop security suite passed 11 tests, the focused secure desktop suite passed 5, and the collector protocol suite passed 7. The desktop single-shot reader returned a Good observation via Basic256Sha256. Collector tests received 12.5 then 73.25 with Good quality, recorded timestamps/evidence, and withdrew the current value when the simulated server stopped. no_fake_check passed. Raw outputs are under opcua-readiness in the Codex task outputs.

Field acceptance remains pending. The 2026-11-06 WinCC evidence shows five GetEndpoints timeouts and zero tag samples. The current desktop destination is loopback, uses Username with SecurityPolicy None, and has no private field mapping. Its project fallback is a synthetic mapping fixture. F6 Browse does not verify mappings or read process values.

A no-socket reproduction confirmed the automatic polling path accepts Username + None and passes credentials to the client object. Starting monitoring also starts the notification worker. Keep F6 automatic monitoring outside the first field check. The next step, after the operator supplies a confirmed endpoint, security mode and one approved process NodeId, is a single read-only acceptance against WinCC. Keep value, StatusCode and timing as acceptance evidence. No source or runtime configuration changes and no real WinCC/Telegram calls were made in this check.

## F1/F2: larger selection targets — 2026-11-09

Click anywhere on a catalog row to toggle its checkbox. Shift+click selects or clears a range, and Space toggles a focused row. The native checkbox, Details button, Enter and double-click still work. Double-click toggles once on the first click and then opens Details; Enter opens Details without changing the ticks. F2 Task options now accept clicks over the wider option area. Selecting an assigned Tag for removal and saving the Task still follow the existing workflow.

Changed `desktop/workspace.py` and `desktop/workspace_style.css` at the existing launcher target. The isolated GTK pointer check reproduced the original failure (clicking the name selected the row but left its checkbox off). The same test passed 10 interaction checks on the installed source. The GTK workspace, presentation and Task persistence suites passed 15 tests. `scripts/no_fake_check.sh` and scoped `git diff --check` passed. No field connection, real send, or runtime configuration change was made. Raw output is in this Codex task's `outputs/f1-f2-tick`. Reopen the existing app to load the change.

## F3 Task groups on data flow — 2026-11-09

F3 shows the F2 Task names associated with each successful, committed OPC UA read. It uses the read evidence ID, current configured host/source/endpoint and exact Tag/NodeId binding. SSE carries each read's own groups even if several Tags from one station arrive before the next snapshot. Moving labels show up to two short names with a remaining count, and the node details show all names for its latest evidence. The live labels mean configured Tag membership. Task evaluation, queuing and Telegram delivery keep their independent evidence states.

The separate F3 simulator evaluates two sample Task groups using one loopback OPC UA read. Matching groups accompany the Task, Outbox and delivery evidence and are listed in the single combined test message. Installed-source F3 Python tests, the Node detector, no_fake_check and scoped whitespace checks passed. WebKitGTK in a loopback-only network namespace verified burst attribution, the simulation stages, stopped updates and fit in a 1024 px candidate window and a 1920 px installed window. No WinCC field read or real Telegram send was run for this update. Raw logs, screenshots and changed-files.txt are in this Codex task's outputs/f3-task-groups. Reopen the existing icon to load the update.

## Program settings shortcut and source publication — 2026-11-09

The native bottom-right gear opens the existing F6 settings page. The former F1 sidebar shortcut moved to this common toolbar. F6 and Ctrl+, still work. Updated the installed app and the F1 assets and tests in the existing checkout.

Published the audited desktop source snapshot as commit `c77c6c985b5b31ff14419a109bed6759ba79712a` on `n0ngXarm/waterlevels` branch `codex/aqua-command-desktop`. The snapshot uses public sample settings and synthetic tests and omits commissioning evidence and build artifacts.

Verified GTK gear placement and activation, F1/F3 contracts, parser and workspace tests, the F3 loopback simulator, syntax, outbound source audit, no_fake_check and git diff --check. Raw output and the remote ref receipt are under outputs/waterlevels-publish in the Codex task workspace. Reopen the existing icon to load the gear.

## Handoff reconciliation — 2026-11-09

Compared the A/B/C handoff with the launcher source and kept the existing F3 evidence stream, Task group animation, F1 row selection and global gear. F3 now uses the same formal palette as F1. F1 displays actual receipt quality and freshness, refreshes observations without replacing the open Task form, and supports keyboard navigation and focus restoration. A failed Task save leaves the draft visible.

Added `tools/check_opcua_readiness.py` and `docs/OPCUA_READINESS.md`. The default action validates only private configuration. Explicit execution checks the approved switch and station TCP before secure discovery, trusted certificate validation, one configured process read per station and a private JSON report. Isolated loopback verified an untrusted-certificate stop and a trusted Basic256Sha256 read. Field acceptance still requires the approved addresses, secure endpoint and mapped NodeId for each station.

The native F3 port-conflict test now reuses the address after the preceding simulator connection enters TIME_WAIT. Verified the installed source with F1/F3 contracts, F3 detector tests, native WebKitGTK on an isolated loopback-only profile, the readiness suite and no_fake_check. Raw logs, screenshots and changed files are in this task's outputs/handoff-reconcile. No field or Telegram traffic was used for these checks. Reopen the existing launcher to load the update.

## Handoff publication — 2026-11-09

Published all 17 handoff source, documentation and test files as commit `d083f1b692c32ebd46305ed60b9db6c732f176f1` on `n0ngXarm/waterlevels` branch `codex/aqua-command-desktop`. Verified the exact branch tip after the fast-forward.

Verified the public checkout with F1/F3 and parser contracts, the F3 detector, native WebKitGTK, loopback OPC UA readiness, no_fake_check, the scoped whitespace check and the outbound source audit. Results and the remote ref receipt are under outputs/waterlevels-publish-handoff. WinCC field acceptance remains pending.

## Desktop workflow retheme — 2026-11-09

The existing launcher now presents daily work in a top navigation row: view Tag observations, manage Task, and inspect the F3 data path. The catalog and host diagnostics are grouped as tools. Function keys keep their meanings and the settings gear stays in the bottom-right. The global header stays stable during F3 navigation. GTK and the WebKit pages use matching dark surfaces and semantic status colors.

F1 fits the action column on a 1024 px window. F2 keeps Save in the dialog footer. F3 labels the WinCC, AQUA COMMAND, and notification zones in flow order. F4 groups system, resources, storage and local network fields. F5 shows the entire catalog, builds the grid when opened and keeps local refresh controls with the catalog. F6 places save/test/browse and certificate controls before automatic reading. Existing configuration, persistence, observation, simulation, network and notification handlers are used.

The pre-change layout clipped F1 row actions and rendered only the first 60 Tag rows in F5. Installed-source checks covered the F1–F6 workflow at 1024 and 1920 px with a 457-Tag local fixture, the native fallback, F1/F3 contracts, the F3 detector and simulator, secure OPC UA loopback and no_fake_check. Screenshots and raw output are under outputs/desktop-retheme in the Codex task workspace. Reopen the original launcher to load the changes.

## REST and MQTT observation sources — 2026-11-10

Added `python3 -B -m collector.telemetry` to read one normalized snapshot from an explicitly configured HTTPS GET endpoint or an exact MQTT topic through the installed Mosquitto client. Validation mode is offline. The optional interval requires explicit read mode and stops before reading a changed source. Normal execution requires TLS. Plain transports are available only for the explicitly flagged loopback LAB.

Both adapters validate the source timestamp, exact Tag allowlist, quality and finite scalar values. The private evidence database separates transport/binding and LAB rows. Replayed and older snapshots do not reset freshness. F1 uses one manually selected source via telemetry_source.json, shows its provenance and source timestamp, and marks receipts older than 60 seconds stale. Removing that selection restores OPC UA. F3's OPC UA checks, automatic Tasks and Telegram continue on their established paths and do not consume this store.

Verified HTTPS trust, Bearer header and redirect rejection, MQTTS subscription against a real loopback Mosquitto broker, exact topic/retained handling, deduplication, F1 WebKit source switching and existing F1/F3 and OPC UA loopback regressions. Logs are in outputs/telemetry-sources. Next step is to obtain a compatible approved Gateway snapshot endpoint or topic and test its actual Tag mapping before field use.

## Windows OPC DA Analog Reader 0.10 — 2026-11-10

The Windows Reader now accepts separate lists of pump-status and Analog Tags within the existing allowlist. Read-only local IOPCItemIO capture preserves finite numeric COM scalar values, source time, quality word and HRESULT. Analog zero and one are numeric observations and never produce pump transitions. Queue sequence, destination pin, and ACK handling retain the established spool behavior. The Gateway accepts v3 Analog observations with the explicit value_type marker and continues to accept legacy binary v3. Use the updated Gateway before sending Analog records.

Cross-built the unsigned self-contained Windows x64 package from the existing local .NET SDK and cached runtime packs. Core assertions, deployed Gateway tests, the pre-change rejection reproduction, and authenticated .NET-to-Node TLS interop passed. Mixed payloads covered 73.25, negative and exponent values, negative zero and exact digest ACK. Test fixtures did not activate local COM or connect to WinCC. Artifacts and logs are in outputs/opcda-analog. Next step is field verification of one approved Analog and one approved pump Tag, comparing values, source timestamps and quality before authorizing delivery.

## F6 Data Sources controls — 2026-11-10

Added the Data Sources tab to the existing settings gear. F6 can choose and save OPC DA via a local Gateway archive, HTTPS REST, or MQTTS for F1 and can explicitly read once, start/stop a five-second reader, or return to OPC UA. Alternative profiles remain separate and the F6 reader stays idle on startup. The controlled process is stopped when the app exits. Existing OPC UA, Telegram and history controls remain on their own tabs.

The OPC DA adapter reads an explicitly selected aqua.sqlite3 file in SQLite read-only mode, matches the selected Windows Reader ID and validates the latest committed OPC DA snapshot and its digest. F1 keeps each tag's source timestamp and does not infer a current measurement from Gateway arrival time. Windows Reader capture and Gateway receive approvals still take place separately. Alternative sources feed F1 only.

Verified the missing-tab baseline, native GTK F6 source selection/read/start/stop/return workflow, independent OPC DA source freshness, original F1/F3 regressions, HTTPS/MQTTS loopback tests and signed Windows Reader test events through the real Gateway SQLite schema. No field connection was used. Logs and screenshots are under outputs/f6-telemetry.

## Context help button — 2026-11-10

Added the question-mark button at the right edge of the common top navigation. It opens a local GTK help popover for the visible page. In F6 Data Sources it shows setup guidance for the protocol currently selected in the form. Opening help does not save settings or start a reader.

Reproduced the missing button before the change. Verified placement and click behavior at 1024 and 1920 px, F1 and per-source F6 content, and no_fake_check on the installed source. Screenshots and raw logs are in outputs/aqua-help. Reopen the existing icon to load the button.

## Offline operator manual window — 2026-11-10

The question-mark button in the top-right navigation opens a separate modal GTK window titled คู่มือการใช้งาน AQUA COMMAND. Twelve chapters sit in the left sidebar and explanatory text opens on the right. The manual covers getting started, F1–F5, OPC UA, OPC DA, REST, MQTT, Telegram and history. It reads independently of the active program page. Close and Escape hide the window, and reopening it keeps the last chapter for the running app session.

Reproduced the previous context popover before applying the change. Verified direct opening, switching chapters, closing and reopening, unchanged F6 selection, and no telemetry worker or configuration write in native GTK at 1024 and 1920 px. no_fake_check passed. Screenshots and raw logs are in outputs/aqua-manual.

## Operator labels and keyboard shortcuts — 2026-11-10

The Fedora launcher menu, settings, backup-source controls, Grafana menu and manual now use the operator-facing page and protocol names. Function-key numbers appear in the dedicated คีย์ลัด chapter. Existing F1–F8 mappings are preserved. F9 opens the manual in GTK and both WebKit pages, and Ctrl+, reaches connection settings from the diagram as well.

Reproduced the old numbered menu labels before the change. Verified the new labels, manual and F1–F9/Ctrl+, routes in the installed launcher at 1024 and 1920 px, 41 F1/F3 contract tests in the candidate, JS syntax and no_fake_check. Raw output and screenshots are in outputs/aqua-shortcuts. Reopen the existing icon to load the change.

## Operator wording revision — 2026-11-10

Reworded the navigation, GTK/WebKit headings, settings and manual to use ติดตามค่า, งานเฝ้าระวัง and ผังการสื่อสาร consistently. Kept คลัง Tag and ข้อมูลเครื่อง. The backup-source controls now distinguish saving the source from starting a read, and the help chapter labels match the main menu.

Reproduced the previous labels with the focused GTK check, then verified the labels and F1–F9/Ctrl+, shortcuts at 1024 and 1920 px with a temporary profile and an isolated loopback network. Logs and screenshots are in outputs/aqua-labels. Reopen the existing launcher icon to load the update.

## Compact top bar — 2026-11-10

Kept the catalog count and read-only status beside the app title. Removed the local NIC and Internet badges from the header, removed the header clock and its timer, and mount the Grafana menu only when the optional bridge is configured. Network detail remains available in the communication diagram.

Reproduced the old header, then verified the compact header, optional menu placement and navigation at 1024 and 1920 px in the isolated GTK check. The Grafana branch used a test double for the bridge. Native check logs, screenshots, and the no_fake_check output are in outputs/aqua-topbar. Reopen the existing launcher icon to load the update.

## Passive Internet and router IP status — 2026-11-10

The top bar shows NetworkManager's cached Internet connectivity and the observed default IPv4 gateway. The AQUA COMMAND column in the communication diagram displays the kernel-selected source IPv4 and configured target separately for the OT and WAN paths. A routed path shows the intermediate gateway. Stale snapshots do not display a current source IP. The status follows the configured switch and router roles and does not infer router reachability, OPC UA health or equipment state.

The implementation reads local D-Bus properties and uses local kernel route lookups. No connectivity recheck, network probe, collection or settings write is triggered. Passive host readback reported FULL, an IPv4 default gateway, an indirect OT route and a direct WAN route at verification time. Logs use no production addresses. Adapter tests, the F1/F3 contracts and isolated GTK/WebKit checks are in outputs/aqua-router-status. Reopen the existing launcher to load the change.

## Phase 1B RPM startup dependencies — 2026-11-10

Accepted the packaging follow-up against Gemini's 0db6e72 baseline in fix/phase-1b-rpm-runtime-dependency. Release 2 requires python3-cryptography for startup PKI imports and gobject-introspection for the Cairo typelib used by PangoCairo. A clean Fedora 45 run with only the first change exposed the missing typelib. asyncua remains optional.

Built noarch RPMs for Fedora 44 and 45 on the Fedora 45 build host. Verified package digests, required dependencies, absence of runtime databases and test files in the payload, and no_fake_check. Installed each unsigned candidate in a fresh matching Fedora container with DNF weak dependencies disabled. Ran /usr/bin/aqua-command --help with temporary HOME and container networking disabled. Both returned 0. This covers launcher imports and argument processing. Graphical desktop use, field connectivity and signed distribution were outside the test.

Rollback is a revert of the isolated packaging commit. The installed host package and canonical checkout were kept separate. Raw evidence is in outputs/aqua-roadmap-phase1b-fix. Phase 2 DATA-04 requires its separate approval before implementation.

## Phase 2 DATA-04 — durable alert production — 2026-11-10

Implemented DATA-04 on fix/phase-2-data04-durable-alerts, based on c5eb38c. The legacy web producer stages alerts, outbox jobs and rule transitions together, checks capacity for the entire update, and writes one atomic JSON snapshot before reporting success. Existing IDs and legacy JSON remain readable. Pre-rename failures and capacity rejection return 503 without publishing the candidate. A post-rename directory-sync failure reports ALERT_COMMIT_UNKNOWN and suspends delivery while durability is uncertain. Corrupt snapshots block startup and remain available for recovery.

Four focused regression cases failed on 0db6e72 and passed after remediation. The web suite passed 16/16, Desktop Gateway passed 58/58, node syntax, diff check and no_fake_check passed. Tests used isolated loopback and synthetic fixtures. A real filesystem rename failure and SIGKILL after a successful response were covered. Power loss, Windows Reader runtime and Telegram delivery or lost response were not validated. Raw logs are in outputs/aqua-roadmap-phase2-data04. The wider Phase 2 exit gate and main integration remain on hold.

## Phase 2 fault acceptance — 2026-11-10

Tested fa44140 in isolated LABs. .NET SDK 10.0.403 ran all 59 Windows Reader Core assertions in a Linux container with networking disabled. The existing HTTPS Gateway lost-ACK test passed: one durable receipt, deduplication on retry, exact digest ACK and retained record after restart. The web producer also passed an actual ENOSPC test using a dedicated 2 MiB tmpfs: HTTP 503, byte-for-byte old state retention and successful retry after freeing space.

Phase 2 remains HOLD. The legacy web delivery worker recorded the first lost response as pending, then sent the same payload a second time automatically. The loopback sink recorded two POSTs and the job eventually became sent. The acceptance assertion for a distinct delivery_unknown state failed. No real destination or WinCC was used. Evidence is in outputs/aqua-roadmap-phase2-acceptance. Source stays at fa44140 pending approval of the delivery-state repair. Proposed scope is aqua-command/server.mjs, public/app.js and isolated delivery regression tests. Persist sending before dispatch, recover interrupted sends as delivery_unknown, retain unknown jobs and require an explicit duplicate-aware decision to resend.

## All-phase LAB continuation and Phase 6 review — 2026-11-11

The user authorized every remaining roadmap phase. Implementation and review were carried through Phase 6 in the isolated branch fix/phase-6-source-privacy. Final functional/package source is e466efe8fbcf0c706edb0886271dba4f8cfceb16. Documentation commits follow separately. The canonical checkout remained clean at 0db6e72145ec4b2d1fef0329a285216ac6d49d12 when checked after final validation.

- Phase 2 repaired atomic web alert/outbox/rule state, local Task SQLite transactionality, sending/unknown-delivery recovery and legacy exhausted attempts. Actual ENOSPC, SIGKILL, lost ACK and a failed SQLite trigger have recorded baseline/fix evidence. Web now passes20/20, Gateway59/59, Reader Core59 assertions. Unknown delivery remains held. Explicit resend can duplicate an accepted message.
- Phase 3 passed116/116 source contracts with secure OPC UA/REST/MQTT loopback opt-ins and three actual .NET-to-Node TLS/HMAC/digest-ACK variants. PWA tests passed14/14. The collector waits its configured interval after a full round. Alternative OPC DA/REST/MQTT sources currently feed F1 without local Task evaluation.
- Phase 4 focused active GTK/WebKit checks passed at1024/1360. Synthetic457-Tag fixtures removed the parser/workspace dependence on the site catalog. The broad synthetic desktop run remains red,308 tests with16 failures and5 errors, concentrated in legacy F3 widget expectations. All failing assertions are retained. Earlier broad runs included one test that reached the tracked catalog, followed by the synthetic correction.
- Phase 5 final release4 RPMs for Fedora44/45 match byte for byte across two builds each. The fc44 dist label was built on Fedora45 and installed on actual Fedora44. Offline containers upgraded2→4, ran launcher help, uninstalled, preserved synthetic config+SQLite hashes and passed integrity/content checks. Final extracted RPM UI passed at allocated1440px for a1360px request. Windows0.10.0 x64 cross-builds match, without Windows runtime/COM acceptance. CI proposal is locally syntax checked with no hosted execution.
- Phase 6 removed the tracked catalog from the isolated current tree and sanitized selected defaults. The final RPM excludes the archival Windows preview. All99 extracted files scanned against457 catalog names and recorded private/credential patterns with0 matches. Source/history/old artifacts still require review, and historical credential revocation is unverified. Old Linux release3 and initial99190c8 release4 evidence are superseded by the final e466efe builds.
- Final focused command `python3 -B -m unittest test_credential_permissions test_opcua_security_gate test_task_alert_atomicity test_notification_delivery -v` passed27/27,0 skipped,exit0 in a temporary HOME and loopback-only network namespace. Dependency inventories cover316 Fedora44 packages and319 Fedora45 packages, plus the separately retained Windows restore-input inventory. SHA256SUMS verifies the final artifacts. Inventory scope includes container base packages, rather than exhaustive binary composition.

All20 required Markdown deliverable categories are indexed in docs/reports/ROADMAP_DELIVERABLE_INDEX.md. Current acceptance, hashes, commands, baseline/fix results, source capability boundaries, risk register, rollback and release decision are linked there. Raw logs/artifacts are in the task workspace outputs/aqua-roadmap-phase* directories. Final changed-file and commit receipts are under outputs/aqua-roadmap-phase6-privacy.

Final decision is NO-GO for public distribution, main integration and production deployment. Open gates include source/history privacy and credential revocation,16 legacy F3 failures+5 errors, Windows/COM and actual WinCC/OT/Telegram acceptance, hosted CI/signing/composition review, full backup restoration, power-loss and performance acceptance. No production install, field connection, actual Telegram send, main merge or push occurred in this continuation.

Next work follows MASTER_REMEDIATION_PLAN.md after owners and the required operational/release authorization are available. Do not reactivate old delivery workers onto unresolved sending/unknown records.

## Phase 7 P0 — isolated privacy and credential remediation (2026-11-11)

Implemented only the approved P0 scope on local branch `fix/phase7-p0-privacy`,
based on e5d6a931c0c16017736fa36bf43fe38878b62fd3. Original ancestry, installed
checkout, private configuration, catalogs and databases remain preserved.

Private catalog selection now supports an explicit path or the private desktop
profile and retains legacy Downloads import. The factory OPC UA mapping is empty;
private mappings still take priority with exact existing Tag/NodeId/namespace
semantics. No mapping/parser/database schema was changed. Historical images,
old executables and two private Tag lists were quarantined from this checkout;
original files and hashes remain private. Public documentation copies and the
archived preview were sanitized. Public third-party license text is preserved.

CLI setup uses secure terminal input, masks configured credentials and writes an
external owner-only profile through backup/fsync/atomic replace. Unknown keys and
legacy input survive. Failed secure input and pre-rename failures leave the
selected configuration unchanged. Post-rename sync failure reports uncertain
durability. Notifier/bot and desktop manual-send errors redact credentials.
Windows CLI writes fail closed pending separate owner-only ACL verification.
Legacy fallback files remain read-only and their original permissions are not
changed; operators must handle legacy copies privately.

A shared privacy guard checks staged bytes, file modes and extracted build
inputs. It rejects credential/key patterns, private filenames, populated factory
mappings, symlinks and unreviewed binary data. Five public fonts require exact
reviewed hashes. Optional private catalog comparison stays outside source. The
local hook is configured here; hooks remain opt-in for other clones. Build guard
failure stops rpmbuild before consuming the source archive.

Validation: PWA/CLI 39 tests, desktop source contracts 116, focused security/task/
delivery 27, web 20 and Gateway 59 passed. Reader Core passed 59 assertions in an
offline Linux .NET container; this does not establish Windows/COM acceptance.
Native AquaApplication first run loaded zero Tags and mappings. A separate
private legacy import loaded 457 Tags plus an exact private mapping without
changing original files. Broad desktop 313 tests still has exactly the previous
16 failures and 5 errors, with identical diagnostic IDs; existing GUI tests and
safety assertions were not edited. The original independent baseline had 309
tests; four new private-runtime tests account for the increase. no_fake_check
and diff whitespace checks passed. Commands, raw-output redactions, baseline/fix
results, manifests and final package scans accompany the Phase 7 evidence.

P0 implementation is ready for Independent Review within the tested Linux LAB
scope. Public push/distribution, main merge and production deployment remain
NO-GO. History is NOT_CLEARED; token rotation is PENDING_OWNER_ACTION. P1 has a
21-row requirements-linked plan only; GUI remediation remains HOLD. Do not push
this ancestry, install the LAB artifact, or begin P1 before separate review.


## Owner-authorized GitHub main publication — 2026-11-11

After P1 Independent Review, the owner explicitly requested pushing all current
project files to main. Publication prepares the reviewed P1 current snapshot
and sanitized Phase7 text evidence as a new commit on the existing GitHub main,
without attaching the uncleared local ancestry, force push, history rewrite or
visibility change. P0 runtime is unchanged. GUI319,source contracts116,security27
and PWA/privacy39 passed in the isolated LAB. See docs/reports/phase7/PUBLICATION.md
and its reports for evidence and scope. Publication is not production deployment
or public release acceptance; history/rotation/Windows/field/CI/signing gates
remain unresolved. No operational action is authorized by this update.


## Owner-authorized native GTK4 UX polish — local branch

The owner corrected the target to the native application and supplied the GTK4
UX task. The mistakenly prepared standalone web checkout, its six local commits
and uncommitted changes were deleted; the original web source in the canonical
checkout was never changed. Native work is isolated on ux/desktop-polish from
445e1e6. GUI/presentation only; no installation, push, merge, backend change,
new dependency, field probe or Telegram send is authorized/performed here.

Baseline: desktop/tests319 and source contracts116 passed. The legacy ui_test.py
and layout_test.py fail at import because AquaWindow no longer exists. Existing
F3 handoff passed1360x616/1920x1009 and failed1024x496: actual WebView1024x457,
scrollHeight499. Before screenshots cover F1–F6 at3 requested sizes with labelled
SIMULATED disposable profiles; 1024x600 actually allocates1024x700 due to the
existing minimum height. Raw results are in artifacts/ux-before (local only).

Item1: confirmed F8 and window close lack a safeguard with two failing GTK tests.
Added a cancel-default native close question; original cleanup runs only after
acceptance. Exit is separated into the far-right navigation area. Existing
lifecycle test assertions are retained and now explicitly accept the close
question. New capture/run support uses disposable HOME and loopback namespace.


Item2: nav buttons/tooltips expose F1–F6, close F8 and help F9; the F1 catalog
refresh control exposes F7 and uses its existing catalog-only handler. Settings
mentions Ctrl+,. Task navigation now has a toggle selected only while its Task
dialog is open, synchronized through a presentation-only WebKit message. The
fallback Task entry keeps the same Thai/F2 wording. No business action/schema,
collector, worker or listener was added.


Item3: raised CSS secondary text to >=10pt and table/body text to >=10.5pt,
controls to >=36px, and the native minimum window to1024x600. The F3 diagram
uses its actual available height; short views retain statuses/age and move
secondary descriptions to the existing details dialog. The same F3 handoff
assertions now pass all3 sizes, including the pre-existing1024x496 overflow
(actual1024x457). Font lint and5 focused GTK/contrast tests pass. Measured12
palette pairs now all >=4.5:1; disabled Task3.499→7.978, running status3.518→5.091,
catalog badge4.091→5.773 and WebKit faint3.526→6.991. These are measured CSS pairs,
not a claim that every possible composited screen pixel was audited.

The first broad323-test run had one polling timing failure at a fixed0.4s wait;
the identical narrow test then passed in isolation without changing its test
or polling implementation. Source contracts116 and F3 fit3/3 passed. Preserve
both raw results in artifacts/ux-after; rerun the complete suite at final state.
Dark remains the default; the optional theme switch is skipped because private
settings handling is outside the authorized presentation scope.
