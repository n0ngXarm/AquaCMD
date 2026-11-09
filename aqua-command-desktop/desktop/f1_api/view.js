/**
 * AQUA COMMAND - F1 Unified Tag Overview & Task Manager Controller
 * Vanilla JS, accessible, zero external runtime dependencies.
 * Full keyboard navigation, Shift-click selection, 1-click +Task with Undo Toast.
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
      .replace(/"/g, '&quot;');
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
    STALE: { label: 'ข้อมูลเก่า', icon: '◔', colorVar: '--stale', tintVar: '--stale-tint' },
    FAIL: { label: 'คุณภาพเสีย', icon: '✕', colorVar: '--fail', tintVar: '--fail-tint' },
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
    activeModal: null, // null | { type: 'inspector', tagName: ... } | { type: 'task_dialog', taskId: ... } | { type: 'bulk' }
    taskDialogDraft: null,
    toastTimeout: null
  };

  // --- WebKit Bridge Communication ---
  function sendBridge(action, payload) {
    const message = { action, payload: payload || {} };
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.f1Bridge) {
      try {
        window.webkit.messageHandlers.f1Bridge.postMessage(JSON.stringify(message));
      } catch (err) {
        console.error('Error posting to f1Bridge:', err);
      }
    } else {
      // Local development / browser fallback
      handleLocalMockBridge(action, payload);
    }
  }

  function handleLocalMockBridge(action, payload) {
    if (action === 'add_tag_to_task') {
      const task = state.tasks.find(t => t.id === payload.task_id);
      if (task && !task.tags.includes(payload.tag_name)) {
        task.tags.push(payload.tag_name);
      }
      render();
    } else if (action === 'add_tags_to_task') {
      const task = state.tasks.find(t => t.id === payload.task_id);
      if (task) {
        (payload.tag_names || []).forEach(name => {
          if (!task.tags.includes(name)) task.tags.push(name);
        });
      }
      state.checkedTags.clear();
      render();
    } else if (action === 'remove_tag_from_task') {
      const task = state.tasks.find(t => t.id === payload.task_id);
      if (task) {
        task.tags = task.tags.filter(t => t !== payload.tag_name);
      }
      render();
    } else if (action === 'save_task') {
      const idx = state.tasks.findIndex(t => t.id === payload.task.id);
      if (idx >= 0) {
        state.tasks[idx] = Object.assign({}, state.tasks[idx], payload.task);
      }
      render();
    }
  }

  // --- Helper Getters ---
  function getGroupName(groupId) {
    if (GROUP_METADATA[groupId]) return GROUP_METADATA[groupId].name;
    return groupId || 'Default';
  }

  function getGroupDesc(groupId) {
    if (GROUP_METADATA[groupId]) return GROUP_METADATA[groupId].desc;
    return 'สัญญาณในระบบ';
  }

  function getTagTask(tagName) {
    for (let i = 0; i < state.tasks.length; i++) {
      if (state.tasks[i].tags && state.tasks[i].tags.includes(tagName)) {
        return state.tasks[i].id;
      }
    }
    return null;
  }

  function getTagStatus(tag) {
    if (!state.liveMode) return 'NO';
    if (tag.quality === 'BAD' || tag.status === 'FAIL') return 'FAIL';
    if (tag.status === 'STALE') return 'STALE';
    if (tag.status === 'OK' && tag.observed_value !== undefined) return 'OK';
    return 'NO';
  }

  function getFilteredTags() {
    return state.tags.filter(tag => {
      // Group filter
      if (state.selectedGroup !== 'all' && tag.group !== state.selectedGroup) {
        return false;
      }
      // Status filter
      const st = getTagStatus(tag);
      const taskId = getTagTask(tag.name);
      if (state.statusFilter === 'TASK' && !taskId) return false;
      if (state.statusFilter !== 'ALL' && state.statusFilter !== 'TASK' && st !== state.statusFilter) {
        return false;
      }
      // Search query filter
      if (state.searchQuery) {
        const text = `${tag.name} ${getGroupName(tag.group)} ${tag.type} ${tag.addr || ''}`.toLowerCase();
        if (!text.includes(state.searchQuery)) return false;
      }
      return true;
    });
  }

  function calculateCounts() {
    const counts = { ALL: state.tags.length, OK: 0, STALE: 0, FAIL: 0, NO: 0, TASK: 0 };
    state.tags.forEach(t => {
      const st = getTagStatus(t);
      if (counts[st] !== undefined) counts[st]++;
      if (getTagTask(t.name)) counts.TASK++;
    });
    return counts;
  }

  function calculateGroupCounts(groupId) {
    const groupTags = groupId === 'all' ? state.tags : state.tags.filter(t => t.group === groupId);
    const counts = { OK: 0, STALE: 0, FAIL: 0, NO: 0 };
    groupTags.forEach(t => {
      const st = getTagStatus(t);
      if (counts[st] !== undefined) counts[st]++;
    });
    return { total: groupTags.length, counts };
  }

  // --- Rendering UI ---
  function render() {
    renderKPIs();
    renderGroupsSidebar();
    renderCatalogTable();
    renderFloatingActionBar();
    renderModal();
  }

  function renderKPIs() {
    const counts = calculateCounts();
    const kpisEl = document.getElementById('kpisRow');
    if (!kpisEl) return;

    const cards = [
      { id: 'ALL', label: 'ทั้งหมด', count: counts.ALL, colorVar: '--accent' },
      { id: 'OK', label: 'ปกติ', count: counts.OK, colorVar: '--ok' },
      { id: 'STALE', label: 'ข้อมูลเก่า', count: counts.STALE, colorVar: '--stale' },
      { id: 'FAIL', label: 'คุณภาพเสีย', count: counts.FAIL, colorVar: '--fail' },
      { id: 'NO', label: 'ยังไม่ได้สังเกต', count: counts.NO, colorVar: '--unv' },
      { id: 'TASK', label: 'อยู่ใน Task', count: counts.TASK, colorVar: '--accent' }
    ];

    kpisEl.innerHTML = cards.map(c => `
      <button class="kpi-card" data-kpi="${c.id}" aria-pressed="${state.statusFilter === c.id}" style="--c:var(${c.colorVar})">
        <b>${c.count}</b>
        <span>${c.label}</span>
      </button>
    `).join('');
  }

  function renderGroupsSidebar() {
    const sidebarEl = document.getElementById('groupsList');
    if (!sidebarEl) return;

    const groupKeys = ['all', 'High_VSD', 'High_Valve', 'High1_PT1PT', 'High_Analog', 'High_DPM',
      'High1_Sound', 'High1_Totalize_Flow', 'Temp_High_Alarm', 'Timer_Of_Start_Second_CTM', 'Default'];

    sidebarEl.innerHTML = groupKeys.map(gid => {
      const { total, counts } = calculateGroupCounts(gid);
      const isSelected = state.selectedGroup === gid;
      const meta = GROUP_METADATA[gid] || { name: gid, desc: '' };

      const barSegments = ['OK', 'STALE', 'FAIL', 'NO'].map(st => {
        const pct = total > 0 ? (counts[st] / total) * 100 : 0;
        const colorVar = STATUS_DEFS[st].colorVar;
        return `<i style="width:${pct}%;background:var(${colorVar})"></i>`;
      }).join('');

      return `
        <button class="group-btn" data-group="${gid}" aria-pressed="${isSelected}">
          <div class="title-row">
            <span>${escapeHtml(meta.name)}</span>
            <em class="mono">${total}</em>
          </div>
          <small>${escapeHtml(meta.desc)}</small>
          <div class="group-bar" aria-hidden="true">${barSegments}</div>
        </button>
      `;
    }).join('');
  }

  function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    const escapedText = escapeHtml(text);
    const escapedQuery = escapeHtml(query);
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    return escapedText.replace(regex, '<mark class="search-match">$1</mark>');
  }

  function renderCatalogTable() {
    const filtered = getFilteredTags();
    const countEl = document.getElementById('catalogCounter');
    if (countEl) {
      countEl.textContent = `แสดง ${filtered.length} จาก ${state.tags.length} รายการ`;
    }

    const tableBodyEl = document.getElementById('tableBody');
    if (!tableBodyEl) return;

    if (filtered.length === 0) {
      tableBodyEl.innerHTML = `
        <div class="empty-state">
          <span>ไม่พบ Tag ตรงตามเงื่อนไขการค้นหา</span>
          <button class="btn btn-secondary" id="btnResetFilter">ล้างตัวกรองทั้งหมด</button>
        </div>
      `;
      const btnReset = document.getElementById('btnResetFilter');
      if (btnReset) {
        btnReset.onclick = () => {
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
      const boundTaskId = getTagTask(tag.name);

      let valText = '—';
      if (state.liveMode && tag.observed_value !== undefined) {
        valText = tag.type === 'Binary Tag' || tag.type === 'Bool'
          ? (tag.observed_value ? 'TRUE' : 'FALSE')
          : String(tag.observed_value);
      }

      return `
        <div class="table-row ${isNavActive ? 'is-active-nav' : ''}" role="row" data-tag-name="${escapeHtml(tag.name)}" data-index="${idx}" aria-selected="${isChecked}">
          <div class="cell-checkbox" onclick="event.stopPropagation()">
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
          <div class="cell-task mono">${boundTaskId ? escapeHtml(boundTaskId) : ''}</div>
          <div class="cell-actions" onclick="event.stopPropagation()">
            <button class="btn-quick-task" data-quick-tag="${escapeHtml(tag.name)}" title="ผูกกับ ${escapeHtml(state.recentTaskId)} ทันที">+ Task</button>
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

    if (state.activeModal.type === 'inspector') {
      renderInspectorModal(contentEl, state.activeModal.tagName);
    } else if (state.activeModal.type === 'task_dialog') {
      renderTaskDialogModal(contentEl, state.activeModal.taskId);
    } else if (state.activeModal.type === 'bulk_add') {
      renderBulkAddModal(contentEl);
    }
  }

  function renderInspectorModal(container, tagName) {
    const tag = state.tags.find(t => t.name === tagName);
    if (!tag) {
      closeModal();
      return;
    }

    const boundTaskId = getTagTask(tag.name);
    const statusKey = getTagStatus(tag);
    const statusDef = STATUS_DEFS[statusKey];
    const taskOptions = state.tasks.map(t =>
      `<option value="${t.id}" ${t.id === (boundTaskId || state.recentTaskId) ? 'selected' : ''}>${t.id} · ${escapeHtml(t.name)} (${(t.tags || []).length} Tags)</option>`
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
            <dd class="mono">${state.liveMode && tag.observed_value !== undefined ? escapeHtml(tag.observed_value) : '— ยังไม่มีการสังเกตสด'}</dd>
            <dt>เวลาที่ตรวจล่าสุด</dt>
            <dd>${statusKey === 'NO' ? 'ยังไม่มีประวัติการอ่านสด' : '2 วินาทีที่แล้ว'}</dd>
            <dt>คำอธิบาย Tag</dt>
            <dd>${escapeHtml(tag.comment || 'ไม่มีคำอธิบาย')}</dd>
          </dl>

          <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--line)">
            <h4 style="margin:0 0 8px 0;font-size:13px;font-weight:600">การผูกกับ WinCC Task</h4>
            <div style="font-size:12.5px;color:var(--mut);margin-bottom:8px">
              ${boundTaskId ? `Tag นี้ผูกอยู่กับ <b>${boundTaskId}</b>` : 'Tag นี้ยังไม่ได้ผูกกับ Task ใด'}
            </div>
            <div class="form-row" style="margin-bottom:8px">
              <select id="modalTaskSelect" class="in" style="flex:1" aria-label="เลือก Task">${taskOptions}</select>
              <button class="btn btn-primary" id="btnAssignToTask">${boundTaskId ? 'ย้ายเข้า Task นี้' : 'เพิ่มเข้า Task'}</button>
            </div>
            ${boundTaskId ? `<button class="btn btn-danger" id="btnUnassignTask" style="font-size:12.5px">เอาออกจาก ${boundTaskId}</button>` : ''}
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
        sendBridge('add_tag_to_task', { tag_name: tag.name, task_id: selTask });
        showToast(`เพิ่ม ${tag.name} เข้า ${selTask} เรียบร้อยแล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
        closeModal();
      };
    }

    const btnUnassign = document.getElementById('btnUnassignTask');
    if (btnUnassign && boundTaskId) {
      btnUnassign.onclick = () => {
        sendBridge('remove_tag_from_task', { tag_name: tag.name, task_id: boundTaskId });
        showToast(`เอา ${tag.name} ออกจาก ${boundTaskId} แล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
        closeModal();
      };
    }
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
          <tr style="border-bottom:1px solid var(--line)">
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
              <label class="form-check">
                <input type="checkbox" id="chkActionLog" ${currentTask.action_log ? 'checked' : ''}>
                <span>บันทึกประวัติในเครื่อง (Local CSV & SQLite)</span>
              </label>
              <label class="form-check">
                <input type="checkbox" id="chkActionNotify" ${currentTask.action_notify ? 'checked' : ''}>
                <span>แจ้งเตือนผ่าน Telegram</span>
                <button type="button" class="btn btn-ghost" id="btnF6Link" style="padding:0 4px;font-size:12px;margin-left:auto">ตั้งค่าที่ F6 →</button>
              </label>
              <label class="form-check" style="margin-top:6px;border-top:1px solid var(--line);padding-top:8px">
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
        const nextNum = state.tasks.length + 1;
        const newId = `TASK-${pad(nextNum)}`;
        sendBridge('create_task', {
          task: {
            id: newId,
            name: `Task เฝ้าระวังใหม่ ${pad(nextNum)}`,
            cycle_sec: 5,
            action_log: true,
            action_notify: false,
            active: false,
            tags: []
          }
        });
        state.activeModal.taskId = newId;
        showToast(`สร้างร่าง ${newId} เรียบร้อยแล้ว`, null);
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
          active: document.getElementById('chkTaskActive').checked
        };
        sendBridge('save_task', { task: updatedTask });
        showToast(`บันทึกการตั้งค่า ${currentTask.id} เรียบร้อยแล้ว`, null);
        closeModal();
      };
    }

    const btnF6 = document.getElementById('btnF6Link');
    if (btnF6) {
      btnF6.onclick = () => {
        closeModal();
        sendBridge('navigate_f6', {});
      };
    }

    const chkSelectAll = document.getElementById('chkSelectAllAssigned');
    if (chkSelectAll) {
      chkSelectAll.onchange = () => {
        const boxes = document.querySelectorAll('[data-assigned-checkbox]');
        boxes.forEach(b => b.checked = chkSelectAll.checked);
      };
    }

    const btnRemoveSelected = document.getElementById('btnRemoveSelectedAssigned');
    if (btnRemoveSelected) {
      btnRemoveSelected.onclick = () => {
        const selectedNames = [];
        document.querySelectorAll('[data-assigned-checkbox]:checked').forEach(b => {
          selectedNames.push(b.dataset.assignedCheckbox);
        });
        if (selectedNames.length === 0) return;

        sendBridge('remove_tags_from_task', { tag_names: selectedNames, task_id: currentTask.id });
        showToast(`เอา ${selectedNames.length} Tag ออกจาก ${currentTask.id} แล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
      };
    }

    const btnClearAll = document.getElementById('btnClearAllAssigned');
    if (btnClearAll) {
      btnClearAll.onclick = () => {
        if (assignedTags.length === 0) return;
        sendBridge('remove_tags_from_task', { tag_names: [...assignedTags], task_id: currentTask.id });
        showToast(`ล้าง Tag ทั้งหมดจาก ${currentTask.id} แล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
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
        sendBridge('add_tags_to_task', { tag_names: tagList, task_id: targetTaskId });
        showToast(`เพิ่ม ${tagList.length} Tag เข้า ${targetTaskId} เรียบร้อยแล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
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

  // --- Toast with Undo ---
  function showToast(message, undoCallback) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    if (state.toastTimeout) {
      clearTimeout(state.toastTimeout);
      state.toastTimeout = null;
    }

    toastContainer.innerHTML = `
      <div class="toast-item">
        <span class="toast-msg">${escapeHtml(message)}</span>
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
            sendBridge('remove_tags_from_task', { tag_names: matching, task_id: t.id });
          }
        });
        state.checkedTags.clear();
        showToast(`เอา ${tagList.length} Tag ออกจาก Task แล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
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

      // Quick + Task button clicks
      const quickBtn = e.target.closest('[data-quick-tag]');
      if (quickBtn) {
        const tagName = quickBtn.dataset.quickTag;
        sendBridge('add_tag_to_task', { tag_name: tagName, task_id: state.recentTaskId });
        showToast(`เพิ่ม ${tagName} เข้า ${state.recentTaskId} แล้ว`, () => {
          sendBridge('undo_last_action', {});
        });
        return;
      }

      // Checkbox clicks (with Shift+Click range support)
      const chkBox = e.target.closest('[data-checkbox-name]');
      if (chkBox) {
        const tagName = chkBox.dataset.checkboxName;
        const clickedIdx = parseInt(chkBox.dataset.checkboxIndex, 10);
        const filtered = getFilteredTags();

        if (e.shiftKey && state.lastCheckedIndex >= 0 && state.lastCheckedIndex < filtered.length) {
          const start = Math.min(state.lastCheckedIndex, clickedIdx);
          const end = Math.max(state.lastCheckedIndex, clickedIdx);
          const targetChecked = chkBox.checked;
          for (let i = start; i <= end; i++) {
            if (filtered[i]) {
              if (targetChecked) state.checkedTags.add(filtered[i].name);
              else state.checkedTags.delete(filtered[i].name);
            }
          }
        } else {
          if (chkBox.checked) state.checkedTags.add(tagName);
          else state.checkedTags.delete(tagName);
          state.lastCheckedIndex = clickedIdx;
        }

        renderCatalogTable();
        renderFloatingActionBar();
        return;
      }

      // Table Row click -> Open Inspector Modal
      const tableRow = e.target.closest('.table-row');
      if (tableRow && !e.target.closest('.cell-checkbox') && !e.target.closest('.cell-actions')) {
        const tagName = tableRow.dataset.tagName;
        const rowIdx = parseInt(tableRow.dataset.index, 10);
        state.activeRowIndex = rowIdx;
        openInspector(tagName);
        return;
      }

      // Close modal on clicking outside card
      if (e.target.id === 'modalOverlay') {
        closeModal();
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
            if (state.checkedTags.has(tName)) state.checkedTags.delete(tName);
            else state.checkedTags.add(tName);
            state.lastCheckedIndex = state.activeRowIndex;
            renderCatalogTable();
            renderFloatingActionBar();
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

  // --- Exposed F1 Public API for Python Host ---
  window.F1 = {
    onStateUpdated: function (incoming) {
      if (!incoming) return;
      if (Array.isArray(incoming.tags)) state.tags = incoming.tags;
      if (Array.isArray(incoming.tasks)) state.tasks = incoming.tasks;
      if (incoming.recentTaskId) state.recentTaskId = incoming.recentTaskId;
      if (incoming.liveMode !== undefined) state.liveMode = !!incoming.liveMode;
      render();
    },

    openTaskDialog: function (taskId) {
      openTaskDialog(taskId);
    },

    setMode: function (mode) {
      if (mode === 'task_manager') {
        openTaskDialog();
      } else {
        closeModal();
      }
    },

    refresh: function () {
      sendBridge('get_state', {});
    }
  };

  // --- Bootstrap on Load ---
  document.addEventListener('DOMContentLoaded', () => {
    setupEvents();
    render();
    // Notify host that UI is ready to receive state
    sendBridge('get_state', {});
  });

})();
