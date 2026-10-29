# AQUA COMMAND v0.4 — ส่งมอบ LAB DEMO

G0–G5 ผ่าน6/6 ตามลำดับ ทดสอบล่าสุด28/28 ไม่มีfail/skip ต่อจากSource v0.3จริงและรักษาIsometric UIเดิม ไม่แก้ต้นฉบับDownloadsทั้ง13ไฟล์ ไม่แตะProduction/PLC/WinCC/Network configuration

## เปิดโปรแกรม

แตก `AQUA_COMMAND_v0.4_Source.zip` เข้าโฟลเดอร์ `aqua-command-isometric-demo` ติดตั้งNode22.13+ แล้วใช้:

```sh
npm install --offline --ignore-scripts --no-audit --no-fund
npm run demo:single
```

เปิด http://127.0.0.1:4173 Gatewayเริ่มoffline ให้รอเห็นsnapshotและคิวเพิ่ม แล้วCONNECT GATEWAY คงInternet DOWNเพื่อเห็นGatewayคิวสะสม คลิกPUMP-03หนึ่งครั้ง จากนั้นInternet ONเพื่อส่งCentralและสร้างTelegram DRY-RUNหนึ่งครั้ง Ctrl+Cหยุดโปรแกรม ข้อมูลอยู่ในlab-data-v04 เปิดซ้ำด้วยdata-dirเดิมเพื่อกู้คืน

[คู่มือภาษาไทย](source/README_TH.md) · [สคริปต์3–5นาที](source/docs/DEMO_SCRIPT_TH.md) · [ตั้งค่าLAN](source/docs/LAN_SETUP_TH.md) · [Architecture](source/README.md) · [Rollback](source/docs/ROLLBACK.md)

## ผลตรวจรับ

|Stage|ผล|จำนวนtestผ่าน|
|---|---|---|
|G0|Audit/baselineก่อนแก้|4|
|G1|Agent/Gatewayคนละprocess+HTTPจริง|7|
|G2|Durable ACK/retry/dedup/recovery|12|
|G3|Central+transition-only dry-run|19|
|G4|เชื่อมUIเดิมและแก้overflow|22|
|G5|Cadence/reset/review/package/install|28|

[รายงานรวม](ACCEPTANCE.md) · [G0](G0_AUDIT_TH.md) · [G1](G1_REPORT_TH.md) · [G2](G2_REPORT_TH.md) · [G3](G3_REPORT_TH.md) · [G4](G4_REPORT_TH.md) · [G5](G5_REPORT.md) · [ผลtest](evidence/g5-tests.txt) · [ผลตรวจแพ็กเกจ](evidence/g5-package-audit.json)

Clean installยืนยัน6PIDแยกกัน ส่งข้อมูลจริงผ่านloopback HTTP,คิวระบายเหลือ0,เปิดปั๊มหนึ่งครั้งแจ้งDry-run1รายการแม้Snapshotเดินต่อ ภาพทั้ง1366×768/1600×900/1920×1080อยู่ในevidence ไม่ได้เปลี่ยนฉากSVGเดิม

**ทดสอบจริงบนLinuxเครื่องเดียว (TESTED ON ONE HOST)** ข้อมูลปั๊ม/กราฟ/Internet gateเป็นSIMULATED **ยังไม่ทดสอบ2เครื่องจริงในLAN,Windows,Telegramจริง,HTTPSข้ามเครื่องหรือไฟดับ/rebootจริง** ไม่มีWinCCdriverจริง ไม่มีPLCaddress mapping และไม่รับรองTelegram exactly-once

ไฟล์.tgzเป็นnpmแพ็กเกจที่ตรวจติดตั้งแล้ว Git bundleเก็บประวัติG0–G5และbaseline-v0.3เพื่อrollbackแยกcheckout ค่าhashอยู่ในSHA256SUMS.txt ทั้งZIPและnpmแพ็กเกจไม่ใส่generated enrollment,key,SQLiteหรือnode_modules ค่าเริ่มต้นTelegram DRY-RUNและไม่มีexternal networking
