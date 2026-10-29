# G3 — Event rules / outbound / Telegram

STAGE: **G3** · SCOPE COMPLIANCE: **PASS** · PROGRESS: **4/6 gates** (G0–G3)

CHANGED FILES: `src/lan/{store,services}.js`, new `telegram.js`, `adapters.js`, Central role CLI, `tests/lan-g3.test.js`, an additional stalled-handshake producer regression in G2 tests, WinCC preflight and stage documents. Public UI unchanged.

IMPLEMENTED: Gateway has independent durable inbound records, outbound status and transition-notification table. Local Central receives real authenticated HTTP and deduplicates event IDs/digests before returning ACK. A local HTTP notification sink also deduplicates effects after lost response. Gateway's own Internet gate/egress mode is separate from Agent↔Gateway LAN availability.

STATE RULES: simulator transitions are persisted once at the source. Repeating an unchanged command creates no transition. Gateway atomically creates one notification alongside a new STATE_CHANGE record; repeated snapshots create none. Replayed batches and restart do not recreate a sent dry-run notification or false pump change.

TESTS: initial five new G3 tests failed because outbound/sink capability was missing; placeholder-adapter and stalled-producer regressions also failed before implementation/correction. Final `npm test`: **19 pass / 0 fail / 0 skipped**, **5020.23144 ms**.

RUNTIME PROOF: real loopback HTTP Central retains two unique records when ACK is dropped; Gateway retains its outbound queue, retries the same IDs, Central remains two records and reports duplicates. Mock HTTP notification sink creates exactly one effect despite a lost first response. Internet DOWN prevents forwarding; UP resumes it. Producer timer runs independently while a Gateway handshake deliberately never responds.

TELEGRAM: default local **dry-run**. Real transport requires `TELEGRAM_ENABLED=true`, valid test bot token/chat ID, `TELEGRAM_APPROVED_ENDPOINT=https://api.telegram.org`, Gateway `internetMode=real`, and outbound gate UP. Only fixed verified HTTPS `api.telegram.org:443` is used; no proxy/redirect following or arbitrary URL. `getMe` probes only Gateway's own egress. No real request was made in verification. 429 cooldown pauses the whole bot queue and probes across restart; send attempts are paced at least1.1s. Errors/ambiguous replies keep the notification pending and do not log token/URL.

DATA SAFETY: Central effects and dry-run delivery are idempotent under local transactions; Telegram itself can duplicate a message after a successful send whose response is lost. No unconditional exactly-once claim. Source quota/ACK/retention remain from G2. Notification records share the bounded Gateway database/ledger.

SECURITY: simulator adapter is default. `wincc-readonly` is an unavailable interface only and fails before any driver/network access; see preflight. No PLC/WinCC reads/writes, network sharing/routing/firewall changes or production Telegram.

UI REGRESSION: existing Isometric UI still untouched; next gate connects it to these services.

RISKS/UNVERIFIED: **NOT VERIFIED: two physical hosts**; Telegram real delivery and Windows remain unexecuted. Central is optional for role deployments; without configured upstream, raw snapshots remain in Gateway storage and only configured notification sinks can finish their own queue. Default single-host demo will include the Central mock for visible snapshot delivery.

ROLLBACK: stop LAB services, `git switch -c rollback/g2 d036a95`; preserve data. Do not erase queues to hide a failed stage.

NEXT STAGE: **G4** — connect existing API/SSE/Isometric controls to actual services, truthful freshness/diagnostics and desktop overflow correction.
