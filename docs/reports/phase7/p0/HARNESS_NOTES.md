# Harness notes

- One final CLI rerun invocation used an incorrect relative PYTHONPATH and exited 1 with three import errors for the existing dotenv dependency. No dependency was installed or source assertion changed. The corrected existing dependency path was then used in the network-disabled final run: all 39 tests passed, exit 0; see regressions/pwa-final-command.json and pwa-final.txt.
- Headless D-Bus/portal/a11y warnings are retained in sanitized session/compositor logs. Native source and extracted-payload runs exited 0. They do not establish a full interactive desktop or Windows/COM acceptance.
- Initial P0 RPM build evidence is superseded by rpm-final from ca1a96fe9323d1758dc59a00498c39fde4c67d94. Initial intermediate raw logs are labeled earlier-build records; final source/payload preflight, manifest, installed-container receipt and artifact hashes reference the final build.
- Transport suites intentionally log rejected untrusted TLS certificates. Their pass/fail decision comes from the anchored unittest/TAP summary and actual process exit code, not substring matches for FAILED in an expected TLS diagnostic.
- Baseline privacy regressions intentionally captured synthetic leakage. Delivery copies redact those sentinels; original raw bytes remain private. Source tests contain only clearly synthetic test constants.
