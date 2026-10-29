# ตั้งค่า Real LAN ใน LAB ที่ได้รับอนุญาต

สถานะหลักฐาน: **NOT VERIFIED: two physical hosts** คู่มือนี้เตรียมความสามารถแยกเครื่อง ใช้เฉพาะเครื่องทดสอบที่ได้รับอนุญาต ไม่เปลี่ยน Router/Firewall/Switch/NAT/bridge หรือเชื่อม PLC/WinCC เครื่องจริง

## 1. เตรียมและลงทะเบียน

ติดตั้ง Source/แพ็กเกจเดียวกันและ Node22.13+ บนเครื่องLABแต่ละเครื่อง ตั้งเวลาเครื่องให้ใกล้กันภายใน30วินาทีสำหรับการยืนยันลายเซ็น ห้ามให้โปรแกรมไปแก้นาฬิกา/เครือข่ายให้อัตโนมัติ สร้าง enrollmentในโฟลเดอร์ส่วนตัวครั้งเดียว:

```sh
npm run enroll -- --data-dir ./lab-enrollment --port 4173
```

คำสั่งพิมพ์เฉพาะเส้นทางไฟล์ ไม่พิมพ์key ไฟล์จะอยู่ใต้ `lab-enrollment/enrollment/config-<uuid>/` และmanifestชี้รุ่นปัจจุบัน ไฟล์เหล่านี้เป็นความลับ ไม่ใส่Git/ZIP/ภาพหน้าจอ ส่งเฉพาะไฟล์บทบาทที่ต้องใช้ผ่านช่องทางที่ได้รับอนุญาต ห้ามคัดลอก enrollmentทั้งหมดให้ทุกเครื่อง Dashboardมีสิทธิ์อ่านสถานะและkeyควบคุมLAB; ให้ผู้ดูแลที่อนุญาตเท่านั้น

## 2. แก้ค่าบนสำเนา configของแต่ละเครื่อง

เลือก private IPv4ที่ผู้ดูแลยืนยันแล้วเท่านั้น (10.x,172.16–31.x,192.168.x) โปรแกรมไม่ค้นหาIPให้และไม่รับpublic IP/hostnameสุ่ม ตัวอย่างต่อไปนี้คือdocumentation addressesของLAB ไม่ใช่IPหน่วยงานที่ตรวจพบ:

| บทบาท | ค่าในconfigที่ต้องแก้ |
|---|---|
| Agent PC-01 | `listen.host` = private IPของPC1, `listen.port` =4181, `gatewayUrl` = `http://<approved-PC4-IP>:4174`, `dataDir` = absolute local directoryเฉพาะPC-01 |
| Agent PC-02/03 | เหมือนกัน ใช้id/secretเดิมของตัวเองและพอร์ต4182/4183 |
| Gateway PC-04 | `listen.host` = private IPของPC4, `listen.port` =4174, `dataDir` = absolute local directoryเฉพาะPC-04; เก็บkeysจากenrollmentเดิม |
| Central (optional) | private/loopback listenerที่ได้รับอนุญาต; Gateway `upstream.url`ตรงกันและsecretต้องคู่กัน |
| Dashboard | listenerคง`127.0.0.1:4173`; `agents[].url`และ`gateway.url`ชี้approved IP; config.roleยังเป็นdashboard |

ทุกบทบาทที่รับ/เรียกprivate IPต้องมี `"allowLan":true` และเมื่อสั่งต้องเติม `--allow-lan` ด้วย ถ้าเลือกHTTPต้องมี `"allowInsecureLabHttp":true` ชัดเจน **ใช้เฉพาะisolated trusted LAB**: HMACยืนยันตัวตนและความครบถ้วนแต่ไม่ปิดบังpayloadหรือsessionจากผู้ดักฟัง ไม่ใช้production ไม่ตั้ง`0.0.0.0`หรือpublic listener

แนะนำHTTPSที่ผู้ดูแลอนุมัติ: บนlistener Agent/Gateway/Centralเพิ่ม `"tls":{"keyFile":"/absolute/private/key.pem","certFile":"/absolute/cert.pem"}` เปลี่ยนURLที่ผู้เรียกใช้เป็นhttpsและเพิ่ม`caFile`ชี้CAที่อนุมัติในconfigผู้เรียกแต่ละบทบาท Certต้องมีSANตรงIPที่ใช้ Nodeตรวจchainและชื่อเสมอ ไม่มีตัวเลือกปิดTLS verification ในโปรแกรม การออกcert/ติดตั้งCAอยู่นอกงานนี้

Centralไม่บังคับ: ถ้าไม่มีให้ลบ`upstream`ออกจากGateway และ`central`ออกจากDashboard Raw snapshotsจะคงอยู่Gateway (pendingไม่ลดเพราะไม่มีCentral) ส่วนtransitionยังเข้าdry-runได้ ไม่มีการส่งออกที่อื่นแทนโดยอัตโนมัติ ถ้าใช้CentralบนPC4เดียวกันให้คงloopback4175และเริ่มแยกโปรเซส

คง `sourceAdapter:"simulated-runtime"`, `intervalMs:5000`, `internetMode:"simulated"` เป็นค่าเริ่มต้น เลือก `readOnly:true` บนAgent/Gatewayหากต้องการห้ามคำสั่งจำลอง LAN Dashboardบังคับread-onlyเสมอ ไม่มีปุ่มสั่งPLC ไม่ปรับTagจริง ไม่สร้างDB22/DB34 mapping

## 3. เปิดบทบาทแยกเครื่อง

เปิดGatewayบนPC4:

```sh
npm run demo:lan -- --role gateway --config /absolute/private/gateway.json --allow-lan
```

เปิดAgentตามเครื่องของตัวเอง:

```sh
npm run demo:lan -- --role agent --config /absolute/private/PC-01.json --allow-lan
```

เปิดCentralถ้าเลือกใช้ และlocalDashboardบนเครื่องผู้สาธิต:

```sh
npm run demo:lan -- --role central --config /absolute/private/central.json --allow-lan
npm run demo:lan -- --role dashboard --config /absolute/private/dashboard.json --allow-lan
```

เปิดviewerที่127.0.0.1:4173ของเครื่องDashboardเอง ไม่เปิดinboundจากInternet คำสั่งเริ่มเฉพาะroleที่ระบุ ไม่forkชุดsingle ไม่แก้การตั้งค่าเครือข่าย โปรแกรมGET `/health`บอกเพียงid/role; ข้อมูลสถานะและuploadต้องauth

ผู้ดูแลที่ได้รับอนุญาตต้องตรวจสิทธิ์รับส่งระหว่างIP/portที่เลือกเอง ถ้าถูกFirewallบล็อก ให้หยุดที่ข้อผิดพลาด ไม่มีคำสั่งเปิดFirewallในคู่มือนี้ ห้ามลดความปลอดภัยหรือเปิดพอร์ตออกนอกLABเพียงเพื่อให้DEMOผ่าน

## 4. ตรวจรับข้ามเครื่องก่อนอ้างผล

บันทึกOS/Node/role PIDและapproved endpointแบบredactedจากแต่ละเครื่อง แสดงclockและtimestampให้เทียบได้ โดยไม่บันทึกkey หยุดGatewayด้วยCtrl+Cแล้วรอ15วินาที:Agentต้องมี3snapshotใหม่และpendingเพิ่ม เปิดGatewayที่endpointเดิมและdataDirเดิม:handshake/authต้องผ่าน,pendingลดหลังACK,Gateway receivedเพิ่ม หยุด/เปิดAgentแล้วเลขsequenceและpumpstateไม่ถอยหลัง

หากเลือกCentralให้ตั้งGateway`internetOnline:true`ในconfigใหม่ก่อนเริ่มsession (ค่าในDBเดิมมีลำดับความสำคัญและจะไม่ถูกoverwrite) เพื่อทดสอบdrain simulated gate การเปลี่ยนconfigอย่างเดียวไม่ใช่หลักฐานnetwork failure ไม่ต้องตัดInternetจริงหรือแก้routing การจำลองtoggleแบบinteractiveครบถ้วนอยู่ในdemo:single

เมื่อทดสอบจริงสำเร็จค่อยเพิ่มรายงานแยก **VERIFIED ON TWO LAN HOSTS** พร้อมเหตุการณ์/เวลา/ผล ไม่แก้labelในsingleเพื่อแกล้งอ้างข้ามเครื่อง ปัจจุบันviewerLANแสดงว่า2เครื่องยังไม่verified

## 5. เก็บข้อมูลและหยุด

Ctrl+Cหยุดแต่roleของตนเอง dataDirต้องอยู่local diskของroleนั้น ไม่แชร์SQLiteผ่านnetwork filesystem เก็บenrollmentและdataของsessionไว้ด้วยกัน กระบวนการ ownershipตรวจboot/start identityเพื่อกันเปิดสองwriter ถ้าตรวจidentityไม่ได้จะfail closed ห้ามลบowner metadataขณะโปรเซสยังทำงาน
