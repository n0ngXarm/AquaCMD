# Actual-use independent read-only safety review

Status: final focused source review complete. No unresolved significant implementation bug found in the current reviewed code. Windows/WinCC/physical-LAN acceptance is still unverified and is not implied by this result.

Scope: Windows Core/WinForms/local OPC DA read worker; native actual setup/consent; deployed Node Agent/Gateway and existing custody/protocol changes. No source edits, production connection, WinCC/PLC activation/configuration or actual Telegram request performed by this review. Review probes used only owned temporary synthetic events and local Store objects.

## Final recheck

- Numeric Tag keys are now ordered with JavaScript canonical uint32 array-index rules before C# event serialization (`Core/Model.cs:15,65`). Non-index keys keep stable input order. This removes the confirmed binary-value `2`,`1` digest mismatch, without assuming arbitrary JSON numeric formats are interchangeable.
- Windows actual COM path only produces integral raw numbers within ±1e15 (or null), so values remain exactly representable by the Node protocol; unsupported nonintegral/nonfinite types never become OFF. This is a binary pump monitor, not a general analog-tag serializer.
- Independent fresh desktop pure test run:30 tests passed. Independent execution of the current Release Windows Core test assembly:47 assertions passed (`review-core-tests.txt`); fakes are confined to the test project, and no external requests were made. Reviewed final cross-language evidence `cross-language-interop.json`:both ordinary and numeric-Tag real HTTPS/HMAC/digest-ACK runs passed, each committing3 events/2 snapshots with outbound egress disabled. Inputs are synthetic test frames, not actual WinCC readings. The final interoperability fixture preserves a known old source timestamp separately from fresh read time.
- Current stable C# source profile uses SourceId+ProgID; CaptureRevision clears continuity inside the same atomic append transaction without resetting sequence/pending. Current Node actual profile similarly retains the stable source dataset and revision-specific cursor namespace.
- Current C# request timeout is translated to TimeoutException when caller consent cancellation did not occur; native retry remains active. Local worker timeout is explicit and stops only the owned reader child.

## Findings resolved during review

- C# numeric Tag dictionary ordering now matches Node JSON serialization, preventing digest mismatch for accepted integer-only Tag names.
- Native Agent Python/JS configuration mismatch (mandatory Telegram mode/custom CA on JS path) aligned; OS trust and no Agent Telegram mode are supported.
- C# stalled response body now has a linked whole-request deadline; request-only timeout becomes TimeoutException so forwarding retries instead of mistaking it for operator cancellation.
- Worker connection/read timeout becomes an explicit error, killing only the owned child. Native stop remains separate from internal failure.
- Windows and Node uploads choose a byte-bounded prefix instead of endlessly retrying an oversized32-record batch.
- Source identity/spool stays stable across selected Tag/mapping changes, while capture revision resets prior-state continuity atomically; Node CSV revisions use separate cursor namespaces and preserve immutable pending records/source sequence.
- Native Agent custom CA bytes are immutable within session; replacement files cannot expand trust. New approval requires a reviewed restart on changed CA material.
- Windows CSV export is constrained to the owned AQUA profile and CreateNew, preventing arbitrary source/project file overwrite; default dialog directory follows that owned profile.
- Windows read scheduling skips missed deadlines instead of issuing catch-up OPC read bursts.
- JS backend rejects shared keys reused across source identities, matching native validation.

## Positive boundaries checked

- OPC readiness inspects registry read-only; no CLSIDFromProgID, registration, service enablement, browse, remote DCOM target or OPC write method projection.
- COM local-server activation exists only in the explicitly started child, after organizational-authorization confirmation and manual capture review; activation can launch the registered local server and the UI discloses this.
- OPC DA quality192/mask0xC0, signed HRESULT and raw source FILETIME remain separate from read_at/local record/Gateway receipt times. BAD/UNCERTAIN/unconfirmed mapping never synthesizes OFF.
- Read/send permissions reset on every launch and are separate; Node Gateway local receive/outbound controls are independent. No headless Dashboard remote polling or exporter use of Gateway administrative credentials.
- Authenticated HTTPS validates trust/name; HMAC covers method/path/time/nonce/body and response digest; ACK follows durable Gateway ingest. No scans, NAT/bridge/firewall/Internet-sharing changes or website/webview/UI HTTP listener.
- Source files are read-only. Owned local config, spool and export writes are intentional. No simulator source is exposed in normal native launch; synthetic observations remain in test projects and explicitly gated developer tools.
- Gateway UI shows received data rather than fabricated exporter process reachability; configured endpoints and unknown NIC/hostname are distinct, with no invented Central receipt.

## Verification limits / operational boundaries

- Linux Core, local HTTPS and native GTK tests do not verify Windows COM/WinCC V8.1 or two physical machines. Organizational OPC DA approval is still absent; no actual read is claimed.
- Windows GUI execution/accessibility/display scaling and real Telegram delivery require later authorized validation. Internal dedup does not promise Telegram exactly-once after an ambiguous external response.
- Gateway archive is finite (current SQLite64MiB/database and50k record ceiling), not an unlimited historical archive. Windows pending spool is bounded too; full storage must stop/preserve pending and be surfaced before operational deployment.
- Atomic/restart tests do not certify physical power-loss durability or hardware caching behavior.
