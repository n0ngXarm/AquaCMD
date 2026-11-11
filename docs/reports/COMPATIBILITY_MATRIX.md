# AQUA COMMAND LAB compatibility matrix

| Source or layer | LAB evidence | Production capability boundary |
| --- | --- | --- |
| OPC UA | Local simulator read with explicitly mapped NodeIds, Basic256Sha256 trust rejection and approval, quality and receipt timestamps | F1 and the desktop Task engine use the OPC UA read pipeline. Actual WinCC endpoints and credentials require separate field acceptance. |
| OPC DA | Windows Reader Core produced binary, numeric-name and analog fixtures. Node Gateway accepted each set over HTTPS with exact digest ACK. A separate SQLite snapshot test preserved per-tag quality and age. | Windows OPC DA COM was not run. The backup-source reader supplies F1 values and does not feed the local Task engine. |
| Runtime CSV | Gateway and CSV Agent tests passed for capture/transfer separation, ordered replay, digest ACK, and retained backlog. | Runtime data and file permissions on the actual Windows host require commissioning. The Agent flow is separate from the local OPC UA Task engine. |
| REST | HTTPS loopback fixture verified CA trust, data validation, and redirect refusal. | This is a backup source for F1. There is no confirmed Task or Telegram integration for it. |
| MQTT | A TLS loopback Mosquitto broker verified the exact topic and retained-message exclusion. | This is a backup source for F1. There is no confirmed Task or Telegram integration for it. |
| LAB | Isolated synthetic inputs exercised source contracts, local SQLite, and notification paths. | Data retains its simulation provenance. A LAB observation cannot fill a missing field observation. |
| Gateway event schemas | v1 covers explicitly simulated events. v2 covers Runtime CSV snapshots and transitions. v3 covers Windows OPC DA binary and analog observations. | The deployed Gateway rejects simulated input. ACK means durable custody with matching event ID and digest. |
| Persistence | The web snapshot and existing SQLite tables keep prior event IDs. New delivery states fit the existing text status fields. | Older workers may interpret in-flight state differently. Follow the rollback plan before downgrading. |
| Runtime and packages | Node 22.23.1 and .NET SDK 10.0.403 were exercised in LAB. The RPM candidate is 0.9.0-4 for Fedora 44/45. The Windows candidate is 0.10.0 win-x64. | Windows EXE startup and OPC DA COM, production LAN, and real Telegram delivery are unverified. |

## Contract and version policy

The Linux RPM version, Reader assembly version and backend package metadata are independent identifiers. Reader 0.10.0 requires a Gateway with v3 analog support when analog payloads are enabled. Tested source is e466efe, following the analog-capable handoff. A v3 numeric observation requires its explicit value_type marker. Do not downgrade the receiver before draining or preserving those records.

Gateway custody tables retain existing record IDs, source sequences and digests. Local Task and notification state remain in their existing SQLite domains. New sending/unknown states use existing text status fields, with recovery rules for legacy interrupted or exhausted jobs. This is compatibility within the tested migrations, rather than a universal SQLite-schema version promise.

Local F1/F3 HTTP and host IPC contracts were tested with the corresponding candidate assets. Keep the matched frontend/backend pair. Preserve private state before upgrade and hold unknown deliveries before downgrade. See ROLLBACK_PLAN.md.
