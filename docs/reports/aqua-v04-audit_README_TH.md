# AQUA COMMAND v0.4 — คู่มือเริ่ม DEMO

พัฒนาต่อจาก Source v0.3 จริง โดยเก็บหน้า Isometric เดิมไว้ Agent ทั้ง3ตัวเป็นคนละโปรเซส เขียนข้อมูลจำลองทุก5วินาทีลง SQLite ของตัวเอง ส่งผ่าน HTTP ที่มี handshake/auth ไป Gateway และรับ ACK หลังบันทึกสำเร็จจริง

**ข้อมูลปั๊ม/กราฟและสวิตช์ Internet เป็น SIMULATED** ส่วนการส่งข้อมูลระหว่างโปรเซสเป็น TCP จริง ทดสอบแล้วบน Linux เครื่องเดียว (**TESTED ON ONE HOST**) ยังไม่ทดสอบ2เครื่องจริงใน LAN, Windows, Telegram จริง หรือ PLC/WinCC

## เปิดใช้งาน

ต้องมี Node.js22.13ขึ้นไปและ npm; ไม่มี dependency ภายนอก Node22 อาจแสดง ExperimentalWarning ของ SQLite ตามปกติ

```sh
npm install --offline --ignore-scripts --no-audit --no-fund
npm test
npm run demo:single
```

เปิด http://127.0.0.1:4173 ค่าเริ่มต้นไม่มีการออก Internet, ไม่มี PLC access, Telegram เป็น **DRY-RUN** คำสั่ง `npm run dev` ใช้งานได้เช่นกัน ถ้าพอร์ตชน ให้เลือกโฟลเดอร์ข้อมูลใหม่พร้อมพอร์ตใหม่ เช่น

```sh
npm run demo:single -- --data-dir ./lab-data-show --port 4273
```

เมื่อเริ่มจะมี Agent3ตัว, Central mock และ Dashboard เป็นคนละโปรเซส Gateway ยังไม่เริ่มจนกด **CONNECT GATEWAY** Internet เริ่ม DOWN เพื่อให้เห็นคิวสะสม กดปั๊มบนฉากเพื่อสลับสถานะจำลองได้ แผง Diagnostics แสดง PID, เวลา Export ล่าสุด/ครั้งถัดไป, snapshotจริง, pending/in-flight/ACKed/retry, disk และ notification

```text
PC1 → Snapshot5s → Local SQLite ─┐
PC2 → Snapshot5s → Local SQLite ─┼→ Gateway SQLite → Internet gate → Central mock
PC3 → Snapshot5s → Local SQLite ─┘        └→ เฉพาะ ON/OFF transition → Telegram DRY-RUN
                        ← ACK หลัง commit
Dashboard เดิมอ่านสถานะจากแต่ละบริการผ่าน API ที่ยืนยันตัวตน
```

แผนภาพ Mermaid อยู่ใน README.md คิวแต่ละช่วงแยกกัน: Source pending ลดเมื่อ Gateway ACK; Gateway pending ลดเมื่อ Central ACK; Notification เป็นรายการแยก การสร้าง Snapshot ไม่ใช่การส่ง Telegramทุก5วินาที ค่าไม่ทราบ/ข้อมูลเก่าแสดง stale ไม่แปลงเป็น Pump OFF

## สาธิตและหยุด

ทำตาม [สคริปต์3–5นาที](docs/DEMO_SCRIPT_TH.md) ปิดด้วย Ctrl+C แล้วเปิดด้วย data-dirเดิมเพื่อดูการกู้คืน กด RESET LAB เพื่อเริ่ม sessionใหม่โดยเก็บข้อมูลเก่าไว้ อย่าลบเฉพาะฐานข้อมูลAgentหรือGatewayกลางsession เพราะเลขลำดับและประวัติรับต้องสอดคล้องกัน

โหมดดูอย่างเดียว:

```sh
npm run demo:single -- --data-dir ./lab-data-readonly --port 4373 --read-only
```

read-only จะถูกจำไว้ใน enrollment นั้น ถ้าต้องการโหมดควบคุมจำลองใหม่ ให้ใช้ data-dirใหม่ ไม่มีการควบคุมปั๊มจริงไม่ว่าโหมดใด

## LAN และ Telegram

[คู่มือ LAN](docs/LAN_SETUP_TH.md) อธิบายการแยกเครื่องโดยระบุอุปกรณ์ที่อนุญาตไว้ล่วงหน้า ไม่มีการสแกนทั้งวงแลน คำสั่ง `npm run demo:lan -- --role ... --config ... --allow-lan` เปิดเฉพาะบทบาทที่ระบุ ต้องแก้ configเป็น private IPที่อนุญาตและเก็บ keyเป็นความลับ การมีคู่มือไม่ได้แปลว่าทดสอบข้าม2เครื่องแล้ว

Telegramจริงปิดไว้ ต้องได้รับอนุญาตใช้ test botและตั้ง environmentทั้ง4ค่าตาม `.env.example` พร้อม `--internet real` โปรแกรมไม่อ่าน.envให้อัตโนมัติ ห้ามใช้ production bot ค่าInternet UPในโหมดsimulatedเป็นเพียงเงื่อนไขจำลอง ไม่ใช่ผลตรวจInternetจริง Telegramอาจซ้ำได้เมื่อส่งสำเร็จแต่คำตอบหาย จึงไม่รับรอง exactly-once

Windowsใช้ Node/npm และคำสั่งเดียวกันใน PowerShell ดู README.md; ยังไม่ได้ทดสอบบนWindows ไม่ติดตั้งบริการหรือเปลี่ยนFirewallให้อัตโนมัติ ไฟล์enrollmentต้องป้องกันด้วยACLที่เหมาะสม

## หลักฐานและข้อจำกัด

อ่าน [ผลตรวจรับ](docs/ACCEPTANCE.md), [รายงานแต่ละStage](docs/stages/G0.md), [ย้อนกลับ](docs/ROLLBACK.md) และ [WinCC preflight](docs/WINCC_READONLY_PREFLIGHT.md) Source v0.3ต้นฉบับไม่ถูกแก้ รูปปั๊มSVGเดิมเก็บไว้ครบ ทดสอบหน้าจอ1366×768,1600×900,1920×1080 ไม่มีpage overflow

คิวมีขีดจำกัด: Agent pending10000, เก็บACKedล่าสุด2000, Gateway/Central ledger50000รายการ ฐานข้อมูลประมาณ64MiBบวกWAL/SHM; เมื่อเต็มจะหยุดรับ/รายงานข้อผิดพลาดและเก็บข้อมูลที่ยังไม่ACKไว้ ไม่ใช่historianสำหรับเปิดทิ้งไม่จำกัด ตรวจดิสก์และเริ่มsessionใหม่ก่อนสาธิตยาว
