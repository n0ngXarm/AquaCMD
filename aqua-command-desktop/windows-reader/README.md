# AQUA COMMAND Windows Runtime Reader 0.10

Native WinForms executable for an existing authorized **WinCC Classic V8.1 OPC DA server on the same Windows computer**. It reads selected pump-status and numeric (Analog) Tags; no mock source is shipped. Linux remains the Gateway/operations development platform. This companion continues the existing AQUA transport and source repository.

This is an unsigned engineering build. It is cross-compiled on Linux; actual Windows11/WinCC COM interoperability, permissions, bitness and Runtime load still require authorized LAB verification. Do not treat build/tests as production acceptance. The user's current OPC DA has not yet been formally enabled/authorized; this program does not enable it.

## Operator workflow

1. Open `AquaCommand.WinCCReader.exe`. Startup is idle: no COM activation, source read, spool creation, egress probe or Gateway request.
2. Click **Readiness** only when needed. It reads local existing registry registration for `OPCServer.WinCC`; it does not activate COM or certify organizational approval/Runtime readiness.
3. Choose a unique enrolled source identityPC-01,PC-02 orPC-03. One computer/spool owns each identity; do not run another exporter stream with the same identity against the same Gateway.
4. Enter exact Tag names, one per line, in the separate pump-status or Analog field. Use 1–100 unique names across both fields. Supported names use letters, digits, `_`, `-`, and `.`. This does not browse all Tags or accept an engineering Tag export as current values.
5. Obtain organizational approval outside AQUA. Only then tick its confirmation and click **Approve read every5s**. Review exact local server/CLSID/executable, selected names and interval before confirming. COM connection can launch the already registered local OPC server. No WinCC project, service, registry or DCOM settings are changed.
6. The mapping checkbox applies to pump-status Tags only. It confirms ON=1/OFF=0. Analog Tags accept finite numeric values, including fractions, regardless of that checkbox. A Boolean, string, array, nonfinite value or 64-bit integer VARIANT outside the exact JSON safe-integer range is unsupported as Analog. The reader sends numeric values in the original WinCC units without scaling. An Analog zero or one never produces a pump state or transition.
7. Collection appends durable snapshots everyfive seconds with no overlapping read. Slow reads skip missed ticks instead of issuing catch-up bursts. Stop reading terminates only the owned reader child; it never terminates WinCC.
8. Enter an explicit HTTPS Gateway private IPv4 URL and64 lowercase hex enrollment characters for this source. The key is held in process memory and is not saved. Windows/Gateway clocks must agree within30seconds for request authentication; AQUA never changes system time or enables time services. Use Windows certificate trust, or explicitly select the Gateway CA certificate. No TLS validation bypass, remote DCOM, subnet scan, proxy or Internet sharing is used.
9. Click **Approve send** separately and review destination. Pending records retry until an authenticated digest ACK is received or sending is stopped. Gateway ACK means durable Gateway receipt, not Telegram/Internet success. The Gateway handles its own separately approved external delivery.
10. Close/reopen always returns to idle. Reenter configuration/key and approve actions again. Existing spool data remains; do not delete it to clear an error.

## Data and storage

The fixed source adapter is `wincc-opc-da`, event schema `aqua.runtime.v3`, `simulated:false`. The companion preserves OPC quality word, signed per-item HRESULT and source FILETIME separately from local read completion time. `observed_at` is explicitly the read completion time for compatibility; it is not a manufactured device timestamp. GOOD OPC class uses mask 0xC0 = 0xC0 (192). Uncertain or failed samples retain diagnostic quality, HRESULT, and available source time.
An Analog observation is marked `value_type: "analog"` and carries its number in `observations[tag].raw_value`. Its `values[tag]` entry is null because that map represents pump states. Use the matching 0.10-compatible Gateway for Analog. The updated Gateway also accepts binary events from older Readers. Gateway archive CSV retains the numeric raw value.

State is one owned per-user profile under LocalAppData/AquaCommand/WinCCReader/profiles. Profile identity is stable for SourceId+local server. Changing selected Tags or mapping changes an atomic capture revision, resets transition continuity and preserves the same monotonic sequence and old pending records. Changing SourceId uses a distinct profile. The operator must consider old queued selections when approving delivery.

The state file commits pending event bytes, sequence and previous values together using a flushed temporary file plus atomic replacement. One process holds the owner lock. Missing/corrupt state, quota errors and ACK mismatches fail closed; pending records are not purged. Limits:10,000pending events and64MiB serialized state. Physical power-loss durability is unverified. After Gateway ACK the local pending payload is removed; sequence/counts/latest remain and Gateway keeps its own ledger. This is a transport spool, not an unlimited historian.

Destination URL+certificate trust is pinned while pending records exist, so a new destination cannot silently receive old backlog. Restore the approved destination to drain it. Source-side ACK means Gateway receipt only. TLS/HMAC/HTTP failures retain the original UUID/sequence/payload for retry and deduplication.

CSV export contains pending records only, always inside the owned AQUA profile directory. Its output is created as a new file; existing files and WinCC source files cannot be overwritten. The dialog starts in the valid profile folder.

## Build and tests

Requires.NET10 SDK. WindowsDesktop reference/runtime packs come from Microsoft NuGet during cross-build. No OPC Automation wrapper or third-party OPC library is assumed installed.

```sh
dotnet run --project windows-reader/Tests/Aqua.Reader.Tests.csproj -c Release
bash packaging/build-windows.sh /absolute/owned/windows-output
```

Optional `AQUA_DOTNET` chooses the SDK executable. Keep DOTNET_CLI_HOME,NUGET_PACKAGES and XDG_RUNTIME_DIR in owned development storage when running in a restricted environment. The final output is a compressed single-file self-containedwin-x64 executable; Windows extracts bundled runtime native libraries to its normal per-user.NET temporary directory. Keep the generated Microsoft runtime LICENSE/THIRD-PARTY-NOTICES files beside the distributed executable. There is no Windows service/autostart or administrator setup script.

`Tests/` contains all synthetic test inputs/fake HTTP handlers. They are not referenced by the Windows executable. Its `--emit-test-events`, `--interop` and `--interop-numeric` test CLI exercise Core serialization/TLS/HMAC/handshake/ACK against the existing Node Gateway without a production COM connection. Do not present these synthetic test values as actual WinCC observations.

## Read-only implementation and prerequisites

The production COM projection declares only the first `IOPCItemIO::Read` slot. It has no tag-write/WriteVQT/browse method. The local reader resolves the installed CLSID through read-only registry access; it avoids `CLSIDFromProgID`, which can register an absent ProgID. Remote/redirected registrations and current-user class overrides are rejected. Local-server activation selects the registered bitness.

Each read uses an owned STA worker process. Startup/read reply timeout is8seconds; cancellation kills only that process. Parent-loss monitoring ends the worker even if the UI process disappears. Transfer has an8second deadline covering headers and body; bounded prefix batches stay within500KiB, and exact signed ACK sets are required before local removal.

The DA component/project/Runtime startup entry and existing user access must already be configured and approved by the WinCC owner. Registration is not proof of that. AQUA performs no remediation. ODK/Unified/VBScript globals are not fallback drivers; no simulation replaces an unavailable server.

Sources: [Siemens WinCC V8.1 communication manual](https://cache.industry.siemens.com/dl/files/219/109990219/att_1333168/v1/WinCC_Communication_en-US_en-US.pdf), [OPC Foundation interop declarations](https://github.com/OPCF-Members/UA-.NET-Legacy/blob/master/ComIOP/Rcw/DataAccess.cs), [Microsoft CLSIDFromProgID behavior](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-clsidfromprogid).
