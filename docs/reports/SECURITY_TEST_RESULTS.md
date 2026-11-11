# Security verification

Final focused command runs inside a temporary HOME and loopback-only network namespace.

```sh
python3 -B -m unittest test_credential_permissions test_opcua_security_gate test_task_alert_atomicity test_notification_delivery -v
```

Working directory is `aqua-command-desktop/desktop/tests`, with desktop, application root and isolated Python dependencies on PYTHONPATH. Result is exit 0, 27 tests, all passed, zero skipped. This suite combines credential/PKI tests with local atomicity and delivery recovery.

The recorded source contract suite also exercised HTTPS CA trust, OPC UA secure-channel trust, SQL parameter binding and read-only API behavior. Web tests cover authorization and held-delivery controls. Compose configuration was parsed with synthetic environment inputs and verified to publish host loopback only.

The final extracted RPM scan returned zero pattern matches across 99 files and compared 457 private catalog names without printing them. It checks selected credential formats and private extensions. Source/history clearance, credential rotation and the Windows binary remain separate verification gaps.

Raw logs are `outputs/aqua-roadmap-phase6-privacy/final4-security-reliability.txt`, `final4-payload-privacy.txt`, `contracts.txt`, `web-tests.txt` and `outputs/aqua-roadmap-phase5-release/compose-loopback.txt`.
