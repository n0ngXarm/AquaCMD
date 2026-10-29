# AQUA COMMAND0.9 — Actual-use implementation report

วันที่ส่งมอบตามเวลาผู้ใช้:29ตุลาคม2026

**สร้างตัวอ่านจริงและตัวรับจริงแล้ว โดยไม่ใช้simulatorในเส้นทางใช้งานปกติ** Windows/WinCC/สองเครื่องLAN/Telegramจริงยังไม่ผ่านstationacceptance เพราะOPC DAของหน้างานยังไม่ได้รับอนุญาตให้เปิดใช้งานทางการ ไม่มีการเปิดบริการหรือเชื่อมProductionในการพัฒนานี้

## ผลตามStageของincrementข้อมูลจริง

ตารางนี้เป็นขั้นตอนimplementationรอบข้อมูลจริงหลังG2 ไม่ได้อ้างว่าrequirementsUI/UXv2.1ที่ยังไม่มีBackendรองรับผ่านทั้งหมด

| Stage | ผลจริง | Evidence / ความเสี่ยง / Rollback |
| --- | --- | --- |
| G0 Audit |PASS | ตรวจsourceที่d838bfd,แยกWinCCRuntime/Tagconfiguration,พบnativehostเป็นloopbackLAB,ตรวจOPCDAตามเอกสารSiemens;ไม่แตะหน้างาน |
| G1 Actual-read design |PASS | WindowslocalOPCDA3Read-only+ownedspool,explicitTLSGateway,permissionแยก;การactivateCOMต้องได้รับอนุญาตก่อน |
| G2 Implementation |PASSด้านsource/build | ตัวอ่านWindowsจริง,5s,quality/time,v3queue/ACK,retry;LinuxactualAgent/Gateway ไม่มีautomaticLABfallback;Windowsruntimeยังต้องตรวจรับ |
| G3 Integration |PASSในLinux/localTLS | Backend57/57,Python30/30,Core47assertions;C#↔NodeHTTPSจริง+HMAC+digestACKสองกรณี;ข้อมูลทดสอบอยู่เฉพาะtests ไม่ใช่ค่าจากWinCC |
| G4 Native/package |PASSภายในขอบเขต | WindowsPE64GUIself-containedbuild,actualRPMlauncher/modules,56GTKlayoutcombinations;ไม่อ้างDNFsystemtransactionหรือWindowsGUI/COMexecution |
| G5 Review/delivery |PASSด้านreview/artifacts | Reviewไม่พบsignificantbugค้าง แก้sequence/config,timeout/retry,largebatch,CApin,numerickeycanonicalization,ownedexport;รักษาคิวเมื่อrollback |
| Authorized station acceptance |PENDING | ต้องได้รับอนุญาตOPC DAและทดสอบWindows/WinCC/two-hostLANจริงก่อนproductionrollout |

## Changed Files

- Windowsใหม่ในrepositoryเดิม:`windows-reader/Core/{Model,Spool,Sender}.cs`,`windows-reader/Windows/{Program,LocalOpcReader,WorkerSession}.cs`,projectfiles,TestsและREADME ไม่มีsimulatorในWindowsproductionproject
- Linuxnative:`desktop/app.py`,`console.py`,`presentation.py`,ใหม่`production.py`,`actual_editor.py`,`deployed-host.mjs`,hostdispatchและnative/puretests
- Reuseengine:`backend/src/lan/{csv-source,protocol,services,store,telegram}.js`;เพิ่มdeployedregressionsและtest-onlyTLShelper
- Build/delivery:`packaging/build-windows.sh`,RPMspec/buildversion0.9,releases/checksums/runtime notices
- Docs:`AGENTS.md`,`PLAN.md`,`README.md`,`VERIFICATION.md`,`docs/REAL_USE_DESIGN.md`,`docs/COMMISSIONING.md`;rootREADMEอัปเดตentrypointสองplatformเท่านั้น

การอนุญาตล่าสุดให้พัฒนาข้อมูลจริงขยายscopeจากG2เดิม จึงมีการเปลี่ยนengine/IPCอย่างตั้งใจ ไม่อ้างprotected38filesของG2ว่ายังไม่เปลี่ยน ไม่แก้sourceweb/PWAหรือProductionservicesเดิม ไม่ใส่SCADAตัวอย่าง/Tagหน้างาน/credentialsจริงในpublicrepository

## Architectureและพฤติกรรมจริง

WindowsReader.exe → localOPCServer.WinCC(IOPCItemIO.Readเท่านั้น) → atomicAQUAspool → HTTPS/HMACGateway → durableSQLitearchive → separatelyapprovedTelegram

- เปิดโปรแกรมidle ไม่อ่าน/activateCOM/สร้างคิว/probe/sendเอง ไม่จำpermissionเพื่อautorunครั้งถัดไป
- Readinessอ่านregistrationอย่างเดียว;CLSIDFromProgIDที่อาจเขียนregistryไม่ถูกใช้ LocalCOMactivationอาจเริ่มserverที่ติดตั้งไว้ จึงอยู่หลังยืนยันสิทธิ์หน่วยงานและmanualcaptureconsent
- เลือกexactbinaryTagเอง1–100รายการ อ่านcacheทุก5s ไม่บังคับdevicepollด้วยmaxAge0 งานช้าจะข้ามtickที่พลาด ไม่ยิงชดเชยถี่ WorkerSTAแยกprocessมี8sdeadlineและหยุดเฉพาะchildของAQUA
- OPCGOODใช้mask0xC0=192 เก็บrawqualityword/HRESULT/sourceFILETIMEแยกreadtimeและreceiverreceipt BAD/UNCERTAIN/unsupported/unconfirmedไม่สร้างOFF ตัวอ่านนี้ไม่ใช่analogcollector
- StableSourceIDเก็บsequenceต่อเนื่องแม้เปลี่ยนTags/mapping โพรไฟล์captureเปลี่ยนแล้วตัดtransitioncontinuityอย่างatomic แต่pendingเก่ายังเหมือนเดิม
- Gatewayรู้เฉพาะสมาชิกที่ลงทะเบียน รับเฉพาะactualpayload ไม่สแกนLAN ไม่เปิดremoteDCOM ไม่ส่งremoteadmincommand ไม่แก้NAT/bridge/firewall/Internetsharing
- Receiverpermissionและoutboundpermissionแยกกัน Gatewayรับเก็บofflineได้หลังอนุญาตรับ และจะไม่probeTelegramจนอนุญาตส่ง
- Request/responseมีHMAC,nonce/timestampและbodydigest TLSตรวจCA/IPname ไม่มีvalidationbypass/redirect/proxy WindowsปิดAIA/certificateautodownloadเพื่อไม่ออกURLนอกpeerที่เลือก
- Retryส่งimmutableUUID/sequence/payloadเดิม GatewayACKหลังcommit;wrongACK/lostACK/duplicateไม่ลบข้อมูลที่ยังไม่ยืนยัน Telegramresponseกำกวมอาจทำให้ข้อความซ้ำ จึงไม่อ้างexactly-onceภายนอก

## Test Results / Evidence

| การทดสอบ | ผล | ไฟล์ในevidence |
| --- | --- | --- |
| Nodebackendregression |57passed,0failed,0skipped |backend-tests-actual-final.txt |
| Newdeployedregressions |7passed |deployed-test.txt |
| Pythondesktop |30passed |python-tests-final.txt |
| WindowsCoreonLinux |47assertionspassed |windows-core-final-tests.txt |
| ActualTLSinteropordinary/numericTags |ทั้งคู่PASS,แต่ละรอบ3events/2snapshots/ไม่มีegress |cross-language-interop.json |
| NormalnativeworkflowwithRPMmodules |PASSidle,noLAB,cancel,receive/sendแยก,quality/time/export,relaunchidle |native-actual.log |
| Legacyconsent/freeze/regression |PASSโดยexplicitdeveloperflag/testfixturesเท่านั้น |native-final.log |
| ActualGatewayGTKlayouts |56combinations:7pages×4sizes×100/125%text |actual-layout-results.json |
| Actualgeometry/fontgrowth |1366×768,1440×900,1600×900,1920×1080;title33→41px |rpm-audit.json/layoutresults |
| RPMaudit |25installedcode/datafilesตรงsource,ไม่มีscriptlets/webUI/tests/keys/DBpayload |rpm-audit.json/rpm-payload.txt |
| Windowspublish |PE32+x64GUI,singlefile,self-contained,cleanbuild |windows-publish.txt/windows-source-hashes.json |
| Independentreview |ไม่พบsignificantimplementationbugค้าง |review.md |

เครื่องมือทดสอบใช้nativeGTK/privateheadlessWaylandและlocalTLSsocketจริงพร้อมtestpayload ข้อมูลทดสอบไม่ถูกนำมาแทนค่าจริงในโปรแกรม productionไม่มีmocksource การtestCoreบนLinuxไม่พิสูจน์WinCCCOMinterop ผู้ใช้ยังต้องตรวจรับจริงตามCOMMISSIONING.md

## Risksและขอบเขตที่ยังไม่รับรอง

1. OPC DAหน้างานยังไม่เปิดใช้งานทางการ ต้องได้รับอนุญาตก่อน ตัวโปรแกรมไม่ทำให้เอง ยังไม่ทดสอบregistration/architecture/marshalling/permissions/loadบนWindowsWinCCจริง
2. WindowsGUI/display/accessibility,LANข้ามเครื่องจริงและTelegramจริงยังไม่ตรวจรับ การcross-buildEXEไม่เท่ากับทดสอบติดตั้งWindows
3. Windowspending10,000events/64MiB หลังACKนำpayloadออกจากpending เก็บsequence/counts/latest;CSVexportเป็นpendingเท่านั้น Gatewayarchive50,000records/DB64MiB ไม่มีunlimitedhistorianหรือautomaticretention เมื่อเต็มจะหยุด/ปฏิเสธรับเพื่อรักษาข้อมูล ต้องตกลงarchivepolicyก่อนใช้งานระยะยาว
4. โปรแกรมรองรับbinaryselectedTagsตามallowlistformat ไม่รองรับUnicode/arbitraryanalogtags,OPCbrowseทั้งหมด,per-itemrule/hotreload/fullauditในรุ่นนี้ ค่าที่ไม่รองรับเป็นUNKNOWN
5. SourceIDต้องไม่ซ้ำต่อGatewayและต้องรักษาข้อมูลstreamเดิมไว้ ห้ามลบspoolเพื่อresetsequenceหรือย้ายคีย์เดียวกันไปหลายเครื่อง
6. EXE/RPMยังunsigned ไม่มีบริการautostartหรือDNFsysteminstallationในเครื่องพัฒนา Physicalpowerloss/hardwarediskcacheไม่ผ่านการรับรองจากtestrestart

## Rollback

หยุดอ่าน/ส่ง ปิดAQUA เก็บWindowsLocalAppDataและLinuxactual-profiles/SQLite/คิว/ACK/sequenceไว้ทั้งหมด ถอนหรือแทนที่ไฟล์โปรแกรมได้โดยไม่ลบข้อมูล รุ่น0.8ไม่รองรับactualprofile/v3นี้ ห้ามชี้รุ่นเก่าเข้าคิว0.9หรือresetฐานข้อมูลเพื่อให้ทำงานต่อ ใช้รุ่นที่รองรับกู้/ส่งpendingเดิม ไม่มีการเปลี่ยนWinCC/PLC/networkที่ต้องย้อนกลับ

## เริ่มใช้

ดูCOMMISSIONING.mdและWINDOWS_READER_GUIDE.md เปิดEXEบนเครื่องWinCCหลังอนุญาต ส่วนRPMใช้เป็นGateway ตั้งค่าIP/TLS/memberkeysด้วยตนเอง บันทึกไม่เริ่มงาน แล้วกดอนุญาตรับ/อ่านและส่งแยกกัน เก็บwindows-runtime-noticesไว้ข้างEXEที่แจกจ่าย

## Git publication

Localcommit:`29876277ae0599955c43f63fdec3cb87b3be4e4f` บนสาขา`codex/aqua-native-desktop-rpm` workingtreeสะอาด

Pushไปorigin`n0ngXarm/waterlevels`ยังไม่สำเร็จ/ไม่ยืนยัน เนื่องจากDNSตอบว่าCouldnotresolvehost:github.com ไม่ได้แก้DNS/networkconfiguration ตัวโปรแกรมและsourcecommitทั้งสองยังเก็บครบในเครื่อง หลักฐานในevidence/git-publication.json
