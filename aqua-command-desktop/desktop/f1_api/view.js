/**
 * AQUA COMMAND - F1 Unified Tag Overview & Task Manager Controller
 * Vanilla JS, accessible, zero external runtime dependencies.
 * Full keyboard navigation, Shift-click selection, transactional persistence with undo.
 */

(function () {
  'use strict';

  // --- Utility functions ---
  const pad = (n) => String(n).padStart(2, '0');
  const escapeHtml = (str) => {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  // Group definitions matching the official catalog
  const GROUP_METADATA = {
    'all': { name: 'ทุกกลุ่มอุปกรณ์', desc: 'รวมสัญญาณทั้งหมดในระบบ SCADA' },
    'High_VSD': { name: 'ปั๊มน้ำแรงดันสูง VSD', desc: 'ระบบสูบน้ำหลักปรับความเร็วรอบอัตโนมัติ' },
    'High_Valve': { name: 'วาล์วท่อส่งแรงดันสูง', desc: 'วาล์วควบคุมการจ่ายน้ำแรงดันสูง' },
    'High1_PT1PT': { name: 'เซนเซอร์วัดแรงดัน PT', desc: 'เพรสเซอร์ทรานสมิตเตอร์วัดแรงดันน้ำ' },
    'High_Analog': { name: 'สัญญาณอนาล็อกแรงดันสูง', desc: 'เซนเซอร์สัญญาณอนาล็อกทางวิศวกรรม' },
    'High_DPM': { name: 'ดิจิทัลเพาเวอร์มิเตอร์ DPM', desc: 'ระบบวัดกำลังไฟฟ้าและพลังงาน' },
    'High1_Sound': { name: 'ระบบตรวจวัดเสียงและความขุ่น', desc: 'ตรวจสอบความผิดปกติทางกล' },
    'High1_Totalize_Flow': { name: 'มาตรวัดปริมาณน้ำสะสม', desc: 'มิเตอร์วัดปริมาณและอัตราการไหล' },
    'Temp_High_Alarm': { name: 'สัญญาณเตือนอุณหภูมิสูง', desc: 'ระบบเฝ้าระวังอุณหภูมิปั๊มและมอเตอร์' },
    'Timer_Of_Start_Second_CTM': { name: 'ตัวจับเวลาสตาร์ทปั๊ม', desc: 'ระบบกำหนดลำดับเวลาสตาร์ทเครื่องสูบ' },
    'Default': { name: 'ค่าเริ่มต้นระบบ (Default)', desc: 'สัญญาณระบบพื้นฐานที่ยังไม่ได้จัดกลุ่ม' }
  };

  const STATUS_DEFS = {
    OK: { label: 'ปกติ', icon: '✓', colorVar: '--ok', tintVar: '--ok-tint' },
    STALE: { label: 'ข้อมูลค้าง', icon: '◔', colorVar: '--stale', tintVar: '--stale-tint' },
    FAIL: { label: 'สัญญาณขัดข้อง', icon: '✕', colorVar: '--fail', tintVar: '--fail-tint' },
    BLOCKED: { label: 'ทางผ่านล่ม', icon: '⊘', colorVar: '--blocked', tintVar: '--blocked-tint' },
    NO: { label: 'ยังไม่ได้สังเกต', icon: '?', colorVar: '--unv', tintVar: '--unv-tint' }
  };

  // --- Application State ---
  const state = {
    tags: [],
    tasks: [],
    liveMode: false,
    selectedGroup: 'all',
    statusFilter: 'ALL',
    searchQuery: '',
    checkedTags: new Set(),
    activeRowIndex: -1,
    lastCheckedIndex: -1,
    recentTaskId: 'TASK-01',
    activeModal: null, // null | { type: 'inspector', tagName: ... } | { type: 'task_dialog', taskId: ... } | { type: 'bulk_add' }
    toastTimeout: null
  };

  // --- WebKit Bridge Communication & Request Sequencing ---
  let requestSeq = 0;
  function getNextRequestId() {
    requestSeq = (requestSeq + 1) % 1000000;
    return `req_${Date.now()}_${requestSeq}`;
  }

  const pendingSuccessMessages = {};

  function sendBridge(action, payload) {
    const message = { action, payload: payload || {} };
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.f1Bridge) {
      try {
        window.webkit.messageHandlers.f1Bridge.postMessage(JSON.stringify(message));
      } catch (err) {
        console.error('Error posting to f1Bridge:', err);
      }
    } else {
      console.warn('WebKit bridge not present in this runtime:', action);
    }
  }

  function sendMutatingBridge(action, payload, successMsg, undoCb) {
    const reqId = getNextRequestId();
    const fullPayload = { ...(payload || {}), request_id: reqId };
    if (successMsg) {
      pendingSuccessMessages[reqId] = { message: successMsg, undoCb: undoCb || null };
    }
    sendBridge(action, fullPayload);
    return reqId;
  }

  function getGroupName(groupKey) {
    if (!groupKey) return GROUP_METADATA.Default.name;
    const item = GROUP_METADATA[groupKey];
    return item ? item.name : groupKey;
  }

  function getTagTasks(tagName) {
    return state.tasks.filter(t => (t.tags || []).includes(tagName));
  }

  function getTagStatus(tag) {
    if (!tag) return 'NO';
    if (!state.liveMode) {
      return 'NO'; // In configured / catalog mode, strictly Not Observed until live telemetry runs
    }
    return tag.status || 'NO';
  }

  function getFilteredTags() {
    return state.tags.filter(tag => {
      // Group filter
      if (state.selectedGroup !== 'all' && tag.group !== state.selectedGroup) {
        return false;
      }
      // Status filter
      if (state.statusFilter !== 'ALL') {
        const st = getTagStatus(tag);
        if (st !== state.statusFilter) return false;
      }
      // Search query filter (matches name, group, addr, type, comment)
      if (state.searchQuery) {
        const q = state.searchQuery;
        const matchesName = tag.name && tag.name.toLowerCase().includes(q);
        const matchesGroup = tag.group && tag.group.toLowerCase().includes(q);
        const matchesGroupName = getGroupName(tag.group).toLowerCase().includes(q);
        const matchesAddr = tag.addr && tag.addr.toLowerCase().includes(q);
        const matchesType = tag.type && tag.type.toLowerCase().includes(q);
        const matchesComment = tag.comment && tag.comment.toLowerCase().includes(q);
        if (!matchesName && !matchesGroup && !matchesGroupName && !matchesAddr && !matchesType && !matchesComment) {
          return false;
        }
      }
      return true;
    });
  }

  function calculateKpis() {
    const total = state.tags.length;
    let ok = 0, stale = 0, fail = 0, unv = 0;
    for (const tag of state.tags) {
      const st = getTagStatus(tag);
      if (st === 'OK') ok++;
      else if (st === 'STALE') stale++;
      else if (st === 'FAIL') fail++;
      else unv++;
    }
    return { total, ok, stale, fail, unv, tasksCount: state.tasks.length };
  }

  // --- Rendering Functions ---

  function render() {
    renderKpis();
    renderGroupSidebar();
    renderCatalogTable();
    renderFloatingActionBar();
    renderModal();
  }

  function renderKpis() {
    const kpis = calculateKpis();
    const setTxt = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    setTxt('kpiTotal', kpis.total);
    setTxt('kpiOk', kpis.ok);
    setTxt('kpiStale', kpis.stale);
    setTxt('kpiFail', kpis.fail);
    setTxt('kpiUnv', kpis.unv);
    setTxt('kpiTasks', kpis.tasksCount);

    const ribbonEl = document.getElementById('catalogRibbon');
    if (ribbonEl) {
      if (state.liveMode) {
        ribbonEl.innerHTML = `<span class="badge" style="background:var(--ok-tint);color:var(--ok);border:1px solid var(--ok)">● สังเกตสด (Live Telemetry)</span>`;
      } else {
        ribbonEl.innerHTML = `<span class="badge" style="background:var(--accent-tint);color:var(--link);border:1px solid var(--line-strong)">● แคตตาล็อก WinCC (${kpis.total} Tags)</span>`;
      }
    }
  }

  function renderGroupSidebar() {
    const groupsListEl = document.getElementById('groupsList');
    if (!groupsListEl) return;

    // Count tags per group
    const counts = { all: state.tags.length };
    state.tags.forEach(t => {
      const g = t.group || 'Default';
      counts[g] = (counts[g] || 0) + 1;
    });

    const groupKeys = Object.keys(GROUP_METADATA);
    groupsListEl.innerHTML = groupKeys.map(key => {
      const meta = GROUP_METADATA[key];
      const isSelected = state.selectedGroup === key;
      const count = counts[key] || 0;

      return `
        <button class="group-item ${isSelected ? 'is-selected' : ''}" data-group="${escapeHtml(key)}" role="tab" aria-selected="${isSelected}">
          <div class="group-info">
            <span class="group-name">${escapeHtml(meta.name)}</span>
            <span class="group-desc">${escapeHtml(meta.desc)}</span>
          </div>
          <span class="group-count">${count}</span>
        </button>
      `;
    }).join('');
  }

  function highlightMatch(text, query) {
    if (!query || !text) return escapeHtml(text || '');
    const cleanText = String(text);
    const lower = cleanText.toLowerCase();
    const idx = lower.indexOf(query);
    if (idx === -1) return escapeHtml(cleanText);
    const before = cleanText.substring(0, idx);
    const match = cleanText.substring(idx, idx + query.length);
    const after = cleanText.substring(idx + query.length);
    return `${escapeHtml(before)}<mark class="search-match">${escapeHtml(match)}</mark>${escapeHtml(after)}`;
  }

  function renderCatalogTable() {
    const tableBodyEl = document.getElementById('tableBody');
    if (!tableBodyEl) return;

    const filtered = getFilteredTags();

    if (filtered.length === 0) {
      tableBodyEl.innerHTML = `
        <div class="empty-state" role="status">
          <span>ไม่พบ Tag ตรงกับเงื่อนไขการค้นหา</span>
          <button class="btn btn-secondary" id="btnResetFilters" style="margin-top:8px;font-size:12px">ล้างตัวกรองทั้งหมด</button>
        </div>
      `;
      const resetBtn = document.getElementById('btnResetFilters');
      if (resetBtn) {
        resetBtn.onclick = () => {
          state.selectedGroup = 'all';
          state.statusFilter = 'ALL';
          state.searchQuery = '';
          const searchInput = document.getElementById('searchInput');
          if (searchInput) searchInput.value = '';
          render();
        };
      }
      return;
    }

    const query = state.searchQuery;
    tableBodyEl.innerHTML = filtered.map((tag, idx) => {
      const isChecked = state.checkedTags.has(tag.name);
      const isNavActive = state.activeRowIndex === idx;
      const statusKey = getTagStatus(tag);
      const statusDef = STATUS_DEFS[statusKey];
      const boundTasks = getTagTasks(tag.name);
      const boundText = boundTasks.map(t => escapeHtml(t.id)).join(', ');

      let valText = '—';
      if (state.liveMode && tag.observed_value !== undefined && tag.observed_value !== null) {
        valText = tag.type === 'Binary Tag' || tag.type === 'Bool'
          ? (tag.observed_value ? 'TRUE' : 'FALSE')
          : String(tag.observed_value);
      }

      return `
        <div class="table-row ${isNavActive ? 'is-active-nav' : ''}" role="row" data-tag-name="${escapeHtml(tag.name)}" data-index="${idx}" aria-selected="${isChecked}">
          <div class="cell-checkbox">
            <input type="checkbox" data-checkbox-name="${escapeHtml(tag.name)}" data-checkbox-index="${idx}" ${isChecked ? 'checked' : ''} aria-label="เลือก ${escapeHtml(tag.name)}">
          </div>
          <div class="cell-tag-name mono">${highlightMatch(tag.name, query)}</div>
          <div class="cell-group">${escapeHtml(getGroupName(tag.group))}</div>
          <div class="cell-type mono">${escapeHtml(tag.type || 'Word')}</div>
          <div class="cell-status" style="--c:var(${statusDef.colorVar});--t:var(${statusDef.tintVar})">
            <span>${statusDef.icon}</span>
            <span>${statusDef.label}</span>
            ${state.liveMode && statusKey !== 'NO' ? `<span class="mono" style="margin-left:4px">· ${escapeHtml(valText)}</span>` : ''}
          </div>
          <div class="cell-task mono" title="${boundText}">${boundText}</div>
          <div class="cell-actions">
            <button class="btn-quick-task" data-quick-tag="${escapeHtml(tag.name)}" title="ผูกกับ ${escapeHtml(state.recentTaskId)} ทันที">+ Task</button>
            <button class="btn-inspect" data-inspect-tag="${escapeHtml(tag.name)}" title="ตรวจสอบรายละเอียด">🔍</button>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderFloatingActionBar() {
    const barEl = document.getElementById('floatingActionBar');
    if (!barEl) return;

    if (state.checkedTags.size === 0) {
      barEl.hidden = true;
      return;
    }

    barEl.hidden = false;
    const countLabel = document.getElementById('selectedCountLabel');
    if (countLabel) {
      countLabel.textContent = `เลือกแล้ว ${state.checkedTags.size} รายการ`;
    }
  }

  function renderModal() {
    const overlayEl = document.getElementById('modalOverlay');
    const contentEl = document.getElementById('modalContent');
    if (!overlayEl || !contentEl) return;

    if (!state.activeModal) {
      overlayEl.hidden = true;
      contentEl.innerHTML = '';
      return;
    }

    overlayEl.hidden = false;
    const modalType = state.activeModal.type;

    if (modalType === 'inspector') {
      renderInspectorModal(contentEl, state.activeModal.tagName);
    } else if (modalType === 'task_dialog') {
      renderTaskDialogModal(contentEl, state.activeModal.taskId);
    } else if (modalType === 'bulk_add') {
      renderBulkAddModal(contentEl);
    }
  }

  function renderInspectorModal(container, tagName) {
    const tag = state.tags.find(t => t.name === tagName);
    if (!tag) {
      container.innerHTML = `<div class="modal-card"><div class="modal-body">ไม่พบข้อมูล Tag</div></div>`;
      return;
    }

    const boundTasks = getTagTasks(tag.name);
    const statusKey = getTagStatus(tag);
    const statusDef = STATUS_DEFS[statusKey];

    const taskOptions = state.tasks.map(t =>
      `<option value="${t.id}" ${t.id === state.recentTaskId ? 'selected' : ''}>${t.id} · ${escapeHtml(t.name)}</option>`
    ).join('');

    let rawMetaHtml = '';
    if (tag.raw_metadata && Object.keys(tag.raw_metadata).length > 0) {
      const rows = Object.entries(tag.raw_metadata)
        .filter(([k]) => !k.startsWith('['))
        .map(([k, v]) => `<tr><td style="color:var(--mut);padding:4px 8px">${escapeHtml(k)}</td><td class="mono" style="padding:4px 8px">${escapeHtml(v || '—')}</td></tr>`)
        .join('');
      rawMetaHtml = `
        <details style="margin-top:14px">
          <summary style="cursor:pointer;color:var(--link);font-weight:500">ข้อมูล Raw Metadata จาก WinCC Export (${Object.keys(tag.raw_metadata).length / 2 | 0} ช่อง)</summary>
          <div style="max-height:160px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--radius);margin-top:6px">
            <table style="width:100%;font-size:12px;border-collapse:collapse">${rows}</table>
          </div>
        </details>
      `;
    }

    const boundTasksHtml = boundTasks.length === 0
      ? `<div style="color:var(--mut);font-size:12.5px;margin-bottom:8px">Tag นี้ยังไม่ได้ผูกกับ Task ใด</div>`
      : `
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">
          ${boundTasks.map(bt => `
            <span class="badge" style="background:var(--surface-3);color:var(--ink);border:1px solid var(--line);padding:3px 8px;border-radius:4px;display:inline-flex;align-items:center;gap:6px;font-size:12px">
              <b>${escapeHtml(bt.id)}</b>: ${escapeHtml(bt.name || '')}
              <button type="button" class="btn-ghost" data-remove-bound-task="${escapeHtml(bt.id)}" data-tag-name="${escapeHtml(tag.name)}" title="เอาออกจาก ${escapeHtml(bt.id)}" style="padding:0 2px;cursor:pointer;color:var(--fail)">✕</button>
            </span>
          `).join('')}
        </div>
      `;

    container.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3 class="mono">${escapeHtml(tag.name)}</h3>
          <button class="btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span class="sub">${escapeHtml(getGroupName(tag.group))} · ${escapeHtml(tag.type || 'Word')}</span>
            <div class="cell-status" style="--c:var(${statusDef.colorVar});--t:var(${statusDef.tintVar})">
              <span>${statusDef.icon}</span>
              <span>${statusDef.label}</span>
            </div>
          </div>

          <dl class="detail-grid">
            <dt>ที่อยู่ PLC / S7 Offset</dt>
            <dd class="mono">${escapeHtml(tag.addr || 'Internal')}</dd>
            <dt>Connection</dt>
            <dd class="mono">${escapeHtml(tag.conn || 'Internal')}</dd>
            <dt>ค่าล่าสุด</dt>
            <dd class="mono">${state.liveMode && tag.observed_value !== undefined && tag.observed_value !== null ? escapeHtml(tag.observed_value) : '— ยังไม่มีการสังเกตสด'}</dd>
            <dt>เวลาที่ตรวจล่าสุด</dt>
            <dd>${escapeHtml(tag.age_text || (statusKey === 'NO' ? 'ยังไม่ได้สังเกต' : 'ยังไม่มีประวัติการอ่านสด'))}</dd>
            <dt>คำอธิบาย Tag</dt>
            <dd>${escapeHtml(tag.comment || 'ไม่มีคำอธิบาย')}</dd>
          </dl>

          <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--line)">
            <h4 style="margin:0 0 8px 0;font-size:13px;font-weight:600">การผูกกับ WinCC Task (${boundTasks.length} Task)</h4>
            ${boundTasksHtml}
            <div class="form-row" style="margin-top:8px">
              <select id="modalTaskSelect" class="in" style="flex:1" aria-label="เลือก Task">${taskOptions}</select>
              <button class="btn btn-primary" id="btnAssignToTask">เพิ่มเข้า Task นี้</button>
            </div>
          </div>

          ${rawMetaHtml}
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" id="btnCloseModalBottom">ปิด</button>
        </div>
      </div>
    `;

    document.getElementById('btnCloseModal').onclick = closeModal;
    document.getElementById('btnCloseModalBottom').onclick = closeModal;

    const btnAssign = document.getElementById('btnAssignToTask');
    if (btnAssign) {
      btnAssign.onclick = () => {
        const selTask = document.getElementById('modalTaskSelect').value;
        state.recentTaskId = selTask;
        sendMutatingBridge(
          'add_tag_to_task',
          { tag_name: tag.name, task_id: selTask },
          `เพิ่ม ${tag.name} เข้า ${selTask} เรียบร้อยแล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเพิ่ม Tag เรียบร้อยแล้ว')
        );
        closeModal();
      };
    }

    // Bind remove buttons for individual bound tasks
    container.querySelectorAll('[data-remove-bound-task]').forEach(btn => {
      btn.onclick = () => {
        const tId = btn.dataset.removeBoundTask;
        const tgName = btn.dataset.tagName;
        sendMutatingBridge(
          'remove_tag_from_task',
          { tag_name: tgName, task_id: tId },
          `เอา ${tgName} ออกจาก ${tId} เรียบร้อยแล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเอาออกเรียบร้อยแล้ว')
        );
        closeModal();
      };
    });
  }

  function getNextTaskIdClient() {
    const existing = new Set(state.tasks.map(t => t.id));
    let num = 1;
    while (existing.has(`TASK-${pad(num)}`)) {
      num++;
    }
    return `TASK-${pad(num)}`;
  }

  function renderTaskDialogModal(container, taskId) {
    let currentTask = state.tasks.find(t => t.id === taskId);
    if (!currentTask && state.tasks.length > 0) {
      currentTask = state.tasks[0];
    }
    if (!currentTask) {
      currentTask = { id: 'TASK-01', name: 'Task ใหม่', cycle_sec: 5, action_log: true, action_notify: false, active: true, tags: [] };
    }

    const taskOptions = state.tasks.map(t =>
      `<option value="${t.id}" ${t.id === currentTask.id ? 'selected' : ''}>${t.id} · ${escapeHtml(t.name)} (${(t.tags || []).length} Tags)</option>`
    ).join('');

    const assignedTags = currentTask.tags || [];
    const assignedTagsRows = assignedTags.length === 0
      ? `<tr><td colspan="4" style="text-align:center;color:var(--mut);padding:14px">ยังไม่มี Tag ใน Task นี้</td></tr>`
      : assignedTags.map(tn => {
        const tObj = state.tags.find(x => x.name === tn) || { type: 'Word', group: 'Default' };
        return `
          <tr style="border-bottom:1px solid var(--line);cursor:pointer" data-assigned-tag="${escapeHtml(tn)}">
            <td style="width:36px;padding:6px 8px">
              <input type="checkbox" data-assigned-checkbox="${escapeHtml(tn)}" aria-label="เลือก ${escapeHtml(tn)}">
            </td>
            <td class="mono" style="padding:6px 8px;font-weight:500">${escapeHtml(tn)}</td>
            <td style="padding:6px 8px;color:var(--mut)">${escapeHtml(getGroupName(tObj.group))}</td>
            <td class="mono" style="padding:6px 8px;color:var(--mut);font-size:12px">${escapeHtml(tObj.type || 'Word')}</td>
          </tr>
        `;
      }).join('');

    container.innerHTML = `
      <div class="modal-card wide">
        <div class="modal-header">
          <h3>จัดการ Task (WinCC Task Manager)</h3>
          <button class="btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body" style="display:grid;grid-template-columns:1fr 1.2fr;gap:16px">
          <!-- Left Column: Task Settings Form -->
          <div>
            <div class="form-group">
              <label for="taskPickerSelect">เลือก Task ที่ต้องการจัดการ</label>
              <div class="form-row">
                <select id="taskPickerSelect" class="in" style="flex:1">${taskOptions}</select>
                <button class="btn btn-secondary" id="btnCreateNewTaskDraft" title="สร้าง Task ใหม่">+ สร้าง</button>
              </div>
            </div>

            <div class="form-group">
              <label for="inputTaskName">ชื่อ Task</label>
              <input type="text" id="inputTaskName" class="in" value="${escapeHtml(currentTask.name || '')}">
            </div>

            <div class="form-group">
              <label for="selectTaskCycle">รอบตรวจวัด (Cycle)</label>
              <select id="selectTaskCycle" class="in">
                <option value="1" ${currentTask.cycle_sec === 1 ? 'selected' : ''}>1 วินาที (High Priority)</option>
                <option value="5" ${currentTask.cycle_sec === 5 ? 'selected' : ''}>5 วินาที (มาตรฐาน WinCC V8.1)</option>
                <option value="10" ${currentTask.cycle_sec === 10 ? 'selected' : ''}>10 วินาที (General Monitoring)</option>
                <option value="30" ${currentTask.cycle_sec === 30 ? 'selected' : ''}>30 วินาที (Slow Sampling)</option>
                <option value="60" ${currentTask.cycle_sec === 60 ? 'selected' : ''}>60 วินาที</option>
              </select>
            </div>

            <div style="background:var(--surface-2);border:1px solid var(--line);border-radius:var(--radius);padding:10px;margin-top:12px">
              <div style="font-weight:600;font-size:12.5px;color:var(--mut);margin-bottom:6px">เมื่อ Task ทำงาน</div>
              <label class="form-check" style="cursor:pointer;display:flex;align-items:center;gap:8px;padding:4px 0">
                <input type="checkbox" id="chkActionLog" ${currentTask.action_log ? 'checked' : ''}>
                <span>บันทึกประวัติในเครื่อง (Local CSV & SQLite)</span>
              </label>

              <!-- Telegram Row with distinct F6 link -->
              <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0">
                <label class="form-check" style="cursor:pointer;display:flex;align-items:center;gap:8px;margin-bottom:0">
                  <input type="checkbox" id="chkActionNotify" ${currentTask.action_notify ? 'checked' : ''}>
                  <span>แจ้งเตือนผ่าน Telegram</span>
                </label>
                <button type="button" class="btn btn-ghost" id="btnF6Link" style="padding:2px 8px;font-size:12px;color:var(--accent);cursor:pointer;border:1px solid var(--line);border-radius:4px" title="เปิดหน้า F6 เพื่อตั้งค่า Telegram Token & Chat ID">ตั้งค่าปลายทางที่ F6 →</button>
              </div>

              <label class="form-check" style="cursor:pointer;display:flex;align-items:center;gap:8px;margin-top:6px;border-top:1px solid var(--line);padding-top:8px">
                <input type="checkbox" id="chkTaskActive" ${currentTask.active ? 'checked' : ''}>
                <span style="font-weight:600">เปิดใช้งาน Task นี้</span>
              </label>
            </div>

            <div style="margin-top:16px;display:flex;gap:8px">
              <button class="btn btn-primary" id="btnSaveTaskForm" style="flex:1">บันทึก Task</button>
            </div>
          </div>

          <!-- Right Column: Assigned Tags Table -->
          <div style="display:flex;flex-direction:column;min-height:0">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <span style="font-weight:600;font-size:13px">Tag ใน Task (${assignedTags.length} รายการ)</span>
              <div style="display:flex;gap:6px">
                <button class="btn btn-secondary" id="btnRemoveSelectedAssigned" style="font-size:12px;padding:3px 8px">เอาที่เลือกออก</button>
                <button class="btn btn-secondary" id="btnClearAllAssigned" style="font-size:12px;padding:3px 8px">ล้างทั้งหมด</button>
              </div>
            </div>

            <div style="flex:1;max-height:320px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)">
              <table style="width:100%;font-size:12.5px;border-collapse:collapse;text-align:left">
                <thead style="position:sticky;top:0;background:var(--surface-2);border-bottom:1px solid var(--line)">
                  <tr>
                    <th style="width:36px;padding:6px 8px">
                      <input type="checkbox" id="chkSelectAllAssigned" aria-label="เลือกทั้งหมด">
                    </th>
                    <th style="padding:6px 8px">ชื่อ Tag</th>
                    <th style="padding:6px 8px">กลุ่มอุปกรณ์</th>
                    <th style="padding:6px 8px">ชนิด</th>
                  </tr>
                </thead>
                <tbody>${assignedTagsRows}</tbody>
              </table>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" id="btnCloseModalBottom">ปิดหน้าต่าง</button>
        </div>
      </div>
    `;

    document.getElementById('btnCloseModal').onclick = closeModal;
    document.getElementById('btnCloseModalBottom').onclick = closeModal;

    const taskPicker = document.getElementById('taskPickerSelect');
    if (taskPicker) {
      taskPicker.onchange = () => {
        state.activeModal.taskId = taskPicker.value;
        renderModal();
      };
    }

    const btnCreateDraft = document.getElementById('btnCreateNewTaskDraft');
    if (btnCreateDraft) {
      btnCreateDraft.onclick = () => {
        const newId = getNextTaskIdClient();
        sendMutatingBridge(
          'create_task',
          {
            task: {
              id: newId,
              name: `Task เฝ้าระวังใหม่ ${newId.replace('TASK-', '')}`,
              cycle_sec: 5,
              action_log: true,
              action_notify: false,
              active: false,
              tags: []
            }
          },
          `สร้างร่าง ${newId} เรียบร้อยแล้ว`
        );
        state.activeModal.taskId = newId;
      };
    }

    const btnSave = document.getElementById('btnSaveTaskForm');
    if (btnSave) {
      btnSave.onclick = () => {
        const updatedTask = {
          id: currentTask.id,
          name: document.getElementById('inputTaskName').value.trim() || currentTask.id,
          cycle_sec: parseInt(document.getElementById('selectTaskCycle').value, 10) || 5,
          action_log: document.getElementById('chkActionLog').checked,
          action_notify: document.getElementById('chkActionNotify').checked,
          active: document.getElementById('chkTaskActive').checked,
          tags: currentTask.tags || []
        };
        sendMutatingBridge(
          'save_task',
          { task: updatedTask },
          `บันทึกการตั้งค่า ${currentTask.id} เรียบร้อยแล้ว`
        );
        closeModal();
      };
    }

    // F6 Navigation link in Task dialog
    const btnF6 = document.getElementById('btnF6Link');
    if (btnF6) {
      btnF6.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
        sendBridge('navigate_f6', {});
      };
    }

    // Select all assigned checkboxes
    const chkSelectAll = document.getElementById('chkSelectAllAssigned');
    if (chkSelectAll) {
      chkSelectAll.onchange = () => {
        const boxes = document.querySelectorAll('[data-assigned-checkbox]');
        boxes.forEach(b => b.checked = chkSelectAll.checked);
      };
    }

    // Remove selected assigned tags
    const btnRemoveSelected = document.getElementById('btnRemoveSelectedAssigned');
    if (btnRemoveSelected) {
      btnRemoveSelected.onclick = () => {
        const selectedNames = [];
        document.querySelectorAll('[data-assigned-checkbox]:checked').forEach(b => {
          selectedNames.push(b.dataset.assignedCheckbox);
        });
        if (selectedNames.length === 0) return;

        sendMutatingBridge(
          'remove_tags_from_task',
          { tag_names: selectedNames, task_id: currentTask.id },
          `เอา ${selectedNames.length} Tag ออกจาก ${currentTask.id} แล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเอาออกเรียบร้อยแล้ว')
        );
      };
    }

    // Clear all assigned tags
    const btnClearAll = document.getElementById('btnClearAllAssigned');
    if (btnClearAll) {
      btnClearAll.onclick = () => {
        if (assignedTags.length === 0) return;
        sendMutatingBridge(
          'remove_tags_from_task',
          { tag_names: [...assignedTags], task_id: currentTask.id },
          `ล้าง Tag ทั้งหมดจาก ${currentTask.id} แล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการล้าง Tag เรียบร้อยแล้ว')
        );
      };
    }
  }

  function renderBulkAddModal(container) {
    const selectedCount = state.checkedTags.size;
    const taskOptions = state.tasks.map(t =>
      `<option value="${t.id}" ${t.id === state.recentTaskId ? 'selected' : ''}>${t.id} · ${escapeHtml(t.name)} (${(t.tags || []).length} Tags)</option>`
    ).join('');

    container.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3>เพิ่ม ${selectedCount} Tag เข้าสู่ Task</h3>
          <button class="btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body">
          <p style="margin:0 0 12px 0;font-size:13px;color:var(--ink)">
            เลือก Task ปลายทางที่ต้องการผูกสัญญาณจำนวน <b>${selectedCount}</b> รายการที่เลือกไว้:
          </p>
          <div class="form-group">
            <label for="bulkTaskSelect">Task ปลายทาง</label>
            <select id="bulkTaskSelect" class="in">${taskOptions}</select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" id="btnCloseModalBottom">ยกเลิก</button>
          <button class="btn btn-primary" id="btnSubmitBulkAdd">ยืนยันการเพิ่มเข้า Task</button>
        </div>
      </div>
    `;

    document.getElementById('btnCloseModal').onclick = closeModal;
    document.getElementById('btnCloseModalBottom').onclick = closeModal;

    const btnSubmit = document.getElementById('btnSubmitBulkAdd');
    if (btnSubmit) {
      btnSubmit.onclick = () => {
        const targetTaskId = document.getElementById('bulkTaskSelect').value;
        const tagList = Array.from(state.checkedTags);
        state.recentTaskId = targetTaskId;
        sendMutatingBridge(
          'add_tags_to_task',
          { tag_names: tagList, task_id: targetTaskId },
          `เพิ่ม ${tagList.length} Tag เข้า ${targetTaskId} เรียบร้อยแล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเพิ่ม Tag เรียบร้อยแล้ว')
        );
        state.checkedTags.clear();
        closeModal();
      };
    }
  }

  function openInspector(tagName) {
    state.activeModal = { type: 'inspector', tagName };
    renderModal();
  }

  function openTaskDialog(taskId) {
    state.activeModal = { type: 'task_dialog', taskId: taskId || state.recentTaskId };
    renderModal();
  }

  function openBulkAddDialog() {
    if (state.checkedTags.size === 0) return;
    state.activeModal = { type: 'bulk_add' };
    renderModal();
  }

  function closeModal() {
    state.activeModal = null;
    renderModal();
  }

  // --- Toast with Undo & Error Support ---
  function showToast(message, undoCallback, isError) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    if (state.toastTimeout) {
      clearTimeout(state.toastTimeout);
      state.toastTimeout = null;
    }

    const toastBg = isError ? 'var(--fail-tint)' : 'var(--surface-3)';
    const toastBorder = isError ? 'var(--fail)' : 'var(--line-strong)';
    const toastColor = isError ? 'var(--fail)' : 'var(--ink)';

    toastContainer.innerHTML = `
      <div class="toast-card" role="alert" style="background:${toastBg};border:1px solid ${toastBorder};color:${toastColor}">
        <span>${escapeHtml(message)}</span>
        ${undoCallback ? `<button class="toast-undo-btn" id="btnToastUndo">เลิกทำ</button>` : ''}
      </div>
    `;

    if (undoCallback) {
      const undoBtn = document.getElementById('btnToastUndo');
      if (undoBtn) {
        undoBtn.onclick = () => {
          undoCallback();
          toastContainer.innerHTML = '';
        };
      }
    }

    state.toastTimeout = setTimeout(() => {
      toastContainer.innerHTML = '';
      state.toastTimeout = null;
    }, 6000);
  }

  // --- Event Bindings ---
  function setupEvents() {
    // Mode toggling
    const btnModeReal = document.getElementById('btnModeReal');
    const btnModeSim = document.getElementById('btnModeSim');
    if (btnModeReal && btnModeSim) {
      btnModeReal.onclick = () => {
        state.liveMode = false;
        btnModeReal.setAttribute('aria-pressed', 'true');
        btnModeSim.setAttribute('aria-pressed', 'false');
        render();
      };
      btnModeSim.onclick = () => {
        state.liveMode = true;
        btnModeReal.setAttribute('aria-pressed', 'false');
        btnModeSim.setAttribute('aria-pressed', 'true');
        render();
      };
    }

    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.oninput = (e) => {
        state.searchQuery = e.target.value.trim().toLowerCase();
        state.activeRowIndex = -1;
        renderCatalogTable();
      };
    }

    // Floating action bar buttons
    const btnBulkAdd = document.getElementById('btnBulkAdd');
    if (btnBulkAdd) btnBulkAdd.onclick = openBulkAddDialog;

    const btnBulkRemove = document.getElementById('btnBulkRemove');
    if (btnBulkRemove) {
      btnBulkRemove.onclick = () => {
        const tagList = Array.from(state.checkedTags);
        if (tagList.length === 0) return;
        state.tasks.forEach(t => {
          const matching = tagList.filter(name => t.tags && t.tags.includes(name));
          if (matching.length > 0) {
            sendMutatingBridge(
              'remove_tags_from_task',
              { tag_names: matching, task_id: t.id },
              `เอา ${matching.length} Tag ออกจาก ${t.id} แล้ว`,
              () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเอาออกเรียบร้อยแล้ว')
            );
          }
        });
        state.checkedTags.clear();
        render();
      };
    }

    const btnClearSelection = document.getElementById('btnClearSelection');
    if (btnClearSelection) {
      btnClearSelection.onclick = () => {
        state.checkedTags.clear();
        state.lastCheckedIndex = -1;
        render();
      };
    }

    // Helper: toggle tag selection with optional range support
    function toggleTagSelection(tagName, rowIdx, isShift) {
      const filtered = getFilteredTags();
      if (isShift && state.lastCheckedIndex >= 0 && state.lastCheckedIndex < filtered.length) {
        const start = Math.min(state.lastCheckedIndex, rowIdx);
        const end = Math.max(state.lastCheckedIndex, rowIdx);
        const willCheck = !state.checkedTags.has(tagName);
        for (let i = start; i <= end; i++) {
          if (filtered[i]) {
            if (willCheck) state.checkedTags.add(filtered[i].name);
            else state.checkedTags.delete(filtered[i].name);
          }
        }
      } else {
        if (state.checkedTags.has(tagName)) {
          state.checkedTags.delete(tagName);
        } else {
          state.checkedTags.add(tagName);
        }
        state.lastCheckedIndex = rowIdx;
      }
      state.activeRowIndex = rowIdx;
      renderCatalogTable();
      renderFloatingActionBar();
    }

    // Global Click Delegation
    document.addEventListener('click', (e) => {
      // KPI clicks
      const kpiBtn = e.target.closest('[data-kpi]');
      if (kpiBtn) {
        const kpi = kpiBtn.dataset.kpi;
        state.statusFilter = (state.statusFilter === kpi && kpi !== 'ALL') ? 'ALL' : kpi;
        render();
        return;
      }

      // Group sidebar clicks
      const groupBtn = e.target.closest('[data-group]');
      if (groupBtn) {
        state.selectedGroup = groupBtn.dataset.group;
        state.activeRowIndex = -1;
        render();
        return;
      }

      // Quick + Task button clicks in catalog row
      const quickBtn = e.target.closest('[data-quick-tag]');
      if (quickBtn) {
        e.stopPropagation();
        const tagName = quickBtn.dataset.quickTag;
        sendMutatingBridge(
          'add_tag_to_task',
          { tag_name: tagName, task_id: state.recentTaskId },
          `เพิ่ม ${tagName} เข้า ${state.recentTaskId} แล้ว`,
          () => sendMutatingBridge('undo_last_action', {}, 'ยกเลิกการเพิ่ม Tag เรียบร้อยแล้ว')
        );
        return;
      }

      // Dedicated Inspector button in row
      const inspectBtn = e.target.closest('[data-inspect-tag]');
      if (inspectBtn) {
        e.stopPropagation();
        const tagName = inspectBtn.dataset.inspectTag;
        openInspector(tagName);
        return;
      }

      // Assigned tag row click in Task Manager dialog (toggles assigned checkbox)
      const assignedTr = e.target.closest('tr[data-assigned-tag]');
      if (assignedTr && e.target.type !== 'checkbox') {
        const chk = assignedTr.querySelector('input[type="checkbox"]');
        if (chk) {
          chk.checked = !chk.checked;
        }
        return;
      }

      // Catalog Table Row Click: Seamless toggling without requiring clicking the small checkbox
      const tableRow = e.target.closest('.table-row');
      if (tableRow && !e.target.closest('.cell-actions')) {
        const tagName = tableRow.dataset.tagName;
        const rowIdx = parseInt(tableRow.dataset.index, 10);
        toggleTagSelection(tagName, rowIdx, e.shiftKey);
        return;
      }

      // Close modal on clicking outside card
      if (e.target.id === 'modalOverlay') {
        closeModal();
      }
    });

    // Double-click on row opens Inspector
    document.addEventListener('dblclick', (e) => {
      const tableRow = e.target.closest('.table-row');
      if (tableRow && !e.target.closest('.cell-actions')) {
        const tagName = tableRow.dataset.tagName;
        openInspector(tagName);
      }
    });

    // Keyboard Navigation
    document.addEventListener('keydown', (e) => {
      // Escape closes open modals
      if (e.key === 'Escape') {
        if (state.activeModal) {
          closeModal();
          e.preventDefault();
        }
        return;
      }

      // / focuses search input (when modal not open)
      if (e.key === '/' && !state.activeModal && document.activeElement !== searchInput) {
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
          e.preventDefault();
        }
        return;
      }

      // Arrow navigation in table (when modal not open and not typing in search)
      if (!state.activeModal && document.activeElement !== searchInput) {
        const filtered = getFilteredTags();
        if (filtered.length === 0) return;

        if (e.key === 'ArrowDown') {
          state.activeRowIndex = Math.min(state.activeRowIndex + 1, filtered.length - 1);
          renderCatalogTable();
          scrollActiveRowIntoView();
          e.preventDefault();
        } else if (e.key === 'ArrowUp') {
          state.activeRowIndex = Math.max(state.activeRowIndex - 1, 0);
          renderCatalogTable();
          scrollActiveRowIntoView();
          e.preventDefault();
        } else if (e.key === 'Enter') {
          if (state.activeRowIndex >= 0 && state.activeRowIndex < filtered.length) {
            openInspector(filtered[state.activeRowIndex].name);
            e.preventDefault();
          }
        } else if (e.key === ' ' || e.code === 'Space') {
          if (state.activeRowIndex >= 0 && state.activeRowIndex < filtered.length) {
            const tName = filtered[state.activeRowIndex].name;
            toggleTagSelection(tName, state.activeRowIndex, e.shiftKey);
            e.preventDefault();
          }
        }
      }
    });
  }

  function scrollActiveRowIntoView() {
    const activeEl = document.querySelector('.table-row.is-active-nav');
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }

  // --- Public API for WebKit Bridge Host ---
  window.F1 = {
    onStateUpdated(newState) {
      if (!newState) return;
      if (newState.tags) state.tags = newState.tags;
      if (newState.tasks) state.tasks = newState.tasks;
      if (newState.recentTaskId) state.recentTaskId = newState.recentTaskId;
      if (newState.liveMode !== undefined) state.liveMode = newState.liveMode;
      render();
    },

    onBridgeResponse(resp) {
      if (!resp) return;
      if (resp.ok) {
        if (resp.state) {
          if (resp.state.tags) state.tags = resp.state.tags;
          if (resp.state.tasks) state.tasks = resp.state.tasks;
          if (resp.state.recentTaskId) state.recentTaskId = resp.state.recentTaskId;
          if (resp.state.liveMode !== undefined) state.liveMode = resp.state.liveMode;
        }
        render();
        if (resp.request_id && pendingSuccessMessages[resp.request_id]) {
          const entry = pendingSuccessMessages[resp.request_id];
          showToast(entry.message, entry.undoCb);
          delete pendingSuccessMessages[resp.request_id];
        }
      } else {
        if (resp.request_id && pendingSuccessMessages[resp.request_id]) {
          delete pendingSuccessMessages[resp.request_id];
        }
        showToast(resp.error || 'การดำเนินการล้มเหลว', null, true);
      }
    },

    openTaskDialog(taskId) {
      openTaskDialog(taskId);
    },

    setMode(mode) {
      if (mode === 'task_manager') {
        openTaskDialog(state.recentTaskId);
      } else {
        closeModal();
      }
    }
  };

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    setupEvents();
    render();
    sendBridge('get_state', {});
  });

})();
