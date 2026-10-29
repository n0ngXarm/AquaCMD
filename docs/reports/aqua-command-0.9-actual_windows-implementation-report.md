# Windows real Runtime reader implementation

Implemented only windows-reader/ and packaging/build-windows.sh in the existing AQUA repository. No production WinCC, PLC, network configuration or external Telegram access occurred.

## Result

- Native WinForms real OPC DA reader source, with fixed OPCServer.WinCC and only IOPCItemIO.Read COM projection. No simulator/mock source in the application.
- Explicit CoInitializeEx/CoUninitialize balance initializes only the owned STA thread before native COM activation.
- User-selected binary Tag allowlist, explicit organizational authorization and capture confirmation. Startup idle; separate send approval; no service installation/autostart/OPC enablement.
- Registry-only passive readiness; local COM activation only after approval. Matching registration bitness, no remote DCOM/redirected class/current-user override.
- Owned STA child process for local reads,8second connection/read timeout; stop kills only that child. Parent-loss watchdog. Five-second monotonic scheduler skips missed ticks.
- OPC quality/HRESULT/source time preserved, local read_at separate; unsupported/BAD/UNCERTAIN/unverified mapping states remain UNKNOWN.
- Atomic flushed queue/previous/sequence state, one owner lock, pending/byte quotas preserve existing records. Profile stable SourceId+server; capture revision resets continuity on selection/mapping changes without sequence reset.
- HTTPS private IPv4 transport uses existing Node HMAC handshake/digestACK. OS/custom root trust; no bypass, redirects, proxy or certificate downloads. Request8second body-inclusive deadline is retryable; operator cancellation stops the approved loop. Batch prefix obeys500KiB and32event limits.
- Exact event JSON replay and JS array-index property ordering support numeric Tag IDs. Binary integer raw values avoid number-format digest divergence.
- CSV writes only new files in owned AQUA profile; cannot overwrite source/existing export.

## Artifact

work/real-usage/windows-publish/AquaCommand.WinCCReader.exe

SHA256:715d16134eb3b65993812db89d52afb0f99bd379c02d305fab53a1ffc6b4bcae

Actual PE32+ x64 GUI, approximately50MiB, compressed single-file self-contained.NET runtime. Microsoft runtime LICENSE/THIRD-PARTY-NOTICES files are alongside it. No binary was added to Git by this agent.

## Validation

-47 core assertions pass on Linux: windows-core-final-tests.txt.
- Cross-publish successful with no compiler warnings: windows-publish.txt.
- Core tests include durable restart/sequence/ownership/quotas, exactACK failure retention, timeout retry vs cancellation, large batches, JSnumericTag ordering, capture revision continuity and CSV source immutability.
- Root is running actual Node Gateway HTTPS/HMAC/ACK interoperability with --interop and --interop-numeric. Those use clearly labelled test observations from the Tests project, not actual WinCC data.
- Source whitespace check clean. Generated bin/obj are ignored and not shipped as tests in the Windows executable.

## Limits

Windows GUI startup/layout, WinCC COM proxy/marshalling/bitness/access rights, real source timestamp/acquisition behavior and physical two-machine operation were not executed in this Linux environment. The user's OPC DA remains not formally enabled/approved; do not run against it or alter it automatically. No source/data sample is simulated in the shipped app. Unsupported interface remains an error, never a fallback.

Storage is bounded transport spool, not unlimited historian:10,000pending/64MiB, ACKed payload removed locally, Gateway retains ledger. Physical power-loss durability, Windows install/signing/SmartScreen and production acceptance remain unverified. SourceId must uniquely identify one exporter stream; do not run a separate CSV/Windows producer with the same source identity against a Gateway.
