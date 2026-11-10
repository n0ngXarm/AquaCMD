# AQUACMD — PHASE 1A COMPLETION REPORT & PHASE 1B PROPOSAL

**Working Branch:** `fix/phase-1a-security-hardening`  
**Base Commit:** `74027e2` on `main`  
**Head Commit:** `c6df2df`  
**Execution Environment:** Fedora Linux 43 (x86_64), Python 3.14.8, Node.js v22.23.1, GTK4 4.14  
**Status:** **PHASE 1A COMPLETED (AWAITING INDEPENDENT REVIEW)**

---

## 1. CHANGED FILES & COMMIT REGISTRY

All modifications were partitioned into independent, reviewable, and revertible commits:

| Commit SHA | Task ID | Scope & Summary | Files Changed |
| :--- | :--- | :--- | :--- |
| **`bdfa900`** | **SEC-01** | Sanitize example credentials in `.env.example` | `AquaCMD/.env.example` |
| **`e9bf7dd`** | **SEC-02** | Enforce 0600 file permissions on sensitive config files | `desktop/app.py`, `desktop/tests/test_credential_permissions.py` |
| **`fd4e0cb`** | **SEC-04** | Enforce security gate on cleartext auth, fail-closed cert check, add missing `serialization` | `desktop/opcua_polling_engine.py`, `desktop/opcua_reader.py`, `tests/test_opcua_security_gate.py` |
| **`c6df2df`** | **REL-02** | Disable unconsented initial Telegram dispatch on service start | `src/config.py`, `src/monitor_service.py`, `tests/test_water_system.py` |

### Diff Stat Summary (`74027e2..HEAD`):
```text
 .env.example                                       |   6 +-
 aqua-command-desktop/desktop/app.py                |  51 ++++++--
 aqua-command-desktop/desktop/opcua_polling_engine.py|  30 +++--
 aqua-command-desktop/desktop/opcua_reader.py       |   3 +
 aqua-command-desktop/desktop/tests/test_credential_permissions.py |  58 +++++++++
 aqua-command-desktop/tests/test_opcua_security_gate.py            | 138 +++++++++++++++++++++
 src/config.py                                      |   2 +
 src/monitor_service.py                             |   5 +-
 tests/test_water_system.py                         |  32 +++++
 9 files changed, 300 insertions(+), 25 deletions(-)
```

---

## 2. ROOT CAUSE ANALYSIS & DETAILED REMEDIATION

### SEC-01: Secret Remediation in `.env.example`
- **Root Cause:** In commit `9164258`, active testing values for `TELEGRAM_BOT_TOKEN` (`[REDACTED_TELEGRAM_TOKEN]`) and `TELEGRAM_CHAT_ID` (`[REDACTED_CHAT_ID]`) were committed into the example configuration file.
- **Remediation:** Replaced values with explicit placeholders `YOUR_TELEGRAM_BOT_TOKEN_FROM_BOTFATHER` and `YOUR_TELEGRAM_CHAT_ID`.
- **Secret Scan Verification:** `git grep -iE "([REDACTED_TOKEN_PREFIX]|[REDACTED_BOT_ID]|[REDACTED_CHAT_ID])"` verified zero active matches in tracked tree.
- **Git History Policy:** In accordance with instructions, Git history was **NOT rewritten**. Token revocation guidance has been documented for the bot owner to revoke via `@BotFather`.

### SEC-02: Credential File Permissions (`0600`)
- **Root Cause:** `save_atomic_json()` wrote to a temporary file via standard `open(..., 'w')`, which inherits the ambient umask (`022`), creating files readable by all local users (`0644`).
- **Remediation:**
  1. Updated `CONFIG_DIR` creation to enforce directory mode `0o700`.
  2. Enhanced `save_atomic_json(filepath, data, mode=None)`: when `mode` is specified, it opens the temporary file using low-level `os.open(temp_p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)`, writes and syncs via file descriptor, and applies `os.chmod(p, mode)` after the atomic rename.
  3. Bound `save_telegram_config()` and `save_opcua_config()` to `mode=0o600`.
- **Regression Test:** Added `desktop/tests/test_credential_permissions.py` asserting that created and updated files maintain exact `0600` mode.

### SEC-04: OPC UA Security Gate & Fail-Closed Validation
- **Root Cause:**
  1. `opcua_polling_engine.py` allowed `auth_mode == "Username"` even when `sec_policy == "None"`, transmitting credentials in cleartext over unencrypted TCP.
  2. Peer certificate validation was skipped if `server_cert` was None instead of failing closed.
  3. `opcua_reader.py` referenced `serialization.Encoding.DER` without importing `serialization` from `cryptography.hazmat.primitives`.
- **Remediation:**
  1. In `opcua_polling_engine.py`: strictly raised `PermissionError("Plaintext username/password is strictly forbidden when SecurityPolicy is None")`.
  2. In `opcua_polling_engine.py`: enforced fail-closed validation when `sec_policy == "Basic256Sha256"`; raises `PermissionError("Server certificate missing during secure session establishment")` if missing.
  3. In `opcua_reader.py`: added `from cryptography.hazmat.primitives import serialization`.
  4. Preserved compatibility with `Anonymous` on policy `None` (for isolated test labs).
- **Regression Test:** Added `aqua-command-desktop/tests/test_opcua_security_gate.py` with 5 positive and negative test cases.

### REL-02: Legacy Telegram Auto-Send Removal
- **Root Cause:** `src/monitor_service.py` had an automatic cold-start trigger: whenever `existing_count == 0` in SQLite, it called `self.notifier.send_message(...)` without operator consent.
- **Remediation:**
  1. Added `ENABLE_INITIAL_BROADCAST = False` (default-deny) to `src/config.py`.
  2. Gated the startup broadcast behind `if Config.ENABLE_INITIAL_BROADCAST and self.notifier.default_chat_id:`.
  3. Logged skipped dispatch at INFO level when disabled.
- **Regression Test:** Added `TestMonitorServiceSecurity` to `tests/test_water_system.py` using a mock notifier, asserting that zero external network calls occur on baseline sync.

---

## 3. REGRESSION TEST SUMMARY COMPARISON

All test suites were executed before and after Phase 1A changes:

| Test Suite | Baseline (Phase 0) | Phase 1A Post-Fix | Delta | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Desktop Backend** (`node --test`) | 58 Passed, 0 Failed | **58 Passed, 0 Failed** | 0 | **PASS** |
| **Web Backend** (`node --test`) | 6 Passed, 0 Failed | **6 Passed, 0 Failed** | 0 | **PASS** |
| **Desktop Integration** (`unittest`) | 100 Passed, 3 Skipped | **105 Passed, 3 Skipped** | **+5 Passed** (SEC-04 suite) | **PASS** |
| **Legacy Root Tests** (`unittest`) | 5 Passed, 0 Failed | **6 Passed, 0 Failed** | **+1 Passed** (REL-02 suite) | **PASS** |
| **Desktop Unit Tests** (`unittest`) | 270 Passed, 17 Fail, 5 Err | **271 Passed, 17 Fail, 5 Err** | **+1 Passed** (SEC-02 suite) | **PASS** (Zero new failures; 22 held failures untouched) |
| **Windows Reader** (`dotnet`) | BLOCKED_BY_ENVIRONMENT | **BLOCKED_BY_ENVIRONMENT** | 0 | **BLOCKED** |

---

## 4. PHASE 1B ARCHITECTURE PROPOSALS

### Proposal A: SEC-03 (Web Telemetry API Access Protection)
- **Problem:** `aqua-command/server.mjs` serves `GET /api/state` and `GET /api/stream` (SSE) unauthenticated. Docker Compose binds `0.0.0.0:8787`.
- **Consumer Discovery:**
  - `aqua-command/public/app.js` connects via `new EventSource('/api/stream')` and `fetch('/api/state')`.
  - Browser standard `EventSource` **does not support custom HTTP headers** (such as `x-api-key`).
- **Proposed Architecture Solution:**
  1. **Network Binding Hardening:** In `docker-compose.yml`, change ports binding from `"8787:8787"` to `"127.0.0.1:8787:8787"` so the service is only reachable from loopback on the host.
  2. **Loopback Pass-through & Query Token Fallback:**
     - Requests originating from `127.0.0.1`, `::1`, or Docker internal bridge (`172.x.x.x`) can read `/api/state` and `/api/stream` without friction for local operations.
     - Remote/non-loopback requests must supply either the `x-api-key` header (for REST) or `?key=<ADMIN_API_KEY>` (for SSE/EventSource).
     - If neither matches, return `401 Unauthorized` with JSON error.
  3. **Compatibility Impact:** Transparent to the local dashboard UI while fully closing external unauthenticated network exposure.

### Proposal B: PKG-01 (RPM Packaging Dependency Closure & Acceptance Plan)
- **Problem:** `aqua-command-desktop.spec` installs only 10 legacy files from version 0.9.0. It omits all modern desktop views (`f1_overview.py`, `f2_tasks.py`, `f3_network.py`, `workspace.py`, `opcua_*.py`, embedded WebKit views).
- **Proposed Architecture Solution:**
  1. **Complete File Manifest:**
     - Package `desktop/` directory recursively, including `f1_api/`, `f3_api/`, CSS themes, and embedded assets.
     - Package `collector/`, `src/`, `config/`, and licensed offline fonts (`fonts/`).
     - Package desktop icons and desktop launcher script.
  2. **Spec Requirements Update:**
     - Add `python3-cryptography >= 3.4`, `python3-asyncua >= 0.9.9`, and `webkit2gtk4.1` / `gtk4` dependencies.
     - Bump package version from `0.9.0` to `0.10.0` to match Reader and Commissioning documentation.
  3. **Clean-Install Acceptance Plan:**
     - Build RPM using `rpmbuild -ba`.
     - In an isolated staging directory, extract or install the RPM payload.
     - Run a headless verification smoke test:
       `python3 -c "import sys; sys.path.insert(0, '/usr/share/aqua-command-desktop/desktop'); import app; print('RPM Import Closure OK')"`
     - Assert that all required modules resolve without `ModuleNotFoundError`.

---

## 5. EXIT GATE & SIGN-OFF

- **Phase 1A Tasks:** All 4 approved security tasks completed and verified with regression tests.
- **Safety Safeguards:** Zero real network traffic, zero production SCADA connections, zero unconsented Telegram messages.
- **Git State:** 4 clean commits on branch `fix/phase-1a-security-hardening`. Clean working tree.
- **Next Step:** Stopping now. Waiting for independent review and approval before proceeding to Phase 1B or any further phases.
