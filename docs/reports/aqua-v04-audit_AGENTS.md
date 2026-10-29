# AQUA COMMAND DEMO — CODEX SCOPE GUARD (AGENTS.md)

This file is the persistent instruction guard for Codex agents working in the **separate AQUA COMMAND LAB DEMO**. Place a copy named `AGENTS.md` at the root of the demo repository. It never grants permission to modify production OT systems.

## Immutable mission
1. Every offline SCADA simulator agent independently writes a durable runtime snapshot every five seconds.
2. Agents transfer retained snapshots to an explicitly enrolled LAN gateway via real network transport; the gateway authenticates peers, durably commits before ACK, stores outbound queue during internet failure, and forwards event notifications when recovered.
3. Keep the existing desktop Isometric SCADA scene and UI. Replace simulated internal counters with real demo-service telemetry; do not redesign the entire UI instead of implementing transport.
4. `Export All` WinCC tag configuration is not verified live runtime. No fabricated PLC mapping or confirmed DB22/DB34 meaning.

## Safety boundaries — STOP if violated
- Lab/demo workspace only. Preserve original repo history/source and user edits.
- Never connect to or alter real PLC/WinCC, SCADA production PCs, network firewall/router/switch configuration, production Telegram, or organizational credentials without separate authorization.
- No PLC writes, internet sharing, NAT/bridge, indiscriminate LAN or port scanning, arbitrary inbound Internet access, or network takeover.
- Known gateway/agent enrollment only. Gateway checks its own Internet egress; never claim that scanning all LAN PCs for Internet is necessary.
- No hardcoded secrets; default Telegram dry-run, explicit opt-in for test bot.
- Buttons controlling pump/Internet/Gateway affect LAB simulation only; never issue physical commands.

## Engineering constraints
- Audit actual repo and run baseline tests before edits.
- Distinguish in-process v0.3 simulator from cross-process and multi-host verification.
- Use independent OS processes and real authenticated network transport. Preserve per-agent local spool and per-gateway durable outbound queue.
- ACK only after durable gateway commit; idempotent event IDs; replay/retention/backoff; do not promise exactly-once Telegram delivery.
- Status states: exported, queued locally, transferred, gateway ACKed, external delivered, notification sent/dry-run — do not conflate.
- Snapshot every five seconds, notify only on state change or independently configured health alerts.
- Do not invent WinCC driver access: provide interface/preflight until verified and authorized.
- Desktop-only 1366×768, 1600×900, 1920×1080: no horizontal overflow, no missing panels, preserve Isometric SCADA.
- All npm install/build/test/pack commands must be tested, not just documented.

## Execution stages
G0 baseline audit; G1 agents and LAN transport; G2 durability and replay; G3 event + optional Telegram; G4 backend-connected isometric UI + overflow fixes; G5 cross-process tests, packaging, rollback and demo script. Do not skip a failing gate.

## Required per-stage report
`stage / scope pass-hold / verified progress / changed files / tests with actual counts / cross-process evidence / safety and secrets / UI regression / unverified items / rollback / next stage`.

## Completion definition
Functional demo shows PC agents writing while gateway is off, backlog transfers after gateway returns, Internet-off outbound buffering, Internet-on resume, ON/OFF event deduplication, durable restart, truthful UI, npm package installation, and explicit statement when cross-physical-host is not yet verified.
