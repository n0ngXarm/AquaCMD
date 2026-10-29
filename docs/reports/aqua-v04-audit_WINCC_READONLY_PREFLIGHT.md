# WinCC read-only adapter — unavailable in this LAB

`WinCCReadonlyAdapter` is an interface boundary only. It has no driver, URL, DB mapping or network call, and an attempted read fails explicitly. Default source is the built-in `simulated-runtime` adapter.

Before any separate implementation, obtain written LAB/OT owner approval and confirm the exact WinCC edition/version, supported runtime-read mechanism, vendor driver/licence, read-only account and permission scope, network boundary, export schema, timezone, quality meanings, permitted tag list, expected update/freshness, test fixture provenance, audit/rollback and permitted destinations. Validate fixtures offline first. Configuration `Export All`, StartValue and Tag Object addresses do not prove live runtime values. DB22/DB34 meanings and types remain unverified; there is no PLC mapping here.

No production connectivity, firewall changes, write commands, driver install or credential reuse is authorized by enabling the simulator or this interface.
