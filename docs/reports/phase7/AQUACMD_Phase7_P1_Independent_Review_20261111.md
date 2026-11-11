# AQUACMD — Phase 7 P1 Independent Review

**Review date:** 2026-11-11 (Asia/Bangkok)  
**Scope:** P1 controlled GUI test reconciliation, Linux LAB only  
**User-provided bundle:** `AQUACMD-Phase7-P1-GUI-Reconciliation-20261111.zip`  
**Reported local P1 commit:** `dcd36196c5be9efe53ae71d43508bd0f59801687`  
**Reported local P0 commit:** `ca1a96fe9323d1758dc59a00498c39fde4c67d94`  
**Decision:** **CONDITIONAL PASS for P1 test/harness reconciliation within LAB. NO-GO for public distribution, main merge, and production.**

## Evidence checked independently

| Item | Independent finding | Method / limitation |
|---|---|---|
| ZIP archive | PASS; 461 members; decompressed size 5,463,839 bytes | `zipfile.testzip()` passed; no absolute/parent-traversal entries or symlink entries |
| Whole-bundle manifest | PASS; 460/460 entries | Rehashed each archived member against `BUNDLE_SHA256SUMS` |
| ZIP SHA-256 | `3421f22999851e125a1e5b1e83474150115ba71618181c898636665aefaa2bd3` | Independently computed |
| P0-to-P1 source snapshot | PASS; P0 414 files, P1 416 | Direct byte-by-byte comparison against the previously attached P0 review ZIP |
| Changed files | Exactly 6 under `aqua-command-desktop/desktop/tests/` | 4 modified tests, 2 new test/fixture files; none outside tests |
| Unchanged non-test source | PASS; 310/310 files byte-identical | Comparison between both original ZIP payloads, plus SHA-256 against P1 evidence inventory |
| Build inputs | PASS; 117/117 input hashes correspond to current P1 snapshot | Evidence inventory verified; no new RPM was created |
| GUI test-method inventory | PASS; original 313 methods preserved; 6 added, 319 total | AST comparison against the original P0 snapshot |
| No new skip/xfail in modified files | PASS from static AST review | No added `skip`, `xfail`, or `expectedFailure` attributes detected in the 6 changed files |
| Diagnostic-to-assertion mapping | PASS; 21/21 mapped | Baseline diagnostic IDs match traceability JSON exactly; original and new method names/line numbers resolve in actual sources |
| Classification | 20 `STALE_TEST`, 1 `ENVIRONMENT` according to evidence and test reconciliation | Strong traceability, but not an independent full GTK runtime investigation |
| Privacy preflight | PASS; 416 source files, 0 findings | Re-ran `python -B scripts/privacy_preflight.py --directory .`; **no private-catalog input** was available, so all 457 original private names were not independently compared |
| Privacy guard unit tests | PASS; 8/8 | Re-ran `python -B -m unittest discover -s tests -p test_privacy_preflight.py -v` |
| No-fake production-source guard | PASS | Re-ran `bash aqua-command-desktop/scripts/no_fake_check.sh` |

## Raw regression log review

The ZIP contains log text, command receipts and exit codes. The following were **validated from supplied logs**, not freshly executed by the independent reviewer:

| Suite | Raw log summary | Reported exit |
|---|---|---|
| Original P0 GUI baseline | 313 tests; 16 failures, 5 errors | 1 |
| Intermediate focused test run | 65 tests; 4 failures, 1 error | 1 |
| Focused reconciliation | 70 passed | 0 |
| Final GUI suite | **319 passed**, 0 skipped | **0** |
| Source contracts | 116 passed | 0 |
| Focused security, PKI, task and delivery | 27 passed | 0 |
| PWA/credential/storage/privacy | 39 passed | 0 |
| Negative-control fault injection | Three groups report intentional assertion failures detected without harness errors | 0 (runner) |

The suite method inventory matches the GUI run counts, strengthening internal consistency. Count overlap across suites is possible; do not sum as unique tests. GUI baseline and final logs contain environment warnings (including GTK/portal and an unclosed event-loop warning); no test failure is shown in the final log.

### Current functional checks represented in P1

- **G01–G04:** DEMO/LIVE separation and late-callback isolation.
- **G05–G06, G09, G15–G17:** Actual renderer/paging bounds, provenance-dependent connection indicators and finite SQLite-committed animation; configuration versus observed-state separation.
- **G07–G08, G11, G19–G20:** OPC UA authorization and confirmation, single-dispatch/busy guard, stale-confirmation rejection, readiness and policy gates.
- **G10, G12–G14, G21:** Active F3 WebKit dialog and native dock ownership, focus, navigation and listener lifecycle.
- **G18:** Synthetic 457-tag catalog fixture in an isolated HOME, together with an empty-first-run case. This is not an acceptance of the actual private WinCC catalog.

The provided negative-control matrix covers authorization bypass, wrongly promoting config flags into observations, and permissive OPC UA readiness. I verified the presence of related assertions and recorded controls in the bundle, but did **not** run these GTK-dependent injections again.

## Important boundaries and outstanding gates

1. **No independent full GTK/WebKit test rerun:** The reviewer environment lacks the `gi` (PyGObject) and `asyncua` modules and cannot reproduce the project's compositor/isolated Fedora LAB execution environment. GUI 319/319 remains **log-backed evidence**.
2. **Local Git ancestry is not cryptographically verified:** This is a current-only snapshot without `.git` metadata. The local commit SHA, clean worktrees, and no-push claims are report evidence, not independently verified Git objects. Direct byte comparison supports the six-file test-only delta.
3. **Privacy comparison is partial:** Local privacy rules detected no common patterns across 416 source files. The owner-provided catalog of 457 private Tag names was not included, so a truly independent owner-catalog comparison cannot be claimed. Source/history privacy is still `NOT_CLEARED`.
4. **Credentials and platform:** Telegram credential rotation is a pending owner action. Windows file ACL, native Windows Reader / OPC DA COM startup, actual WinCC/OT and real Telegram acceptance are not proven.
5. **Release gates:** Hosted CI, signed release artifacts, source-history clearance, backup/physical power-loss recovery and full production authorization are outstanding.
6. **Build scope:** P1 changed only tests; no new RPM was built. Existing P0 packaging evidence is not re-certified for a new production release by this review.

## Acceptance verdict

**P1 GUI TEST/HARNESS RECONCILIATION: CONDITIONAL PASS (LAB)**. Direct artifact hashes, byte-preservation, method inventory, traceability and local privacy guard checks passed; the final test result is independently traceable through supplied raw logs. No runtime GUI code change is justified by these 21 historical diagnostics alone.

**MERGE, PUBLIC DISTRIBUTION, PRODUCTION: NO-GO**. Next action is release-blocker closure outside P1: owner credential rotation and source/history privacy, Windows ACL/COM, hosted CI/signing and authorized field acceptance. Do not modify field systems or send real Telegram messages without explicit operational approval. Keep source changes and artifacts isolated until publishing preflight and release gates clear.
