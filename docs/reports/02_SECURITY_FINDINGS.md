# Security findings and current boundary

| Finding | Current LAB evidence | Remaining boundary |
| --- | --- | --- |
| Secret configuration permissions | Final 27-test focused suite includes atomic 0600 writes, symlink rejection, concurrent saves and pre/post-commit distinctions | Windows ACL behavior and credential rotation require their own acceptance |
| OPC UA trust and downgrade | Explicit PKI/anti-downgrade tests and loopback secure-read contracts pass | No actual WinCC trust enrollment was exercised |
| Web read endpoints | Inherited Phase 1A controls remain in the candidate and web regression passes | Reverse proxy or external exposure requires deployment review |
| Compose publication | Parsed configuration publishes the dashboard through host `127.0.0.1` | Other containers and custom proxies remain separate access paths |
| Source privacy | Tracked site catalog removed in the isolated current tree, selected runtime defaults sanitized, final extracted RPM scan reports zero matches | Git history, archival preview, historical documents and older artifacts still require review before publication |
| Exposed historical credentials | Prior remediation records describe redaction | Revocation and rotation have no verified receipt in this task |

The payload scan checked all 99 extracted files against 457 known catalog names, selected site/workstation literals, credential formats and prohibited private artifact extensions. A zero match is limited to those patterns and files. It does not establish a complete secret audit of source, history or the separate Windows binary.

Final security and reliability tests returned exit 0, 27 tests passed, with temporary HOME and a loopback-only network namespace. Raw evidence is in `outputs/aqua-roadmap-phase6-privacy/final4-security-reliability.txt`. The pattern scan and manifests are recorded alongside it.
