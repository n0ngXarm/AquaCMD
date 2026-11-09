# Phase 3.1 — corrected evidence contract

F3 reads API only. Main result state survives age; `freshness`, `age_seconds`, and server-formatted `age_label` are separate. No evidence remains UNKNOWN. Unbuilt pipeline components are NOT_BUILT.

SQLite is OBSERVED_LOCAL from its read-only SQL snapshot, with COUNT(*) and MAX(ts). Remote hosts means distinct checked targets; responding means a current, fresh positive ICMP/ARP/TCP/UA response from the latest round/source. Router excludes old TCP records and uses ICMP or reachable ARP cache. Historical rows remain unchanged.

`local_nic` stores actual OS interfaces/CIDRs/flags/wireless classification. Each OT route stores the real OS route lookup. Configuration comparison uses the selected interface subnet and private expected OT CIDR. This does not prove physical OT binding or PLC state.

Optional, explicit Internet check performs OS DNS resolution and CA/hostname-verified TLS to api.telegram.org:443. No HTTP request or message is sent. DNS/TCP/TLS failures retain the actual stage/error. TLS success does not establish Telegram delivery.

Only API edges carrying observer/target evidence IDs are drawn. Arrowheads use a WebKit-compatible fill. Card and column height adapt to available space; short displays scroll. Raw Inspector retains complete evidence and local route details. SSE particles remain one SVG object per newly committed event; no idle or replay traffic. No collector starts from F3.

Tests that expected STALE as a primary state and an exact four-field counter schema were migrated to the user's explicit new contract. Primary state/reason, separate age, and five SQL counters are asserted; archived original bytes are retained. No tests skipped or fabricated success substituted.
