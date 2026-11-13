# Checkpoint เฉพาะ native theme redesign

วันที่ 2026-11-13; รายละเอียดและ RAW pointers ใน UX_THEME_REPORT.md
ฐาน f14cf2e; branch ux/desktop-theme-redesign; ทำแปด commits ตามคำขอ
ไฟล์ checkpoint นี้อยู่ใน desktop/ เพื่อรักษาขอบเขตงานที่ผู้ใช้กำหนด

ทำแล้ว: token source/parity/lint, atomic UI prefs, live GTK/WebKit themes,
chrome/nav/footer, widget/button skin, F1 density, F2/F6 layout, F3 fit ทั้งสองธีม
บันทึก FAIL ก่อนแก้ F1 และ expectations เดิมของ workspace tests ไว้ใน local artifacts
ไม่มี runtime data จำลองเพิ่มใน product, ไม่แตะ operator config, ไม่ติดตั้ง/เผยแพร่ในรอบนี้

ผลสุดท้าย: desktop353 / contracts116 / UX13 / F3 fits6 ผ่าน exit0; ภาพ48ครบ
contrast text50/UI84ผ่าน; final guards และ commit hash อยู่ใน final receipt
ยังมี warnings เดิม; ยังไม่ได้ตรวจสอบ operator interactive GUI, Python3.14 GUI, Windows/WinCC/PLC/LAN/Telegramจริง

ขั้นตอนถัดไปหากรับงานต่อ: อ่าน UX_THEME_REPORT.md และ final receipt ใน artifacts/ux-theme/
ตรวจ git branch/status ปัจจุบันก่อนแก้; การเผยแพร่/ติดตั้ง/ทดสอบหน้างานเป็นงานแยกตามสิทธิ์ที่ได้รับ
ไม่เปิด collector, demo, WinCC/PLC หรือ Telegram จริงจากการเปิด UI
