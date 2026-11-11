# Harness notes

- The first request to start the network namespace timed out in automatic permission review before execution. The permitted one retry succeeded; no approval policy was bypassed.
- Baseline was reproduced unchanged before editing:313tests,16failures+5errors,exit1.
- First reconciliation run:65tests,4failures+1error,exit1. These exposed extra harness assumptions behind the old first failing assertions:initial session state is NOT_TESTED, default service has no numeric target/port, retired port-layout variable names are not geometry contracts, F2 uses unified workspace mode/dialog, and anonymous Gtk.Application registration collides when reused in one process. Corrected only tests/fixtures after reading actual source.
- Focused second run:70tests,OK,exit0. Final full run includes six added tests and the strengthened configured-state check:319tests,OK,exit0.
- One preservation-inventory attempt mishandled Git quoting for a Thai filename. It was corrected to NUL-delimited ls-tree records and the byte comparison passed for all310 non-test P0 files. This was not a source/test failure.
- Negative controls inject faults only in memory and require actual assertion failures (not harness errors) to count as detected. Normal suite tests are not skipped, xfailed or marked expectedFailure.
- Headless D-Bus/portal/a11y warnings and expected refused TLS diagnostics remain in redacted raw outputs. Use the anchored test summary and recorded child exit codes.
- No new RPM was built for test-only work. All117 inputs of the final P0 desktop source archive match P1 byte-for-byte, all changed files are under desktop/tests, and the old build excludes tests. Its100-file payload and117-file source archive were rescanned.
