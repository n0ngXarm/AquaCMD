# Reliability verification

| Check | Actual result | Evidence directory or log |
| --- | --- | --- |
| DATA-04 baseline | Four targeted failures before repair | `aqua-roadmap-phase2-data04` |
| Capacity and atomic persistence | Web suite now 20/20, exit 0 | `aqua-roadmap-phase6-privacy/web-tests.txt` |
| Actual full filesystem | ENOSPC on dedicated tmpfs returned 503, old state retained, retry passed | `aqua-roadmap-phase2-acceptance/disk-full.txt` |
| Crash after accepted response | SIGKILL/restart retained committed alert state | `aqua-roadmap-phase2-data04` |
| Gateway lost ACK | One durable receipt, matching digest, deduplicated retry and restart retention | `aqua-roadmap-phase2-acceptance/gateway-ack-loss.txt` |
| Original ambiguous Telegram response | Failed with two automatic POSTs | `aqua-roadmap-phase2-acceptance/ambiguous-delivery.txt` |
| Repaired unknown delivery | Web/Gateway tests and final desktop recovery tests pass | `aqua-roadmap-phase2-delivery` and `aqua-roadmap-phase6-privacy` |
| SQLite Task outbox failure | Real trigger abort failed baseline, repaired atomic retry passes | `aqua-roadmap-phase3-integration/task-*.txt` and final focused log |
| Reader Core | 59 assertions passed, exit 0, Linux offline SDK container | `aqua-roadmap-phase2-acceptance/dotnet-core.txt` |

All evidence paths are relative to the task workspace `outputs/`. The tests use synthetic records and loopback sinks. Exactly-once external delivery, real COM lifecycle and physical power-loss recovery remain unverified. See `03_RELIABILITY_FINDINGS.md` for backpressure and resend semantics.
