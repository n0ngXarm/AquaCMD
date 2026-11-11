# AQUACMD Phase 7 — P0 review handoff

P0 ภายใน Linux LAB พร้อมส่ง Independent Review ตามขอบเขตที่อนุมัติ ผลยังเป็น **NO-GO สำหรับ public push/distribution, merge to main และ production deployment** เนื่องจาก history ยังไม่ cleared, rotation ยังรอเจ้าของ และ GUI gate เดิมยังเปิดอยู่ ไม่เริ่ม P1 source changes

## 1. Source และขอบเขต

- Local branch: `fix/phase7-p0-privacy`
- Full commit: `ca1a96fe9323d1758dc59a00498c39fde4c67d94`
- Baseline: `e5d6a931c0c16017736fa36bf43fe38878b62fd3`; functional Phase 6 ancestor: `e466efe8fbcf0c706edb0886271dba4f8cfceb16`
- รักษา ancestry เดิมครบ 61 commits และเพิ่ม local commit หนึ่งรายการ ไม่มี history rewrite, force push, delete branch, public push, main merge หรือ production install
- Original Phase 6 และ canonical checkout ยัง clean ที่ SHA เดิมตาม `commit-and-preservation.json` ไฟล์ evidence Phase 0–6 เดิมไม่ได้ถูกเขียนทับ
- GUI source ที่แก้มีเฉพาะ private catalog selection, placeholder hygiene และ credential error redaction ภายใต้ P0 ไม่มีการเปลี่ยน layout/navigation หรือแก้ GUI regression tests เดิม

ไฟล์เปลี่ยนทั้งหมดอยู่ใน `changed-files.tsv`; diff สำหรับอ่านตรวจอยู่ใน `SOURCE_DIFF_REDACTED.patch` ซึ่งปกปิดค่าที่ถูกลบและไม่ใช่ patch สำหรับ apply

## 2. การแก้ไข P0

**Catalog และ compatibility.** ตรวจ callers ก่อนเปลี่ยน ไม่มี runtime consumer ของ private Tag-list filenames สองไฟล์ที่ quarantine แล้ว Catalog ใช้ explicit `AQUACMD_CATALOG_PATH` ก่อน private desktop profile และ legacy Downloads; explicit path ที่หายไม่ fallback ไป catalog อื่น ไม่มี repository catalog fallback หรือการคัดลอก catalog เข้า public payload Template mapping เป็น `mappings: {}` ส่วน private mapping เดิมยังมีลำดับความสำคัญเหนือ template Parser, mapper, schema, engineering group keys และ import/export implementations เดิมไม่ถูกเปลี่ยน ไม่เขียน DB หรือ runtime config เดิม

**Credential I/O.** `main.py setup` ใช้ secure input สำหรับ token และ recipient ไม่เติมค่าที่บันทึกไว้ใน prompt และไม่รับ credentials ผ่าน CLI arguments Non-TTY ที่รับแบบปลอดภัยไม่ได้จะออกด้วย exit 1 ก่อนอ่าน credential ที่ pipe มา Configuration display ปกปิด recipient และ notifier/bot/manual-send error paths ปกปิด token/recipient รวม URL-encoded variants

**Storage และ rollback.** เขียนไป `AQUACMD_ENV_FILE` หรือ XDG private profile นอก source, ตรวจ owner/regular file, ปฏิเสธ symlink ทุกชั้นและ path ภายใน repo ใช้ directory 0700, profile/backup 0600 บน Linux คง unknown keys, เก็บ exact backup และไม่แก้ legacy input ใช้ file fsync → atomic rename → directory fsync มีผลทดสอบก่อน rename, backup failure, หลัง rename durability failure และ actual backup restoration แยก committed-but-unconfirmed ออกจาก write failure ก่อน commit อย่างชัดเจน Windows CLI writes ปฏิเสธไว้ก่อนจนกว่าจะตรวจ owner-only ACL ได้ ส่วน legacy fallback ไม่เปลี่ยน permissions เดิม จึงต้องรักษาสำเนา legacy เป็นข้อมูลส่วนตัวต่อไป

**Current source และ artifacts.** Sanitize public documentation copies และ archival preview ใช้ documentation addresses โดยคง validation network constants ที่จำเป็น Quarantine ภาพ 143 ไฟล์, EXE/RPM เก่า 2 ไฟล์ และ private Tag lists 2 ไฟล์ รวม 147 ไฟล์ เก็บ originals + SHA-256 ในพื้นที่ส่วนตัว mode 0700/0600 และใน ancestry เดิม ไม่อ้างว่าภาพเก่าผ่าน visual scrub Public third-party license/attribution คง byte-for-byte

**Prevention.** `.gitignore`, pre-commit hook และ shared build guard ตรวจ staged bytes/file modes จริง ไม่อาศัย working-tree substitute ตรวจ credential/key patterns, known private Tags เมื่อให้ owner catalog, private/runtime/artifact filenames, populated factory mapping, symlinks และ unknown binaries Font exceptions จำกัด hash ของ public fonts ห้าไฟล์ Build guard ตรวจ exact source archive ก่อน rpmbuild Hook configured ใน clone นี้; clone อื่นต้อง opt in และ hook ไม่ใช่ enforcement ที่ bypass ไม่ได้

## 3. Privacy acceptance

| Surface | ผลจริง | หลักฐาน |
|---|---|---|
| Current source รวมไฟล์ใหม่ 414 ไฟล์ | 0 strict sensitive findings; 0 unknown binary | `source-privacy-audit.json` |
| Staged index | PASS, 0 findings พร้อม private catalog comparison | `preflight-staged.json` |
| Final desktop source archive 117 ไฟล์ | PASS, 0 findings | `source-archive-preflight.json` |
| Final extracted RPM payload 100 ไฟล์ | PASS, 0 findings | `rpm-payload-preflight.json`, payload manifest |
| Real pre-commit: staged credential + safe unstaged bait | ปฏิเสธ exit 1 และไม่แสดง sentinel; safe staged text ผ่าน exit 0 | `hook-negative-acceptance.json` |
| Staged symlink + regular working-tree bait | baseline FAIL, แก้แล้วผ่าน โดยตรวจ mode ของ index | `staged-symlink-baseline.txt`, final PWA tests |
| Git history | NOT_CLEARED; ไม่มีการ rewrite | `history-exposure-inventory.json` |
| Token rotation | PENDING_OWNER_ACTION | ไม่มี owner confirmation ใน scope นี้ |

เทียบ known private Tag names 457 ชื่อโดยอ่าน comparison input ภายนอก source และไม่แจก comparison catalog ผล 0 findings หมายถึงขอบเขต patterns และ names ที่ตรวจ ไม่ใช่การรับรองว่าไม่มี secret ทุกชนิด Pattern matches ที่เหลือมีเฉพาะ RFC1918 network-class constants/synthetic validation endpoints และ public copyright contacts โดยแสดง file-level rationale ในรายงาน ไม่มี field catalog, operator identity, known exposed credential value หรือ private home path ใน current indexed source

## 4. Tests และ raw evidence

| ชุด | ผลจริง | Exit |
|---|---:|---:|
| Credential baseline ก่อนแก้ | 4 failures ตามช่องทาง prompt/status/legacy overwrite/transport error | 1 |
| Credential fixed ชุดเดิม | 4 passed | 0 |
| Catalog baseline ก่อนแก้ | 3 failures; existing exact mapping case ผ่าน | 1 |
| Private runtime fixed | 4 passed | 0 |
| Storage hardening baseline เพิ่มเติม | 12 cases, 2 failures: default path ใน repo และ symlink ancestor | 1 |
| Guard binary baseline เพิ่มเติม | unknown binary ภายใต้ font path ไม่ถูกปฏิเสธ | 1 |
| Final PWA/CLI รวม privacy/storage/guard | 39 passed = เดิม 14 + ใหม่ 25 | 0 |
| Desktop source contracts | 116 passed | 0 |
| Focused permissions/OPC UA/task/delivery | 27 passed | 0 |
| Web | 20 passed, 0 skipped | 0 |
| Gateway | 59 passed, 0 skipped | 0 |
| Windows Reader Core บน Linux .NET container | 59 assertions passed | 0 |
| Broad desktop GUI | 313 tests, 16 failures + 5 errors | 1 |
| no_fake_check | PASS | 0 |
| diff whitespace, changed Python AST, Node syntax | PASS | 0 |

GUI baseline independent run มี 309 tests; เพิ่ม private runtime tests 4 รายการเป็น 313 รายการ Exact failing IDs ทั้ง 21 รายการตรงเดิม ไม่มี failure เพิ่มหรือหาย และไม่ได้แก้ assertions/tests เดิมตาม `gui-regression-comparison.json` ดังนั้น full GUI gate **ยังไม่ผ่าน** ไม่ใช้คำว่า all-green

Native `AquaApplication.activate` ทั้งจาก source และ final RPM payload เปิดได้เมื่อไม่มี catalog ด้วย Tag/mapping count 0 จากนั้นใน temporary HOME อ่าน legacy private catalog 457 รายการพร้อม exact private mapping ได้ Mapping bytes และต้นฉบับ catalog ไม่เปลี่ยน ไม่มี network authorization หรือ field connection การทดสอบนี้ยืนยัน private configuration load และ parser compatibility ไม่ยืนยันข้อมูล telemetry หน้างานหรือความถูกต้องของ NodeId หน้างาน

Final RPM ติดตั้งเฉพาะ ephemeral Fedora 45 container แบบ `--network none`; launcher `--help`, installed helper, empty template, absent catalog/archival preview และ `rpm -V` ผ่าน ไม่ติดตั้งบน host หรือ canonical application

คำสั่งจริง, durations, exit codes และ output อยู่ใน `regressions/`, build/container logs และ command receipts แนบมาด้วย Full regression และ native/container checks ใช้ temporary HOME และ network namespace/container ที่ไม่เปิด egress สำหรับ transport fixtures เปิดเพียง loopback; narrow baselines ใช้ temporary profiles และ mocked transports โดยไม่เรียก external endpoints Tests ที่จำลอง Telegram ใช้ test doubles ไม่ส่งจริง ไม่มีการเพิ่ม dependencies

Raw outputs ในชุดส่งตรวจเป็นสำเนาที่ redact private paths/values และ rendered pixel byte literals เพื่อเผยแพร่ได้ ต้นฉบับ raw ถูกเก็บแยกใน private evidence สำหรับตรวจภายใน การ redact ไม่เปลี่ยน exit codes, failing IDs หรือ pass/fail counts Baseline synthetic credential ที่เคยรั่วถูกปกปิดในสำเนาส่งตรวจด้วย

## 5. Artifact provenance

RPM และ exact desktop build source archive อยู่ใต้ `artifacts/` พร้อม hash ใน `artifact-hashes.json` RPM เป็น **LAB TEST ONLY / NOT FOR INSTALLATION OR PUBLIC RELEASE** ยังคง NEVRA เดิม `0.9.0-4.fc45` เพื่อไม่อ้างว่าเป็น release ใหม่ Artifact ครั้งแรกของ Phase 7 ก่อน freeze ถูก supersede ด้วย build จาก local commit ข้างต้น รายงาน payload/manifest และไฟล์ใน bundle อ้าง final build เท่านั้น

Current source snapshot มาจาก `git archive` ของ commit ข้างต้น ไม่รวม `.git`, private originals, catalog, credentials, databases หรือ history ใน snapshot Source snapshot ที่สะอาดไม่ทำให้ ancestry สะอาด และไม่อนุญาตให้ push branch นี้

## 6. P1 planning only

`P1_GUI_REMEDIATION_MATRIX.md` และ JSON ครบ 21 rows: 20 STALE_TEST + 1 ENVIRONMENT เชื่อมกับ OPC UA authorization, DEMO/LIVE isolation, active F3 API/communication/provenance, private Tag loading และ navigation/lifetime/layout

แผนกำหนดให้คง safety assertions ทุกข้อ เปลี่ยน fixture/adapter ให้ตรง contract ปัจจุบันก่อน และพิสูจน์ product defect จริงก่อนเสนอ GUI runtime fix ไม่มีการลบ/skip/xfail/ลดความเข้มของ tests การปิด diagnostic ต้องได้รับ approval และมี semantic assertion traceability ไม่ใช้ triage classification แทนผลทดสอบ

## 7. Rollback

1. หยุด CLI ก่อนย้อน private profile เก็บ profile ปัจจุบันในพื้นที่ส่วนตัว ใช้ exact `.env.bak` สร้าง temporary file mode 0600 ใน directory เดิม แล้ว atomic replace; รักษา directory 0700 มี automated restoration test ยืนยันโหลดค่าเดิมได้
2. การกลับไปใช้ legacy input ทำได้เมื่อไม่มี private profile และไม่มี explicit selection โดย legacy input เดิมยังอยู่ อย่าแสดงหรือใส่ credential bytes ลง command/history/log
3. Source rollback ใช้ baseline branch/commit แยก ไม่ต้อง reset/destroy working branch นี้ ไม่ต้องย้อน DB/catalog/private mapping เพราะงานนี้ไม่ได้เปลี่ยนต้นฉบับเหล่านั้น
4. ไม่ restore quarantined assets ลง public source และไม่ย้อน notification worker ให้ส่งซ้ำจาก unresolved/unknown records
5. ไม่ต้อง rollback โปรแกรมใช้งานจริง: ไม่มี production/host installation ในงานนี้ LAB container ถูกทิ้งหลังทดสอบ

รายละเอียดสำหรับ operator อยู่ใน source `docs/PRIVATE_CONFIGURATION.md`

## 8. Remaining risks และ decision

- **History/public main:** inventory แสดง exposure ใน ancestry เดิม ยัง NOT_CLEARED Public main ที่อ่านตรวจล่าสุดคือ `d7508f85954a65f347806b3a4ff652614c620e15`; Phase 7 ไม่ได้แก้หรือรับรอง public main ใหม่ ต้อง review/remediate แยกโดยไม่มีสิทธิ์ rewrite ในงานนี้
- **Credentials:** revocation/rotation เป็น PENDING_OWNER_ACTION Current-source redaction ไม่ทำให้ token เก่าใช้ไม่ได้
- **GUI:** gate เดิม 16 failures + 5 errors ยังเปิด P1 source/test remediation HOLD
- **Windows:** CLI write fails closed; owner-only ACL/Windows runtime/COM/WinCC ยังไม่ได้ตรวจรับจาก Linux tests
- **Field:** ไม่มี real SCADA/PLC/Telegram acceptance ไม่มี write/probe/send หน้างาน
- **Release engineering:** hosted CI, signing, broader composition/license review, full operational backup restoration, power-loss และ performance acceptance ยังเป็น gates เดิม RPM นี้ไม่ใช่ production release
- **Preserved legacy:** read-only fallback อาจยังมี broad permissions เดิม; ไม่ลบสำเนา credential เก่าโดยอัตโนมัติ Hook เป็น local opt-in และ scanner มีขอบเขตตาม patterns/comparison input

**ส่ง P0 Linux LAB ให้ Independent Review แล้วหยุด** ไม่เริ่ม P1 GUI source changes และยัง NO-GO สำหรับ public distribution/push, main integration และ production deployment
