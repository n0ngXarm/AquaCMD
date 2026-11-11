# Integration verification

The application contracts executed 116 tests with both opt-in loopback integration flags and isolated asyncua 2.1.0 dependencies. All 116 passed with no skips. The legacy PWA suite ran separately with its own pinned Python dependency target and passed 14 tests.

A network-disabled container with Node 22.23.1 and .NET SDK 10.0.403 exercised the actual Reader-to-Gateway wire protocol over internal loopback TLS. Variants `--interop`, `--interop-numeric` and `--interop-analog` each produced three durable Gateway records and two snapshots. HMAC authentication, event identity, canonical digest ACK and retained scalar typing were verified. External delivery remained disabled.

The source contract suite also covers secure OPC UA loopback, explicit NodeId mapping, per-tag quality/time, alternative HTTPS and MQTT/TLS fixtures, and read-only SQLite snapshot ingestion. Local Task atomicity is covered separately. The source capability matrix records which paths currently reach local Tasks.

Raw logs are in `outputs/aqua-roadmap-phase3-integration/final-all-contracts.txt`, `wire-interop.txt`, `pwa-tests.txt` and the later `outputs/aqua-roadmap-phase6-privacy/contracts.txt`. Windows COM, actual WinCC and field networking remain unverified.
