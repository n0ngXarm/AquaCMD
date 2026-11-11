# Repository inventory at the LAB candidate

Reviewed source commit `e466efe8fbcf0c706edb0886271dba4f8cfceb16`. The isolated branch is `fix/phase-6-source-privacy`, based on the Gemini packaging handoff `0db6e72`. Later documentation commits record this validation without changing the tested package inputs.

| Path | Role and entry point | Classification |
| --- | --- | --- |
| `aqua-command-desktop/desktop/` | GTK application `app.py`, F1 WebKit view, F2 Tasks, F3 `F3ApiView`, diagnostics, catalog, settings | Active Linux application |
| `aqua-command-desktop/backend/` | `bin/aqua-service.js`, authenticated Gateway and Runtime CSV Agent, Node SQLite | Active separately authorized roles |
| `aqua-command-desktop/windows-reader/` | .NET Core and Windows OPC DA process, durable Reader spool | Windows candidate, COM runtime unverified |
| `aqua-command-desktop/src/collector/` | Explicit transport/OPC UA and alternative-source readers | Active explicit collectors |
| `aqua-command-desktop/collector/` | Source-layout package route to `src/collector` | Import/CLI entry point |
| `aqua-command-desktop/packaging/` | RPM spec, launchers, Windows cross-build | Release inputs |
| `aqua-command/` | Native Node HTTP legacy dashboard and durable JSON alert state | Separate legacy web product |
| Root `main.py`, `src/`, `tests/` | Legacy PWA/notification service and tests | Separate legacy Python product |
| `.github/workflows/lab-validation.yml` | Proposed isolated Node, RPM and .NET validation | Locally parsed, hosted run pending |
| `tools/sim/`, test directories | Explicit synthetic fixtures and loopback servers | LAB only |
| `desktop/win_desktop.py` | Archival Edge-based preview | Excluded from Linux RPM, source privacy review pending |
| `releases/`, old reports and Git history | Prior binaries and historical claims | Historical, excluded from current acceptance claims |

The RPM candidate contains GTK/WebKit assets, Python collectors and the LAN service. It excludes desktop tests, runtime databases, private keys, private configuration, the original catalog and the archived Windows preview. Windows Reader has a separate executable artifact. Legacy web/PWA services are separate launch paths.

Historical discovery and Phase 1A records remain in `PHASE0_AUDIT_REPORT.md` and `PHASE1A*_REPORT.md`. Their host versions, test totals and readiness statements describe those earlier runs. Current verification uses Fedora 45, Python 3.15.2, Node 22.23.1, RPM 6.1.0, and SDK 10.0.403 inside recorded containers.
