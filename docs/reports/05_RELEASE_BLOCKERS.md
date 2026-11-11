# Release blockers

1. Source/history privacy review remains open. The final Linux RPM scan has zero known matches, while archived source, historical artifacts and Git history retain material requiring review. Historical secret revocation is unverified.
2. Broad desktop regression is red with 16 failures and 5 errors. Legacy F3 coverage must be reconciled with the supported entry points without deleting safety assertions.
3. Windows runtime and OPC DA COM acceptance are missing. Linux Core tests and cross-builds do not cover activation, cancellation, shutdown or the installed Windows environment.
4. Actual WinCC/OT, enrolled production networking and Telegram acceptance are missing. No field authorization was exercised during this continuation.
5. Release signatures and hosted CI evidence are missing. The SBOMs inventory the tested RPM environments and Windows restore inputs. Exhaustive executable composition analysis remains open.
6. Performance/load targets, full backup restoration and physical power-loss behavior have no complete acceptance evidence.

The readiness decision is `NO-GO`. Keep the candidates in the isolated LAB until these gates have owners, evidence and the required operational authorization.
