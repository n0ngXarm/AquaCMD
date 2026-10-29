# AQUA COMMAND0.9 — Actual read-only runtime path

โปรแกรม Desktop สำหรับอ่านสถานะปั๊มที่ผู้ใช้เลือก เก็บคิวในเครื่อง และส่งผ่านเครื่องรับที่ลงทะเบียน ไม่มีเว็บไซต์ ไม่มีข้อมูลจำลองในเส้นทางใช้งานปกติ

| เครื่อง | โปรแกรม | หน้าที่ |
| --- | --- | --- |
| Windowsเครื่อง WinCC V8.1 | `AquaCommand.WinCCReader.exe` | อ่าน local OPC DA3 เฉพาะ binary Tagsทุก5วินาที เก็บdurable spool ส่งHTTPSหลังอนุญาตแยก |
| Linux/Fedora44เครื่อง Gateway | `aqua-command-desktop-0.9.0-1.fc44.noarch.rpm` | Native GTK7หน้า รับจากสมาชิกด้วยTLS/HMAC เก็บSQLite archiveและแจ้งเตือนตามสิทธิ์ |
| Linuxที่มีRuntimeCSVจริงอยู่แล้ว | RPMเดียวกัน | Agentอ่านเฉพาะ complete CSV framesแล้วส่งGatewayที่ระบุ ไม่มีLAB fallback |

**ขณะนี้ OPC DA ของหน้างานยังไม่ได้รับอนุญาตให้เปิดใช้งานทางการ** โปรแกรมไม่เปิดบริการ ไม่แก้WinCC/PLC/DCOM/firewallให้เอง ตัวอ่านWindowsต้องยืนยันว่าได้รับอนุญาตจากหน่วยงานแล้วและกดเริ่มอ่าน Linux testsและการสร้างEXEไม่ใช่การตรวจรับบนWindows/WinCCจริง

## พฤติกรรมและความปลอดภัย

- เปิดโปรแกรมแล้วidle ไม่เริ่มworker/source read/probe/transferเอง อ่านและส่งต้องกดอนุญาตแยกกันในแต่ละการเปิดใช้งาน
- Windows readinessอ่านregistrationเท่านั้น COMactivationอยู่หลังยืนยันสิทธิ์และอาจเริ่มlocal OPC serverที่ติดตั้งไว้ ไม่ถือว่าreadinessเป็นการอนุญาต
- ใช้ `OPCServer.WinCC` และ `IOPCItemIO::Read` เฉพาะเครื่องWindowsนั้น ไม่เปิดremoteDCOM ไม่browseทุกTag ไม่มีAPIเขียนหรือสั่งปั๊ม
- อ่านcached Runtimeทุก5วินาที (`maxAge=UINT_MAX`) ไม่บังคับPLCอ่านdeviceทุกครั้ง แยกเวลาReadกับsourceFILETIME เก็บquality/HRESULTจริง;qualityBAD/UNCERTAIN/unknownไม่ตีเป็นOFF
- เลือก1–100 exactbinaryTag namesเท่านั้น ตรวจmapping0=OFF/1=ONเอง ตัวเลขanalogหรือชนิดที่ไม่รองรับเป็นUNKNOWN ไม่มีค่าตัวอย่างมาแทน
- HTTPSเฉพาะprivateIPv4ที่ระบุและคีย์64hexแยกแต่ละPC ตรวจCA/IP SANและHMACทั้งrequest/response ไม่สแกนLAN ไม่เปิดNAT/bridge/Internet sharing
- Gatewayรับเก็บได้เมื่อผู้ใช้อนุญาตรับ แม้Internetยังไม่พร้อม การprobe/sendTelegramต้องอนุญาตส่งแยก
- ACKหมายถึงGatewaycommitลงdiskแล้ว ไม่ใช่Telegramส่งสำเร็จ Retryใช้eventUUID/sequence/digestเดิม ไม่ลบpendingเมื่อผิดพลาด เปลี่ยนTagรักษาsequenceและคิวเดิม แต่ตัดการเปรียบเทียบON/OFFข้ามconfiguration

## เริ่มใช้งาน

อ่าน [ขั้นตอนติดตั้งและตรวจรับ](docs/COMMISSIONING.md) ก่อนใช้งานจริง

Linux:

```sh
sudo dnf install ./aqua-command-desktop-0.9.0-1.fc44.noarch.rpm
aqua-command
```

เลือก **ตั้งค่าแหล่งข้อมูล → Gateway** ระบุIPที่เครื่องนี้มีอยู่จริง,certificate/privatekeyที่ได้รับอนุญาตและคีย์สมาชิก บันทึกแล้วกดเริ่มรับข้อมูลอีกครั้ง โปรแกรมไม่สร้างcertificateหรือเปลี่ยนnetwork configurationให้เอง

Windows:เปิด `.exe` บนเครื่องWinCC ปกติด้วยสิทธิ์ที่ได้รับอนุญาต ไม่จำเป็นต้องรันAdministratorอัตโนมัติ ระบุPC-01/02/03ให้ไม่ซ้ำกัน,รายชื่อTag,GatewayURL/คีย์/CA ตรวจความพร้อม ยืนยันสิทธิ์หน่วยงานแล้วกดอ่าน การส่งต้องกดอนุญาตต่างหาก ปิดโปรแกรมแล้วคิวไม่หาย ไม่มีautostart service

## Telegram

ค่าเริ่มต้นGatewayเป็นdry-run ไม่ส่งภายนอก หากเลือกTelegramจริง ต้องตั้งenvในsessionที่เปิดGateway:

```sh
export TELEGRAM_BOT_TOKEN='your-approved-token'
export TELEGRAM_CHAT_ID='your-approved-chat-id'
export TELEGRAM_APPROVED_ENDPOINT='https://api.telegram.org'
aqua-command
```

เลือกTelegramจริงในหน้าตั้งค่าแล้วกดอนุญาตส่งจึงเริ่มgetMe/probeและsendMessage ไม่ใส่tokenในURLหน้าจอ/log/repository โปรแกรมแจ้งเตือนเฉพาะtransition;Runtime snapshotsอยู่ในGatewayarchive TelegramAPIไม่มีtransactionร่วมกับคิว ข้อความอาจซ้ำหากresponseหายหลังส่งสำเร็จ มีevent_idไว้ตรวจสอบ

## ข้อจำกัดข้อมูล

- Windowsคิวpendingสูงสุด10,000events/64MiB ACKแล้วจะนำออกจากpending CSVส่งออกเฉพาะpendingไปไฟล์ใหม่ในAQUAprofile จึงไม่ใช่คลังประวัติถาวรหลังส่ง
- Gatewayarchiveสูงสุด50,000recordsและdatabase64MiB เต็มแล้วจะปฏิเสธcustodyโดยไม่ลบข้อมูลที่ยังเก็บอยู่ ต้องกำหนดนโยบายarchive/retentionที่อนุมัติก่อนรันระยะยาว ไม่มีปลายทางเก็บsnapshotถาวรภายนอกในรุ่นนี้
- LinuxCSVAgentเพดานpending10,000/ACKedhistory2,000/DB64MiB;CSVexportสูงสุด2,000events/250KBพร้อมpartialflag
- ปุ่มที่ยังไม่รองรับ เช่น per-itemrule/hot reload/fullauditจะแสดงเหตุผล ไม่มีการสร้างข้อมูลเทียมเติมหน้าจอ
- EXEเป็นunsigned Windowsx64 self-contained cross-build;RPMเป็นunsigned Fedora44 LABpackage ตรวจด้วยpayloadจริง ยังไม่อ้างsystemDNF/Windows/WinCC/physicalLAN/Telegramจริงผ่านการตรวจรับ

## ตรวจสอบและสร้างใหม่

```sh
npm test --prefix backend
python3 -B -m unittest discover -s desktop/tests -v
bash packaging/build-rpm.sh /absolute/owned-build-directory
AQUA_DOTNET=/path/to/dotnet bash packaging/build-windows.sh /absolute/owned-output-directory
```

WindowsCoretestsมีข้อมูลทดสอบเฉพาะprojectTests โปรแกรมจริงไม่มีsimulator แยกผลprotocol/LinuxออกจากWindowsCOM/WinCCและLANข้ามเครื่องเสมอ [ผลทดสอบ/ขอบเขต](VERIFICATION.md)
