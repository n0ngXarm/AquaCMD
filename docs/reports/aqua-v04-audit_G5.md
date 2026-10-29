# G5 — Packaging and LAB acceptance

STAGE: **G5** · SCOPE COMPLIANCE: **PASS** · PROGRESS: **6/6 gates** (G0–G5), with physical LAN/Windows/real Telegram explicitly outside verified evidence.

CHANGED FILES: `.gitignore`, `package.json`, `package-lock.json`, `bin/aqua-{lab,service}.js`, `src/lan/{config,dashboard,protocol,store,supervisor,telegram}.js`, new `src/lan/process-identity.js`, `tests/lan-g5.test.js`; README.md/README_TH.md, `.env.example`, LAN setup/demo script/rollback/acceptance/review/evidence/stage documents. Original SVG and legacy simulator remain unchanged.

IMPLEMENTED: explicit single/init/lan CLI, one-role LAN dispatch with --allow-lan guard; immutable fsynced enrollment generations and manifest, data-preserving readonly override/reset archive; final0.4.0 package whitelist. Overall request deadlines and truncated-response rejection preserve retry. Storage ownership uses process creation identity instead of PID alone. Permanent shutdown cancels queued/active reset and prevents role resurrection. No unrelated feature or UI redesign.

TESTS: latest full `npm test`: **28 pass /0 fail /0 skipped,18467.382809ms**. New tests were observed failing before their fixes (response hang, reused PID, readonly override, active reset/shutdown race); targeted reset GREEN1/1 precedes final complete pass. Default5000ms cadence measured, not inferred from accelerated tests. Actual npm install/dev/demo:single/enroll/demo:lan/pack dry-run/pack/clean tarball install executed. See ACCEPTANCE.md and docs/evidence/g5-tests.txt, g5-commands.json. `git diff --check` clean.

RUNTIME PROOF: clean-installed tarball ran six distinct role PIDs. Gateway absent kept source snapshots; Gateway return produced authenticated ACKs. Simulated Internet DOWN retained18 records on Gateway while source queue0; UP delivered to real HTTP Central. One pump change produced1 dry-run notification through54 snapshots/55 total delivered records, with queues0. Enrollment keys were not exposed in logs/screenshots. Evidence uses loopback ports only and labels TESTED ON ONE HOST.

DATA SAFETY: FULL SQLite commit-before-ACK, durable spools/outbound notification queue, exact ACK id/digest set, dedup, retry limits/cooldown and quotas from prior gates retained. Reset preserves old session DBs/configs; stopping during reset cannot restart roles. Unknown legacy live-owner identity fails closed. Archives contain source/docs/tests only; no generated enrollment, real credentials, SQLite/runtime data or node_modules.

SECURITY: private LAN endpoints require explicit enrollment/config plus CLI permission; insecure HTTP is isolated-LAB-only opt-in. Default local listeners, no external traffic, dry-run. No PLC/WinCC access, scan, NAT/bridge/sharing/firewall changes. LAN local Dashboard read-only; real Telegram needs separate test-bot opt-in. Independent scoped review findings addressed with no open Critical/Important findings.

UI REGRESSION: original isometric scene, branding, hover/pump controls, camera, sidebar, telemetry and event stream preserved. G4+installed G5 screenshots at1366×768/1600×900/1920×1080 and matching page dimensions pass. Readonly/unknown/stale remain truthful. Source original13files and SVG hashes verified unchanged.

RISKS/UNVERIFIED: **NOT VERIFIED: two physical hosts**, Windows, real Telegram, deployed cross-host HTTPS, host reboot/power loss or production OT. Telegram timeout may duplicate externally accepted messages. SQLite experimental warning onNode22; receiver caps backpressure long sessions. No production-readiness claim. See ACCEPTANCE.md limits.

ROLLBACK: stop owned LAB roles; preserve full stopped data/enrollment/session directory. Use baseline-v0.3 (`5f25be6`) or last gate `d839024` in a separate branch/check-out and NEW compatible data directory. No destructive reset/clean or production rollback. Release source lacks.git; supplied Git bundle retains stage history. See ROLLBACK.md.

NEXT STAGE: none within authorized G0–G5 implementation. A separate, authorized two-host LAB acceptance run may use LAN_SETUP_TH.md and record real physical-host evidence; it is not silently marked passed here.
