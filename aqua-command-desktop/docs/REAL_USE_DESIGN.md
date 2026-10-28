# Actual read-only runtime path

Windows WinCC host: AQUA Runtime Reader.exe (manual native UI) -> local OPCServer.WinCC / IOPCItemIO::Read only -> AQUA-owned atomic spool. Separate manual send -> explicitly enrolled private HTTPS Gateway -> existing authenticated durable SQLite ledger -> separately authorized Telegram transport. The app does not install/enable OPC, expose DCOM over LAN, browse every Tag, scan peers or change network settings.

Registration readiness uses read-only registry inspection. COM activation may launch the local server and is permitted only after the operator confirms prior organizational authorization and explicitly starts reading. No source is invented if unavailable. Each process launch resets read/send permission.

Event v3 preserves OPC raw numeric value, raw quality word, HRESULT and source FILETIME separately from read_at/local commit/receiver time. GOOD requires OPC quality mask0xC0, successful HRESULT and confirmed binary mapping. Source timestamp is never synthesized from read time. Raw0 is distinct from missing. BAD/UNCERTAIN/unknown mapping never becomes OFF.

Gateway TLS validates CA/name and HMAC authenticates exact enrolled source IDs. Authenticated digest ACK follows durable commit. Lost ACK retries the same immutable event; records stay pending on ambiguous failure. Telegram does not guarantee exactly-once on an ambiguous send response. Snapshots remain in a finite Gateway archive; Telegram sends transitions, not a substitute snapshot archive.

Normal installations expose no LAB source; legacy test tools require an explicit developer flag. Windows execution/COM, organizational approval, actual two-host LAN and actual Telegram delivery remain separate acceptance steps, never inferred from Linux test fixtures.
