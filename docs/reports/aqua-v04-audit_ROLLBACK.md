# Rollback without destroying LAB data

1. Stop the LAB supervisor/individual role terminals with Ctrl+C. It stops only its owned child roles; do not use broad process-kill commands.
2. Keep the whole data directory, enrollment and all sessions. Stop every writer before making a backup. Do not copy only the SQLite main file while WAL writers run; copy the full stopped directory.
3. For a source checkout containing this development Git history, inspect `git status` and save any user changes. Create a separate branch/check-out from `baseline-v0.3` (commit `5f25be6`) to view the original; start v0.3 with a NEW data directory. Do not run v0.3 against v0.4 data. The Downloads source was left untouched.
4. Intermediate validated commits: G1 `c26ae1e`, G2 `d036a95`, G3 `876d2a7`, G4 `d839024`. A separate branch can be created with `git switch -c rollback/g4 d839024` after preserving local edits and stopping LAB services. Do not reset/clean the working tree destructively.
5. Release ZIP/npm tarball has no `.git` or enrollment. To restore a previous installed release, extract/install that saved release in a SEPARATE folder and use its own new data directory. Keep v0.4 data archived for returning to v0.4.
6. Reinstall v0.4 from the saved package and use the original complete v0.4 data directory to resume. RESET LAB creates another session without erasing old databases. Do not delete one receiver ledger while retaining an advanced source sequence.

There are no production, firewall, router, NAT/bridge or PLC changes to undo. Telegram test mode, if separately enabled, is disabled by removing its environment variables and starting with `--internet simulated`; all retained data remains local. A historical archive is not evidence that every snapshot was exported during disk-full or host-power failure.
