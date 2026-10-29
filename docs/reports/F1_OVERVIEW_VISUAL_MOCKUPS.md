# 🎨 AQUA COMMAND — Visual Design Mockups: F1 Overview

เอกสารนี้แสดงภาพจำลองจริง (Visual Mockups) สำหรับการออกแบบ **พื้นที่เนื้อหาภายในหน้า F1 (Overview)** ใหม่ทั้งหมด โดย**คงโครงสร้างระบบนำทางเดิมไว้ 100% (Global Navigation Freeze)**

---

## 🔒 1. การคงโครงสร้างเดิมที่ถูก Freeze (ไม่แตะต้อง)
- **Top Header:** ชื่อระบบ, ป้ายสถานะเครือข่าย, ป้าย Tag สรุป, นาฬิกาดิจิทัล
- **Alarm Ribbon:** แถบวินิจฉัยสถานะฮาร์ดแวร์จริง (`enp0s31f6: NO-CARRIER / nope`)
- **Bottom Navigation F1–F8:** ปุ่ม F1 ถึง F8 พร้อมคีย์ลัดเดิมทั้งหมด (ไม่มีการย้ายไปเป็น Left Sidebar)

---

## 🖼️ 2. แบบจำลองภาพจริง (Visual Mockups Comparison)

````carousel
![Option A — Station Overview Grid](/home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/mockup_option_a_station_overview.png)
<!-- slide -->
![Option B — Station Explorer Master-Detail](/home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/mockup_option_b_station_explorer.png)
````

---

## 📊 3. เปรียบเทียบข้อดีและข้อจำกัดของทั้ง 2 แบบ

| มิติการประเมิน | 🌟 Option A: Station Overview | 🎛️ Option B: Station Explorer |
| :--- | :--- | :--- |
| **โครงสร้างเลย์เอาต์** | การ์ดสถานี 4 กลุ่มขนาดใหญ่ (2x2 Grid) | แบ่ง 2 คอลัมน์ (ซ้าย: รายชื่อ 4 สถานี / ขวา: เจาะลึกสถานีที่เลือก) |
| **ภาพอุปกรณ์ (Vector Illustration)** | มีภาพ Vector สัญลักษณ์ประจำทั้ง 4 สถานีพร้อมกันบนหน้าจอ | มีภาพ Vector ขนาดใหญ่พร้อมตารางข้อมูลเทเลเมทรีเจาะลึกเฉพาะสถานีที่เลือก |
| **การเข้าถึงข้อมูล Tag & PLC Address** | แสดง Tag รวม, PLC DataBlock และอุปกรณ์หลักในการ์ด | แสดงตารางเจาะลึกระดับ Tag Name, PLC DB Addr, Data Type, Signal Quality ครบทุกจุด |
| **ความหนาแน่นของข้อมูล (Density)** | ปานกลาง สบายตา เห็นภาพรวม 4 สถานีครบในจอเดียว | ละเอียดเป็นระเบียบ ไม่รกตา สลับดูสถานีได้ทันที |
| **เหมาะสำหรับ** | ผู้ปฏิบัติการที่ต้องการดูภาพรวมพร้อมกันทั้ง 4 จุดในแวบเดียว | วิศวกรที่ต้องการตรวจเช็กและวินิจฉัยอุปกรณ์รายตัวอย่างละเอียด |
