# Baseline verification

The input to this continuation was the Gemini Phase 1B packaging branch at `0db6e72`. The initial RPM digest matched its provided artifact. Inspection and import smoke exposed missing cryptography, then a missing Cairo introspection typelib. The repaired release 2 was installed in fresh Fedora 44 and 45 containers with weak dependencies disabled.

Four narrow DATA-04 regressions failed before the repair and passed afterward. The original web suite passed 12 tests before adding those regressions. The first ambiguous-delivery acceptance failed because a lost response led to a second automatic POST. The original local Task outbox-trigger test failed because rule state advanced despite the rejected outbox insert.

Broad desktop baseline used an archived source copy with the site-export lookup redirected for the baseline check. It ran 303 tests with 23 failures and 7 errors. The later full synthetic candidate run has different fixture/regression coverage and ran 308 tests with 16 failures and 5 errors. These totals are separate runs.

Raw baseline logs are in `outputs/aqua-roadmap-phase1b-review`, `outputs/aqua-roadmap-phase2-data04`, `outputs/aqua-roadmap-phase2-acceptance/ambiguous-delivery.txt`, `outputs/aqua-roadmap-phase3-integration/task-baseline.txt` and `outputs/aqua-roadmap-phase4-ui/desktop-baseline.txt`.

The older `PHASE0_AUDIT_REPORT.md` is retained as a historical handoff. Its Fedora version and its test counts were not reused as current-host measurements.
