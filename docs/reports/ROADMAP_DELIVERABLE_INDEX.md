# Roadmap deliverable index

Published report snapshot on main, 2026-11-11. Test results describe isolated LAB source `e466efe` and the documentation snapshot `e5d6a93`. This publication commit contains the reports. Implementation acceptance remains governed by the NO-GO review. Raw logs and release artifacts remain in the original task workspace.

Current review is pinned to functional source `e466efe`. Documentation commits follow separately. All requested deliverable categories are under `docs/reports` to follow this repository's report layout.

## Audit

- [00_REPOSITORY_INVENTORY.md](00_REPOSITORY_INVENTORY.md)
- [01_ARCHITECTURE_AND_DATA_FLOW.md](01_ARCHITECTURE_AND_DATA_FLOW.md)
- [02_SECURITY_FINDINGS.md](02_SECURITY_FINDINGS.md)
- [03_RELIABILITY_FINDINGS.md](03_RELIABILITY_FINDINGS.md)
- [04_UI_UX_FINDINGS.md](04_UI_UX_FINDINGS.md)
- [05_RELEASE_BLOCKERS.md](05_RELEASE_BLOCKERS.md)

## Roadmap

- [MASTER_REMEDIATION_PLAN.md](MASTER_REMEDIATION_PLAN.md)
- [PHASE_ACCEPTANCE_MATRIX.md](PHASE_ACCEPTANCE_MATRIX.md)
- [RISK_REGISTER.md](RISK_REGISTER.md)
- [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md)

## Verification

- [BASELINE_RESULTS.md](BASELINE_RESULTS.md)
- [SECURITY_TEST_RESULTS.md](SECURITY_TEST_RESULTS.md)
- [RELIABILITY_TEST_RESULTS.md](RELIABILITY_TEST_RESULTS.md)
- [INTEGRATION_TEST_RESULTS.md](INTEGRATION_TEST_RESULTS.md)
- [PACKAGE_VALIDATION.md](PACKAGE_VALIDATION.md)
- [REGRESSION_RESULTS.md](REGRESSION_RESULTS.md)

## Release

- [RELEASE_CANDIDATE_REPORT.md](RELEASE_CANDIDATE_REPORT.md)
- [CHANGELOG.md](CHANGELOG.md)
- [ROLLBACK_PLAN.md](ROLLBACK_PLAN.md)
- [FINAL_GO_NO_GO.md](FINAL_GO_NO_GO.md)

Raw logs and artifacts are outside the source repository, under this task workspace's `outputs/aqua-roadmap-phase*` directories. Phase 6 SHA256SUMS identifies final release 4 RPMs, inventories and the separately located Windows candidate. Phase 5 release 3 files and the early Phase 6 build logs are superseded for Linux release selection. Retain them as historical evidence.

The final decision is NO-GO. Evidence covers isolated LAB behavior with the remaining failures and capability limits explicitly recorded.

## Historical phase reports

These reports preserve the earlier authors' findings and execution claims. Use the current verification and acceptance matrix for the latest independently recorded evidence. The public copies redact a token example and replace two local-machine links with repository links.

- [PHASE0_AUDIT_REPORT.md](PHASE0_AUDIT_REPORT.md)
- [PHASE1A1_COMPLETION_REPORT.md](PHASE1A1_COMPLETION_REPORT.md)
- [PHASE1A1_FINAL_ACCEPTANCE_EVIDENCE.md](PHASE1A1_FINAL_ACCEPTANCE_EVIDENCE.md)
- [PHASE1A2_FINAL_ACCEPTANCE_REPORT.md](PHASE1A2_FINAL_ACCEPTANCE_REPORT.md)
- [PHASE1A2_TARGETED_CORRECTIONS_REPORT.md](PHASE1A2_TARGETED_CORRECTIONS_REPORT.md)
- [PHASE1A_COMPLETION_REPORT.md](PHASE1A_COMPLETION_REPORT.md)
- [PHASE1A_FINAL_CLOSURE_REPORT.md](PHASE1A_FINAL_CLOSURE_REPORT.md)
- [PHASE1B_RPM_COMPLETION_REPORT.md](PHASE1B_RPM_COMPLETION_REPORT.md)
