# การติดตั้งและตรวจรับข้อมูลจริง

เอกสารนี้ไม่ใช่การอนุญาตให้เปิดOPC DAหรือเชื่อมต่อProduction ต้องได้รับอนุญาตจากเจ้าของWinCC/เครือข่ายก่อนตามที่ผู้ใช้ระบุ

## ก่อนนำไปเครื่องWinCC

1. ให้ผู้ดูแลยืนยันรุ่นWinCCV8.1Classic,Runtimelicense/Runtimeที่ทำงานอยู่,ส่วนOPC DAที่ติดตั้งและเปิดใช้งานโดยผู้มีอำนาจ โปรแกรมใช้ `OPCServer.WinCC` ไม่ใช้ชื่อ `WinCC.OPCServer.1` และไม่เปิดOPC UA
2. ขอรายการbinaryTagsที่อนุญาตอ่าน ตรวจ0/1mappingกับหน้าจอWinCC และสิทธิ์Windowsของผู้รัน ห้ามเพิ่มสิทธิ์หรือแก้DCOM/บริการเพียงเพื่อให้โปรแกรมผ่าน
3. กำหนดExporterIDไม่ซ้ำ PC-01..03และคีย์64hexที่แตกต่างกัน ลงทะเบียนในGatewayเฉพาะสมาชิกเหล่านี้ คีย์ไม่ใช่passwordของPLC/WinCC
4. ให้ผู้ดูแลจัดHTTPSservercertificateที่มีIP SANตรงGateway,privatekeyและCAที่เครื่องส่งตรวจสอบได้ โปรแกรมไม่ออกcertificate/ติดตั้งCAหรือแก้firewallเอง Default127.0.0.1เหมาะทดสอบเครื่องเดียว สำหรับข้ามเครื่องต้องระบุprivateIPที่มีอยู่จริงบนGateway

## Gateway Linux

ติดตั้งRPMผ่านDNFที่ได้รับอนุญาตแล้วเปิดจากเมนูแอป ค่าเริ่มต้นไม่ทำงาน

- ตั้งค่าGateway:IP/port,TLS certificate/key,คีย์สมาชิก บันทึกยังไม่รับข้อมูล
- กดเริ่มรับข้อมูลแล้วตรวจpermissionreviewจึงเปิดreceiver;ยังไม่มีInternetprobe/send
- ค่าแรกเป็น0เมื่อGatewayรายงานจริง หรือขีดหากไม่เคยตรวจ ไม่แสดงExporterว่าonlineเพียงเพราะลงทะเบียน
- ระหว่างofflineรับเก็บลงarchiveได้ คิวเครื่องส่งลบเฉพาะหลังตรวจsigneddigestACKจากGateway
- Telegramเลือกdry-runไว้ได้ หากจะส่งจริงต้องตั้งtoken/chat/approvedfixedendpointและกดอนุญาตส่งแยก นี่เป็นการกระทำภายนอกที่ต้องอนุญาตก่อน

## Windows Runtime Reader

เปิดEXEบนWindowsเครื่องWinCC ไม่มีworker/COMconnectionตอนเปิด

- เลือกSourceID/Tagallowlist(1–100)/GatewayURL/คีย์/CA ไม่มีรายชื่อTagตัวอย่างเริ่มต้น เลือกCAว่างได้เฉพาะเมื่อWindows truststoreเชื่อถือchainนั้นอยู่แล้ว
- ปุ่มตรวจความพร้อมอ่านregistryที่มีอยู่ ไม่activateCOMและไม่รับรองว่าRuntimeพร้อม หากไม่มีregistrationให้หยุดและส่งข้อมูลแก่ผู้ดูแล ห้ามเปิดบริการเอง
- ยืนยันว่าได้รับอนุญาตจากหน่วยงานแล้ว ตรวจTagmappingและกดอนุญาตอ่าน หน้าตรวจย้ำว่าCOMอาจเริ่มlocalserver ไม่แก้WinCCconfiguration
- ตรวจRAW/Qualityword/HRESULT/source timestamp/readtimeกับWinCCจริง ก่อนยอมรับผล ทดสอบON/OFFด้วยเหตุการณ์หน้างานที่เกิดโดยผู้ควบคุมตามปกติ AQUAไม่มีปุ่มสั่งปั๊ม
- คิวอยู่ในLocalAppData/AquaCommand/WinCCReader/โปรไฟล์SourceID ไม่อยู่ในWinCCproject path ตอนเริ่มครั้งแรกจึงสร้างคิว เมื่อหยุดอ่านค่าบนหน้าจอเป็นCACHED
- กดอนุญาตส่งแยก ระบุHTTPSGatewayให้ตรงcertและคีย์ ลองปิดการรับที่Gatewayแล้วตรวจpendingเพิ่ม/คงอยู่ เปิดรับกลับแล้วตรวจACKและduplicateไม่เพิ่มผลซ้ำ
- ก่อนเปลี่ยนGateway/CAต้องจัดการpendingที่ผูกปลายทางเดิม โปรแกรมไม่ย้ายข้อมูลค้างไปปลายทางใหม่เงียบๆ เปลี่ยนTagไม่resetsequenceหรือทิ้งpending แต่ต้องหยุดsession/อนุญาตใหม่

## เกณฑ์ตรวจรับที่ยังต้องทำบนเครื่องที่อนุญาต

| ข้อ | หลักฐานหน้างานที่ต้องเก็บ |
| --- | --- |
| Windows/COM | OS/architecture,registration,Runtimeprocess,permissions,actualreadHRESULT |
|5s | timestampหลายรอบจริง ตรวจโหลดWinCCและไม่อ่านถี่ชดเชยเมื่อรอบช้า |
|Dataquality | RAW0/1,bad/uncertain,sourceFILETIMEแยกจากreadtime,ไม่มีOFFเทียม |
|Read-only | ไม่เปลี่ยนTag/PLC/project/DCOM/services/firewall;ตรวจpermissionและauditที่หน่วยงานใช้ |
|Durability | ปิด/เปิดAQUAขณะpending,ตรวจUUID/sequenceเดิมและไม่เริ่มอ่าน/ส่งเอง |
|สองเครื่องจริง | cert/IPtrust,คีย์ผิด,networkdisconnect/rejoin,คิวdrain,GatewayarchiveและACK |
|Outbound | หลังอนุมัติเท่านั้น ตรวจTelegramgetMe/sendMessageจริง,event_idและduplicateambiguousresponse |
|Capacity | ตกลงfinitearchive/retentionก่อนใช้งานหลายวัน ไม่ลบrecordsเพื่อทำให้หน้าจอเขียว |

ผลจากLinuxprotocoltestsหรือtestfixturesไม่ใช้แทนการตรวจรับตารางนี้

## Rollback

หยุดอ่าน/ส่งและปิดAQUA เก็บLocalAppDataและGatewayactual-profilesรวมSQLite/คิวไว้ทั้งหมด ถอน/ย้ายตัวโปรแกรมได้โดยไม่ลบข้อมูล ห้ามเปิดโปรแกรมรุ่นเก่ามารับv3หรือresetคิวเพื่อให้ส่งผ่าน รุ่น0.8ไม่มีdirectOPCreaderและไม่รองรับdeployedprofileนี้ การย้อนกลับต้องรักษาข้อมูล0.9สำหรับอ่าน/กู้คืนต่อด้วยรุ่นที่รองรับ
