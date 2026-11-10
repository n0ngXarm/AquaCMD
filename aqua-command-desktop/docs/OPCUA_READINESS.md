# ตรวจความพร้อม OPC UA แบบครั้งเดียว

สคริปต์ `tools/check_opcua_readiness.py` ใช้ client และหลักฐานชุดเดียวกับ F3 เพื่อทดสอบว่าเส้นทางอ่านทำงานครบหรือยัง โปรแกรมเดสก์ท็อปไม่เรียกสคริปต์นี้เอง

เตรียมไฟล์ส่วนตัวในรูปแบบ [collector](PROBE_PHASE4.md) โดยเลือกเฉพาะสถานีที่ได้รับอนุญาต 1–4 เครื่อง ตั้ง `ping_timeout_s` และ `tcp_timeout_s` ตามเวลาที่อนุมัติ และกำหนดแต่ละ target ดังนี้

- ใช้ IPv4 ใน RFC 1918 พอร์ต TCP 4840 และ URL `opc.tcp` ที่ตรงกับ host/port โดยไม่มีบัญชีผู้ใช้ใน URL
- ใช้ `ua.security_policy: "Basic256Sha256"` แบบ SignAndEncrypt และ Anonymous ตามขีดความสามารถของ collector
- กำหนด `ua.nodes` เป็นชื่อ Tag และ NodeId ที่วิศวกรหน้างานยืนยันแล้ว **หนึ่งคู่ต่อสถานี** เช่น `"Tank.Level": "ns=2;s=Tank.Level"` สำหรับระบบตัวอย่าง
- กำหนด `ua.pki_dir` เป็น path เต็มหากใช้ PKI ส่วนตัวคนละที่กับ `~/.config/aqua-command/pki` ต้องมีใบรับรองและกุญแจ client ที่ยังใช้ได้ และยืนยัน server certificate ใน trust store ไว้ก่อน
- ตัด `interval_s` และ `internet` ออกจากชุดตั้งค่านี้

WinCC Export เป็นแคตตาล็อกชื่อ Tag จึงต้องยืนยัน NodeId แยกต่างหาก เครื่องมือไม่เดา NodeId และไม่เลือก ServerStatus มาแทน Tag กระบวนการ

รันจากโฟลเดอร์โปรเจกต์ โดยกำหนดตัวแปร `READINESS_CONFIG` และ `APPROVED_SWITCH_IP` จากข้อมูลที่ได้รับอนุญาต คำสั่งนี้ตรวจรูปแบบข้อมูลโดยยังไม่ส่งแพ็กเก็ต

```bash
python3 -B tools/check_opcua_readiness.py \
  --config "$READINESS_CONFIG" --switch "$APPROVED_SWITCH_IP"
```

เมื่อผู้รับผิดชอบยืนยันให้ตรวจหน้างาน ให้กำหนด `NEW_PRIVATE_REPORT` เป็นไฟล์ใหม่ในโฟลเดอร์ส่วนตัวนอกรีโป แล้วสั่งรันหนึ่งรอบ

```bash
python3 -B tools/check_opcua_readiness.py \
  --config "$READINESS_CONFIG" --switch "$APPROVED_SWITCH_IP" \
  --execute --report "$NEW_PRIVATE_REPORT"
```

สคริปต์ ping สวิตช์ครั้งเดียว แล้วตรวจ TCP ของแต่ละสถานีที่ได้รับอนุญาต หาก TCP ผ่าน จึงตรวจความพร้อมของใบรับรองและกุญแจ client ใน PKI ก่อนส่ง GetEndpoints จากนั้นเลือก SignAndEncrypt ตรวจใบรับรอง server เปิด session อ่าน Value หนึ่ง NodeId และปิด session เครื่องที่ติดขั้นใดจะข้ามขั้นถัดไป การตรวจ PKI ทำบนสำเนาชั่วคราวส่วนตัว โดยต้นฉบับไม่ได้รับการแก้ไขหรือเพิ่มใบรับรองที่ยังไม่ผ่านการอนุมัติ

ตารางแสดง PASS, FAIL หรือ SKIPPED พร้อมสาเหตุ รายงาน JSON mode 0600 ใช้โครง `generated_at / stale_ms / nodes` ของ F3 และมี `readiness` สำหรับผลรายขั้น หลักฐานที่เขียนลง SQLite ชั่วคราว และตัวอย่าง DataValue ที่อ่านได้จริง เก็บรายงานไว้ในพื้นที่ส่วนตัว เพราะมี IP, NodeId และค่าที่อ่านจากหน้างาน Exit code 0 คือผ่านครบหรือผ่านการตรวจรูปแบบแบบไม่ส่งแพ็กเก็ต, 1 คือมีขั้นที่ไม่ผ่าน, 2 คือข้อผิดพลาดด้านการตั้งค่าหรือการรัน และ 130 คือผู้ใช้หยุด

การทดสอบซอฟต์แวร์ใช้ `sim: true` ที่ 127.0.0.1:4850 และใช้ loopback อีกที่เป็นสวิตช์ทดสอบ เช่น 127.0.0.2 ให้รันตัวจำลองและชุดเทสต์ใน network namespace ที่มีเฉพาะ loopback ผล SIMULATED ใช้ตรวจซอฟต์แวร์เท่านั้น
