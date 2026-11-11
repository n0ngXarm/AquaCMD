# UI and operator verification

The active application constructs `F3ApiView` in `desktop/app.py`. Focused native GTK/WebKit checks exercised Thai navigation, F1–F9 and Ctrl+comma routing, the manual, alternative-source settings, current versus stale route presentation, and the held-delivery count.

- Source UI checks passed at 1024 and 1360 pixels. Screenshots and logs are under `outputs/aqua-roadmap-phase4-ui/final-*`.
- Final release 4 extracted-payload smoke passed with a temporary profile and loopback-only network namespace. The requested width was 1360, and the allocated window reported 1440 pixels. Screenshots are under `outputs/aqua-roadmap-phase6-privacy/final4-ui`.
- The synthetic catalog fixture generates 457 generic Tags in 10 groups. Parser and workspace tests exercise it without loading the original export. The original export remains a configuration catalog, rather than runtime telemetry.
- The broad synthetic desktop run executed 308 tests and returned exit 1 with 16 failures and 5 errors. Failing assertions were retained. The remaining cases instantiate the legacy `F3NetworkTopologyView` and expect older demo, popup, inspector and layout behavior.

The broad test baseline requires reconciliation before release approval. Focused entry-point coverage does not clear that gate. A source baseline run had 23 failures and 7 errors across 303 tests. Earlier broad runs also reached the tracked catalog through one parser test. Subsequent synthetic runs removed that dependency.

F3 has separate capability labels for modules whose monitoring integration is unavailable. Successful local Task/outbox tests do not establish a complete F3 projection of those workers. No field status or reachability result was inferred from the synthetic UI screenshots.
