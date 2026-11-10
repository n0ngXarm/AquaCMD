# AQUA COMMAND — RISK REGISTER

## Active Risk Ledger

| Risk ID | Title | Component | Severity | Status | Discovery Phase | Target Remediation |
|---|---|---|---|---|---|---|
| **DATA-04** | Silent Event Loss upon Alert Store Saturation | `aqua-command/server.mjs` | **HIGH** | **OPEN** | Phase 1A Review | Phase 2 (Isolated Web Remediation) |

---

## Detailed Risk Profiles

### DATA-04: Silent Event Loss upon Alert Store Saturation

- **Finding ID**: `DATA-04`
- **Component**: Legacy Web Alert Pipeline (`aqua-command/server.mjs`, `aqua-command/rules.mjs`)
- **Severity**: **HIGH**
- **Status**: **OPEN** (Registered in Phase 1B per directive; legacy web source unmodified in packaging branch)
- **Runtime Reachability**: Reached whenever active unacknowledged alert count reaches store capacity (`400` alerts) during continuous rule violations.

#### 1. Source Evidence
In `AquaCMD/aqua-command/server.mjs`:
```javascript
// Lines 252-258: Alert creation with capacity rejection
function createAlert(candidate) {
  if (store.alerts.length >= 400 && !trimAlerts(1)) {
    return null; // Alert store saturated; unacknowledged records protected by DATA-02
  }
  const alert = { id: uid(), createdAt: now(), status: 'OPEN', ...candidate };
  store.alerts.push(alert);
  schedulePersistence();
  return alert;
}

// Lines 304-320: Rule processing loop committing state before confirming persistence
for (const rule of rules) {
  const violation = evaluateRule(rule, telemetry);
  const key = `${rule.station}:${rule.parameter}`;
  if (violation) {
    const { severity, message, value } = violation;
    // createAlert returns null when capacity is full
    const a = createAlert({ type: 'RULE_VIOLATION', severity, message, ruleId: rule.id, payload: { value, rule } });
    
    // DEFECT: store.active[key] state is committed unconditionally!
    store.active[key] = { severity, lastNotice: Date.now() };
    if (a) {
      enqueueNotification(a);
    }
  }
}
```

#### 2. Failure Scenario Walkthrough
1. **Saturation Event**: SCADA telemetry generates alert activity until `store.alerts.length` reaches `400`. Because all 400 alerts are unacknowledged or linked to pending jobs (protected from premature pruning by `DATA-02`), `trimAlerts(1)` fails and returns `false`.
2. **Alert Rejection**: `createAlert(...)` returns `null`.
3. **State Transition Mutation**: `processRules()` ignores the `null` return value of `createAlert()` and executes `store.active[key] = { severity, lastNotice: Date.now() }`.
4. **Permanent Notification Suppression**:
   - The in-memory rule engine now records the rule as already active and in notification cooldown (`lastNotice`).
   - On the next processing tick (e.g. 1000ms later), `evaluateRule` checks `store.active[key]` and determines that notification cooldown has not elapsed, or that the transition has already occurred.
   - The event was never persisted to `store.alerts`, never enqueued in `store.queue`, and never sent to operators.
   - If the condition later clears without capacity freeing up, the incident was completely lost from the historical record with **zero trace, zero log warning, and zero operator notification**.

#### 3. Impact Analysis
- **OT Safety Blindspot**: In a municipal or industrial flood control SCADA installation, critical water level overflow thresholds would fail to alert field operators.
- **Audit Compliance Breach**: Regulatory audit trails would miss critical excursion events, creating compliance violations.
- **Silent Degradation**: The system appears healthy and reporting telemetry, giving operators a false sense of normal operating conditions.

#### 4. Remediation Architectural Design (Target: Phase 2)
The remediation must implement **Durable Event Persistence Before Rule State Commit (Two-Phase / Outbox Pattern)** with strict adherence to **Zero Silent Dropping**:

1. **Transactional Rule State Commitment**:
   - `store.active[key]` state transition MUST NOT be committed in-memory unless `createAlert()` succeeds in acquiring durable storage.
   - If `createAlert()` fails or cannot allocate space, the rule evaluation must record an uncommitted breach state and flag backpressure.

2. **Durable Overflow Backlog (Outbox Pattern)**:
   - Introduce an on-disk, append-only overflow queue (`state.overflow.json` or WAL) when the memory ring buffer reaches 400 items.
   - Alerts stored in overflow are automatically drained into the active alert queue as soon as existing alerts are acknowledged and pruned.

3. **Backpressure & Operator Warning**:
   - If disk overflow threshold is also reached, the system must enter an explicit `ALARM_BACKPRESSURE` state, emit a high-priority system telemetry event, and prevent silent discarding.

4. **Required Verification Test Matrix**:
   - **Capacity Saturation Test**: Fill alert store to 400 un-prunable alerts; trigger threshold violation; assert rule state does not mark event as notified; assert alert is queued in overflow buffer.
   - **Crash & Recovery Test**: Trigger rule violation with full store; simulate SIGKILL / crash; verify upon restart that rule state re-evaluates and generates retroactive alert once capacity is freed.
   - **Zero Silent Dropping Assertion**: Across continuous load runs, mathematically verify:
     $$\text{Total Rule Violations} = \text{Persisted Alerts} + \text{Active In-flight} + \text{Durable Overflow}$$
     with 0 dropped events.
