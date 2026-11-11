# Regression results and commands

| Suite | Result | Raw evidence |
| --- | --- | --- |
| Legacy web `npm test --prefix aqua-command` | 20 passed, 0 failed, 0 skipped, exit 0 | `aqua-roadmap-phase6-privacy/web-tests.txt` |
| Desktop Gateway `npm test --prefix aqua-command-desktop/backend` | 59 passed, 0 failed, 0 skipped, exit 0 | `aqua-roadmap-phase2-delivery` |
| Source contracts `python3 -B -m unittest discover -s tests -v` from desktop root | 116 passed, 0 failed, 0 skipped, exit 0 | `aqua-roadmap-phase6-privacy/contracts.txt` |
| Legacy PWA `python3 -B -m unittest discover -s tests -v` from repository root | 14 passed, exit 0 | `aqua-roadmap-phase3-integration/pwa-tests.txt` |
| Final desktop security/atomicity/delivery focused suite | 27 passed, 0 skipped, exit 0 | `aqua-roadmap-phase6-privacy/final4-security-reliability.txt` |
| Broad synthetic desktop discover suite | 308 executed, 16 failures, 5 errors, exit 1 | `aqua-roadmap-phase4-ui/desktop-synthetic-final.txt` |
| Windows Reader Core via `dotnet run ... -c Release` | 59 assertions, exit 0 in Linux SDK container | `aqua-roadmap-phase2-acceptance/dotnet-core.txt` |
| Native UI | Focused source checks at 1024/1360 and final package check at allocated 1440, exit 0 | Phase 4 UI and Phase 6 final4 UI logs |
| RPM reproducibility/lifecycle/privacy | Two builds per dist identical, lifecycle exit 0, privacy matches 0 | `aqua-roadmap-phase6-privacy/final4-*` |

Evidence paths are under the task workspace `outputs/`. Suite counts overlap in coverage and should not be summed as unique tests. Later packaging-only changes did not alter Gateway production logic after its recorded run. The final security/atomicity suite ran on the final functional source.

Python source contracts used an isolated dependency target containing asyncua 2.1.0 with `AQUA_TEST_OPCUA_READINESS_LOOPBACK=1` and `AQUA_TELEMETRY_LOOPBACK_TEST=1`. PWA requirements were resolved separately. GTK runs used temporary HOME, separate D-Bus/compositor and a network namespace containing only loopback. Node and .NET LAB containers used `--network none`.

Harnesses under `work/aqua-phase2-acceptance` include `final4-focused.sh`, `final4-lifecycle.sh`, `final4-ui.sh`, `check_packaged.py` and `check_payload_privacy.py`. The privacy harness requires the owner's private catalog solely to compare names without printing values. Reproducibility commands use `packaging/build-rpm.sh` and an explicit `.fc44` dist macro with normalized build metadata.

Existing stderr includes expected injected-fault messages, GTK accessibility/portal warnings and compositor teardown messages. The explicit test and process exit values above determine each result. The broad desktop failures are unresolved.
