# AQUACMD Phase 7 P1 — Controlled GUI Test Reconciliation

ผล Linux LAB: **GUI test reconciliation ผ่าน** — 21 diagnostics เดิมปิดด้วยการปรับ tests/harness/fixtures เท่านั้น Full GUI ผ่าน **319 tests, 0 failures, 0 errors, 0 skips** ไม่พบ confirmed runtime bug ในขอบเขต 21 รายการนี้ Source Phase 7 P0 นอก tests คงเดิมทุก byte

ผลนี้พร้อมส่งตรวจ ไม่เปลี่ยน verdict เดิม: **Public Distribution / Merge / Production — NO-GO** และไม่อนุญาตให้เริ่ม Runtime GUI Remediation

## 1. Branch และ source preservation

- Branch ใหม่: `test/phase7-p1-gui-reconciliation`
- P0 base: `ca1a96fe9323d1758dc59a00498c39fde4c67d94`
- P1 full local commit: `dcd36196c5be9efe53ae71d43508bd0f59801687`
- เปลี่ยนเฉพาะ 6 ไฟล์ใน `aqua-command-desktop/desktop/tests/`: `test_f3_continuation.py`, `test_f3_details_window.py`, `test_f3_network_topology.py`, `test_f3_usability.py`, `f3_reconciliation_fixture.py`, `test_f3_active_reconciliation.py`
- P0 non-test files 310 ไฟล์เหมือนเดิมทุก byte รวม runtime, packaging, config template, privacy/credential code และเอกสาร P0
- คง original test method names ทั้ง 472 รายการตาม AST inventory ของทั้ง repository ไม่ลบ safety test, ไม่เพิ่ม skip/xfail/expectedFailure เพิ่ม tests ใหม่ 6 methods จาก 313 เป็น 319 ใน GUI suite
- P0 branch, Phase 6 checkout และ canonical checkout ยัง clean ที่ SHA เดิม ไม่มี push, merge, history rewrite, deploy หรือ production connection

หลักฐาน: `p0-source-preservation.json`, `commit-and-checkout-preservation.json`, `changed-files.tsv`, `SOURCE_DIFF_REDACTED.patch` รายงานและ progress ของ P1 อยู่ใน task evidence แยก เพื่อคง P0 source/documents เดิม

## 2. Root cause ของ 21 รายการ

Reproduce baseline บน branch ใหม่ก่อนแก้: **313 tests, 16 failures + 5 errors, exit 1** ตรงกับชุดเดิม จากนั้นอ่าน implementation, callers และทดลอง runtime boundaries ปัจจุบันเพื่อยืนยัน classification ทั้งหมด:

- **20 STALE_TEST ยืนยันแล้ว:** LIVE aliases ไม่มีใน DEMO inventory; legacy detector mocks ไม่ใช่ secure OPC UA dispatch boundary; worker ที่ค้างทำให้ subtest ถัดไปติด busy guard; actual renderer ไม่เรียก drawing helpers เดิม; config flags ไม่ใช่ structured evidence; animation ต้องมี committed event; library inspector เป็น dock แต่ active F3 เป็น WebKit; layout ใช้ paging และ store เป็น source of truth
- **1 ENVIRONMENT ยืนยันแล้ว (G18):** temporary HOME ไม่มี private catalog และ P0 ยกเลิก repository fallback จึงได้ 0 Tags แก้เฉพาะ test setup ให้สร้าง UTF-16/33-column catalog ที่มี 457 generic LAB Tags และ inject ก่อนสร้างหน้าต่าง เพิ่ม first-run ไม่มี catalog อีกกรณี

Original tests บางรายการหยุดตั้งแต่ assertion แรก จึงพบ harness assumptions เพิ่มเมื่อเดินต่อ: ตัวแปร geometry ที่เลิกใช้, default service ที่ไม่มี numeric address/port, F2 ที่เปิด task dialog ผ่าน unified workspace และ Gtk.Application registration ที่ต้องแยก identity เมื่อสร้างหลาย instance แก้หลังตรวจ source เท่านั้น ไม่แก้ runtime เพื่อรองรับ test เก่า

รายละเอียดครบทุก G01–G21 พร้อม owning source, assertion เดิม/ใหม่, line references และ function hashes อยู่ใน `ORIGINAL_TO_NEW_ASSERTION_TRACEABILITY.md` และ `original-to-new-assertion-traceability.json` Historical test IDs ที่มีชื่อ popup เดิมยังคงไว้เพื่อ trace review; docstrings/comments อธิบาย contract ปัจจุบัน

## 3. Security coverage ที่รักษาและเพิ่ม

**OPC UA authorization.** ใช้ independent fixture ต่อ probe/read จับ `SecureF3OpcUa.probe_sync/read_sync` จริง ก่อนยืนยันต้องไม่มี adapter call หรือ worker หลังยืนยันมีงานเดียวสำหรับ endpoint เดิม Duplicate click ถูก block; confirmation เก่าเมื่อ disable/เปลี่ยน endpoint/สลับ mode ต้องไม่ dispatch ตรวจ real readiness ว่า missing PKI/mapping และ security policy None ยังถูกปฏิเสธ ไม่เปลี่ยน trust policy

**DEMO/LIVE isolation.** ตรวจ inventory IDs แยกกันจริง, DEMO labels, config bytes ไม่เปลี่ยน, LIVE alias คงเดิม, ค่า/quality/session/read evidence ไม่ถูกปน และส่งผล worker ที่มาช้าหลังกลับ LIVE ไม่ได้ ไม่เรียก real adapters ใน DEMO

**F3 provenance และ animation.** Bare flags ต้อง UNKNOWN; ต้องมี source/time/target receipt จึงได้ REMOTE หรือ session ที่ตรวจแล้ว แยก reachability กับ UA; expiry/target change ยกเลิก verification Actual active page ไม่รับ injected config success เป็น observed success ชุด native renderer ตรวจ no-event/no-motion, real temporary SQLite insert+commit ให้ finite pulse, หมดอายุแล้วหยุด ไม่สร้างผลสำเร็จเพื่อให้ภาพเคลื่อนไหว

**Tag loading และ navigation.** ใช้ catalog generator เดิมที่เป็น synthetic เท่านั้น ตรวจทั้ง 457 Tags และ empty profile พร้อม F1/F2 unified workspace/F6 normal entry ปรับ owner assertions ให้ตรง real dock/root และคง mapped/transient/destroy-with-parent checks

**Active F3 และ listener lifecycle.** เพิ่ม 5 tests ที่รัน Gtk/WebKit จริง: HTML dialog เริ่มปิด เปิดเมื่อเลือก node, ใช้ object เดิม, close แล้วคืน focus; WebKit F2/Ctrl+, bridge ไป owner; ไม่มี API ก่อน map; map/unmap/remap และ owner close ปิด worker/listener จริงโดยทดสอบ connection refused; late-ready ไม่ฟื้น listener ตรวจว่า database bytes เดิมไม่เปลี่ยนและไม่มี remote probe/OPC UA dispatch เมื่อเปิดหน้าจอ

**Sensitivity controls.** Fault injection ในหน่วยความจำ 3 กลุ่มทำให้ new assertions ล้มเหลวจริงตามที่ควร: authorization bypass, ยก config flag เป็น observation และ readiness ที่ยอมทุกอย่าง Control runner ยืนยันว่าจับ faults ได้โดยไม่มี harness error ไม่แก้ runtime files และไม่ได้ใช้ Skip/XFail/expectedFailure ใน normal suite ดู `security-negative-controls.json`

## 4. Full regression / exit codes

| Run | ผลจริง | Child exit |
|---|---|---:|
| GUI baseline ก่อนแก้ | 313 tests, 16 failures + 5 errors | 1 |
| Focused reconciliation ครั้งแรก | 65 tests, 4 failures + 1 error จาก harness assumptions ที่ระบุไว้ | 1 |
| Focused reconciliation ครั้งที่สอง | 70 passed | 0 |
| Final full GUI | **319 passed, 0 skipped** | **0** |
| Source contracts | **116 passed, 0 skipped** | **0** |
| Security/permissions/OPC UA/task/delivery | **27 passed, 0 skipped** | **0** |
| PWA/credential/storage/privacy guard | **39 passed, 0 skipped** | **0** |
| 3 negative-control groups | ทุกกลุ่มถูก assertion ปฏิเสธ; normal suite ไม่เปลี่ยนสถานะ | 0 |
| Privacy staged/current/source snapshot | PASS, 0 findings | 0 |
| Reused P0 payload/source archive privacy | PASS, 0 findings | 0 |
| no_fake_check / diff whitespace | PASS | 0 |

Full GUI รันหลังแก้ tests ครั้งสุดท้ายแล้ว ไม่มี safety test ถูกลดเป็น skip/xfail และไม่มี diagnostic ที่ปิดโดยไม่ trace ข้อกำหนดเดิม Full regression ในขอบเขต P1 นี้ไม่ได้ rerun Web/Gateway/.NET suites ที่ source ไม่เปลี่ยน ไม่อ้างผลเหล่านั้นเป็น run ใหม่

คำสั่งจริงอยู่ใน raw logs/command receipts ใต้ `regressions/` ตัวอย่าง:

```text
unshare --user --map-root-user --net dbus-run-session -- python3 -B work/aqua-phase7-p1-evidence/run_regression.py gtk
# Final invocation supplies P1_GUI_RUN_ID=gui-final
python3 -B -m unittest discover -s desktop/tests -v
unshare --user --map-root-user --net python3 -B work/aqua-phase7-p1-evidence/run_regression.py python
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest test_credential_permissions test_opcua_security_gate test_task_alert_atomicity test_notification_delivery -v
python3 scripts/privacy_preflight.py --staged --private-catalog /private/catalog.txt
sh aqua-command-desktop/scripts/no_fake_check.sh
```

ใช้ temporary HOME, private D-Bus/headless compositor และ network namespace ที่มีเฉพาะ loopback Tests ที่จำลองผล transport ใช้ test doubles อยู่ใน tests; secure protocol fixtures ใช้ loopback ที่เปิด opt-in ชัดเจน ไม่มี real SCADA/PLC/Telegram และไม่ติดตั้ง dependencies ใหม่

Log ส่งตรวจเป็น redacted copies ของ raw output เก็บ test names, summaries, child exit codes และเวลาไว้ ต้นฉบับ raw เก็บแยกเป็น private evidence ไม่แจก pixel byte dumps หรือ private paths มี `HARNESS_NOTES.md` อธิบาย environment/harness issues และ intermediate results รวม automatic permission-review timeout ครั้งแรกซึ่ง retry ที่อนุญาตแล้วสำเร็จ

## 5. Privacy / build artifacts

Current source snapshot **416 ไฟล์** ผ่าน guard เทียบ private catalog names 457 ชื่อ โดย comparison input อยู่นอก repository และไม่ถูกคัดลอกเข้า fixtures/bundle ไม่มี private catalog, credentials, operator home path หรือ site data ที่ตรง patterns ใน test changes และ delivery text

ไม่มี RPM ใหม่ใน scope test-only นี้ ตรวจว่า inputs ของ P0 desktop source archive **117 ไฟล์** ตรงกับ P1 ทุก byte และ test paths ที่เปลี่ยนทั้งหมดถูก build exclusions ตัดออก Rescan final P0 source archive 117 ไฟล์และ extracted payload **100 ไฟล์** ได้ 0 findings พร้อมตรวจ hashes เดิม ดู `build-input-preservation.json` และ `privacy-p0-*.json` ผลนี้ไม่ใช่ new build/install acceptance

Audit ZIP มี current source snapshot และ sanitized evidence เท่านั้น ไม่มี `.git`, history, private originals, runtime profiles/catalogs, generated keys หรือ dependency caches Current-source scan ไม่รับรอง history clearance และไม่ทำให้ exposed token เดิมถูก revoke

## 6. Remaining Runtime Bug Findings

**ไม่มี confirmed runtime bug ใน 21 diagnostics ที่ตรวจนี้** ไม่มี runtime patch ถูก apply หรือเสนอใน scope นี้ `REMAINING_RUNTIME_BUG_FINDINGS.json` ระบุขอบเขตและไม่มีรายการ patch ไม่ตีความว่า runtime/product ทุกส่วนไม่มี bug หรือผ่าน field acceptance

## 7. Updated GO/NO-GO และจุดหยุด

- P1 GUI Test Reconciliation — **Linux LAB PASS / ส่งผลตรวจ**
- Phase 7 P0 — คง **CONDITIONAL PASS** ตาม Independent Review ไม่ยกระดับ verdict เอง
- Runtime GUI Remediation — **NOT STARTED / ต้องอนุมัติแยก**
- Public distribution/push, main merge, production — **NO-GO**
- Gates ที่ยังคงอยู่: history NOT_CLEARED, credential rotation PENDING_OWNER_ACTION, Windows ACL/runtime/COM, actual OT/Telegram acceptance และ CI/signing/operational release gates เดิม

หยุดหลังส่งผลตรวจ ไม่เริ่ม runtime remediation หรือขั้นตอน release ใดต่อเอง Local source branch clean และแยกจาก P0; การยกเลิกงาน P1 ทำได้โดยกลับไปใช้ P0 branch เดิมโดยไม่ reset/delete/rewrite branch ใด
