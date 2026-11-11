# Phase 4 — read-only OPC UA evidence collector

อ่าน AGENTS.md ก่อน การติดตั้งนี้เพิ่ม client อ่านอย่างเดียวใน evidence pipeline เดิม ไม่เปิด OPC DA ไม่เริ่ม service/collector จาก F3 และไม่เปลี่ยนการตั้งค่าเครือข่าย

`python -m collector.probe_once` ยังคงตรวจ transport อย่างเดียว ส่วน `python -m collector.run` ตรวจ transport แล้วอ่าน OPC UA เฉพาะ target ที่มี `ua` ใน private configuration เป็นหนึ่งรอบ เพิ่ม `--loop` เพื่อวนรอบตาม `interval_s` ที่ระบุไว้ เมื่อจบรอบหนึ่ง collector จะพักตามช่วงที่ตั้งไว้ก่อนเริ่มรอบถัดไป ไม่เริ่ม loop อัตโนมัติ และไม่มีการทำรอบซ้อนกัน Ctrl+C/SIGTERM หยุดหลังงานที่กำลังตรวจแบบ bounded เสร็จ

Configuration เดิมยังใช้ได้ แต่การวนรอบต้องมี `interval_s` เป็นจำนวน finite บวกไม่เกิน3600 วินาที target ของ UA ต้องมี endpoint แบบ opc.tcp ที่ hostname/port ตรงกับ IP/port ของ target ไม่มี credentials/query/fragment และ `nodes` เป็น mapping ชื่อ tag → NodeId ที่ชัดเจน Client ไม่ browse เพื่อเดา NodeId และไม่ตาม endpoint URL ที่ server อื่นโฆษณาไปยัง host ใหม่

`ua.security_policy` ต้องระบุ `None` หรือ `Basic256Sha256` อย่างชัดเจน `None` เป็น Anonymous/ไม่เข้ารหัสและไม่ยืนยันตัวตน server แม้จะบันทึก certificate ที่ได้รับได้ ห้ามใช้ผลนี้เป็นการยืนยัน secure channel สำหรับ `Basic256Sha256` ใช้ SignAndEncrypt และ PkiManager เดิม ตรวจวัน/SAN/URI/trust store ก่อนเชื่อม ไม่ auto-trust และไม่ fallback ไป None กำหนด `pki_dir` เป็น absolute private path ได้ ถ้าไม่ระบุใช้ private PKI เดิม ไม่รับ username/password ใน pipeline นี้

ลำดับหลักฐานจริงคือ GetEndpoints (`ua_endpoints`) → Create/ActivateSession (`ua_session`) → อ่าน Value ของ NodeIds ที่ตั้งไว้ (`ua_read`) → teardown (`ua_close`) ขั้นต่อไปที่ไม่ได้เริ่มไม่มีแถวสำเร็จปลอม การตรวจ metadata ของ certificate เก็บ subject/issuer/not_before/not_after/SHA256 เท่าที่ได้รับจริง ไม่อ้างว่า server ที่เชื่อมไม่ถึงมี certificate แล้ว

`tag_samples(id,host,tag,node_id,value,quality,ts,evidence_id)` เก็บค่าจาก DataValue จริง ค่าเป็น JSON และ quality เป็น OPC UA status ที่ได้รับ `ts` คือเวลา receipt; source/server timestamps อยู่ใน detail การ INSERT sample และ ua_read เป็น transaction เดียวและมี foreign key ถ้า sample เขียนไม่สำเร็จจะไม่มี read receipt ค้าง

Bad/Uncertain quality ไม่ใช่ READ_OK และไม่ถูกนับเป็น read receipt สำเร็จ ถ้า transport/session/read ล้มเหลว ค่าปัจจุบันใน API เป็น null/available:false โดยไม่ลบประวัติ quality ใน sample คือ quality ของ DataValue ครั้งนั้น ไม่สร้าง Bad quality สมมติแทน connection error หลักฐานเก่ายังมี primary result/ป้ายอายุแยกตาม phase3.1 แต่ไม่ใช้ค่าเก่าเป็นค่าปัจจุบันเมื่อมี failure/รอบใหม่/อายุเกิน60วินาที/bindingเปลี่ยน

ทุกครั้งที่เริ่ม collector อ่าน `/proc/sys/net/ipv4/ip_forward` และบันทึก `ip_forward` ลง probe_evidence F3 แสดงคำเตือนเมื่อหลักฐานระบุ1 ไม่มีการแก้ค่า OS การ์ด Collector และเส้นคู่ภายในอ้างอิง observer จริงเท่านั้น ค่า NIC/route ของอีก observer ไม่ถูกนำมาปะปน

## Simulator แยก process

`tools/sim/opcua_server.py --data-dir <private-directory> --level <finite-level>` เปิด real asyncua server เฉพาะ127.0.0.1:4850 URI `urn:aqua-command:sim` และ T-101.level ค่า NodeId จริงพิมพ์ใน ready JSON ให้คัดลอกค่านั้นไป config ไม่เดา namespace index

`tools/sim/set_level.py <finite-level>` เขียนได้เฉพาะ simulator URL/namespace นี้เท่านั้น ไม่มี argument สำหรับ field endpoint การเขียนอยู่ใน tools/sim ไม่อยู่ใน src client อ่านข้อมูลนั้นผ่าน protocol จริง และ target ต้องเป็น sim:true จึงแสดง SIMULATED การทดสอบเก็บ config/certs/DB ใต้ tests แบบชั่วคราว ไม่ใส่ simulator target/แถวจำลองลง DB หน้างาน

ตัวอย่าง config shape (เป็นการตั้งค่า ไม่ใช่ telemetry):

```json
{
  "targets": [{
    "host": "127.0.0.1", "port": 4850, "sim": true,
    "ua": {"endpoint": "opc.tcp://127.0.0.1:4850/aqua-sim/",
           "nodes": {"T-101.level": "ns=1;s=T-101.level"},
           "security_policy": "None"}
  }],
  "ping_timeout_s": 1, "tcp_timeout_s": 2, "interval_s": 1.2
}
```

ใช้ NodeId จาก ready JSON ของ server ที่เปิดจริง Standard ServerStatus ใช้ NodeId `i=2256` ได้เมื่อเลือกไว้ใน private config ไม่มีการนำ WinCC Export/tag catalog มาเป็น runtime values

ตรวจแล้วด้วย asyncua2.1.0 ที่ติดตั้งอยู่ อ้างอิง [Client API](https://opcua-asyncio.readthedocs.io/en/latest/api/asyncua.client.html) และ [DataValue API](https://opcua-asyncio.readthedocs.io/en/latest/api/asyncua.common.html) ผลการทดสอบ/ข้อจำกัดหน้างาน/คำสั่งและ output ดิบอยู่ในรายงาน phase4 ข้าง source ไม่มีการอ้าง Windows/WinCC/production acceptance จากการทดสอบ simulator นี้
