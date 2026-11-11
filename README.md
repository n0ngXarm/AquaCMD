# AQUA COMMAND

Read-only desktop monitoring, explicit source enrollment, local SQLite evidence,
Task/outbox custody, and operator-authorized notification delivery.

The GTK desktop lives in `aqua-command-desktop/`. Launch it with
`python3 aqua-command-desktop/desktop/app.py`. Starting the application does not
authorize a collector, SCADA connection, or Telegram delivery. Missing telemetry
remains UNKNOWN. Private configuration and databases stay outside the source.

The public factory mapping is empty. Import the operator's catalog and mapping
through private runtime configuration; exact Tag names, NodeIds, namespace URIs,
and existing configuration formats remain supported. See
[Private configuration and rollback](docs/PRIVATE_CONFIGURATION.md).

For the separate PWA CLI, use `python3 main.py setup` from a secure terminal.
Credentials are entered without echo and stored in an owner-only profile. The
example environment defaults to LAB with external Telegram access disabled.

The archived `desktop/win_desktop.py` preview is historical source and is excluded
from the RPM. Use `aqua-command-desktop/windows-reader/` for the current Windows
Reader sources. Windows/COM and real WinCC acceptance remain unverified.

Historical screenshots and executable distributions are quarantined from this
branch pending separate review. Earlier reports may retain references to them;
those references are archival records, not available release downloads.

Install the local hook with `git config core.hooksPath .githooks`; run
`python3 scripts/privacy_preflight.py --private-catalog /private/catalog.txt`
before preparing any public artifact. Comparison input stays local; scanner
output contains reason labels only. Current/index-tree and source-archive scans
do not establish history clearance or credential revocation. This branch retains
historical private blobs and must remain local until history review is resolved.

Public release, main integration, production deployment, and GUI remediation
remain on hold pending independent review. Historical results are indexed in
[Roadmap reports](docs/reports/ROADMAP_DELIVERABLE_INDEX.md).
