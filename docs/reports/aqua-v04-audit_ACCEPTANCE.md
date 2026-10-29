# v0.4 acceptance and evidence

SCOPE: PASS for the authorized LAB continuation. G0–G5: **6/6 gates**. Physical LAN validation remains explicitly unverified; no production connection or external send was made. Evidence collected27–28 October2026 Asia/Bangkok.

| Gate | Verified result | Actual complete suite at that gate |
|---|---|---|
|G0|Audited actual v0.3 source/scripts/API/UI before changes; copied source with baseline tag|4 pass|
|G1|Three independent agent OS processes; real signed HTTP and absent-Gateway backlog|7 pass|
|G2|Commit-before-ACK, retry/replay, dedup, quotas, nonce/session and SIGKILL recovery|12 pass|
|G3|Central durable effects, transition-only notifications, dry-run/mockHTTP, Telegram boundary/cooldown tests|19 pass|
|G4|Existing UI connected to actual roles; readonly/stale/auth semantics; desktop fit|22 pass|
|G5|Cadence, reset/shutdown/recovery, explicit role CLI, clean install, package, docs and rollback|**28 pass /0 fail /0 skipped**|

Final `npm test`: **18467.382809ms**, Node22.23.1/Linux. `docs/evidence/g5-tests.txt` is the captured TAP output. Initial focused G5 measured snapshot intervals5019ms and5030ms; final complete suite includes the same default5000ms cadence test. Most earlier tests use accelerated timers, which are not represented as a5-second timing test.

## Runtime and packaging proof

- `npm install --offline --ignore-scripts --no-audit --no-fund`: no third-party dependencies; package-lock updated to0.4.0.
- `npm run dev`, `npm run demo:single`: actually started separate Agent PIDs and a loopback viewer, then stopped only their owned process groups. `npm run enroll` created six private role files without printing key contents. `npm run demo:lan -- --role gateway --config ...` actually started one Gateway, with no Agent/Dashboard data created. See `docs/evidence/g5-commands.json`.
- `npm pack --dry-run` and `npm pack` executed. A task-local npm cache was used because the system cache is read-only in this environment. No new dependency was downloaded. The initial candidate had40 files; final documentation/evidence increases this count. Final file inventory and hashes accompany the release.
- The generated tarball was installed with `npm install --offline --ignore-scripts --no-audit --no-fund --prefix <clean-directory> <local-tarball>`. Its own installed executable started a fresh session at127.0.0.1:16073. Real installed Gateway/UI actions and Central delivery were exercised.
- Before Internet gate UP:18 snapshots, source pending0, Gateway pending18, delivered0, notification0. After one PUMP-03 OFF→ON and continued snapshots:54 snapshots, source/Gateway pending0/0, Central delivered55 records (54 snapshots plus1 transition), dry-run notification1. Six distinct PIDs: sources192861/192862/192863, Central192864, Dashboard192891, Gateway192965. These are captured observations, not fixed demo data. Sanitized evidence JSON is under `docs/evidence/`.
- Installed UI screenshot dimensions1366×768,1600×900,1920×1080 matched page scroll dimensions exactly; no page overflow. Screenshots are in the handover `evidence/` directory. Earlier G4 includes diagnostics, ACK-loss and Internet-down screenshots and DOM panel measurements. One transient screenshot capture failed after changing viewport; a refreshed screenshot succeeded. Viewport override restored afterward.
- Original Downloads source **13/13 file hashes unchanged**; original SVG hash equals v0.4 SVG: `082d576067c3a064731c93e310210f87322e4a30a66cba19e6633ad0e37fee37`.

## Review and failure injection

Independent review found partial-response hangs and reused-PID ownership blocking. Both now have regression tests and corrections. Scoped re-review also reproduced a reset/public-stop race; a failing test observed4 resurrected children before correction, then passed after permanent shutdown intent and reset-task coordination. Final review has **no open Critical/Important findings** in its scope; see REVIEW_INITIAL.md and REVIEW_FOLLOWUP.md. Final full suite passed after all code corrections.

Tests include precommit failure, ACK lost after durable commit, malformed/colliding data, replay, source/Gateway restart, source writing while handshake stalls, HTTP response truncation, actual IPC/supervision and readonly API protection. Mock HTTP response-loss tests prove idempotent downstream effects. Telegram tests inject a transport boundary without making external calls.

## Evidence levels and limits

| Level | Status |
|---|---|
|SIMULATED|All pump/runtime readings, derived flow/pressure, toggled Internet availability; labelled throughout|
|TESTED ON ONE HOST|Linux OS process separation, real HTTP on loopback, SQLite restart/dedup/retry and installed UI/package|
|VERIFIED ON TWO LAN HOSTS|**NOT VERIFIED: two physical hosts**; approved-host configuration is implemented, not physically certified|

Not verified: Windows execution/ACL behavior, real HTTPS certificate deployment across hosts, real Telegram egress/send, hardware power interruption/reboot, WinCC/PLC/SCADA integration. SQLite FULL transactions and stable boot/start ownership support recovery; SIGKILL testing is not a physical power-loss test. Telegram ambiguous sends can duplicate; there is no exactly-once claim for the Bot API. Receiver ledger quotas eventually backpressure; this is a bounded LAB session, not unlimited retention.

No production host, PLC/WinCC driver, org credential, external Telegram destination, firewall/router/switch change, scan, NAT/bridge or Internet sharing was used. Default listeners and peers stay loopback and Telegram is dry-run. Private HTTP configuration requires explicit opt-in and an isolated trusted LAB. WinCC Tag Configuration is not asserted as live runtime. DB22/DB34 remain unverified.
