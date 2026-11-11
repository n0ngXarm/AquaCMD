# Release 4 package validation

Source inputs are archived from `e466efe8fbcf0c706edb0886271dba4f8cfceb16`. SOURCE_DATE_EPOCH is that commit's timestamp. Build host is Fedora 45 with RPM 6.1.0. Two independent build directories produced identical RPMs for each dist label. The Fedora 44 label was built on Fedora 45 and installed in an actual Fedora 44 container.

| Artifact | SHA-256 |
| --- | --- |
| `aqua-command-desktop-0.9.0-4.fc44.noarch.rpm` | `4ad5be72d6117d2cd30e4f21027e092e8b05ae813c26ee73b6b4f40ecc0a7348` |
| `aqua-command-desktop-0.9.0-4.fc45.noarch.rpm` | `1e012ebe6eebf9ef83d0f88703157ae694e357ac85ada8b4c9ae40a9a538e58b` |
| `AquaCommand.WinCCReader.exe` | `52487b212001832fe264e3ebec8d156c0c9f3ca99350049459439bee1b1397d1` |

Actual offline containers upgraded installed release 2 to release 4, ran `/usr/bin/aqua-command --help`, checked the seeded config and SQLite hashes, uninstalled, checked both hashes again and ran SQLite integrity/content assertions. Both containers exited 0. This verifies preservation of the synthetic files, rather than exhaustive application-state migration or backup restoration.

The final Fedora 45 RPM was extracted and all 99 files were scanned. Zero known privacy-pattern matches were found. Manifests exclude the site catalog, archived Windows preview, tests, DBs, private keys and private config. Header and payload digests pass with `rpm --nosignature -K`. Default `rpm -K` reports missing required signatures under the host policy. These candidates are unsigned.

Extracted-payload GTK/WebKit navigation passed in a temporary profile, isolated network namespace and headless compositor. The allocated window width was 1440 pixels for a 1360-pixel request. This check is distinct from the container package lifecycle.

Windows 0.10.0 win-x64 was cross-built twice from identical source/restore inputs and the EXEs match. Runtime notices accompany it. Startup and OPC DA COM have no Windows execution evidence.

Evidence and RPMs are under `outputs/aqua-roadmap-phase6-privacy`. Windows artifacts remain in `outputs/aqua-roadmap-phase5-release/windows`. CycloneDX inventories cover 316 Fedora 44 RPM components and 319 Fedora 45 components, including container base packages. Windows inventory covers restore inputs. A complete executable composition scan remains open.
