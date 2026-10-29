# AQUA COMMAND UI/UX v2.1 — G0/G1 review pack

เริ่มอ่านที่ PDF เพื่อเปรียบเทียบสองแนวทาง แล้วอ่าน G0 และ G1 ก่อนอนุมัติขั้นถัดไป ทุกภาพเป็นแบบเสนอและข้อมูลจำลอง ไม่ใช่หน้าจอที่พัฒนาเสร็จหรือการเชื่อมต่อหน้างานจริง

- AQUA_UIUX_v2.1_G1_WIREFRAMES.pdf:16หน้า (หน้า1เปรียบเทียบ,หน้า2legend,หน้า3–9OptionA,หน้า10–16OptionB)
- DESIGN_COMPARISON.png:ภาพเทียบหน้าแรก
- G0_AUDIT_REPORT.md:ข้อเท็จจริงจากRepo,contracts,capabilities,metricsemantics,risksและtestbaseline
- G1_DESIGN_PROPOSAL.md:แผนสองแนวทาง,7หน้า,flows,tokens,bindings,ผลกระทบ,testing/rollbackและscopeG2ที่ขออนุมัติ
- DATA_BINDING_MATRIX.md / .csv:44ช่องข้อมูลพร้อมexisting/derived/gap,freshnessและfallback
- wireframes/:14ภาพPNG +14ไฟล์SVGสำหรับขยายรายละเอียด
- SOURCE_INTEGRITY.json:ตรวจ96ไฟล์trackedและcommitก่อน/หลังตรงกัน Gitstatusยังclean
- G0_G1_REVIEW_CHECKS.json:ผลsafechecksและการตรวจภาพระดับdesign ไม่ใช่runtimeacceptance

แนะนำ OptionB — Network & SCADA Visibility Console ตามเป้าหมายเห็นเครื่อง/IP/การส่งหลายเครื่อง OptionAเหมาะกับการเฝ้าตารางค่าปั๊มเป็นหลัก

ขออนุมัติเฉพาะG2 UI foundations/presentation bindingเมื่อเลือกแนวทางแล้ว ไม่รวมBackend/API/DB/OPC/WinCC/Network ไม่มีการแก้Source,commit,pushหรือสร้างinstallerใหม่ในรอบนี้

APPROVAL REQUIRED — NO SOURCE MODIFICATION PERFORMED
