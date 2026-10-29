# สคริปต์สาธิต3–5นาที (บนLaptopเครื่องเดียว)

เตรียม Node22.13+ ใช้ source/tarball v0.4และโฟลเดอร์ข้อมูลใหม่ ไม่มีtoken/envภายนอก เปิดด้วย `npm run demo:single -- --data-dir ./lab-data-presentation --port 4173` เข้า127.0.0.1:4173 ตั้งหน้าจอ1366×768ขึ้นไป กดDiagnosticsดูactualPIDของ3AgentและCentral Gatewayยังไม่เริ่ม

| เวลา | ทำอะไร | สิ่งที่พูด/หลักฐานที่ต้องเห็น |
|---|---|---|
|0:00–0:40|ชี้ฉากเดิมและป้ายSIMULATED / TESTED ON ONE HOST|“ปั๊มเป็นข้อมูลจำลอง แต่3Agentเป็นคนละโปรเซสและเขียนข้อมูลลงดิสก์จริง ไม่แตะPLC/WinCC” ดูPID,latest/next exportในDiagnostics|
|0:40–1:15|คงGateway DISCONNECTED รอ15วินาที|snapshotของแต่ละAgentเพิ่มประมาณ3รายการ pendingเพิ่ม เปิดsnapshotJSONจากDiagnostics ให้เห็นtimestamp,sequence,values boolean,simulated:true|
|1:15–1:50|กดCONNECT GATEWAY คงInternet DOWN|Gatewayเป็นโปรเซสใหม่จริง แสดงhandshake/auth,ACKเวลาและsource pendingลด Gateway received/pendingเพิ่ม อธิบายว่าACKแล้วไม่ได้แปลว่าส่งออกภายนอกแล้ว|
|1:50–2:20|คลิกPUMP-03จากOFFเป็นONหนึ่งครั้ง|STATE_CHANGEเพิ่มหนึ่ง Exportยังเดินทุก5วินาที ขณะInternet DOWN notificationยังรอ|
|2:20–2:55|กดInternet ON|นี่คือsimulated gate ไม่ใช่การตรวจเน็ตจริง Central mockรับผ่านHTTP,Gateway pendingลดและTelegram DRY-RUNเพิ่ม1ครั้ง รอ2snapshotยืนยันไม่แจ้งทุก5วินาที|
|2:55–3:35|เปิดDiagnostics กดDROP NEXT ACK รอรอบถัดไป|แสดงRETRY/ACK,duplicatesฝั่งGatewayเพิ่ม แต่notificationไม่เพิ่มซ้ำ แสดงdiskbytesและlogDELIVERY|
|3:35–4:20|Ctrl+Cแล้วเริ่มคำสั่งเดิม/data-dirเดิม|Agentกลับมาพร้อมstate/sequence/queueเดิม Gatewayเริ่มabsentอีกครั้ง ให้CONNECTแล้วดูข้อมูลต่อ ไม่สร้างfalse transition|
|4:20–4:40|สรุปข้อจำกัด|“พิสูจน์transportจริงบนเครื่องเดียวแล้ว การเดินสายLAN2เครื่อง,Windows,TelegramจริงและWinCCยังไม่ได้ทดสอบ ต้องแยกตรวจรับก่อนใช้”|

ถ้าGateway queueระบายเร็วจนเห็นไม่ทัน ให้คงInternet DOWNนานขึ้น ห้ามเพิ่มข้อมูลปลอมเพื่ออวดcounter ถ้าเกิดERRORให้อ่านlogและข้อมูลจริง ไม่ถือว่าPump OFFเมื่อsourceหาย

RESET LABใช้เริ่มsessionใหม่และเก็บsessionเก่าไว้ ถ้าต้องการหลักฐานrecoveryห้ามRESETก่อนเปิดdata-dirเดิม ไม่ต้องเปิดFirewall,Internet sharing,NAT/bridgeหรือเชื่อมต่ออุปกรณ์OTเพื่อทำสาธิตนี้
