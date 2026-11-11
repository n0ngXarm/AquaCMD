# AQUA COMMAND unsigned LAB candidates

Linux candidate 0.9.0-4 for Fedora 44/45 is built from `e466efe8fbcf0c706edb0886271dba4f8cfceb16` on isolated branch `fix/phase-6-source-privacy`. Both dist variants match byte for byte across two independent builds. The Fedora 44 dist variant was built on Fedora 45 and verified in a Fedora 44 container.

Actual network-disabled Fedora 44/45 containers upgraded release 2→4, ran the installed launcher help, retained synthetic config and SQLite checksums through uninstall, and passed SQLite integrity/content assertions. The final extracted Fedora 45 package passed GTK/WebKit navigation and held-delivery checks at allocated width 1440.

The final 99-file extracted payload has zero matches against the recorded private-catalog/literal/credential patterns. The original catalog and archived preview are excluded from the RPM. Historical source and Git privacy remain release blockers.

Windows Reader 0.10.0 win-x64 was cross-built twice with SDK 10.0.403 and identical restore inputs. The EXEs match and runtime-pack notices accompany them. Windows startup and COM remain unverified.

SHA256SUMS and current CycloneDX JSON inventories are in `outputs/aqua-roadmap-phase6-privacy`. Windows EXE/notices and its restore-input inventory remain in `outputs/aqua-roadmap-phase5-release`. These inventories cover tested environments/restore inputs and include base packages. Exhaustive binary composition and signing are outstanding.

The committed GitHub workflow is a proposed LAB gate with a read-only token. YAML and shell syntax were checked locally. Hosted Actions has not executed it. No protected check or deployment was configured.

`PACKAGE_VALIDATION.md` contains artifact hashes and test scope. `CHANGELOG.md`, `ROLLBACK_PLAN.md` and `FINAL_GO_NO_GO.md` define changes, state retention and the readiness decision. Use only disposable LAB profiles under the current NO-GO decision.
