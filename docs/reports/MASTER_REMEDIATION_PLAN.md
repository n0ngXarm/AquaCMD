# Master remediation disposition

All remaining roadmap phases were authorized for isolated LAB continuation. That authorization covered the implementation, local evidence and readiness review. Main integration, publication and field activity remain gated by the readiness decision.

| Phase | Work performed | Next disposition |
| --- | --- | --- |
| 0 | Preserved historical audit, added current inventory, architecture and baseline boundaries | Use current evidence to interpret earlier reports |
| 1A / 1B | Retained inherited security hardening, repaired PKI/Cairo RPM dependencies, tightened Compose publication and reviewed payload privacy | Verify secret revocation and complete source/history review |
| 2 | Atomic web and Task persistence, explicit unknown delivery, migration/recovery and fault tests | Field/runtime fault acceptance remains open |
| 3 | Reader-to-Gateway TLS/HMAC/digest ACK, source contracts and capability matrix | Alternative-source local Task integration is unsupported and documented |
| 4 | Active GTK/WebKit navigation and semantic checks, synthetic catalog fixtures | Reconcile red legacy F3 regression baseline |
| 5 | Reproducible RPM release 4, offline lifecycle, Windows cross-build, inventories and proposed CI | Hosted CI, signing and Windows acceptance remain open |
| 6 | Reviewed security, reliability, observability, UX, release integrity and operational gaps | Final decision NO-GO |

## Remaining work order

1. Assign a repository owner to source/history privacy review and credential revocation. Review old artifacts before selecting any publishing destination.
2. Assign the desktop maintainer to reconcile legacy F3 expectations with active supported entry points while preserving safety coverage.
3. Obtain an approved Windows LAB host for Reader startup, local COM read-only behavior and bounded stop/restart acceptance.
4. Execute hosted CI and signing through the repository release process after the source review.
5. Prepare authorized field commissioning, performance targets and an actual backup-restoration exercise. Require retained source timestamps, quality, exact ACKs and uncertain-delivery handling.

Rollback steps are in `ROLLBACK_PLAN.md`. Phase acceptance and raw-log locations are in `PHASE_ACCEPTANCE_MATRIX.md` and `REGRESSION_RESULTS.md`.
