# G1 — Real Agent/Gateway transport

STAGE: **G1** · SCOPE COMPLIANCE: **PASS** · PROGRESS: **2/6 gates** (G0/G1)

CHANGED FILES: `src/lan/protocol.js`, `store.js`, `services.js`; `bin/aqua-service.js`; `tests/lan-g1.test.js`; npm role scripts/Node engine metadata; stage plan/report. **No public UI asset changed.**

IMPLEMENTED: real enrolled Agent/Gateway HTTP(S) services, own process/data directory per agent, known endpoint validation, HMAC nonce/time/body authentication with signed nonce-bound replies, short-lived persisted handshake sessions, bounded upload batches and digest ACK validation. SQLite FULL/WAL commits before responding to upload. New role CLI runs independently from the legacy UI simulator; G4 has not connected the UI yet.

TESTS: three G1 tests initially RED (services missing), now GREEN; complete `npm test` **7 passed, 0 failed, 0 skipped**, 2129.165914 ms. Includes four unchanged v0.3 tests. Node22's built-in SQLite emits its documented experimental warning; no native dependency installation was required.

RUNTIME PROOF: G1 test launches **three separate OS agent processes**, each with its own SQLite spool, while the configured Gateway port is absent. All three accumulate at least two records. Starting Gateway on that same known port leads to authenticated handshakes, real HTTP batch transfer and matching committed ACKs. The test transcript records distinct agent PIDs, Gateway PID/port, received/ACK counts and last-ACK timestamps. This is **TESTED ON ONE HOST**, not two machines.

DATA SAFETY: base transactions/ACK ledger are present; quotas, fault injection and abrupt-recovery hardening remain G2 work. No data purged before matching ACK. Per-source sequence is checked; identity/configuration schemas cannot be uploaded as runtime snapshots.

SECURITY: default loopback only; arbitrary/public/wildcard destinations rejected. An explicit private LAN endpoint requires allow-LAN configuration, and HTTP beyond loopback additionally requires isolated-trusted-LAB acknowledgement. HTTPS validates certificates; no TLS bypass. No discovery scan, credentials in source, external Internet call or production interface.

UI REGRESSION: `git diff -- public` is empty; original Isometric assets/theme/layout retained exactly.

RISKS/UNVERIFIED: **NOT VERIFIED: two physical hosts**; no real Telegram or production/WinCC access. UI dev mode is still the baseline simulator until G4. G2/G3 durability and outbound acceptance gates remain unpassed.

ROLLBACK: `git switch -c rollback/g0 baseline-v0.3` creates a baseline source branch without deleting runtime data; stop only LAB-owned processes before switching.

NEXT STAGE: **G2** — bounded durable queues, retry/replay/corruption handling and disconnect/crash fault evidence.
