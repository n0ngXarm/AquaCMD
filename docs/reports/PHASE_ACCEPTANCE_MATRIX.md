# Phase acceptance matrix

| Phase | Recorded evidence | Gate disposition |
| --- | --- | --- |
| 0 | Historical discovery plus current inventory and architecture | Documentation available, historical counts retained as historical |
| 1 | Final focused PKI/permissions and reliability tests 27/27, web 20/20, payload privacy zero known matches | LAB checks pass, historical credentials and source/history review open |
| 2 | Web 20/20, Gateway 59/59, Reader Core 59 assertions, ENOSPC, lost ACK, local atomicity and held delivery | Pass within tested fault model, Windows/runtime and physical power loss open |
| 3 | Contract suite 116/116 with opt-in loopback tests, three real TLS/HMAC wire variants, PWA 14/14 | Supported paths verified in LAB, alternative-source local Tasks unsupported |
| 4 | Focused source UI at 1024/1360 and final RPM UI at allocated 1440 | HOLD, broad desktop run has 16 failures and 5 errors |
| 5 | Fedora 44/45 dist RPMs build identically twice, offline release 2→4 upgrade/uninstall, retained state integrity, repeatable Windows cross-build | LAB package evidence available, hosted CI/signing and Windows runtime open |
| 6 | Current blocker/risk/rollback reports | NO-GO for release/main/production |

A phase listed as tested is not a blanket acceptance of every roadmap requirement. Later packaging and readiness review used the isolated candidate while retaining the failed UI gate. Skips are reported per suite in `REGRESSION_RESULTS.md`. There is no all-tests-passed claim.
