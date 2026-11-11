# LAB candidate changes after Gemini Phase 1B

## Linux 0.9.0-4

- Added required cryptography and Cairo introspection dependencies.
- Made web alert/outbox/rule updates atomic with capacity backpressure and explicit unknown durability.
- Made desktop Task state commit atomically with its event and outbox.
- Added durable sending/unknown-delivery retention to web, Gateway and desktop, including legacy recovery and an explicit duplicate-aware web retry action.
- Changed the collector delay to follow the completed collection round.
- Exposed held-delivery counts in operator settings.
- Restricted the Compose dashboard host publication to loopback.
- Added deterministic RPM metadata and a proposed LAB GitHub workflow.
- Removed implicit repository/personal catalog fallback, removed the tracked catalog from the isolated current tree, sanitized selected site defaults and generated generic test catalogs.
- Excluded the archival Edge Windows preview from the Linux RPM.

## Windows Reader 0.10.0 candidate

Retained the existing binary/analog Reader behavior and cross-built it reproducibly with SDK 10.0.403. The EXE is unsigned and has no Windows runtime or COM acceptance in this continuation.

The final functional/package source is `e466efe`. Full changed-file and commit receipts are in the task's Phase 6 evidence. Read `FINAL_GO_NO_GO.md` before any proposed integration or distribution.
