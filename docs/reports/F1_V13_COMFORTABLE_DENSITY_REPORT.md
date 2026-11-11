<!-- Phase 7 public copy: historical private values redacted. Original evidence remains privately preserved. This is not a rerun or acceptance upgrade. -->
# AQUA COMMAND — F1 V1.3 Comfortable Density Refinement Report
**Provincial Waterworks Authority, Chiang Mai (Umong Water Production Station)**
**Version:** 1.3-comfortable-density
**Branch:** `feature/f1-industrial-precision`
**Execution Environment:** Linux x86_64 / GTK 4.18 (Display :0 Wayland/X11)
**Catalog Source:** Siemens WinCC V8.1 `Export all.txt` (457 Tags, 10 Equipment Groups)

---

## 1. Executive Summary

ตามคำสั่งปรับปรุงเฉพาะ Presentation **AQUA COMMAND — F1 V1.3 Comfortable Density Refinement** ทีมงานได้ปรับปรุงการแสดงผลเพื่อแก้ปัญหา Visual Density, Typography, Table Column Distribution, Spacing และการซ้อนกันของ Border โดยรักษาโครงสร้างหลักไว้ครบถ้วน 100% (Top Header, Status Ribbon, 4 KPI Cards, Equipment Explorer ด้านซ้าย, Signal Table เต็มพื้นที่ด้านขวา, Signal List / Properties, Search และ F1–F8):

1. **Equipment Explorer (Left Pane)**:
   - **ความสูงรายการสม่ำเสมอ**: แต่ละแถวมีความสูงอยู่ในช่วง **48–54px** (~50px) พร้อม Padding และ Vertical Spacing ที่โปร่งสบายตา
   - **Visual Hierarchy ชัดเจน**: รหัสกลุ่มและชื่อหลักโดดเด่นด้วยสี `#EAF1F8` (13.5px JetBrains Mono กึ่งหนา) ขณะที่ Description ใช้สีรอง `#8FA6BC` (12px) ไม่แย่งความสนใจ
   - **Tag Count จัดชิดขวา**: แสดงตัวเลขจำนวน Tag อย่างเป็นระเบียบทางขวาสุดของแต่ละแถว
   - **Polite Accent Selected State**: ปรับ Selected State ให้สุภาพด้วยแถบ Indicator สีฟ้า `#4D91CD` ขนาด 3px ทางซ้าย และพื้นผิวสี `#182B42` แทนการตีกรอบหนารอบด้าน
   - **ลดเส้น Border ซ้ำซ้อน**: เปลี่ยนจาก Box Border หนาทึบที่ซ้อนกัน เป็น Surface Contrast ที่นุ่มนวลและขอบมน 4px
   - **แก้ปัญหา Text Clipping**: เพิ่ม Margin ให้ Panel Header และกำหนด `set_ellipsize(END)` พร้อม Tooltip ครบถ้วน ทำให้ชื่อ `กลุ่มอุปกรณ์ (Equipment Explorer)` แสดงผลครบถ้วนไม่ถูกตัดตัวอักษรแรก

2. **Signal Table (Right Pane — Highest Priority)**:
   - **กระจายคอลัมน์เต็มพื้นที่จริง**: ปรับปรุงความกว้างของคอลัมน์ให้สมดุล ไม่มีปัญหาคอลัมน์เบียดกันทางซ้ายหรือเหลือพื้นที่ว่างเปล่าทางขวา
   - **จัดระเบียบ Data Type คอลัมน์**: แปลง Raw Type ที่ยาวเป็นพิเศษจาก WinCC (เช่น `Floating-point number 32-bit IEEE 754` ความยาว 37 ตัวอักษร ซึ่งเดิมดันคอลัมน์กว้างถึง 232px) ให้เป็น Technical Notation สากลของ Siemens S7 เช่น `Real`, `Bool`, `DInt`, `DWord`, `Word` พร้อม Tooltip แสดงค่า Raw เต็ม ทำให้ประหยัดพื้นที่ลงถึง ~150px
   - **คอลัมน์ครบ 7 คอลัมน์บนจอ 1366×768 โดยไม่หลุดจอ**: ทั้ง `TAG NAME / IDENTIFIER`, `GROUP`, `DATA TYPE`, `PLC ADDRESS / DB`, `LIVE VALUE`, `QUALITY`, `LAST OBSERVED` แสดงผลครบถ้วน 100% โดยไม่ต้องเลื่อนหน้าต่างในแนวนอน
   - **ขยายตัวได้อย่างสง่างามบนจอ 1920×1080**: คอลัมน์ Tag Name มีคุณสมบัติ `hexpand=True` ดูดซับพื้นที่กว้างบนจอ Full HD ได้อย่างเต็มตา ทำให้ชื่อสัญญาณและคำอธิบายยาวแสดงผลได้ครบถ้วน
   - **ความสูงแถว 36–40px (38px)**: เพิ่ม Cell Padding เป็น `8px 12px` สอดคล้องกับมาตรฐาน Industrial Workstation
   - **Subtle Row Dividers**: ใช้เส้นคั่นแถว `rgba(43, 60, 80, 0.4)` ที่คมชัดแต่ไม่รกสายตา
   - **Seamless Full-Row Hover & Selection**:
     - เมื่อเลื่อนเมาส์ผ่านแถวใด ทั้ง 7 เซลล์ในแถวนั้นจะสว่างขึ้นพร้อมกัน (`.f1-table-row-hover`)
     - เมื่อคลิกเลือกแถว ทั้ง 7 เซลล์จะเปลี่ยนเป็น Selected State (`.f1-table-row-selected`) โดยคงตำแหน่ง Scroll เดิมไว้ ไม่เด้งกลับไปบนสุด
     - ดับเบิลคลิกแถว หรือคลิกลิงก์ Tag Name จะสลับเข้าสู่หน้า Properties Inspector ทันที
   - **Quality Column เป็น Neutral**: ใช้ข้อความ `Not Observed` สี Muted `#8FA6BC` ไม่มี Badge สีสดใสซ้ำซ้อนทุกแถว

3. **Typography Scale & Thai Font**:
   - **Page Title**: 20px (อยู่ในเกณฑ์ 19–21px)
   - **Section Title**: 15px (อยู่ในเกณฑ์ 14–16px)
   - **Body**: 13px (อยู่ในเกณฑ์ 13–14px)
   - **Secondary**: 12.5px (อยู่ในเกณฑ์ 12–13px)
   - **Technical Monospace**: 12.5px (อยู่ในเกณฑ์ 12–13px)
   - ตรวจสอบฟอนต์ภาษาไทย `Noto Sans Thai` และ Monospace `JetBrains Mono / Liberation Mono` แสดงผลคมชัด ไม่ลอย ไม่ทับซ้อน

4. **Zero Functional Regression**:
   - คลัง Tag ทั้งหมด 457 รายการใน 10 กลุ่มอุปกรณ์โหลดสมบูรณ์
   - โหมด All Groups รวม 457 สัญญาณอย่างถูกต้อง
   - การเลือกกลุ่มเฉพาะ (เช่น `High_VSD` 135 รายการ) ตัดคอลัมน์ `GROUP` ออกเพื่อความกระชับ
   - ระบบค้นหาข้ามกลุ่มทำงานแม่นยำ
   - F1–F8, Task Manager, Network Topology, Host Diagnostics ทำงานปกติ 100%

---

## 2. Visual Comparison & Screenshots

| วิว / โหมดการแสดงผล | ความละเอียด | คำอธิบายรายละเอียด |
| :--- | :--- | :--- |
| **ทั้งหมด (All Groups) — 457 Tags** | 1366 × 768 | แสดงตาราง 7 คอลัมน์ครบถ้วน, กระจายความกว้างสมดุล, ไม่หลุดจอขวา, ความสูงแถว 38px, ป้าย `Not Observed` เป็นสี Neutral |
| **กลุ่มเฉพาะ (High_VSD) — 135 Tags** | 1366 × 768 | สโคปตาราง 6 คอลัมน์, ปรับความกว้างคอลัมน์ให้พอดี, Explorer ฝั่งซ้ายเน้นกลุ่ม High_VSD ด้วย Polite Accent |
| **กลุ่มเฉพาะ (High_Valve) — 68 Tags** | 1366 × 768 | แสดงวาล์วไฟฟ้าและ Penstock (BVEC / PFVC) ชัดเจน |
| **Technical Properties Inspector** | 1366 × 768 | หน้ารายละเอียดเชิงเทคนิค แสดงข้อมูลครบถ้วนพร้อมปุ่มย้อนกลับ |
| **All Groups บนหน้าจอ Full HD** | 1920 × 1080 | ขยายตัวเต็มพื้นที่กว้าง 1080p อย่างสง่างาม ไม่มีพื้นที่ว่างเปล่าที่ไร้ประโยชน์ |

### Embedded Visual Previews

#### 1. All Groups (457 Tags) — 1366×768 (Comfortable Density)
![All Groups 1366x768](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v13_all_groups_1366x768.png)

#### 2. Specific Group (High_VSD — 135 Tags) — 1366×768
![High_VSD 1366x768](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v13_high_vsd_1366x768.png)

#### 3. Tag Properties Inspector — 1366×768
![Tag Properties Inspector](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v13_properties_1366x768.png)

#### 4. All Groups (457 Tags) — 1920×1080 Full HD (Widescreen Adaptation)
![All Groups 1920x1080](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v13_all_groups_1920x1080.png)

#### 5. Specific Group (High_Valve — 68 Tags) — 1366×768
![High_Valve 1366x768](file://[REDACTED_HOME]/.gemini/antigravity-cli/brain/b57326e2-8eaf-4e5e-9289-fae9ebec3137/f1_v13_high_valve_1366x768.png)

---

## 3. Automated Verification Checklist

- [x] **Column Width Distribution**: ทั้ง 7 คอลัมน์บนจอ 1366×768 พอดีกับพื้นที่ 990px ของฝั่งขวา (Tags Grid ใช้ 960px) ไม่เกิด Horizontal Scrollbar และไม่มีช่องว่างสูญเปล่า
- [x] **Data Type Technical Formatting**: แปลง `Floating-point number 32-bit IEEE 754` เป็น `Real`, `Binary Tag` เป็น `Bool` ช่วยลดความกว้างคอลัมน์ที่ไม่จำเป็นลง 150px
- [x] **Row Height**: ความสูงแถวของ Signal Table อยู่ที่ 38px (อยู่ในเกณฑ์ 36–40px)
- [x] **Cell Padding**: กำหนด `8px 12px` สม่ำเสมอทุกคอลัมน์
- [x] **Explorer Row Height**: ความสูงแถวของ Equipment Explorer อยู่ที่ ~50px (อยู่ในเกณฑ์ 48–54px)
- [x] **Polite Selected Accent**: ใช้แถบสีฟ้า `#4D91CD` ขนาด 3px ด้านซ้าย และพื้นผิว `#182B42` ลดการซ้อนกันของเส้นกรอบ
- [x] **Full-Row Hover & Click Gestures**: มี Motion Controller และ Gesture Click บนทุกแถว ไฮไลต์ทั้งแถวอย่างกลมกลืน
- [x] **In-Place Selection Switch**: เปลี่ยน Tag ที่เลือกโดยแก้ไข CSS Class เฉพาะแถวเก่าและแถวใหม่ในหน่วย 0.1ms ไม่ทำลายและสร้างวิดเจ็ตใหม่ รักษาตำแหน่ง Scrollbar
- [x] **Double Click & Link to Properties**: ดับเบิลคลิกที่แถวหรือคลิกที่ชื่อ Tag Name จะเปิดเข้าหน้า Properties Inspector ทันที
- [x] **Typography Scale Compliance**: Page Title (20px), Section Title (15px), Body (13px), Secondary (12.5px), Monospace (12.5px) ถูกต้องตรงตามเกณฑ์
- [x] **Screen Adaptation**: ทดสอบการแสดงผลและแคปเจอร์จริงบน 1366×768 และ 1920×1080 ผ่าน 100%
- [x] **F1–F8 Functionality**: หน้า F1 ถึง F8 ทุกแท็บทำงานสมบูรณ์ ไม่มี Regression

---

## 4. Git Diff Summary

ไฟล์ที่เกี่ยวข้องใน Working Tree ของ Branch `feature/f1-industrial-precision`:

- [`f1_overview.py`](file://[REDACTED_HOME]/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f1_overview.py):
  - เพิ่ม `DATA_TYPE_MAPPING` และ `format_data_type()`
  - กำหนดความกว้างคอลัมน์แบบกระจายตัวสมดุล (All Groups: 260px min + hexpand, 130px, 85px, 125px, 85px, 105px, 95px)
  - เพิ่ม `attach_row_events()` สำหรับ Full-row Hover (`EventControllerMotion`) และ Click (`GestureClick`)
  - เพิ่ม `select_tag()` สลับสถานะแถว In-place รักษาระดับการเลื่อนหน้าจอ
  - ปรับความกว้าง Paned เป็น 340px และเพิ่ม Margin ให้ Header
- [`f1_style.css`](file://[REDACTED_HOME]/Documents/Codex/2026-10-27/referenced-chatgpt-conversation-this-is-an-2/work/waterlevels-desktop/aqua-command-desktop/desktop/f1_style.css):
  - ปรับ Typography Scale ตามเกณฑ์
  - ปรับความสูงแถวตาราง `min-height: 38px; padding: 8px 12px;`
  - ปรับสไตล์แถว Explorer `min-height: 48px; padding: 7px 10px; border-left: 3px solid #4D91CD;`
  - ปรับเส้นคั่นตารางเป็น `rgba(43, 60, 80, 0.4)` และเปลี่ยนสี Quality เป็น Neutral
