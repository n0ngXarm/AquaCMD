# G1_DESIGN_PROPOSAL — Professional Desktop UI/UX v2.1

**สถานะ: DESIGN ONLY / รออนุมัติ G2–G5** · 28 ตุลาคม 2026 · Asia/Bangkok  
อ้างอิง Master299บรรทัด, Screen Spec520บรรทัด, AGENTS.md และ G0 ของ commit `97451ac17631d4978e21971301c8e8c818ab1894` ไม่มีการแก้ source/backend/API/CSS/config/dependency/schema หรือเปิดบริการใดในการออกแบบนี้

## 1. ข้อเสนอที่แนะนำ

เลือก **Option B — Network & SCADA Visibility Console** เป็นโครงหลัก เพราะเป้าหมายรอบนี้คือเห็นเครื่อง/IP/ตำแหน่งค้างในระบบหลายเครื่องและสาธิตให้หัวหน้าเห็นเหตุผล ใช้ตารางความหนาแน่นของ Option A ภายในหน้า Live Monitoring ได้โดยไม่เพิ่มชุด navigation หรือข้อมูลคนละแหล่ง

**เงื่อนไขสำคัญ:** Backendปัจจุบันยังไม่รองรับทะเบียน NIC/Hostname, WinCC Runtime, OPC Browse, Item Builder แบบมี Rule และ hot reload จึงต้องแสดง Not reported/Not supported และปิด action ที่ยังไม่มีผลจริง รุ่นแรกหลังอนุมัติ G2 จะผูกเฉพาะข้อมูลที่มีอยู่ ไม่ทำให้ภาพดูเหมือน PC1–PC3 เชื่อมหน้างานจริงแล้ว

### เปรียบเทียบสองทางเลือก

| ประเด็น | A — Operations Console | B — Network & SCADA Visibility Console |
| --- | --- | --- |
| หน้าแรก | Export/queue KPI + pipeline + selected signal tableใหญ่ | Registered endpoint graph + identity/IP + stage pipeline + selected signals |
| งานเด่น | เฝ้าค่าปั๊มจำนวนมาก ตรวจ bad/stale และการส่ง | ดูเครื่อง/ลิงก์/ขอบเขต LAN-WAN แล้วเจาะเหตุขัดข้อง |
| ความหนาแน่น | สูง; ให้ตารางเป็นแกน | ปานกลาง; graph+inspector แบ่งพื้นที่กับตาราง |
| Cognitive load | ต่ำสำหรับOperatorที่รู้ว่าแหล่งข้อมูลคือเครื่องใดแล้ว | ต่ำสำหรับอธิบายระบบหลายเครื่อง; ต้องมีlegendและลิงก์ที่มีหลักฐาน |
| Build effort | G2 UIประมาณM; topologyยังต้องทำครบในหน้า02 | G2 UIประมาณM–L; graph/layout/keyboard focusเพิ่มจากA |
| Performance | บริหารแถวและfreeze displayได้ง่าย | update nodeเฉพาะเปลี่ยนค่า; ไม่layout graphใหม่ทุกsnapshot |
| Accuracy risk | สับสนSaved/Pending/Deliveredหากไม่ระบุscope | เผลออ้างIP/NIC/physical switch/WANที่ยังไม่วัด |
| Accessibility | table semantics/keyboardตามแถวตรงไปตรงมา | ต้องมีDevices Tableเทียบเท่าgraph และเข้าถึงdrawerด้วยคีย์บอร์ด |
| Backend availability | count/valueบางส่วนมีแล้ว; rule/audit/queue rowยังขาด | graphความสัมพันธ์configuredพอแสดงได้; realidentity/topologyยังขาด |
| สิ่งที่ต้องติดSIMULATED | ตัวอย่างค่าปั๊ม/egress/Telegramdry-run/fixtureaddresses | เหมือนA รวมทุกnode/link/IP10.10.20.xในภาพตัวอย่าง |
| เหมาะกับAQUAตอนนี้ | ทางเลือกเมื่อเน้นเฝ้าค่าต่อเนื่องเป็นหลัก | **แนะนำ** ตามเป้าหมายNetwork/SCADAvisibilityที่ผู้ใช้ระบุ |

ไม่เปลี่ยนframework: รักษา GTK4/PyGObject, private Node IPC, read-only CSV boundary, SQLite spool/ACK/dedup และ RPM การสร้างwireframeเป็นภาพเอกสาร ไม่ใช่เว็บหรือแอปใหม่

Task / Monitored Item ในข้อเสนอนี้หมายถึง Tag, Signal, OPC Item หรือ Alarm ที่ผู้ใช้เลือก ไม่ใช่ Windows Task Manager และไม่ใช่จำนวน PLC Data Blocks โดยอัตโนมัติ ถ้ามี `DB22,DD32` ให้ระบุว่าเป็น PLC data address ไม่ใช่ IP และไม่เดาความหมายบิต/ค่าเอง

## 2. Information architecture / Desktop shell

```text
AQUA COMMAND | SITE (local label, not verified WinCC project)
01 Overview — ภาพรวมการเก็บและการส่ง
02 Network Topology — Registered devices / configured endpoints
03 SCADA Sources — Connector / capability / read scope
04 Monitored Items — รายการที่ผู้ใช้เลือกและกฎติดตาม
05 Live Monitoring — ค่า/Quality/Freshness/Source
06 Gateway & Delivery — คิว/ACK/ปลายทาง
07 Alerts & Audit — Process events / notification / audit
Utility: Help + Permissions/Connection review + explicitly labelled LAB tools
```

- Shell1440×900: sidebar240px, topbar60px, bottomstatus32px, contentpadding24px, gap16px; 1600×900 และ1920×1080ใช้พื้นที่เพิ่มกับตาราง/inspector ไม่ขยายฟอนต์ทั้งระบบ
- 1366×768: sidebar232px, topbar56px, 14pxbody; ย้ายรายละเอียดรองไปdrawer, scrollตารางภายในpanel, ไม่ซ่อนIPและไม่ย่อเป็นmobilelayout
- Headerติด Site label, source mode, last observed/update label และ Read-only เสมอ; Site labelไม่มีหลักฐานWinCCProjectNameห้ามอ้างว่าเป็นprojectจริง
- Network / Sources แสดง Agent ID และHostnameคนละfield; ถ้าHostnameไม่มีให้เขียน Not reported ให้IPหรือconfiguredendpointcopyได้โดยไม่hover
- Persistent status: permissionอ่าน/ส่ง,collector,approved LAN link,Gatewayegress,localpending,sourcefreshness แสดงเป็นคำพร้อมicon/color
- Global modeสำหรับหลายแหล่งใช้ MIXED พร้อมจำนวนแต่ละชนิด ไม่ย้อมทั้งหน้าว่าLIVEเพราะมีsourceเดียวอ่านได้
- Windowเปิดใหม่คงidle ไม่มีpoll/scan/source readเอง การเปลี่ยนหน้าเป็นการดูข้อมูลเดิมเท่านั้น

### Permission model ที่ต้องรักษา

1. เลือกsource/selecteditemsอย่างชัดเจน → reviewขอบเขต/เวลา/ที่เก็บ → อนุญาตอ่านแบบต่อเนื่องทุก5sจนหยุด
2. อนุญาตforwardingแยก → ระบุข้อมูล/เครื่องรับ/ปลายทาง/โหมดnotification → เริ่มstore-and-forward
3. “ไม่ถามซ้ำ” เป็นการจำขอบเขตเดิมหลังผู้ใช้กดเริ่ม ไม่ใช่autorunเมื่อเปิดแอป ห้ามติ๊กไว้ล่วงหน้า
4. ถอนสิทธิ์หยุดเริ่มคำขอถัดไป คำขอที่ส่งไปแล้วอาจตอบกลับได้ คิวเดิมไม่ถูกลบ
5. ปัจจุบันยังไม่มีsessionสำหรับ “อ่านสถานะAgentอย่างเดียวโดยไม่เริ่มcollector” โดยอิสระ: ถ้าhostsessionยังไม่เริ่ม ให้Topologyแสดงเฉพาะconfiguration/CACHED/UNKNOWN และปิดRefreshพร้อมเหตุผล การเพิ่มobserve-only permission/commandต้องขอbackend scopeแยก ไม่แอบเริ่มworkerเพื่อให้graphมีสี

## 3. Data semantics และ visual states

แยกสถานะเป็นหลายแกน ไม่ใช่badgeเดียวแทนทุกอย่าง:

| แกน | ตัวอย่าง | กฎ |
| --- | --- | --- |
| Source kind | SIMULATED / IMPORTED MAPPING / FILE / LIVE CONNECTOR | simulated=falseของไฟล์ไม่ใช่หลักฐานLiveWinCC |
| Freshness | CURRENT / CACHED / STALE / NEVER READ / CLOCK SKEW | ใช้observed_atจริง; freeze displayแสดงCACHED/เวลาค่าที่แช่ |
| Read quality | GOOD / BAD / UNVERIFIED MAPPING / UNSUPPORTED VALUE / UNKNOWN | แสดงrawquality code;ไม่สร้างUNCERTAINถ้าsourceไม่ได้ส่ง |
| Connectivity | REACHABLE VIA APPROVED STATUS / AUTH DENIED / TIMEOUT / NOT CHECKED | method+observer+checked_at; ไม่มีการอนุมานpoweredoff |
| Authorization | Capture allowed / transfer blocked / permission required / revoked | แยกจากreachabilityและSCADAauth |
| Destination | Gateway accepted / Central accepted / Dry-run recorded / Telegram API accepted | ไม่ใช้Deliveredคำเดียวและไม่อ้างคนอ่านข้อความแล้ว |

คุณภาพBAD/STALE/ไม่ยืนยันmappingให้NormalizedState=Unknownพร้อมเหตุผล แม้rawเป็น0หรือ1; ค่า0แสดงได้ในRAW ไม่ถูกลบเป็นmissing

Freshnessเริ่มจากนโยบายเดิมage>15sหรือfuture>30s พร้อมทดสอบboundaryและclockskew การปรับthresholdตามSourceต้องขออนุมัตินโยบาย ไม่เปลี่ยนรอบ5sโดยตกแต่งUI

Metricทุกใบระบุหน่วย/เวลา/scope: snapshotsสะสมในชุดฐานข้อมูล, pending eventsปัจจุบัน, ACKeventsตามdestination; แหล่งขาดหายให้แสดง partial known count แทน0รวมทั้งหมด ไม่มีค่า24h/latency/rateเมื่อยังไม่มีdenominator

## 4. Wireframes 7หน้าต่อแนวทาง (14ภาพ)

ดู PDF `AQUA_UIUX_v2.1_G1_WIREFRAMES.pdf` และภาพใน `wireframes/` ทุกภาพมี DESIGN ONLY / SIMULATED EXAMPLE / NOT CONNECTED ชัดเจน IP10.10.20.xเป็นตัวอย่างออกแบบ ไม่ใช่การค้นพบหรือIPหน้างาน ปัจจุบันnativeมี1Agentบนloopback ไม่ใช่3เครื่องในภาพ

Legend: **E** existing field, **D** UI-derived/adapter work, **G** new capability requiring separately approved work. ปุ่มGในภาพคือproposed affordance ต้องdisabled+reasonในimplementationจนมีcontractจริง

### 01 — Operations Overview

- **A:** KPI5ใบพร้อมscope → full-widthpipeline → selectedsignalstable65% +attention/events35% ให้ผู้ใช้เห็นtaskสำคัญก่อน
- **B:** registeredendpointgraph55% +device/permissioninspector45% → pipeline → compactselectedsignals +attention ให้เห็นว่าใครอ่าน/ส่งไปไหนก่อน
- Binding: B01/B10–17/B28–35/B38/B40; ไม่ใช้legacyflow/pressure/temperature/8-pumpqualityheuristic
- Actions: กดpendingไปQueue,กดAgentไปNetworkfocus,กดitemไปMonitoringdetail; startcapture/sendใช้consentเดิม; “พักการแสดงผล”ไม่ส่งrecording=false
- Idle: ยังไม่เริ่ม/รออนุญาต; missingSource: routeไปSources,ไม่มีLABfallback; Gatewaylost: บอกขอบเขตtransferโดยไม่ทำsourceทุกตัวเป็นoffline
- Acceptanceที่วางแผน: Operatorตอบได้ใน10sว่าเก็บอะไร/ค้างตรงไหน/ค่าล่าสุดเมื่อไร; counterและreceiptตรงทุกหน้า

### 02 — Network Topology

- **A:** Devices tableใหญ่ซ้าย,logical-flowmini-map+selecteddeviceขวา; IPทุกแถวcopyได้
- **B:** logicaltopologyกลางใหญ่,deviceinspectorขวาและDevicesTableสลับได้; desktopnodekeyboardfocusตามregisteredorder
- แสดงconfiguredendpointแยกจากobservedNICIP;กรณีไม่มีHostnameแสดงNotreported ไม่มีการใช้PC-01แทนชื่อOS; multi-NICต้องแสดงรายการจริงพร้อมinterfaceถ้ามี
- เส้นทึบมีเฉพาะapplicationrelationshipที่มีfreshsignedobservation;เส้นประคือconfigured/unverified;ไม่วาดphysicalswitch/VLANเป็นfactเมื่อไม่ได้รายงาน
- LANobserverแตกต่าง: Console→Agent,Agent→Gateway,Console→Central;WANดูจากGatewayเอง PC1–3=`NOT_MEASURED`
- Actions: CopyIP/DeviceID,focusSource,openlog;Refreshเฉพาะregisteredstatusในsessionที่อนุญาต ไม่มีsubnetscan/pingall
- Empty/loading/partial/denied/timeout/staleทุกกรณีมีmethodและเวลาหรือNotreported; probe failไม่ใช่poweredoff
- Binding: B01–09/B34/B42; realidentity+topologyยังG

### 03 — SCADA Sources & Read-Only Inventory

- **A:** registrytable65% +capability/sessiondrawer35%;selectedsourcecriteriaอยู่หัวtable
- **B:** device/sourcecontexttree20% +sourcecapabilitymatrix50% +readscope/sessioninspector30%;ย้ำความต่างเครื่องกับconnector
- SourcecardsแยกLAB/CSV/importedmapping/directWinCCunavailable;จำนวนAQUAconfigured/importeligible/browsedscopeแยกกัน ไม่แสดงWinCCtotalหรือOSloginโดยไม่มีAPI
- Wizardที่เสนอ: connector type → approved endpoint/scope → least-privilegereadcapability → explicitone-itemtest → saveAQUAconfigเท่านั้น
- ปัจจุบันSourceEditorเก็บCSV/LABได้ แต่ยังไม่มีregisterconnector,OPCsession,browseหรือtest-readIPC;ในG2ปิดปุ่มเหล่านั้นพร้อมเหตุผล
- Session: ไม่แสดงsecret,บัญชีinteractiveหรือWindowsloginจากAQUAHMAC;Notavailableหากไม่มีSCADAconnector
- Binding: B21–25/B34/B38; denial/expiryต้องมาจากconnectorที่ได้รับอนุญาต ไม่เดาจากconnectionfail

### 04 — Monitored Items / Task Builder

- **A:** configureditemstable60% +Add/Editform40%;inlinevalidationและunsavedchangesbar
- **B:** sourcecontext+3-stepbuilder (Identify → Map/Rule → Review) +selectedreadscopepreview;configchangeimpactแสดงก่อนSave
- Required fields: registeredSourceID,displayName,exactTag/NodeId,type,confirmedvalue↔state,qualityinterpretation,enabled,rule;default5sที่sourceรองรับ
- ManualexactIDเป็นทางแรก;conditionalbrowseต้องexplicitapproval/root/depth/itemlimit/timeout/rate/cancel ไม่มีExportAll
- Optionalone-itemreadทำเฉพาะapprovedconnector;ไม่มีsupportให้Notavailable ไม่แอบinvokeCSVfullcaptureหรือแทนด้วยLAB
- Duplicate(SourceID,ItemID),unsupportedtype,missingquality,denied,clockskew,invalidNodeIDต้องblockpublish;syntheticrulepreviewต้องมีSIMULATEDlabel
- **Backendgap:** ปัจจุบันtagsเป็นlistไม่มีper-itemrules/enable/displayname,CSVrejectsunselectedrows และtagchangesสร้างprofileใหม่+stophost ไม่ใช่hotreload;SavebuttonGจนแก้contractโดยอนุมัติ
- Proposedfutureatomicrevision save ต้องpreservecursor/ACK/backlog+oldrevision;configreloadห้ามสร้างtransition/notificationใหม่เอง
- Binding: B21/B26–27/B37/B44;Actor/revision unavailableไม่ใส่ชื่อผู้ใช้ปลอม

### 05 — Live Monitoring

- **A:** selecteditemtableเต็มพื้นที่,filters+quality/freshnesscounts,inspecteditemdetailด้านล่าง
- **B:** device/sourcecontextstripซ้าย +tableกลาง +timestamp/mapping/receiptinspectorขวา ช่วยสลับแก้ปัญหาหลายเครื่อง
- Columns: DisplayName,SourceID+IP/Notreported,technicalID,raw,normalizedstate,quality,freshness/age,rule/deliveryเมื่อมีหลักฐาน
- อย่าใช้globalpumpsของlegacy ใช้agents[].observations[tag]กับpumps[tag]เท่านั้น Missing/Bad/StaleแยกCause
- LastObserved,ProducerRecorded,StatusReceivedแยกกัน LastGoodและSampleReceivedถ้าไม่มีบอกNotrecorded
- Sort/FilterCriticalBad/Stale/recentchange,keyboardnavigation,copyfullTagID,scrollภายในtableไม่ทับprimaryaction
- Isometricเป็นoptionaltabเฉพาะmappedselectedvalues ไม่มีmappeditem=Unmapped ไม่มีpumpwritebuttonในLive
- Binding: B28–34/B36/B43;rule/statushistoryบางส่วนG

### 06 — Gateway & Delivery Queue

- **A:** metric/pipelineบน → queueeventtable65% +deliveryhealth35%;แยก4stageacceptance
- **B:** stageinspectorเริ่มจากCollect→Local→GatewaydurableACK→CentralACK→Notification,เลือกstageแล้วแสดงpending/failure/evidenceเฉพาะstageนั้น
- GatewayLAN,Gatewayegress,Centralreachability,TelegramAPIต้องเป็นคนละstate;rawstatuscachedไม่คงgreenหลังheartbeatหมดอายุ
- pendingcountคือeventsไม่ใช่files/snapshots;อัตราACK/oldestage/perrecordattemptยังไม่มีcontractจึงNotreported
- สำคัญ: freshreadonlyhandshakeรอGatewayreadyถ้าWANblockedอาจเก็บที่Source;sessionเดิมอาจทำให้ข้อมูลค้างต่างstage ห้ามวาดqueuepathให้สำเร็จจากจำนวนลดอย่างเดียว
- ปุ่มreplay/drop/reset/manualsendไม่เปิดในLive;DemoToolsซ่อนในutilityและต้องอนุมัติเพิ่ม ไม่มีการเปิดNAT/bridge
- Binding: B13–20/B36/B41–42;metadataquery/receiptlookupยังG

### 07 — Alerts & Audit

- **A:** Events/Notifications/Audit tabs +filterbar;eventlistกว้างและdetaildrawer
- **B:** Source/devicecontext +correlatedeventtimeline +receipt/notificationpreviewinspector โดยอ้างeventUUIDจริงเมื่อมี
- แยกSystemEvent,ProcessEvent,DeliveryAttempt,ConfigAuditและแยกlogrowIDจากeventID;ไม่joinโดยใช้เวลาใกล้กัน
- Previewที่เสนอ:site/source/displayname/raw/normalized/quality/observedtime/mode/eventID;no secret
- ปัจจุบันtransitionnotifyมีแล้วแต่userdefinablerule/stale/badalert,filteredexportและauditwho/revยังไม่มี;ปุ่มGต้องdisabledพร้อมเหตุผล
- Dry-runrecordedต่างจากTelegramAPIacceptedและต่างจากhumanread;ambiguousresponseยังretained/retryตามevidence ไม่อ้างexactly-onceTelegram
- Binding: B17/B27/B35–39;logsเป็นboundedrecentactivityไม่ใช่auditครบถ้วน

## 5. Design tokens / type / component contracts (ข้อเสนอเท่านั้น)

| Token | Value / behavior |
| --- | --- |
| Background / panel / raised | #0B1420 / #122234 / #192D42 |
| Border / main text / secondary | #2B4257 / #EEF5FA / #A5B8C8 |
| Accent / success / warning / critical / info | #40C7DB / #43C6A0 / #E7B35D / #EC7481 / #80A9E8 |
| Thai/English | Noto Sans Thai / IBM Plex Sans Thai if already available, system fallback; no dependency change G0/G1 |
| IP/technical identifiers | DejaVu Sans Mono/system monospace or approved bundled mono; fullcopy; tabulardigits |
| Type scale | 12metadata,14body/densetable,16IP/keyvalue,18panelheading,24pageheading |
| Spacing | 4/8/12/16/24/32; 40pxrowstandard,32pxdenseopt-in |
| Controls | Min36px,primary40px,focusoutline2px,48pxdrawerheader;disabledhasreason |
| Radius / effects | panels8px,controls6px,tooltip4px;no decorativeglow/animatedflowbydefault |
| Topology lines | labelledsolid=freshapprovedapplicationlink;dashed=configured/unverified;break=observedunreachable;physicaltopologyexplicitunknown |
| Tables | Stickyheader,visibleIP,unit/scopeinheader,selection/focusdistinct,bounded/virtualizedrowswhenneeded |

No CSS patch is supplied. GTKcolor definitions/components are a proposed G2 implementation task, not web CSS. G1 tokencontrast is calculated separately; actual widgetcontrast/focus and allresolutionacceptance remain G2–G5 tests.

Proposedcomponents:DesktopShell,PermissionStatus,ProvenanceBadge,MetricWithScope,ConfiguredEndpointCard,TopologyCanvas+EquivalentTable,SourceCapabilityPanel,SelectedItemForm,SignalTable,StagePipeline,QueueMetadataTable,EventReceiptInspector. Eachsupportsnever-read/loading/empty/unknown/cached/stale/denied/error states withoutinvented0/green.

## 6. Data Binding Matrix

Full44-row field→exactsource→freshness→fallback→requiredwork matrix: `DATA_BINDING_MATRIX.csv`. Everyconceptinwireframesmustbeclassified E/D/G. Criticalexamples:

| UI | Existing binding | Safe fallback / gap |
| --- | --- | --- |
| DeviceIP | configuredlisten/url from enrollment | Labelconfiguredendpoint;observedNICIP/HostnameNOTREPORTED |
| Sourcevalues | agents[].observations[tag],pumps[tag],observedAt | Unknownwithcause;notlegacyglobalmetrics |
| Local/Gatewayqueues | agents[].pending / gateway.pending | Cached/partialunknown;nodeceptionbyzero |
| Centralaccepted | gateway.upstreamDelivered | RenameDelivered;notTelegram |
| Telegramresult | notificationMode + messages[].mode/message_id | Dry-run/ambiguous/notverified;actualfilemessagespolicyblocked |
| SCADAAuthorization | noexistingconnector | Notsupported;AQUAHMACpeerisnotSCADAlogin |
| TaskRule/configrevision | noexistingper-itemcontract | G,disableduntilexplicitapproval |
| SampleReceived/LastGood | notexposed | Notrecorded;lastSeenmeansstatusreceiveonly |

## 7. End-to-end interaction flows

**Add selected item:** เลือก Source ที่ลงทะเบียน → กรอก exact Tag/NodeId (หรือ bounded browse ที่อนุญาตแล้ว) → ตรวจ type และ scope → ผู้ใช้กดอ่านหนึ่งรายการหาก connector รองรับ → review mapping, quality, rule และภาระรอบ 5s → atomic save พร้อม revision/audit → reload ตามความสามารถที่อนุมัติแล้ว ปัจจุบันยังมีช่องว่างก่อนขั้น Save/Reload ต้องแสดงว่าไม่รองรับ ไม่เรียก Export All หรือ reset คิวเพื่อทำให้ดูเหมือนสำเร็จ

**Check source:** อ่าน capability จาก configuration ที่มีอยู่ก่อนโดยไม่ connect → review endpoint/method/item/timeout/security และขอสิทธิ์ → อ่านเฉพาะเมื่อ connector รองรับและได้รับอนุญาต → แสดง raw value, quality, source timestamp และผลที่ redacted แล้ว WinCC Runtime ที่ไม่มี connector ยังคง Not supported ไม่เปิด OPC UA ให้เอง

**Restart-safe queue:** ปิดแอปอย่างเรียบร้อยโดยรักษา SQLite/cursor → เปิดใหม่อยู่ในสถานะ idle → แสดงเฉพาะ configuration หรือ cached metadata พร้อมเวลา → กดเริ่มและอนุญาตอ่านเอง → resume โปรไฟล์เดิม → อนุญาตส่งแยก → ตรวจ batch/digest ACK การเลือก Tag ชุดใหม่ในปัจจุบันจะสร้างโปรไฟล์แยกและพักคิวเดิม ต้องแจ้งผลกระทบจนมีแผน migration ที่อนุมัติ

**Gateway join/loss:** เริ่มจาก configured link ที่ยังไม่ยืนยัน → ทำ signed handshake ภายใต้สิทธิ์ที่ให้ → ตรวจ peer/readiness → ส่ง backlog → Gateway commit durable แล้ว ACK → mark ACK เฉพาะ event set ที่ถูกต้อง หากล้มเหลวเก็บข้อมูลไว้และ retry แบบ backoff ห้ามอนุมานว่า physical LAN ทั้งวงล่มจากวิธีติดต่อเดียว

**Internet failure:** ใช้ observation ของ Gateway ที่ยังสดและระบุ mode → แสดงเหตุเฉพาะขอบเขต → ข้อมูลอาจค้าง Source หรือ Gateway ตาม readiness/session เดิม → retry ภายในสิทธิ์ที่ยังใช้งานได้ → แสดง Central ACK และ notification receipt แยกกัน PC1–PC3 ยังเป็น NOT_MEASURED หากไม่ได้วัดเอง

**ACK / idempotency:** event_id + digest + source/sequence → Gateway commit ก่อน ACK → หาก ACK หาย resend event ID เดิม → deduplicate ทาง Central และ notification เป็น receipt สองเส้นทางจาก Gateway การรับ Central ไม่ได้เป็นเงื่อนไขยืนยันว่า Telegram ส่งแล้ว และ timeout ของ Telegram อาจมีผลลัพธ์กำกวม ไม่มีคำอ้าง exactly-once กับผู้รับ Telegram

**Display freeze:** หยุดเฉพาะการวาดค่าใหม่ แสดง CACHED กับเวลาที่แช่ไว้ → collector/queue ทำงานต่อภายในสิทธิ์เดิม → resume presentation การกดพักหน้าจอต้องไม่ส่งคำสั่ง recording=false หรือ transfer=false

## 8. Proposed file changes / approval scope / compatibility

รายการนี้เป็นแผน ไม่ใช่ patch ไม่มีไฟล์ด้านล่างถูกแก้ใน G0/G1

| Future gate | Proposed files / responsibility | Impact / boundary |
| --- | --- | --- |
| G2 | desktop/app.py, desktop/style.css, desktop/model.py หรือ presentation.py ใหม่, native view components, desktop/tests | M: shell 7 หน้า, tokens, permission bar, provenance adapter และ existing-field bindings เท่านั้น ไม่มี engine/network/schema changes |
| G2 tests | ui_test.py เดิม และ focused presentation/visual checks | รักษา manual start, cancel, revoke, scoped remember, quality และ clock handling; ต้องตรวจหน้าต่างจริงหลังพัฒนา |
| G3 | เสนอ desktop/views/overview.py, topology.py, sources.py และ capability presentation model | M–L: แสดง configured graph และ existing status; real identity กับ observe-only mode ต้องอนุมัติ backend scope แยก |
| G4 | เสนอ desktop/views/items.py, monitoring.py พร้อม selected-config/rule contract | L: versioned config มีความเสี่ยงต่อ cursor/ACK และ source identity ต้องอนุมัติก่อนแก้ backend |
| G5 | เสนอ desktop/views/delivery.py, audit.py พร้อม operator guide/acceptance | M–L: queue/receipt/audit queries ขึ้นกับ contract ที่อนุมัติ; rebuild RPM เมื่ออนุมัติเท่านั้น |
| Separate backend gaps | safe registry/identity, observe-only session, source capability, selected-item/rule storage, bounded queue/receipt lookup, audit schema | ไม่รวมใน G2 โดยอัตโนมัติ ไม่อ้างว่า endpoint ใหม่มีอยู่แล้ว |
| Out of scope | PLC/WinCC/OPC server settings, network/firewall/NAT, root web/PWA application | ไม่เปลี่ยนโดยไม่มีการอนุมัติเฉพาะระบบนั้น |

Effort เป็นขนาดงานสัมพัทธ์: S = presentation เฉพาะจุด, M = หลาย native views/adapters, L = state/config/transport contract ไม่ใช่กำหนดส่งแบบรับประกัน ระยะเวลาขึ้นกับ scope ที่อนุมัติและการเข้าถึง LAB

**Compatibility:** รักษา runtime.v2 payload/digest, CSV cursor, source identity, queue ownership, role HMAC, 5s capture, capture/transfer consent, GTK desktop/RPM และ isometric assets เดิม เพิ่ม presentation ก่อน ไม่ migrate DB หรือเปลี่ยน dependency ใน G2 ไม่ใช้ global legacy aggregates เป็น operational truth

**Rollback:** G0/G1 ไม่ต้อง rollback ซอฟต์แวร์เพราะ Repo ไม่เปลี่ยน หากพัฒนา G2 ในภายหลังให้ revert เฉพาะ approved UI commit และคืน UI assets เดิม ห้ามลบ/reset SQLite, cursor, ACK หรือ source input การ migration configuration ต้องมีแผน version/backup/reversal แยก ไม่รวมอยู่ในการอนุมัติครั้งนี้

## 9. Test plan / acceptance gates

| Test / AC | Planned test | Expected evidence / current status |
| --- | --- | --- |
| T01 / AC01 | Native widgets ที่ 1366×768 / 1440×900 / 1600×900 / 1920×1080 รวม font scale 100% และ125% | ไม่ล้น/ทับ, IP ไม่อยู่เฉพาะ tooltip, keyboard/scroll ทำงาน; ภาพ G1 ไม่ใช่ implementation PASS |
| T02 / AC02–03 | Registered 0/1/3 sources, missing hostname, multi-NIC, DHCP/identity change | Agent ID คงตัว ไม่ปลอม fields; observed identity ยัง BLOCKED ตาม backend |
| T03 / AC03 | LAN up/WAN down, LAN down/WAN up, Gateway lost, Central fail, auth denied, stale heartbeat | แยก observer/method/time และไม่ถ่ายทอด Internet ของ Gateway ไป Agent |
| T04 / AC04 | Add/Edit/Disable exact item โดยไม่ Export All / full browse | Request trace ตรง scope รวม CSV superset selection; BLOCKED จนมี contract |
| T05 / AC05/09 | Unsupported connector, denied/expired read, wrong type, missing quality, invalid NodeId | Cause เฉพาะ ไม่มี background probe, fallback หรือ write; real connector tests BLOCKED |
| T06 / AC06 | Capture 5s เมื่อ Gateway/WAN หาย และเมื่อ storage quota เต็ม | Timestamps + durable records + restart cursor; G0 มีเพียง historical baseline |
| T07 / AC07 | Gateway join/loss, ACK loss ก่อน/หลัง commit, restart source/Gateway | event ID/digest เดิม, exact ACK set, ไม่ลบก่อน ACK; cross-host ต้องอนุมัติ LAB แยก |
| T08 / AC08 | Snapshot ค่าเดิม, GOOD→BAD→GOOD, GOOD→STALE, เปลี่ยน mapping | ไม่ปลอม OFF/recovery transition, ไม่แจ้งเตือนซ้ำทุก5s; new-rule tests BLOCKED |
| T09 / AC09/11 | Startup/cancel, remember scope, new endpoint/tags, revoke ระหว่าง request, crash/restart | ไม่มี auto-start/คำขอใหม่หลัง revoke และไม่รั่ว secret; รักษา consent regressions |
| T10 / AC10 | Source fail, display pause/resume, never-read, future clock, mixed freshness | Provenance ชัด, ค่าเก่าไม่เป็น LIVE; status.time ไม่เปลี่ยนอายุ sample |
| T11 / AC07/10 | Gateway ACK / Central ACK / dry-run / Telegram API accepted | ระบุ destination/mode, ambiguous ไม่เป็น success, ไม่อ้าง human read receipt |
| T12 / AC12 | Existing backend50 + Python7 + native consent tests หลัง approved change | ผลรันใหม่ใน temporary LAB ที่อนุมัติ; G0 ไม่รัน functional suite ใหม่ |
| T13 / AC12 | Save config ขณะค้างส่ง, rollback, no event on reload, stop/crash race | ไม่มี ACK/cursor reset, คิวเก่ายังเข้าถึงได้; hot reload BLOCKED จนอนุมัติ contract |
| T14 / AC11–13 | Audit filter/export redaction, Thai/English/IP readability, copy Tag, unknown actor | รายงาน bounded พร้อม timezone/ID ที่ถูกชนิด; audit ใหม่ยัง BLOCKED |
| T15 / AC13 | Operator walkthrough 3–5นาที และ 10-second comprehension test | ผู้ใช้บอกเครื่อง/IP/สิ่งที่อ่าน/จุดค้างได้ถูกต้องพร้อมข้อจำกัด ไม่ใช่ production certification |

G0 safe checks: JavaScript syntax27/27, Python AST7/7, desktop entry PASS โดยไม่รัน module หรือ service ใหม่ Functional tests = SKIP ในรอบนี้ Historical v0.7 backend50, Python7 และ native installed-payload flow เคยผ่าน แต่ไม่ใช้แทนผลใหม่หรือ claim WinCC/real LAN

### Operator walkthrough หลัง implementation ที่อนุมัติแล้ว (3–5นาที)

- 0:00 เลือก LAB อย่างชัดเจน และอนุญาตอ่าน
- 0:40 เห็น selected values กับรอบ5s และ source timestamp
- 1:20 ดู Network/IP ที่ติด fixture พร้อมแยก LAN/WAN
- 2:00 ดูคิวค้างและความหมาย Gateway/Central/Telegram
- 3:00 เลือก item เฉพาะ workflow ที่ backend รองรับแล้วเท่านั้น
- 4:00 ตรวจ receipt/audit/ข้อจำกัด แล้วถอนสิทธิ์

Simulation controls หรือ item actions ที่ยังไม่รองรับไม่ถูกนำไปสาธิตว่าเป็น working software

## 10. Approval requested / stop condition

เสนอให้เลือก **Option B และอนุมัติเฉพาะ G2 — UI Foundations & Presentation Binding** คง native GTK และ permission เดิม ไม่รวม backend/API/DB/connector/network changes ส่วน G3–G5 กับ Backend Gaps ต้องอนุมัติแยกตามหลักฐานหลัง G2 และ WinCC Runtime จริงต้องมี approved scope, endpoint, method, credential policy และช่วงเวลา LAB ก่อน

หากเลือก A ให้ใช้ bindings/permission/semantics เดียวกัน แต่ให้ตาราง operations เป็นหน้าแรก ความสามารถของ backend ไม่เปลี่ยนตาม layout

**หยุดที่ G1 แล้ว ยังไม่เริ่ม G2 ไม่แก้ Source ไม่ commit/push และไม่ build installer ในรอบนี้**

APPROVAL REQUIRED — NO SOURCE MODIFICATION PERFORMED
