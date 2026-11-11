<!-- Phase 7 public copy: historical private values redacted. Original evidence remains privately preserved. This is not a rerun or acceptance upgrade. -->
# AQUACMD — PHASE 1A FINAL CLOSURE & PHASE 1B DISCOVERY REPORT

**Repository:** `https://github.com/n0ngXarm/AquaCMD`
**Working Branch:** `fix/phase-1a-security-hardening`
**Target Baseline Commit (main):** `74027e22426f021a975b7e0d3beaf591234612d8`
**Previous Verified Remote HEAD:** `024391f409bedc0fc2bcc1d683bed85c16249d9f`
**Phase 1A Final Closure Commits:**
1. `5204811237b914b5cde70e56ac3ecfbb4730dfd5`: `fix(queue): support legacy alert schemas, enforce capacity backpressure and prioritize immutable payload (DATA-02)`
2. `aa4e21b6392366a123fcea1a59cb61f9b8501d2d`: `fix(security): distinguish pre-commit from post-commit errors and prevent automated retries (SEC-02)`
3. `70a3bf6c6bb815b2d943b7a549b286dd257b6599`: `fix(notification): prevent constructor overrides from bypassing deployment authorization in production (REL-02)`

---

## 1. Audit Evidence & Traceability

In response to the Phase 1A Final Closure review directive, all audit evidence and diffs in this report are derived directly from Git:
- Source code in `aqua-command/server.mjs` is verified as **Native Node.js HTTP** (`http.createServer`, `reply(res, code, payload)` calling `res.writeHead()` / `res.end()`), and not Express.
- All diffs shown in Section 5 are genuine outputs from `git diff origin/fix/phase-1a-security-hardening..HEAD` with zero synthetic or mock formatting.
- Test counts between local execution and GitHub reports are verified and synchronized.

---

## 2. Technical Remediation Details

### A. DATA-02 — Queue/Alert Referential Integrity & Legacy Schema Support

#### 1. Dual-Schema Compatibility for Legacy Alerts
Previous alerts stored without `acknowledgedAt` or `resolvedAt` timestamps are now comprehensively supported:
- **`isAlertAcknowledged(alert)`**: Recognizes `alert.acknowledgedAt`, `alert.acknowledged === true`, `alert.ack === true`, `alert.status === 'acknowledged'`, and `alert.acknowledged_at`.
- **`isAlertResolved(alert)`**: Recognizes `alert.resolvedAt`, `alert.resolved === true`, `alert.severity === 'resolved'`, `alert.status === 'resolved'`, `alert.resolved_at`, and `alert.supersededAt`.
- **Automatic Migration on Load (`migrateLoadedAlert`)**: When reading persisted state, legacy alerts are normalized without altering data, ensuring missing timestamps are safely populated and both boolean (`acknowledged`) and timestamp (`acknowledgedAt`) fields coexist.

#### 2. Capacity Limits & Backpressure
- **External Ingest (`POST /api/incidents`)**: When the alert store reaches `MAX_ALERT_STORE` (400) and unacknowledged alerts cannot be safely pruned, the server responds with HTTP **`503 Service Unavailable`** with `{ error: 'Alert store capacity limit reached: active alerts require acknowledgement', retryAfterSeconds: 30 }`.
- **Internal Alert Generation (`createAlert`)**: When capacity is saturated with active alerts requiring operator acknowledgement, internal alert generation gracefully logs a backpressure warning and throttles addition, preventing unbounded growth while preserving state integrity.
- **Queue Pruning Protection**: `trimQueue()` strictly protects active retrying jobs (`j.status === 'failed' && j.attempt < 6`) in addition to `pending` and `blocked_by_policy` jobs.

#### 3. Immutable Job Payload as Primary Delivery Source
In `processQueue()`:
```javascript
const messageText = job.payload?.text || (alert ? alertMessage(alert) : 'AQUA COMMAND Alert');
const isDemo = job.payload ? Boolean(job.payload.demo) : (alert ? Boolean(alert.demo) : Boolean(DEMO));
```
Prioritizing `job.payload.text` ensures that even if an alert is mutated or detached later, the original queued alert notification is delivered with full textual fidelity.

#### 4. Automated Tests (`aqua-command/tests/queue-integrity.test.mjs`)
Expanded suite from 9 to 12 tests:
- `DATA-02: Legacy alert schema migration, ACK evidence, and schema resilience`: Verifies loading legacy alerts lacking timestamps, payload enrichment for legacy jobs, and dual ACK tracking.
- `DATA-02: Boundary and backpressure on saturated capacity for external ingest and internal rules`: Tests 503 backpressure when saturated at 400 alerts, graceful internal throttling, and capacity restoration upon operator ACK.
- `DATA-02: Immutable job payload primary delivery and retry state retention`: Tests primary delivery from immutable payload and retry state preservation.

---

### B. SEC-02 — Explicit Post-Commit Outcomes & Failure Handling

#### 1. Structured Exception Hierarchy (`desktop/app.py`)
```python
class AtomicSaveError(OSError):
    """Base error for atomic configuration save failures."""
    def __init__(self, message: str, committed: bool = False):
        super().__init__(message)
        self.committed = committed

class PreCommitSaveError(AtomicSaveError):
    """Raised when save fails before atomic replace. Original configuration is untouched."""
    def __init__(self, message: str):
        super().__init__(message, committed=False)

class PreCommitPermissionError(PreCommitSaveError, PermissionError):
    """Raised when permission checks fail before commit. Original configuration is untouched."""
    pass

class PostCommitDurabilityError(AtomicSaveError):
    """Raised when atomic replace succeeded but post-commit durability or mode sync failed.
    The new configuration file is retained on disk (not destroyed/unlinked).
    Automatic retry must NOT be attempted without manual reconciliation.
    """
    def __init__(self, message: str):
        super().__init__(message, committed=True)
```

#### 2. Distinct Pre-Commit vs Post-Commit Semantics
- **Pre-Commit Failure (`committed = False`)**: If temporary file creation, mode check, or data serialization fails, the temporary file is unlinked and the original configuration file remains 100% intact. Callers can safely retry or alert the operator.
- **Post-Commit Failure (`committed = True`)**: Once `temp_p.replace(p)` completes, the commit point has passed. If parent directory `os.fsync(dir_fd)` fails or post-replace permission verification fails:
  - The configuration file is **NEVER deleted, unlinked, or destroyed**.
  - A `PostCommitDurabilityError` is raised with `e.committed == True`.
  - **No automated blind retry** is attempted, avoiding accidental overwrite or state corruption.

#### 3. Test Coverage (`desktop/tests/test_credential_permissions.py`)
- Suite expanded to 11 tests, including `test_post_commit_error_distinction_and_retry_prevention`, asserting that post-commit fsync failure preserves new data, flags `committed=True`, and prevents automated retry.

---

### C. REL-02 — Authorization Containment & Production Policy Enforcement

#### 1. Containment of Constructor Overrides (`src/telegram_notifier.py`, `src/telegram_bot.py`)
In `TelegramNotifier.is_delivery_authorized`:
```python
env = getattr(Config, "APP_ENV", "").strip().lower()
if env != "production":
    return False
deployment_authorized = bool(getattr(Config, "TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED", False))
if not deployment_authorized:
    return False
if self._delivery_authorized is False:
    return False
return True
```
In `TelegramBot.is_polling_authorized`:
```python
env = getattr(Config, "APP_ENV", "").strip().lower()
if env != "production":
    return False
deployment_authorized = bool(getattr(Config, "TELEGRAM_INBOUND_POLLING_AUTHORIZED", False))
if not deployment_authorized:
    return False
if self._polling_authorized is False:
    return False
return True
```
- **Rule Enforced:** A constructor override (`delivery_authorized=True` or `polling_authorized=True`) **cannot** bypass the deployment authorization policy (`Config.TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED` or `Config.TELEGRAM_INBOUND_POLLING_AUTHORIZED`).
- Constructor flags can only act as a **restrictive** safeguard (`False`), never to inadvertently grant egress/ingress.
- Non-production environments remain strictly zero-egress.

#### 2. Test Coverage (`tests/test_water_system.py`)
Suite expanded to 14 tests, including `test_production_constructor_override_cannot_bypass_deployment_policy`.

---

## 3. Phase 1B — RPM Packaging Discovery (Read-Only)

As approved under Phase 1B Discovery (Read-Only), an inventory, dependency closure, package availability audit, and build plan have been prepared. **No RPM specs have been modified and no releases have been built in this phase.**

### A. Target Environment
- **Host Platform:** Fedora Linux 44 (Workstation Edition), Kernel x86_64
- **Packaging Target:** `aqua-command-desktop-0.9.0-1.fc44.noarch.rpm`
- **Spec Location:** [`aqua-command-desktop/packaging/aqua-command-desktop.spec`](file://[REDACTED_HOME]/Documents/Work_SHCOOL/project_water/AquaCMD/aqua-command-desktop/packaging/aqua-command-desktop.spec)
- **Build Script:** [`aqua-command-desktop/packaging/build-rpm.sh`](file://[REDACTED_HOME]/Documents/Work_SHCOOL/project_water/AquaCMD/aqua-command-desktop/packaging/build-rpm.sh)

### B. Dependency Closure & Host Package Availability

| Spec Requirement | Host Package Installed | Status |
| :--- | :--- | :---: |
| `python3 >= 3.11` | `python3-3.14.8-1.fc44.x86_64` | **Available** |
| `python3-gobject >= 3.42` | `python3-gobject-3.56.3-1.fc44.x86_64` | **Available** |
| `gtk4 >= 4.10` | `gtk4-4.22.5-2.fc44.x86_64` | **Available** |
| `nodejs22-bin >= 22.13` | `nodejs22-bin-22.23.1-2.fc44.noarch` | **Available** |
| `hicolor-icon-theme` | `hicolor-icon-theme-0.18-3.fc44.noarch` | **Available** |
| `rpm-build` (toolchain) | `rpm-build-6.0.2-1.fc44.x86_64` | **Available** |

All 6 required build and runtime dependencies are verified as installed and available on Fedora 44.

### C. Packaging Inventory
- **Binary Wrapper:** `packaging/aqua-command` (mode 755 -> `/usr/bin/aqua-command`)
- **Desktop Entry:** `packaging/org.aquacommand.Desktop.desktop` (mode 644 -> `/usr/share/applications/`)
- **Application Icon:** `packaging/icons/org.aquacommand.Desktop.svg` (mode 644 -> `/usr/share/icons/hicolor/scalable/apps/`)
- **Desktop Frontend:** `desktop/app.py`, `console.py`, `presentation.py`, `actual_editor.py`, `production.py`, `client.py`, `consent.py`, `model.py`, `host.mjs`, `deployed-host.mjs`, `style.css` (mode 644 -> `/usr/share/aqua-command-desktop/desktop/`)
- **Backend Service:** `backend/bin/aqua-service.js`, `backend/package.json`, `backend/src/lan` (mode 644 -> `/usr/share/aqua-command-desktop/backend/`)
- **Documentation & License:** `LICENSE`, `README.md`, `VERIFICATION.md`, `docs/`

### D. Phase 1B Build Plan (Staged for Implementation Gate)
1. **Source Tarball Staging:** Construct `aqua-command-desktop-0.9.0.tar.gz` excluding git history, pycache, local databases, and temporary artifacts.
2. **Deterministic Build:** Execute `rpmbuild -bb` under isolated `_topdir`.
3. **Validation Gates:**
   - Run `rpmlint` for compliance with Fedora Packaging Guidelines.
   - Run `rpm -qp --requires` and `rpm -qlp` to audit file list and scriptlets.
   - Run dry-run installation via `rpm -ivh --test`.

---

## 4. Test Verification & Regression Summary

| Test Suite | Tests Run | Passed | Baseline Failures | New Regressions | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **aqua-command (Node.js)** | 12 | 12 | 0 | 0 | **100% PASS** |
| **Root Tests (`tests/test_water_system.py`)** | 14 | 14 | 0 | 0 | **100% PASS** |
| **Desktop Security (`test_credential_permissions.py`)** | 11 | 11 | 0 | 0 | **100% PASS** |
| **Desktop Integration (`test_f*.py`)** | 158 | 138 | 20 (Baseline UI) | 0 | **0 Regressions** |
| **Desktop Total Suite (`desktop/tests/test_*.py`)** | 303 | 281 | 22 (Baseline UI) | 0 | **0 Regressions** |

> **Accounting of Baseline Failures:** All 22 GUI test failures across the 303 desktop tests are identical to the baseline observed at initial commit `74027e2` (caused by localized Thai UI strings and fixed canvas geometry expectations). Exactly **0 new regressions** were introduced.

---

## 5. Genuine Git Diff (`024391f..HEAD`)

```diff
diff --git a/aqua-command-desktop/desktop/app.py b/aqua-command-desktop/desktop/app.py
index 7334c8f..f80475f 100644
--- a/aqua-command-desktop/desktop/app.py
+++ b/aqua-command-desktop/desktop/app.py
@@ -172,6 +172,29 @@ TOPOLOGY_CONFIG_FILE = CONFIG_DIR / 'network_topology.json'
 TELEGRAM_CONFIG_FILE = CONFIG_DIR / 'telegram_config.json'
 OPCUA_CONFIG_FILE = CONFIG_DIR / 'opcua_config.json'

+class AtomicSaveError(OSError):
+    """Base error for atomic configuration save failures."""
+    def __init__(self, message: str, committed: bool = False):
+        super().__init__(message)
+        self.committed = committed
+
+class PreCommitSaveError(AtomicSaveError):
+    """Raised when save fails before atomic replace. Original configuration is untouched."""
+    def __init__(self, message: str):
+        super().__init__(message, committed=False)
+
+class PreCommitPermissionError(PreCommitSaveError, PermissionError):
+    """Raised when permission checks fail before commit. Original configuration is untouched."""
+    pass
+
+class PostCommitDurabilityError(AtomicSaveError):
+    """Raised when atomic replace succeeded but post-commit durability or mode sync failed.
+    The new configuration file is retained on disk (not destroyed/unlinked).
+    Automatic retry must NOT be attempted without manual reconciliation.
+    """
+    def __init__(self, message: str):
+        super().__init__(message, committed=True)
+
 def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
     """
     Durable, secure atomic file save adhering to SEC-02:
@@ -205,7 +228,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
         # Check directory ownership (must match current user UID)
         dir_stat = parent_dir.stat()
         if dir_stat.st_uid != os.getuid():
-            err = PermissionError(
+            err = PreCommitPermissionError(
                 f"SEC-02: Directory {parent_dir} ownership mismatch: UID {dir_stat.st_uid} != current UID {os.getuid()}"
             )
             if raise_on_error:
@@ -217,7 +240,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
         if parent_dir.is_symlink():
             resolved = parent_dir.resolve()
             if resolved.stat().st_uid != os.getuid():
-                err = PermissionError(
+                err = PreCommitPermissionError(
                     f"SEC-02: Directory symlink {parent_dir} points to unowned target {resolved}"
                 )
                 if raise_on_error:
@@ -227,7 +250,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):

         # Reject overwrite if target file itself is a symlink
         if p.is_symlink():
-            err = PermissionError(
+            err = PreCommitPermissionError(
                 f"SEC-02: Target path {p} is a symlink; refusing to overwrite to prevent symlink attack."
             )
             if raise_on_error:
@@ -257,7 +280,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
             st = os.fstat(fd)
             actual_mode = st.st_mode & 0o777
             if actual_mode != mode:
-                raise PermissionError(
+                raise PreCommitPermissionError(
                     f"SEC-02: fchmod mode mismatch on temp file {temp_p}: expected {oct(mode)}, got {oct(actual_mode)}"
                 )

@@ -272,7 +295,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
             pre_st = temp_p.stat()
             pre_mode = pre_st.st_mode & 0o777
             if pre_mode != mode:
-                raise PermissionError(
+                raise PreCommitPermissionError(
                     f"SEC-02: Pre-commit mode mismatch on {temp_p}: expected {oct(mode)}, got {oct(pre_mode)}"
                 )

@@ -290,7 +313,7 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
                 err_msg = f"SEC-02: Post-commit directory fsync failed on {parent_dir}: {sync_err}"
                 logger.error(err_msg)
                 if raise_on_error:
-                    raise OSError(err_msg) from sync_err
+                    raise PostCommitDurabilityError(err_msg) from sync_err
                 return False
             finally:
                 if dir_fd is not None:
@@ -313,11 +336,28 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
                     )
                     logger.error(err_msg)
                     if raise_on_error:
-                        raise PermissionError(err_msg)
+                        raise PostCommitDurabilityError(err_msg)
                     return False

         return True

+    except AtomicSaveError as e:
+        phase = "post-commit" if e.committed else "pre-commit"
+        logger.error(f"SEC-02: Error atomic saving {filepath} [{phase}]: {e}")
+        if fd is not None:
+            try:
+                os.close(fd)
+            except Exception:
+                pass
+        if not e.committed:
+            try:
+                if temp_p.exists():
+                    temp_p.unlink()
+            except Exception:
+                pass
+        if raise_on_error:
+            raise
+        return False
     except Exception as e:
         phase = "post-commit" if committed else "pre-commit"
         logger.error(f"SEC-02: Error atomic saving {filepath} [{phase}]: {e}")
@@ -333,7 +373,10 @@ def save_atomic_json(filepath, data, mode=None, raise_on_error=True):
             except Exception:
                 pass
         if raise_on_error:
-            raise
+            if committed:
+                raise PostCommitDurabilityError(f"SEC-02: [{phase}] {e}") from e
+            else:
+                raise PreCommitSaveError(f"SEC-02: [{phase}] {e}") from e
         return False

 MAX_OPCUA_BROWSE_NODES = 500
diff --git a/aqua-command-desktop/desktop/tests/test_credential_permissions.py b/aqua-command-desktop/desktop/tests/test_credential_permissions.py
index a5ef9fa..9b4566c 100644
--- a/aqua-command-desktop/desktop/tests/test_credential_permissions.py
+++ b/aqua-command-desktop/desktop/tests/test_credential_permissions.py
@@ -20,7 +20,14 @@ desktop_dir = Path(__file__).resolve().parent.parent
 if str(desktop_dir) not in sys.path:
     sys.path.insert(0, str(desktop_dir))

-from app import save_atomic_json, IS_WINDOWS
+from app import (
+    save_atomic_json,
+    IS_WINDOWS,
+    AtomicSaveError,
+    PreCommitSaveError,
+    PreCommitPermissionError,
+    PostCommitDurabilityError
+)


 class TestCredentialFilePermissions(unittest.TestCase):
@@ -188,14 +195,50 @@ class TestCredentialFilePermissions(unittest.TestCase):
             return real_fsync(fd)

         with patch("os.fsync", side_effect=fail_dir_fsync):
-            with self.assertRaises(OSError) as ctx:
+            with self.assertRaises(PostCommitDurabilityError) as ctx:
                 save_atomic_json(test_file, data, mode=0o600)
             self.assertIn("post-commit directory fsync failed", str(ctx.exception).lower())
+            self.assertTrue(ctx.exception.committed, "Exception must explicitly reflect committed=True")

         # Target file must still exist and contain the data (not destroyed)
         self.assertTrue(test_file.exists(), "Target config must never be deleted on post-commit fsync failure")
         with open(test_file, "r", encoding="utf-8") as f:
             saved = json.load(f)
         self.assertEqual(saved["key"], "important_config")

+    def test_post_commit_error_distinction_and_retry_prevention(self):
+        """SEC-02: Asserts distinct handling between pre-commit failure (retryable) and post-commit error (non-retryable)."""
+        if IS_WINDOWS:
+            self.skipTest("POSIX directory fsync")
+
+        self.target_dir.mkdir(parents=True, exist_ok=True)
+        test_file = self.target_dir / "retry_check.json"
+        original_data = {"version": 1, "state": "ORIGINAL"}
+        save_atomic_json(test_file, original_data, mode=0o600)
+
+        # 1. Pre-commit failure: committed must be False, safe to retry or abort
+        with patch("json.dump", side_effect=IOError("Simulated write failure")):
+            with self.assertRaises(PreCommitSaveError) as pre_ctx:
+                save_atomic_json(test_file, {"version": 2, "state": "NEW"}, mode=0o600)
+            self.assertFalse(pre_ctx.exception.committed, "Pre-commit error must have committed=False")
+
+        # Original data untouched
+        with open(test_file, "r", encoding="utf-8") as f:
+            self.assertEqual(json.load(f)["version"], 1)
+
+        # 2. Post-commit failure: committed must be True, callers MUST NOT retry automatically
+        real_fsync = os.fsync
+        call_count = [0]
+        def fail_dir_fsync(fd):
+            call_count[0] += 1
+            if call_count[0] > 1:
+                raise OSError("Simulated hardware fsync failure")
+            return real_fsync(fd)
+
+        with patch("os.fsync", side_effect=fail_dir_fsync):
+            with self.assertRaises(PostCommitDurabilityError) as post_ctx:
+                save_atomic_json(test_file, {"version": 2, "state": "COMMITTED_BUT_FSYNC_FAILED"}, mode=0o600)
+            self.assertTrue(post_ctx.exception.committed, "Post-commit error must have committed=True")
+
+        # The new configuration WAS committed to disk; caller must NOT attempt blind automatic overwrite/retry!
+        with open(test_file, "r", encoding="utf-8") as f:
+            persisted = json.load(f)
+        self.assertEqual(persisted["version"], 2, "New config is retained on disk and must not be reverted or unlinked")
+
     def test_parent_directory_fsync_called_on_posix(self):
diff --git a/aqua-command/rules.mjs b/aqua-command/rules.mjs
index ab85775..5205aa3 100644
--- a/aqua-command/rules.mjs
+++ b/aqua-command/rules.mjs
@@ -23,14 +23,16 @@ export function evaluateTelemetry(station) {
 export function alertMessage(alert) {
   const icons = {critical: '🔴', warning: '🟠', resolved: '🟢', info: '🔵'};
   const tag = alert.demo ? '[DEMO] ' : '';
   const area = alert.region ? (alert.region.includes('เชียงใหม่') ? alert.region : `${alert.region}, เชียงใหม่`) : 'จังหวัดเชียงใหม่';
-  return `${icons[alert.severity] || '🔔'} ${tag}AQUA COMMAND — CHIANG MAI (${alert.severity.toUpperCase()})\n` +
-    `ระดับ: ${alert.severity.toUpperCase()}\n` +
-    `เหตุการณ์: ${alert.title}\n` +
-    `สถานี: ${alert.stationName}\n` +
+  const alertDate = (alert.createdAt && !isNaN(new Date(alert.createdAt).getTime())) ? new Date(alert.createdAt) : new Date();
+  const severityStr = String(alert.severity || 'warning').toUpperCase();
+  return `${icons[alert.severity] || '🔔'} ${tag}AQUA COMMAND — CHIANG MAI (${severityStr})\n` +
+    `ระดับ: ${severityStr}\n` +
+    `เหตุการณ์: ${alert.title || 'การแจ้งเตือน'}\n` +
+    `สถานี: ${alert.stationName || 'สถานีทั่วไป'}\n` +
     `พื้นที่: ${area}\n` +
-    `รายละเอียด: ${alert.message}\n` +
-    `เวลา: ${new Intl.DateTimeFormat('th-TH', {timeZone:'Asia/Bangkok', dateStyle:'medium', timeStyle:'medium'}).format(new Date(alert.createdAt))}\n` +
-    `รหัสเหตุการณ์: ${alert.id}\n` +
+    `รายละเอียด: ${alert.message || '-'}\n` +
+    `เวลา: ${new Intl.DateTimeFormat('th-TH', {timeZone:'Asia/Bangkok', dateStyle:'medium', timeStyle:'medium'}).format(alertDate)}\n` +
+    `รหัสเหตุการณ์: ${alert.id || 'N/A'}\n` +
     `แหล่งข้อมูล: ${alert.demo ? 'ข้อมูลจำลอง / DEMO' : 'ระบบตรวจวัด กปภ. เชียงใหม่'}`;
 }
diff --git a/aqua-command/server.mjs b/aqua-command/server.mjs
index 9e06180..682498d 100644
--- a/aqua-command/server.mjs
+++ b/aqua-command/server.mjs
@@ -63,33 +63,89 @@ const history = Array.from({length:96},(_,i)=>({
 }));
 if (!DEMO) history.length=0;
+function isAlertAcknowledged(alert) {
+  if (!alert || typeof alert !== 'object') return false;
+  return Boolean(
+    alert.acknowledgedAt ||
+    alert.acknowledged === true ||
+    alert.ack === true ||
+    alert.status === 'acknowledged' ||
+    alert.acknowledged_at
+  );
+}
+
+function isAlertResolved(alert) {
+  if (!alert || typeof alert !== 'object') return false;
+  return Boolean(
+    alert.resolvedAt ||
+    alert.resolved === true ||
+    alert.severity === 'resolved' ||
+    alert.status === 'resolved' ||
+    alert.resolved_at ||
+    alert.supersededAt
+  );
+}
+
+function migrateLoadedAlert(a) {
+  if (!a || typeof a !== 'object') return a;
+  const isAck = isAlertAcknowledged(a);
+  const isRes = isAlertResolved(a);
+  return {
+    ...a,
+    createdAt: a.createdAt || now(),
+    acknowledgedAt: a.acknowledgedAt || (isAck ? (a.updatedAt || a.createdAt || now()) : null),
+    resolvedAt: a.resolvedAt || (isRes ? (a.updatedAt || a.createdAt || now()) : null),
+    acknowledged: isAck,
+    resolved: isRes
+  };
+}
+
 let store = {alerts:[], queue:[], active:{}, updatedAt:now()};
-try { const previous=JSON.parse(fs.readFileSync(DATA_PATH,'utf8')); store={...store, alerts:previous.alerts||[],queue:previous.queue||[],active:previous.active||{}}; }
+try {
+  const previous=JSON.parse(fs.readFileSync(DATA_PATH,'utf8'));
+  const prevAlerts = (previous.alerts||[]).map(migrateLoadedAlert);
+  let migrated = false;
+  const prevQueue = (previous.queue||[]).map(j => {
+    if (!j.payload) {
+      const al = prevAlerts.find(a => a.id === j.alertId);
+      if (al) {
+        migrated = true;
+        j.payload = {
+          text: alertMessage(al),
+          title: al.title,
+          severity: al.severity,
+          stationName: al.stationName,
+          region: al.region,
+          message: al.message,
+          value: al.value,
+          demo: Boolean(al.demo),
+          createdAt: al.createdAt
+        };
+      }
+    }
+    return j;
+  });
+  store={...store, alerts:prevAlerts, queue:prevQueue, active:previous.active||{}};
+  if (migrated) {
+    saveNow();
+  }
+}
 catch (e) {if (e.code!=='ENOENT') console.error('Could not read state:',e.message);}
 const MAX_ALERT_STORE = 400;

 function isAlertReferenced(alertId) {
-  return store.queue.some(j => (j.status === 'pending' || j.status === 'blocked_by_policy') && j.alertId === alertId);
+  return store.queue.some(j => (j.status === 'pending' || j.status === 'blocked_by_policy' || (j.status === 'failed' && j.attempt < 6)) && j.alertId === alertId);
 }

 function canPruneAlert(alert) {
   if (isAlertReferenced(alert.id)) return false;
-  if (alert.acknowledgedAt === null && alert.resolvedAt === null) return false;
+  if (!isAlertAcknowledged(alert) && !isAlertResolved(alert)) return false;
   return true;
 }

 function canPruneAlerts() {
   return store.alerts.some(canPruneAlert);
 }

-function trimAlerts() {
-  if (store.alerts.length <= MAX_ALERT_STORE) return;
-  const excess = store.alerts.length - MAX_ALERT_STORE;
+function trimAlerts(maxLimit = MAX_ALERT_STORE) {
+  if (store.alerts.length <= maxLimit) return;
+  const excess = store.alerts.length - maxLimit;
   const prunables = new Set();
   for (let i = store.alerts.length - 1; i >= 0 && prunables.size < excess; i--) {
     const a = store.alerts[i];
@@ -104,11 +160,11 @@ function trimQueue() {
   const excess = store.queue.length - MAX_QUEUE_SIZE;
   const prunables = new Set();
   for (let i = 0; i < store.queue.length && prunables.size < excess; i++) {
     const j = store.queue[i];
-    // NEVER prune pending or blocked_by_policy jobs
-    if (j.status === 'pending' || j.status === 'blocked_by_policy') continue;
+    // NEVER prune pending, blocked_by_policy, or actively retrying jobs
+    if (j.status === 'pending' || j.status === 'blocked_by_policy' || (j.status === 'failed' && j.attempt < 6)) continue;

-    // Check associated alert
+    // Check associated alert: keep job if alert is still unacknowledged and unresolved (retaining ACK evidence)
     const alert = store.alerts.find(a => a.id === j.alertId);
-    if (alert && alert.acknowledgedAt === null && alert.resolvedAt === null) {
-      continue; // keep job if alert is still unacknowledged and unresolved
+    if (alert && !isAlertAcknowledged(alert) && !isAlertResolved(alert)) {
+      continue;
     }

     if (j.status === 'sent' || j.status === 'simulated' || (j.status === 'failed' && j.attempt >= 6)) {
@@ -252,6 +308,13 @@ const uid=()=>crypto.randomUUID().slice(0,8).toUpperCase();
 function createAlert(station,rule,severity,value,{resolved=false,demo=DEMO}={}) {
+  if (store.alerts.length >= MAX_ALERT_STORE) {
+    trimAlerts();
+    if (store.alerts.length >= MAX_ALERT_STORE && !canPruneAlerts()) {
+      console.warn(`[DATA-02] Alert capacity limit reached (${store.alerts.length}/${MAX_ALERT_STORE}). Active unacknowledged alerts require acknowledgement. Backpressure engaged.`);
+      return null;
+    }
+  }
   const message=resolved?`${rule.title} กลับสู่เกณฑ์ที่กำหนด (${value}${rule.unit})` :
     `${rule.title}: ${value}${rule.unit} / เกณฑ์เตือน ${rule.warning}${rule.unit}, วิกฤต ${rule.critical}${rule.unit}`;
   const alert={
     id:`AL-${uid()}`,
     stationId:station.id,
     stationName:station.name,
     region:station.region,
     title:resolved?`${rule.title} — กลับสู่ปกติ`:rule.title,
     severity:resolved?'resolved':severity,
     message,
     value,
     ruleId:rule.id,
     createdAt:now(),
     resolvedAt:resolved?now():null,
     acknowledgedAt:null,
+    acknowledged:false,
+    resolved:Boolean(resolved),
     demo
   };
   store.alerts.unshift(alert);
@@ -311,6 +374,6 @@ async function processQueue() {
   const alert=store.alerts.find(x=>x.id===job.alertId);
   // Referential Integrity & Self-Contained Payload:
-  // If alert is somehow detached, the job still possesses its immutable payload.
+  // Primary delivery source: immutable job payload ensures message fidelity even if alert is mutated or pruned
   if(!alert && !job.payload){job.status='failed';job.lastError='Missing alert and payload';trimQueue();saveSoon();return;}
-  const messageText = alert ? alertMessage(alert) : (job.payload?.text || 'AQUA COMMAND Alert');
-  const isDemo = alert ? alert.demo : Boolean(job.payload?.demo);
+  const messageText = job.payload?.text || (alert ? alertMessage(alert) : 'AQUA COMMAND Alert');
+  const isDemo = job.payload ? Boolean(job.payload.demo) : (alert ? Boolean(alert.demo) : Boolean(DEMO));
   if (!TELEGRAM_DELIVERY_AUTHORIZED) {
@@ -384,18 +454,27 @@ async function handler(req,res){
   if(req.method==='POST'&&p==='/api/incidents'){
     if(!checkKey(req))return reply(res,401,{error:'Invalid admin API key'});
     let b=await body(req);
     // Backpressure check when capacity is full of active unacknowledged alerts
-    if (store.alerts.length >= 2000 && !canPruneAlerts()) {
-      return reply(res, 503, {error: 'Alert store capacity limit reached: active alerts require acknowledgement'});
+    if (store.alerts.length >= MAX_ALERT_STORE) {
+      trimAlerts();
+      if (store.alerts.length >= MAX_ALERT_STORE && !canPruneAlerts()) {
+        return reply(res, 503, {
+          error: 'Alert store capacity limit reached: active alerts require acknowledgement',
+          retryAfterSeconds: 30
+        });
+      }
     }
+    const isResolved = b.resolved === true || b.severity === 'resolved' || Boolean(b.resolvedAt);
+    const isAck = b.acknowledged === true || Boolean(b.acknowledgedAt);
     const alert={
       id: b.id || `PWA-${uid()}`,
       stationId: b.stationId || 'PWA',
       stationName: b.stationName || 'กปภ.',
       region: b.region || 'ส่วนภูมิภาค',
       title: b.title || 'ประกาศหยุดจ่ายน้ำ',
-      severity: b.severity || 'warning',
+      severity: b.severity || (isResolved ? 'resolved' : 'warning'),
       message: b.message || '',
       value: b.value !== undefined ? b.value : '-',
       ruleId: b.ruleId || 'pwa-outage',
       createdAt: b.createdAt || now(),
-      resolvedAt: b.resolvedAt || null,
-      acknowledgedAt: null,
+      resolvedAt: b.resolvedAt || (isResolved ? now() : null),
+      acknowledgedAt: b.acknowledgedAt || (isAck ? now() : null),
+      acknowledged: isAck,
+      resolved: isResolved,
       demo: Boolean(b.demo)
     };
@@ -453,3 +532,10 @@ async function handler(req,res){
   const ack=p.match(/^\/api\/alerts\/([A-Za-z0-9-]+)\/ack$/);
-  if(req.method==='POST'&&ack){if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});const a=store.alerts.find(x=>x.id===ack[1]);if(!a)return reply(res,404,{error:'Alert not found'});a.acknowledgedAt=now();saveSoon();broadcast();return reply(res,200,{ok:true});}
+  if(req.method==='POST'&&ack){
+    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
+    const a=store.alerts.find(x=>x.id===ack[1]);
+    if(!a)return reply(res,404,{error:'Alert not found'});
+    a.acknowledgedAt=now();
+    a.acknowledged=true;
+    saveSoon();
+    broadcast();
+    return reply(res,200,{ok:true,id:a.id,acknowledgedAt:a.acknowledgedAt});
+  }
diff --git a/src/telegram_bot.py b/src/telegram_bot.py
index a5cf8f4..062aa6c 100644
--- a/src/telegram_bot.py
+++ b/src/telegram_bot.py
@@ -36,15 +36,17 @@ class TelegramBot:
     @property
     def is_polling_authorized(self) -> bool:
         """
         Inbound command polling authorization check (REL-02).
         Decoupled from outbound notification delivery authorization.
-        Strict default-deny: Only allowed when APP_ENV == 'production'.
-        Any other environment (lab, staging, qa, dev, test, unknown, empty, malformed) is denied.
-        Constructor override cannot enable inbound polling in non-production environments.
+        Strict default-deny:
+        1. APP_ENV must be strictly 'production'.
+        2. Deployment policy Config.TELEGRAM_INBOUND_POLLING_AUTHORIZED must be True.
+        3. Constructor override can only further restrict/disable polling (polling_authorized=False),
+           never bypass or override the deployment policy to True when deployment policy is False.
         """
         env = getattr(Config, "APP_ENV", "").strip().lower()
         if env != "production":
             return False
-        if self._polling_authorized is not None:
-            return bool(self._polling_authorized)
-        return getattr(Config, "TELEGRAM_INBOUND_POLLING_AUTHORIZED", False)
+        deployment_authorized = bool(getattr(Config, "TELEGRAM_INBOUND_POLLING_AUTHORIZED", False))
+        if not deployment_authorized:
+            return False
+        if self._polling_authorized is False:
+            return False
+        return True
diff --git a/src/telegram_notifier.py b/src/telegram_notifier.py
index 99d8d64..72fae7c 100644
--- a/src/telegram_notifier.py
+++ b/src/telegram_notifier.py
@@ -31,15 +31,17 @@ class TelegramNotifier:
     @property
     def is_delivery_authorized(self) -> bool:
         """
         External delivery authorization check (REL-02).
         Decoupled from notification trigger generation.
-        Strict default-deny: Only allowed when APP_ENV == 'production'.
-        Any other environment (lab, staging, qa, dev, test, unknown, empty, malformed) is denied.
-        Constructor override cannot enable external egress in non-production environments.
+        Strict default-deny:
+        1. APP_ENV must be strictly 'production'.
+        2. Deployment policy Config.TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED must be True.
+        3. Constructor override can only further restrict/disable delivery (delivery_authorized=False),
+           never bypass or override the deployment policy to True when deployment policy is False.
         """
         env = getattr(Config, "APP_ENV", "").strip().lower()
         if env != "production":
             return False
-        if self._delivery_authorized is not None:
-            return bool(self._delivery_authorized)
-        return getattr(Config, "TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED", False)
+        deployment_authorized = bool(getattr(Config, "TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED", False))
+        if not deployment_authorized:
+            return False
+        if self._delivery_authorized is False:
+            return False
+        return True
```
