# แหล่งข้อมูล OPC DA, REST และ MQTT สำหรับหน้าติดตามค่า

AQUA COMMAND รองรับการอ่าน snapshot ผ่าน REST และ MQTT ด้วยคำสั่งเดียวกัน เก็บหลักฐานใน SQLite แยกจาก OPC UA แล้วแสดงในหน้าติดตามค่า เมื่อเลือกแหล่งนั้น โปรแกรมจะแสดงชื่อโปรโตคอล รหัสแหล่ง และเวลาที่ต้นทางระบุ ป้าย SIMULATED ใช้กับข้อมูล LAB

ใช้ endpoint หรือ topic จาก Gateway ที่มีสิทธิ์เผยแพร่ข้อมูลอ่านอย่างเดียว Gateway ต้นทางต้องจัดรูปแบบ payload ตามสัญญาด้านล่าง ผู้ดูแลเลือกเส้นทางเครือข่ายและสิทธิ์ก่อนรัน ตัวอ่านไม่เริ่มเองเมื่อเปิดโปรแกรม และการเลือกแหล่งสำรองมีผลเฉพาะการแสดงค่าในหน้าติดตามค่าเท่านั้น การประเมิน Task, ผังการสื่อสาร และ Telegram ไม่ถูกเรียกจากข้อมูลชุดนี้

## เรียกจากหน้าตั้งค่าการเชื่อมต่อ

เปิดฟันเฟืองมุมขวาล่าง แล้วเลือก **แหล่งข้อมูล** เลือกโปรโตคอล กรอกแหล่งข้อมูล และใส่ชื่อ Tag ที่ต้องการอ่านทีละบรรทัด ใช้ **บันทึกและใช้แหล่งนี้** เพื่อสลับหน้าแสดงผลโดยยังไม่เริ่มอ่าน หรือกด **อ่านครั้งเดียว** และ **เริ่มอ่านตามรอบ** เพื่อบันทึกและเริ่มอ่าน กด **หยุดอ่าน** เพื่อหยุดรอบอ่าน หรือ **กลับไปใช้ OPC UA** เพื่อให้หน้าติดตามค่าใช้ OPC UA อีกครั้ง

### OPC DA ผ่าน Windows Reader และ Gateway

1. บน Windows เครื่อง WinCC ให้เปิด Windows Reader 0.10 เลือก Tag สถานะหรือ Analog แล้วอนุญาตอ่านและส่งเมื่อหน่วยงานอนุญาต [คู่มือตรวจรับ](COMMISSIONING.md)
2. ในแท็บแหล่งข้อมูล เลือก **OPC DA · Windows Gateway** ระบุรหัส Windows Reader เช่น `PC-01` และเลือก `aqua.sqlite3` ของ Gateway ที่รับข้อมูล บน Gateway ไฟล์อยู่ในโฟลเดอร์ `PC-04` ของโปรไฟล์ที่ใช้งาน
3. ระบุชื่อ Tag ให้ตรงกันทั้ง Windows Reader และคลัง Tag แล้วกดอ่าน โปรแกรมเปิดฐานข้อมูลด้วยสิทธิ์อ่านอย่างเดียว แสดงค่าจาก snapshot ล่าสุดของ Reader ที่เลือก โดยใช้อายุจากเวลาต้นทางของแต่ละ Tag หาก WinCC ไม่ส่งเวลาต้นทาง ค่า GOOD นั้นจะแสดงเป็นยังไม่ได้สังเกตในหน้าติดตามค่า

ตัวอ่าน OPC DA ทำงานที่ Windows ส่วนปุ่มในแท็บแหล่งข้อมูล เริ่มอ่านหลักฐานที่มาถึง Gateway เท่านั้น ก่อนใช้งานต้องมี Windows Reader และ Gateway ที่พร้อมตามคู่มือตรวจรับ

## ตั้งค่าจาก Terminal (ทางเลือก)

วางไฟล์ส่วนตัวชื่อ `telemetry_source.json` ในโฟลเดอร์ตั้งค่าของ AQUA COMMAND บน Fedora คือ `~/.config/aqua-command/` ชื่อ Tag ต้องตรงกับคลัง Tag ทุกตัว เลือกหนึ่งโปรโตคอลต่อไฟล์ ตั้งสิทธิ์ไฟล์ข้อมูลและไฟล์ลับเป็น 0600

**REST** ส่ง HTTPS GET ไป URL ที่ระบุ ไม่ตาม redirect และรับเฉพาะ HTTP 200 ที่มี Content-Type application/json

```json
{
  "transport": "rest",
  "source_id": "station-gateway",
  "url": "https://gateway.example/v1/snapshot",
  "tags": ["Tank.Level", "Pump.Run"],
  "timeout_s": 5
}
```

เพิ่ม `ca_file` เมื่อใช้ CA ภายใน และเพิ่ม `token_file` เป็นพาธเต็มของไฟล์ Bearer token หาก Gateway กำหนดให้ใช้

**MQTT** ใช้ `mosquitto_sub` เพื่อ subscribe หนึ่ง topic แบบ QoS 1 ขออ่านหนึ่ง snapshot ต่อการเรียก และข้ามข้อความ retained ที่ได้รับตอน subscribe

```json
{
  "transport": "mqtt",
  "source_id": "station-gateway",
  "url": "mqtts://broker.example:8883",
  "topic": "station/snapshot",
  "tags": ["Tank.Level", "Pump.Run"],
  "timeout_s": 10
}
```

เพิ่ม `ca_file` เมื่อใช้ CA ภายใน หาก broker ใช้ mTLS ให้ระบุ `client_cert` และ `client_key` คู่กันเป็นพาธเต็ม Broker ควรกำหนด ACL ให้ตัวอ่าน subscribe เฉพาะ topic นี้ เลือก broker ที่ส่ง snapshot เป็นรอบภายในช่วง timeout

เปิด terminal ที่โฟลเดอร์ `aqua-command-desktop` แล้วใช้คำสั่งต่อไปนี้ บรรทัดแรกตรวจไฟล์โดยไม่เชื่อมต่อ บรรทัดที่สองเริ่มการอ่านหนึ่งครั้งและใช้หลังได้รับอนุญาตแล้ว

```bash
python3 -B -m collector.telemetry --config ~/.config/aqua-command/telemetry_source.json
python3 -B -m collector.telemetry --config ~/.config/aqua-command/telemetry_source.json --read
```

หากต้องการอ่านต่อเนื่อง ให้เพิ่ม `--interval 5` ต่อท้าย `--read` โปรแกรมจะเว้นเวลา 5 วินาทีหลังแต่ละครั้ง หยุดด้วย Ctrl+C หรือเมื่อไฟล์ตั้งค่าเปลี่ยน หากรอบใดอ่านไม่ได้ โปรแกรมจะแจ้งข้อผิดพลาดและรอตามรอบเดิม

หากต้องการกลับไปแสดง OPC UA ให้ย้ายไฟล์ `telemetry_source.json` ออกจากชื่อนี้ ฐานหลักฐาน `telemetry-evidence.db` อยู่ข้างไฟล์ตั้งค่า เมื่อเปลี่ยน endpoint, topic หรือชุด Tag แล้ว หน้าติดตามค่าจะรอ snapshot ที่ตรงกับการตั้งค่าใหม่

## รูปแบบข้อมูล

```json
{
  "observed_at": "2026-01-01T08:30:00+07:00",
  "values": {
    "Tank.Level": {"value": 73.25, "quality": "GOOD"},
    "Pump.Run": {"value": null, "quality": "UNCERTAIN"}
  }
}
```

`observed_at` เป็นเวลาต้นทางของทั้ง snapshot ต้องมี offset และต้องไม่อยู่ในอนาคต ระบุครบเฉพาะ 1–100 Tag ที่อยู่ใน allowlist ค่าที่รองรับเป็น boolean หรือตัวเลขที่ไม่ใช่ NaN/Infinity และ `null` สำหรับ BAD หรือ UNCERTAIN เท่านั้น ข้อมูลเกิน 60 วินาทีแสดงเป็นข้อมูลเก่า Snapshot ซ้ำหรือเก่ากว่าที่บันทึกไว้ถูกข้าม และค่าที่ขัดกันใน timestamp เดียวกันจะถูกปฏิเสธ

ตั้ง `"lab": true` ได้กับ `127.0.0.1` เท่านั้น จึงอนุญาต HTTP หรือ MQTT ที่ไม่เข้ารหัสเพื่อทดสอบ ผล LAB ถูกเก็บเป็นหลักฐานจำลองและแสดง SIMULATED ในหน้าติดตามค่า
