# G2 — Durable queue, ACK/retry/recovery

STAGE: **G2** · SCOPE COMPLIANCE: **PASS** · PROGRESS: **3/6 gates** (G0–G2)

CHANGED FILES: `src/lan/store.js`, `services.js`, `bin/aqua-service.js`, `tests/lan-g2.test.js`, stage plan/report. Public UI unchanged.

IMPLEMENTED: SQLite WAL + FULL synchronous transactions, persisted sequence/event IDs and retry deadlines, exact ID+digest ACK matching, whole-batch ordered ingest, durable replay/session state, post-commit ACK-loss and pre-commit failure simulation, in-flight recovery, and transactional PID ownership guard against concurrent writers using one role's data directory. Startup/storage errors fail visibly instead of resetting a damaged database.

TESTS: initial G2 run **1 pass / 3 fail** correctly exposed missing quota, fault controls and replay status; new ownership regression also initially failed. Complete `npm test` after corrections: **12 pass, 0 fail, 0 skipped**, **3400.334044 ms**.

RUNTIME PROOF: independent Agent and Gateway OS processes were killed with SIGKILL and reopened from the same data directories/ports. Pending event IDs/digests were unchanged and later marked ACKed. Example process evidence: source PID **108857** → **108882**, Gateway restarted PID **108881**. Two retained event IDs were recovered and the Gateway integrity check returned `ok`. Other tests interrupt before commit (no receive/no ACK), then after commit (receive1/source still pending), retry (receive remains1, duplicate1, source ACKed1). A correctly signed but mismatched ACK leaves source data pending.

DATA SAFETY / RETENTION:

- Default source pending quota **10,000**; no unACKed item deleted to free space. Quota/storage failure is visible and export pauses/retries rather than claiming a successful snapshot.
- After matching ACK, retain latest **2,000** source records; cumulative counters/sequence remain durable.
- Gateway ledger cap **50,000** records; retain IDs/digests and apply backpressure at the cap. Archive the stopped LAB or start a new LAB data directory to renew the bounded demonstration; do not silently purge deduplication evidence.
- SQLite main database capped at **64 MiB** (default page size), WAL checkpoint every256 pages, journal size limit4 MiB after checkpoint; transient WAL size is not an OS filesystem quota. Structured DB activity log retains latest1,000 entries. UI status exposes current database/WAL bytes and row limits.
- Simulated read-only storage failure rolls back sequence and records; reopen retains pending data. This is process-crash testing, **not** a hardware power-loss certification.

SECURITY: replay/nonfinite timestamps rejected over actual HTTP; nonce-bound signed responses; loopback/known-enrolled endpoints only; no external calls, secret output, OT/PLC drivers or network configuration changes.

UI REGRESSION: unchanged `public/`; integration remains G4. v0.3's in-process simulator is still only the UI baseline at this gate.

RISKS/UNVERIFIED: **NOT VERIFIED: two physical hosts**; outbound Central/notification delivery is G3 work, not counted as successful by Gateway receipt. Real Telegram/WinCC remain unverified/unconnected.

ROLLBACK: stop owned LAB roles, then `git switch -c rollback/g1 c26ae1e`; keep data directories and identities for audit, do not delete or reuse them with an incompatible schema.

NEXT STAGE: **G3** — durable upstream/outbound notification transport, confirmed state-change rules and Telegram dry-run (one notification per transition, none per repeated snapshot).
