# G0_AUDIT_REPORT — AQUA COMMAND UI/UX v2.1

**Stage:** G0 / Read-only audit. **Date:** 28 October 2026, Asia/Bangkok. **Scope approval:** user requested G0/G1 only. No source/config/API/DB/network modification, no application launch, no production connection, no runtime probe. Documents and evidence are stored outside the repository.

## 1. Inputs and baseline

Read completely: Master v2.1 (299 lines), Screen Spec v2.1 (520 lines), pack README, repository application AGENTS.md. The pack README's suggestion to copy documents into the repository was not executed: the current user forbids repository modifications before approval. Files were read from an isolated working copy of the ZIP.

| Item | Observed evidence |
| --- | --- |
| Repository | `work/waterlevels-desktop` under this chat workspace |
| Application | `aqua-command-desktop/` inside the existing repository; no replacement project |
| Branch / commit | `codex/aqua-native-desktop-rpm` / `97451ac17631d4978e21971301c8e8c818ab1894` |
| Initial status | Clean; 96 tracked files hashed before audit |
| Version | Desktop/RPM0.7.0; reused backend package.json remains0.5.0 (engine metadata, not UI version) |
| Runtime | Fedora44/Linux7.2 x86_64, Python3.14.8, Node22.23.1; GTK4/PyGObject native frontend |
| Frontend transport | Private JSON-lines stdin/stdout to one owned Node host; headless model, no UI HTTP listener |
| Role transport | Authenticated POST over loopback HTTP; protocol permits explicitly approved private-LAN/TLS configuration, not arbitrary discovery |
| Native default | Runtime unavailable, idle; no child until selected source + manual approval; capture and transfer separate |
| Native enrollment | One PC-01 Agent, PC-04 Gateway and CENTRAL-LAB in one host. PC-02/03 exist in legacy LAB code, not evidence of active physical devices |
| Default endpoint configuration | Agent127.0.0.1:4181; Gateway127.0.0.1:4174; Central127.0.0.1:4175. Port4173 is a base parameter, NOT a native UI listener. These are configured service endpoints, not observed workstation NIC addresses |
| Existing root applications | `aqua-command/` web app and `src/` PWA monitor exist separately; not started, replaced, or changed |
| Process visibility | No matching AQUA app/host/service entrypoint observed in the tool's process namespace. Visibility is restricted; no claim about all desktop processes |
| Source/source state | No production endpoints, active enrollment secrets or live DBs opened. User reports WinCC V8.1 and no enabled OPC UA |

Source references below are relative to `aqua-command-desktop/`; line numbers refer to the audited commit.

## 2. Frontend and control map

- `desktop/app.py:79-112`: four current pages: Overview, values, activity, permissions. `SourceEditor` at36, `ConsentDialog` at24. No topology/source registry/task builder pages yet.
- `desktop/app.py:115-128`: scoped remembered grants; source/settings/storage, destination URLs and dry-run mode. Manual start after every launch; change scope asks again. `end_session`221 and revoke232 stop owned roles.
- `desktop/client.py`: owned subprocess and bounded private pipe; no browser/webview. `desktop/host.mjs:19-25`: allowlist `status`, `recording`, `transfer`, `export_csv`; start requires approved:true; generated export location only.
- `desktop/style.css`: Noto Sans Thai14px body,25px title,22px body padding,185px sidebar, dark panels. No tabular/monospace network identity treatment. Existing UI min1050x650/default1320x820; no new layout measurement performed in G0.
- `backend/public/`: old isometric and simple web assets retained for regression; excluded from native RPM. Reuse history/scene only as optional selected-item view after permission; no new 3D work.
- `packaging/`: RPM launcher/application icon and desktop entry. No install scriptlets, auto-start service, browser payload or production deployment was run.

## 3. Current architecture and exact contracts

```text
Native GTK UI (manual start + capture consent)
  -> JSON-lines stdin/stdout -> desktop/host.mjs
  -> readonly source: explicit LAB fixture OR approved already-exported CSV
  -> Agent SQLite spool (5s capture + transaction/cursor)
  -> [separate transfer consent] signed handshake + events -> Gateway SQLite
  -> signed events + ACK -> CENTRAL-LAB
  Gateway also -> STATE_CHANGE notifications -> Telegram dry-run by native default
WinCC Runtime direct driver: unavailable; no OPC browse / PLC access
```

| Surface | Found contract | Limitation |
| --- | --- | --- |
| Native status | host emits ready/status + data, about1s; model polls roles500ms with700ms timeout | UI open does not start a session. Model.time is rendering time, not source observation time |
| Agent | POST /v1/status, /v1/recording, /v1/transfer, /v1/exports | HMAC enrolled identity; source mutation simulation routes reject readonly config |
| Gateway | POST /v1/status, /v1/transfer (DASHBOARD); /v1/handshake, /v1/events (enrolled exporters) | ACK only after SQLite ingest; readiness also depends on approved forwarding and its own egress gate |
| Central | POST /v1/status (DASHBOARD), /v1/events, /v1/notification (Gateway) | Local LAB sink; not a Telegram receipt |
| Health | GET /health | Unauthenticated basic role health is not source read permission or SCADA auth evidence |
| Legacy UI | /api/status, /api/action, downloads, SSE in dashboard.js | Native host always headless; do not add an HTTP frontend or assume legacy endpoints are running |
| Missing native commands | device registry/identity read, source registry, bounded OPC browse/test-read, per-item config/rules, queue row metadata, exact receipt lookup, filtered audit export | All are gaps/proposals. No endpoints or implementations added in G0/G1 |

Security: protocol.js13-17 restricts destination schemes/hosts, private-LAN requires explicit allow flags, insecure LAB HTTP separately acknowledged. HMAC+nonce+timestamp and signed responses authenticate AQUA peers; they are not WinCC/Windows login. TLS verification stays enabled. Secrets live in owned local files, are not UI state; no credential collection. CSV uses read-only fs opens and source/storage alias guards. Role permissions reset false on restart; generation checks prevent new outgoing operations after revocation. No IP scan or service discovery by subnet.

## 4. Capability matrix — observed implementation only

| Source | Hostname / IP | Auth status | Available count | Selected read | Quality / timestamp | Constraints |
| --- | --- | --- | --- | --- | --- | --- |
| LAB native fixture | Logical Agent ID + configured loopback endpoint; no actual hostname/NIC list | Local enrolled AQUA peer only | Configured list (default5), not WinCC total | Configured CSV batch, simulated | Simulated quality128 and source timestamp | Explicit LAB selection + consent; one-host evidence |
| Imported WinCC mapping | No machine identity imported by current parser | N/A; file access only | Eligible Binary .RUN_S names returned (max100); not all input rows or runtime tasks | Names only, no live read | No runtime quality/time | model.py8-17; configuration is not runtime |
| Approved CSV file reader | Agent ID + configured endpoint; not SCADA IP | File/collector outcome, no SCADA session | Configured names | Complete configured frames from existing file | Raw value/code/error and timestamp | 8MiB/file,366 files,32 frames/capture; refuses unexpected tags; not a general superset-selection reader |
| Direct WinCC / OPC UA | Not implemented | Not available | Not available, never0 | Not implemented | Not available | adapters.js7-9 available=false; user reports OPC UA not enabled; no enable/config action performed |
| Future approved local exporter | Depends on approved connector | Depends on actual collector | Selected-only if supported | Not yet validated against WinCC | Depends on supported API | Disabled source template is not an executed/verified connector |

## 5. Data correctness / metric dictionary

| Existing label / field | Correct meaning and scope | Proposed label |
| --- | --- | --- |
| snapshots | Cumulative SNAPSHOT count in current persisted profile/session DB; persists UI/service restart | Saved snapshots · dataset generation |
| pending / scadaQueueCount | Current unACKed events (snapshots AND transitions); aggregate may be partial if sources missing | Local pending events · observed at... |
| gateway.pending | Current Gateway event ledger awaiting upstream ACK | Gateway pending events |
| agents[].acked,lastAckAt | Gateway durable receipt acknowledged locally; count includes all event kinds | Gateway accepted events |
| delivered / gateway.upstreamDelivered | Cumulative Gateway records ACKed by Central | Central accepted events |
| notificationSent | Notifications marked delivered in their mode; dry-run/mock/real are different | Dry-run recorded / Telegram API accepted, mode-qualified |
| observedAt / record.observed_at | Source observation time | Observed, ICT+UTC detail |
| record.at / lastExport | Producer local commit time | Recorded locally |
| agents[].lastSeen | Time dashboard received a role STATUS, not an individual reading | Status received |
| gateway.egress.checkedAt | Time of Gateway's own egress result, real or simulated | Egress checked at... + method/mode |

No per-item received_at or last-good history is currently reported. UI clock must show Asia/Bangkok explicitly; old present_status uses machine-local timezone and must be adapted only after G2 approval. Freshness is independent of raw quality; current presentation treats age>15s or timestamp>30s in future as not safe for ON/OFF. Never infer pump OFF from missing/denied/old data.

## 6. Confirmed gaps and risks

| ID / priority | Finding / evidence | Design boundary |
| --- | --- | --- |
| R01 Critical | No Runtime connector (adapters.js7-9); no approved OPC service | Show unavailable with reason; no automatic enable, import or LAB fallback |
| R02 High | Device hostname/NIC IP/interface/subnet missing; factory IDs and loopback are not physical inventory | Read safe configured endpoints now; real device metadata needs separately approved contract |
| R03 High | Current delivered means Central, not Telegram; placeholder gateway initializes upstreamDelivered0 | Mode/destination-qualified receipts; never show observed0 when not reported |
| R04 High | Legacy dashboard aggregate assumes8 pump IDs, synthesizes flow/pressure/temp, full/dataQuality/queueIsPartial use that heuristic (dashboard.js12-18) | Bind real selected values to per-agent observations; hide synthetic charts and recompute UI coverage. Do not patch backend in G0/G1 |
| R05 High | Current CSV reader rejects any row outside csv.tags (csv-source.js30) and requires whole configured frame | Arbitrary Task Builder subset needs a separately approved reader-selection contract; UI filtering alone is not selected sampling |
| R06 High | Tag/settings changes hash a new profile and stop session (app.py219, model.py55); old queues parked; no hot reload/versioned rules | Explain restart/profile impact. Future selection config must preserve source cursor/ACK and immutable event IDs; needs backend design approval |
| R07 High | State-change only; no per-item ON/OFF/stale/bad/none rule engine, no analog/alarm schema | Show unavailable capability; planned controls disabled until G4/backend approval |
| R08 High | Cached Gateway egress may remain VERIFIED after poll failure; no per-agent egress | Require fresh reporter, checked_at and explicit mode. Never infer PC1 Internet from PC4 |
| R09 Medium | Logs bounded100 merged/1000 per role; IDs are log-row IDs, not process event UUID. Consent hashes are not an actor/config audit ledger | Bounded recent activity only; exact event/receipt/audit capability needs separately approved data contract |
| R10 Medium | No exposed oldest pending/per-row delivery metadata, latency/ACK-rate/trend window | Show Not reported, hide unsupported charts. No frontend direct DB access |
| R11 High | TelegramTransport.send permits only labelled LAB text; real-file notification prefix is different (telegram.js29, store.js120) | Real file Telegram support is blocked/policy-gated, not operational just because env token exists |
| R12 Medium | Quotas:10000 pending source events,2000 ACKed retention,50000 Gateway/Central ledger,64MiB DB. CSV export2000 events/250KB | Finite LAB storage, explicit truncation/quota warnings; no unlimited retention claim |
| R13 Medium | No complete 4-resolution evidence/keyboard/contrast test for proposed UI | G1 wireframes are designs, not AC-01 screenshots of implemented software |

Gateway WAN-down nuance: fresh readonly handshake refuses a Gateway whose ready flag is false, so source may retain backlog. With an already-valid session, behavior and queue location can differ. Do not promise that all WAN failures always grow the same queue; verify both pre/post-handshake cases in approved LAB tests.

## 7. Screenshot review (historical evidence, not newly launched)

- Prior user screenshot: stopped reader,4 snapshots/4 Central deliveries, Telegram0 dry-run; raw log view has large blank region, no clear registered workstation IP or data-definition scope.
- v0.7 `consent-idle.png` and `consent-dialog.png` (existing outputs) show improved separate consent, but only4 pages; no topology, source capability inventory, selected-item editor, or per-stage receipts. Metrics are below the fold at1366x768, long paths dominate overview, and unknown quality causes are not independently surfaced.
- Existing files are referenced only; no app/service was started to capture new screens. G1 mockups will be explicitly labelled SIMULATED / DESIGN ONLY.

## 8. Test baseline and safe checks

| Check | Result this G0 | Evidence / limitation |
| --- | --- | --- |
| Git initial status + 96 tracked SHA256 | PASS read-only baseline | audit before.json outside repository; final comparison required |
| Node --check (all27 application JS/MJS source/tests) | PASS27/27 | Parse only; modules not executed, no listeners/DB |
| Python ast.parse (7 modules/tests) | PASS7/7 | No imports of application, pycache, file fixtures or service |
| Desktop entry validation | PASS | desktop-file-validate; no install |
| Full backend functional suite | SKIP new run | Prior v0.7 log50/50 PASS; historical, not refreshed in G0 |
| Python functional models / permission tests | SKIP new run | Prior7/7 documented in v0.7 report; AST pass is not runtime pass |
| Native installed-payload UI | SKIP new run | Prior JSON result PASS for idle/cancel/approval/revoke/relaunch/export; not recaptured |
| WinCC/OPC, real LAN/Telegram, Windows install | NOT VERIFIED | No authorized environment/access; no attempt |
| New design visual/layout acceptance | DESIGN REVIEW ONLY | Wireframe rendering is not implemented UI acceptance |

## 9. Proposed implementation boundary

G2 approval can cover native UI shell/tokens/presentation adapter and safe bindings only. Do not include new endpoints/DB schema, WinCC/OPC driver, credential handling, probes, item-rule engine, dynamic remote registry or hot reload without a separate approved scope. Maintain existing spool, schema, cursor/ACK, manual consent, native IPC and RPM boundary. Root web/PWA app and production systems remain outside scope.

Changed repository files: **none**. Source patch: **none**. New runtime/config/data objects: **none**. Evidence/design documents only in isolated work/output folders. Rollback G0/G1: no software rollback required; documents can be retained or removed independently. G2–G5 remain unapproved.

APPROVAL REQUIRED — NO SOURCE MODIFICATION PERFORMED
