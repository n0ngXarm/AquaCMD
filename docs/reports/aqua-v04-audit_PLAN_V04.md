# AQUA COMMAND v0.4 — staged continuation of v0.3

Authority: supplied `AQUA_COMMAND_CODEX_MASTER_PROMPT.md` and `AGENTS.md`, both read in full. Existing public scene, branding, sidebar and telemetry/event layout are retained. No fresh UI scaffold. Original Downloads source/data remain untouched.

- [x] G0: actual source + scripts audit, baseline4 tests, API/dev proof, three baseline viewports, source copy and rollback tag.
- [x] G1: `src/lan/{protocol,store,services}.js`, role CLI; pre-enrolled identities, real independent processes and authenticated loopback/configured LAN endpoint; no scanning. Three independent agent PIDs, handshake and offline queues verified; 7/7 tests pass.
- [x] G2: durable commit/ACK, event+digest idempotency, ordered persisted retry, quota/retention, exclusive data ownership, pre/post-ACK faults and actual SIGKILL/restart; 12/12 tests pass. Existing v0.3 simulator remains a regression fixture, not the new data pipeline.
- [x] G3: persisted state transitions only for notification; durable Gateway outbound queue, idempotent local Central/mock HTTP sink, Telegram dry-run default and explicit test-bot opt-in; no snapshot spam. Outage/cooldown/restart/duplicate effects and independent producer timer verified; 19/19 tests pass.
- [x] G4: original API/SSE/scene/controls connected to separate services; independent LAN/auth/egress/upstream status, unknown/stale semantics, operational diagnostics, exact three-viewport overflow proof; 22/22 tests pass and original SVG unchanged.
- [ ] G5: install/dev/single/explicit LAN role commands/tests/pack/tarball install/start; Thai setup/demo guide, architecture, exact stage reports and rollback. Mark physical two-host LAN and real Telegram unverified unless actually tested.

Implementation choice within the approved SQLite architecture: use bundled `node:sqlite` (no npm/native compilation dependencies), requiring Node >=22.13 for v0.4. Local runtime Node22.23.1 already opened/wrote/read a SQLite database successfully. SQLite API is experimental in Node22 and emits its normal warning; document this. [Official Node22 API](https://nodejs.org/download/release/v22.14.0/docs/api/sqlite.html).

Default endpoints are literal loopback, configurable roles require explicit approved host/enrollment. HTTP is allowed only for explicitly acknowledged isolated LAB; HTTPS verifies system/custom approved CA and never disables TLS validation. Services never enable NAT, sharing, routes, firewall rules or production adapters.

Each stage commits only after its gate passes and writes `docs/stages/Gn.md` with changed files, actual test counts/evidence, risks, safety, UI status, rollback and next gate. No stage credit for mocked multi-host or GUI-only toggles.


## Completion
G0–G5 passed sequentially. Final suite28/28 with no skipped tests. Package installation and loopback pipeline exercised; reports under docs/stages. NOT VERIFIED: two physical hosts / Windows / real Telegram / physical power loss.
