# Phase 7 source and evidence publication

The owner explicitly requested pushing all current project files to main on
2026-11-11, after reading the P1 Independent Review. This authorizes this GitHub
main update. Operational release and production gates remain unresolved.

This publication uses the reviewed current source snapshot from local P1 commit
dcd36196c5be9efe53ae71d43508bd0f59801687, based on P0
ca1a96fe9323d1758dc59a00498c39fde4c67d94. A new single-parent commit follows
GitHub main d7508f85954a65f347806b3a4ff652614c620e15. The local private ancestry
is not attached as a parent, and no existing Git history is rewritten.

The source tree contains 416 reviewed files. Added evidence here contains only
sanitized text copies of P0/P1 reports, traceability, privacy scans, manifests
and regression logs, plus the P1 Independent Review. Raw originals, private
catalogs, profiles, keys, databases, quarantined images/executables, dependency
caches and LAB binary artifacts remain outside this publication.

GUI319,source contracts116,security27 and PWA/privacy39 passed in the isolated
LAB. The Independent Review conditionally accepted test/harness reconciliation
from artifact comparisons and supplied logs, without an independent full GTK
rerun or owner-catalog comparison. Existing history remains NOT_CLEARED and
credential rotation PENDING_OWNER_ACTION. Publication does not revoke exposed
credentials or clear old history, validate Windows/COM/field/Telegram, or
authorize installation/deployment.

The repository was Private when inspected for this publication. No visibility
change is requested or performed. Public distribution and production remain
NO-GO. Historical reports retain their original decisions and test dates.

Start with [P1 report](p1/P1_GUI_TEST_RECONCILIATION_REPORT.md),
[assertion traceability](p1/ORIGINAL_TO_NEW_ASSERTION_TRACEABILITY.md),
[P0 report](p0/PHASE7_P0_REVIEW_HANDOFF.md), and the adjacent independent review.
LAB binaries/archive bundles referenced by hashes are intentionally local-only.
