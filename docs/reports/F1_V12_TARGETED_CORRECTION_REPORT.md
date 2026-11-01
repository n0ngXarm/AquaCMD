# AQUA COMMAND — F1 V1.2 Targeted UI Correction Report
**Provincial Waterworks Authority, Chiang Mai (Umong Water Production Station)**  
**Version:** 1.2-targeted-precision  
**Branch:** `feature/f1-industrial-precision`  
**Execution Environment:** Linux x86_64 / GTK 4.18 (Display :0 Wayland/X11)  
**Catalog Source:** Siemens WinCC V8.1 `Export all.txt` (457 Tags, 10 Equipment Groups)

---

## 1. Executive Summary

ตามคำสั่งปรับปรุงเฉพาะจุด **AQUA COMMAND — F1 V1.2 Targeted UI Correction** ทีมงานได้ดำเนินการแก้ไขตามข้อกำหนด 2 รายการอย่างเคร่งครัด โดยไม่มีการรื้อ Layout หรือเปลี่ยนเป็น fullscreen cards และรักษา Dark Industrial Theme ไว้ 100%:

1. **Change 1 — ลบ Technical Blueprint Illustration**:
   - นำพื้นที่ภาพวาดปั๊มน้ำทางขวาบน (`drawing_area` ~140px) และแถบ Submetrics ที่ไม่มีหลักฐานจริงออกทั้งหมด
   - ทดแทนด้วยแถบข้อมูลกลุ่มอุปกรณ์แบบกะทัดรัด (`.f1-group-header-card` ความสูง ~38px) แสดงรหัสกลุ่ม, ชื่อทางการไทย-อังกฤษ, Dynamic Tag Count Pill และสถานะ Catalog Verified
   - คืนพื้นที่แนวตั้งทั้งหมดให้กับ **Signal / Tag Table** ส่งผลให้ตารางแสดงผลได้ **8–10 แถวเต็มบนจอ 1366×768** (จากเดิมที่เห็นเพียง 2 แถว) และ **18–22 แถวบนจอ 1920×1080** โดยไม่ต้องเลื่อนทั้งหน้าจอ

2. **Change 2 — เพิ่ม `ทั้งหมด (All Groups)` ใน Equipment Explorer ฝั่งซ้าย**:
   - เพิ่มตัวเลือกแรกบนสุดเป็น Virtual Filter: `ทั้งหมด (All Groups) — 457 Tags` (คำนวณจาก Catalog จริง ไม่ Hardcode)
   - คงกลุ่มอุปกรณ์หลักทั้ง 10 กลุ่มจริงไว้ด้านล่างครบถ้วน (Header Pill ยังคงระบุ `10 กลุ่ม` ไม่นับ All Groups เป็นกลุ่มที่ 11)
   - เมื่อเลือก **All Groups**: รวม 457 สัญญาณจาก 10 กลุ่มมาไว้ในตารางเดียว, เพิ่มคอลัมน์ `GROUP`, รองรับการ Search ข้ามทุกกลุ่ม, Properties Inspector แสดงข้อมูลถูกต้องตรงจุด และ Counter ระบุ `แสดง X / Y Tags`
   - เมื่อเลือก **กลุ่มเฉพาะ (เช่น High_VSD)**: ตารางสโคปแสดงเฉพาะ 135 Tags ของกลุ่มนั้น, ซ่อนคอลัมน์ `GROUP` เพื่อเพิ่มความกว้างของคอลัมน์อื่น, Search และ Properties ทำงานตามปกติ
   - กำหนดให้ `All Groups` เป็นค่าเริ่มต้นเมื่อเปิดหน้า F1
   - การรีเฟรชแคตตาล็อก (F7) คำนวณจำนวนใหม่ทั้งหมดและรักษา Selection เดิมไว้อย่างแม่นยำ

---

## 2. Visual Verification & Screenshots

| วิว / โหมดการแสดงผล | ความละเอียด | คำอธิบายรายละเอียด |
| :--- | :--- | :--- |
| **ทั้งหมด (All Groups) — 457 Tags** | 1366 × 768 | แสดงตาราง 7 คอลัมน์รวมคอลัมน์ `GROUP`, ตารางขยายเต็มพื้นที่หลังนำ Blueprint ออก, เห็น 8 แถวเต็ม |
| **กลุ่มเฉพาะ (High_VSD) — 135 Tags** | 1366 × 768 | สโคปตาราง 6 คอลัมน์เฉพาะ VSD Inverter Pumps CTM13PT–CTM17PT, กลุ่มและจำนวนตรงตาม WinCC |
| **Technical Properties Inspector** | 1366 × 768 | คลิกเลือก Tag แล้วแสดงรายละเอียดครบถ้วน (Group, Addr, DataType, Quality, Description) พร้อมปุ่มย้อนกลับ |
| **All Groups บนหน้าจอขนาดใหญ่** | 1920 × 1080 | ความหนาแน่นของข้อมูลสูงระดับ Industrial Workstation แสดงตารางได้ถึง 18–22 แถวโดยไม่มี Scrollbar ซ้อน |
| **Empty State (เมื่อยังไม่มี Catalog)** | 1366 × 768 | กล่องข้อความแจ้งสถานะพร้อมปุ่มทางลัด F7, F6, F2 ครบถ้วน |

### Embedded Visual Previews

#### 1. All Groups (457 Tags) — 1366×768
![All Groups View](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v12_all_groups_1366x768.png)

#### 2. Specific Group (High_VSD — 135 Tags) — 1366×768
![High_VSD Group View](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v12_high_vsd_1366x768.png)

#### 3. Tag Properties Inspector — 1366×768
![Tag Properties Inspector](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v12_properties_1366x768.png)

#### 4. All Groups (457 Tags) — 1920×1080 Full HD
![All Groups 1920x1080](file:///home/nong_ing/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v12_all_groups_1920x1080.png)

---

## 3. Automated Verification Checklist

ผลการรันชุดทดสอบด้วยระบบ Safe Offline Test Harness:

- [x] **Catalog Preload & Dynamic Calculation:** โหลด Tag ทั้งหมด 457 Tags จาก `Export all.txt` อัตโนมัติเมื่อเปิดโปรแกรม
- [x] **All Groups Virtual Row:** แถวบนสุดแสดง `ทั้งหมด (All Groups)` พร้อม Badge `457 Tags` โดยไม่มีการเพิ่ม Group ที่ 11 ใน Summary KPI (KPI ยังคงระบุ `10 กลุ่ม`)
- [x] **Default Landing:** เปิดหน้า F1 ครั้งแรกเลือก `All Groups` โดยอัตโนมัติ
- [x] **7-Column Unified Table:** เมื่อเลือก `All Groups` ตารางจะแสดง 7 คอลัมน์ (`TAG NAME / IDENTIFIER`, `GROUP`, `DATA TYPE`, `PLC ADDRESS / DB`, `LIVE VALUE`, `QUALITY`, `LAST OBSERVED`)
- [x] **Specific Group Scoping:** เมื่อคลิกเลือก `High_VSD` ตารางจะกรองเหลือ 135 Tags และตัดคอลัมน์ `GROUP` ออก
- [x] **Specific Group Verification:** ตรวจสอบกลุ่มอื่นๆ มีจำนวนตรงกับ WinCC V8.1:
  - `High1_PT1PT`: 133 Tags
  - `High_Analog`: 75 Tags
  - `High_Valve`: 68 Tags
  - `High_DPM`: 31 Tags
  - `High1_Sound`: 4 Tags
  - `High1_Totalize_Flow`: 4 Tags
  - `Temp_High_Alarm`: 3 Tags
  - `Timer_Of_Start_Second_CTM`: 3 Tags
  - `Default`: 1 Tag
- [x] **Cross-Group Search:** ทดสอบค้นหา `high_valve` พบครบ 68 รายการ, ค้นหา `bvec` พบ 34 รายการถูกต้อง
- [x] **Properties Inspector Accuracy:** เลือก Tag ใดๆ ในตาราง ทั้งจาก `All Groups` หรือกลุ่มเฉพาะ จะแสดงค่า Properties ที่ถูกต้องตรงกันทุกฟิลด์
- [x] **Selection Preservation on Refresh:** เมื่อกด F7 เพื่อรีเฟรชแคตตาล็อก ระบบจะคงการเลือกกลุ่มเดิมไว้ (เช่น เลือก `High_Analog` อยู่ หลังรีเฟรชยังคงอยู่ที่ `High_Analog` 75 Tags)
- [x] **No Layout Overflow:** ปรับ Paned Splitter อยู่ที่ 315px และกำหนด Min Width 300px ทำให้ฝั่งซ้ายและฝั่งขวาไม่มีข้อความถูกตัด และไม่มี Horizontal Scrollbar ที่ 1366×768 และ 1920×1080
- [x] **Data Integrity:** ไม่มี Mock Data, สัญญาณที่ยังไม่เชื่อมต่อแสดง `Not Observed`, ไม่มี Emoji ปะปน

---

## 4. Git Diff Summary

ไฟล์ที่เกี่ยวข้องทั้งหมดอยู่ใน Working Tree ของ Branch `feature/f1-industrial-precision` (ยังไม่มีการ Commit หรือ Push):

- [`f1_overview.py`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f1_overview.py):
  - เพิ่ม `'__ALL__'` definition ใน `EQUIPMENT_GROUPS_DEF`
  - นำ `drawing_area` และแถบตัวเลขจำลองออก
  - สร้าง `.f1-group-header-card` แบบ Compact
  - ปรับ `update_catalog_data` ให้ใส่แถว `ทั้งหมด (All Groups)` ที่หัวรายการ
  - ปรับ `render_tags_table` ให้รองรับ 7 คอลัมน์เมื่อเลือก All Groups และ 6 คอลัมน์เมื่อเลือกกลุ่มเฉพาะ
  - เพิ่มการค้นหาข้ามกลุ่มและตัวนับ `แสดง {filtered} / {total} Tags`
- [`f1_style.css`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f1_style.css):
  - เพิ่มสไตล์ `.f1-group-header-card`
- [`app.py`](file:///home/nong_ing/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/app.py):
  - เพิ่มการตรวจสอบและ Preload `DEFAULT_WINCC_EXPORT` เพื่อให้แคตตาล็อกพร้อมใช้งานทันทีเมื่อเริ่มโปรแกรม
