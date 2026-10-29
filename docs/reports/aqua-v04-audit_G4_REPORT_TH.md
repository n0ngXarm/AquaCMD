# G4 — Existing Isometric UI integration

STAGE: **G4** · SCOPE COMPLIANCE: **PASS** · PROGRESS: **5/6 gates** (G0–G4)

CHANGED FILES: original `public/index.html`, `app.js`, `styles.css` (data bindings and appended desktop sizing corrections); original `bin/aqua-demo.js` entry delegates to the real service supervisor; new `src/lan/{config,dashboard,supervisor}.js`, `bin/aqua-lab.js`, service role wiring, protocol diagnostic flags, `tests/lan-g4.test.js`, scope-preserving data ignore and stage documents. **Original `public/aqua-isometric-pump-scene.svg` unchanged byte-for-byte.**

IMPLEMENTED: existing `/api/status`, SSE and simulation actions now use real authenticated service requests. Single mode starts three agents, Central mock and Dashboard as independent processes; CONNECT GATEWAY starts the actual separate Gateway listener/process and DISCONNECT stops it. No in-process array movement is presented as LAN transport. Original scene, pump artwork/coordinates, hover styling, sidebar, branding, chart location, event stream and pan/reset behavior remain.

UI: per-agent latest/next export, queue and export error count appear in the existing sidebar. Diagnostics provides PIDs, last-seen, in-flight/ACKed/retry, handshake/auth, last ACK, disk bytes, actual snapshots and notification records. Unknown or stale data is not converted to OFF. Read-only mode disables API mutations and buttons. TCP reachability with failed auth is separately represented as LAN_CONNECTED / not authenticated. Viewer action requests require local Host/origin and control token. Graph values are an explicitly labelled mock model derived from backend runtime, not physical flow/pressure sensors or a client sine wave.

TESTS: two initial G4 tests RED (bridge missing); separate reachability/auth regression also RED before correction. Latest complete `npm test`: **22 pass / 0 fail / 0 skipped**, **6623.965374 ms**. Tests use six independent role PIDs and real HTTP, exercise UI-compatible controls and verify no notification spam. Ownership test now observes actual process exit rather than assuming startup finishes within500ms under parallel load.

RUNTIME PROOF: browser at loopback14773 used the original pump scene to change PUMP-03 once. With Gateway connected and simulated Internet DOWN: source queue0, Gateway queue145, delivered0. Internet UP led to real HTTP Central delivery. A later live observation showed source queue0, Gateway queue0, received640, upstream delivered640, notification1. ACK-loss fault/retries were visible in diagnostics; duplicate receipts did not duplicate the transition notification. These are continuously changing live counts, not fixed fixtures. Camera drag changed the world transform and RESET VIEW restored the view.

UI REGRESSION EVIDENCE:

| Viewport | Page width/height | Footer bottom | Sidebar scroll/client height | Result |
|---|---|---|---|---|
|1366×768|1366×768|768|682/682|PASS|
|1600×900|1600×900|900|814/814|PASS|
|1920×1080|1920×1080|1080|994/994|PASS|

Network panel bottoms734/866/1046 respectively, all above footer; navbar, scene, toolbar, chart and logs remain in their own bounded regions. Screenshots and DOM geometry saved in `outputs/aqua-v04-audit/evidence/v04-*.png` and `layout-v04.json`. Desktop-only scope remains1366–1920px; no mobile claim.

DATA SAFETY / SECURITY: pipeline semantics from G1–G3 retained, source keeps pending data while Gateway process is absent, matching ACKs required. Default Telegram remains dry-run even if irrelevant Telegram environment variables exist in simulated mode. Only Gateway can receive Telegram env. No PLC/WinCC access, external default traffic, public dashboard bind, scanning, routing/sharing/bridge or firewall changes.

RISKS/UNVERIFIED: **TESTED ON ONE HOST** using real TCP and simulated runtime/Internet gate. **NOT VERIFIED: two physical hosts**. No actual Telegram send, WinCC/PLC integration or executed Windows test. G5 packaging/role commands remain unpassed at this report.

ROLLBACK: stop LAB services, then `git switch -c rollback/g3 876d2a7`; preserve sessions and enrollment files. Baseline Isometric v0.3 remains available under `baseline-v0.3`.

NEXT STAGE: **G5** — approved-host LAN role CLI, clean install/package/restart tests, user guides, staged evidence and rollback handoff.
