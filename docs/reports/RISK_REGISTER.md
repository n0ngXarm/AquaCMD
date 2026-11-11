# Current LAB risk register

This ledger supersedes the open DATA-04 status in the historical packaging handoff. Earlier evidence remains in the Phase 1A/1B reports and baseline logs.

| ID | Risk | Current disposition | Evidence or remaining gate |
| --- | --- | --- | --- |
| DATA-04 | Rule state can advance without a durable alert/outbox | Repaired in tested candidate | Web backpressure/ENOSPC/crash and actual SQLite-trigger rollback tests pass |
| DEL-01 | Lost Telegram response can cause duplicate automatic send | Repaired for tested ambiguity and restart cases | Persist sending, hold unknown, explicit duplicate-aware web retry. Real API acceptance unverified |
| PKG-01 | PKI and Cairo introspection startup dependencies missing | Repaired | Clean release 2 install and offline release 4 lifecycle on Fedora 44/45 |
| SRC-01 | Private catalog/site data in source, history or old artifacts | OPEN release blocker | Final Linux payload scan passes, broader source/history and credential review still needed |
| UI-01 | Red broad desktop baseline | OPEN release blocker | 16 failures and 5 errors in 308-test synthetic run, largely legacy F3 expectations |
| WIN-01 | Windows/COM lifecycle unverified | OPEN release blocker | Core59 and cross-build evidence cover Linux only |
| FIELD-01 | Actual WinCC, OT network and Telegram acceptance absent | OPEN operational gate | Separate authorized commissioning needed |
| REL-01 | Power-loss and full restore behavior unverified | OPEN | Process crash and hash-retention tests cover narrower faults |
| INT-01 | Alternative-source local Tasks and F3 worker projection incomplete | Documented capability limit | Source compatibility matrix defines supported paths |
| CI-01 | Hosted CI/signing/composition review absent | OPEN release gate | Local workflow syntax and scoped inventories available |
| PERF-01 | Sustained-load/performance targets undefined | OPEN acceptance gap | No complete quantitative load acceptance |

Backpressure returns an explicit failure and preserves prior committed state. The historical proposal for a new overflow queue was replaced by the smaller atomic bounded design. Upstream producers must retain/retry rejected observations. Unknown-delivery resend can duplicate an accepted message, so no exactly-once external guarantee is made.
