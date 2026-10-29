# Actual-use Node role implementation

Implemented within existing native project, JS files only. No production/WinCC/PLC/Telegram request or network configuration change was performed. Existing startSingle loopback path is retained for historical regression tests; deployed settings dispatch separately from desktop/host.mjs.

## Changed files

- New desktop/deployed-host.mjs: strict actual Agent/Gateway settings, locally owned one-role lifecycle, no Dashboard/remote polling, separate capture/receive and outbound manual approvals, native status/export bindings.
- backend/src/lan/services.js: independent receive gate and store-first handshake for actual Gateway, real provenance metadata, byte-bounded upload prefixes.
- backend/src/lan/store.js: realOnly ingest, v3 OPC DA validation, persisted Gateway-local receipt time, provenance-correct notification labels and normal owner release.
- backend/src/lan/telegram.js: supported actual FILE/OPC DA provenance labels. Transport still fixed Telegram HTTPS; actual mode requires configured token/chat/approved endpoint and manual outbound approval.
- backend/src/lan/csv-source.js: optional capture-revision cursor namespace, leaving legacy cursor behavior unchanged.
- backend/src/lan/protocol.js: immutable caData support, preserving legacy caFile caller behavior.
- New backend/tests/deployed.test.js and deployed-gateway-helper.mjs (test helper, not installed).

## Contracts

Agent requires its own PC-01..03 identity, loopback control listener, explicitly selected CSV source/Tag list, approved Gateway HTTPS URL/shared member key and optional custom CA (otherwise verified OS trust). Gateway requires PC-04, explicit private/loopback IPv4 listener, TLS server material and unique 64hex shared keys for1–3 enrolled exporters. Gateway has separate own admin key generated per running instance; exporters never receive it. No wildcard/public endpoint, automatic trust, fixture fallback or network scan is accepted.

Each host starts capture/receive and outbound false. Capture-only Agent makes no remote requests. Gateway receive readiness is durable-store readiness independent of Internet/Telegram so it can accept backlog offline. Gateway actual mode archives finite records without pretending Central delivery; archiveCount/archiveSnapshots/retainedRecords are SQL counts. No unforwarded records are purged. Agent control stays loopback, so the Gateway member secret does not expose remote capture controls.

Gateway status.remoteSources contains latest durable snapshot per enrolled source, source adapter, read/observed/source timestamps and separately persisted local lastReceivedAt. These are received values, not fabricated reachable/local Agent roles. Secrets/private key/file contents/raw retained JSON are omitted from status. Gateway source rows remain qualified by identity.

Runtime v3 adds source_adapter wincc-opc-da and read_at; observed_at equals read_at for compatibility. Each observation preserves raw_value,quality_code,signed HRESULT,quality and source_timestamp. GOOD requires HRESULT>=0,OPC mask0xC0==0xC0,RAW0/1 and matching bool. BAD/UNCERTAIN/unconfirmed/unsupported normalized values are null. Real-only Gateway rejects simulated events. Existing SQLite schema is reused without table migration.

## Revision and trust safeguards

Actual source storage must be stable per role+sourceID (Python parent change). CSV capture revision hashes canonical input folder,Tag list,timezone,mapping and quality rule. On revision change only runtime baseline/current observations/current timestamps are atomically reset; sequence and immutable old pending records survive. Cursors are revision-namespaced, preventing the same daily filename in another source from inheriting an old byte offset. Returning to an earlier revision resumes that source cursor while clearing transition continuity across origins.

Custom CA bytes are copied for the Node session and passed as immutable TLS trust rather than rereading caFile on every request. Re-enabling outbound after CA-file change fails until reviewed configuration restart; active file replacement cannot silently authorize a new TLS root.

Agent and Gateway upstream uploads choose the largest prefix below500000 JSON-body bytes, ensuring a valid32-record backlog larger than512KiB still makes progress.

## Evidence

- New deployed tests:7 passed.
- Full existing+new backend suite:57 passed,0 failed,0 skipped; work/real-usage/backend-tests-actual-final.txt.
- Before-fix regressions for changed capture source and CA trust failed as expected; revision-ca-red.txt. Fixed results in deployed-test.txt.
- Checks:strict config/TLS trust,real-onlyv3/quality,actual HTTPS/HMAC,local approval,offline store-first readiness,lost ACK/dedup,restart,wrong auth/CA,simulated-event rejection,no egress before approval,capture-only zero Gateway contacts,transfer-only backlog,CSV bytes/mtime unchanged,100 longTag×32snapshot oversized batch,stable source sequence across3capture revisions,immutable pending payload and CA replacement rejection.
- One legacy role-readiness test initially failed during concurrent suite run; it passed alone and the subsequent complete57-test run passed. No unrelated supervisor changes were introduced.

## Cross-language helper

Run node backend/tests/deployed-gateway-helper.mjs /absolute/owned-temp-directory (under system temp). It generates ephemeral TLS material/random member key, writes private client.json with gatewayUrl,caFile,secret,sourceId and certificate SHA256, starts receive-only local HTTPS Gateway, then prints ready/configurationFile. Input JSON lines status/close return sanitized status or stop. This is an explicitly invoked integration test tool and is excluded from RPM.

Remaining external acceptance:real WinCC/OPC DA on Windows,two physical LAN hosts,actual Telegram/system install. Binary0/1 interop alone cannot prove every numeric RAW representation: C# System.Text.Json vs Node JSON.stringify canonical-byte differences should be tested with actual Node integration before claiming broad numeric/Tag-name support.
