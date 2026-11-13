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
  let returnModalFocus = null;

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

  function sendMutatingBridge(action, payload, successMsg, undoCb, onResult) {
    const reqId = getNextRequestId();
    const fullPayload = { ...(payload || {}), request_id: reqId };
    if (successMsg) {
      pendingSuccessMessages[reqId] = { message: successMsg, undoCb, onResult };
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

  function recentTask() {
    return state.tasks.find(task => task.id === state.recentTaskId) || state.tasks[0];
  }

  function focusTarget(element = document.activeElement) {
    if (!element || element === document.body) return null;
    const row = element.closest('.table-row, .assigned-tag-row');
    if (row) {
      const attr = row.matches('.table-row') ? 'data-tag-name' : 'data-assigned-tag';
      const selector = `[${attr}="${CSS.escape(row.getAttribute(attr))}"]`;
      const control = ['data-quick-tag', 'data-inspect-tag', 'data-checkbox-name', 'data-assigned-checkbox']
        .find(name => element.hasAttribute(name));
      return () => document.querySelector(control ? `${selector} [${control}]` : selector);
    }
    return () => element.isConnected ? element : element.id ? document.getElementById(element.id) : null;
  }

  function getTagStatus(tag) {
    return tag && Object.hasOwn(STATUS_DEFS, tag.status) ? tag.status : 'NO';
  }

  function observationAge(tag) {
    if (!tag.observation_at) return '';
    const timestamp = Date.parse(tag.observation_at);
    const time = Number.isFinite(timestamp) ? new Date(timestamp).toLocaleTimeString('th-TH', {
      timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    }) : 'เวลาในหลักฐานไม่ถูกต้อง';
    return `<small class="observation-age" title="${escapeHtml(tag.observation_at)}">ข้อมูลล่าสุดเมื่อ ${escapeHtml(time)}${tag.age_text ? ' · ' + escapeHtml(tag.age_text) : ''}</small>`;
  }

  function tagStatusContent(tag, includeValue = false) {
    const status = getTagStatus(tag);
    const def = STATUS_DEFS[status];
    const label = status === 'FAIL' && tag.quality === 'UNCERTAIN' ? 'คุณภาพไม่แน่นอน' : def.label;
    const value = tag.observed_value;
    const shownValue = typeof value === 'boolean' ? (value ? 'TRUE' : 'FALSE') : value;
    return `<span>${def.icon}</span><span>${label}</span>` +
      (includeValue && status !== 'NO' && value != null
        ? `<span class="mono"> · ${escapeHtml(shownValue)}</span>` : '') + observationAge(tag);
  }

  function tagStatusStyle(tag) {
    const def = STATUS_DEFS[getTagStatus(tag)];
    return `--c:var(${def.colorVar});--t:var(${def.tintVar})`;
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

  function render(preserveTaskForm = false) {
    renderKpis();
    renderGroupSidebar();
    renderCatalogTable();
    renderFloatingActionBar();
    if (!preserveTaskForm || state.activeModal?.type !== 'task_dialog') renderModal();
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
      const alternative = state.tags.find(tag => tag.observation_source && tag.observation_source !== 'OPC UA');
      const caption = alternative?.observation_source ||
        (kpis.unv < kpis.total ? 'หลักฐานการอ่าน OPC UA' : `แคตตาล็อก WinCC (${kpis.total} Tags)`);
      ribbonEl.innerHTML = `<span class="badge" style="background:var(--accent-tint);color:var(--link);border:1px solid var(--line-strong)">● ${escapeHtml(caption)}</span>`;
    }
  }

  function renderGroupSidebar() {
    const groupsListEl = document.getElementById('groupsList');
    if (!groupsListEl) return;

    // Count tags per group
    const counts = new Map();
    state.tags.forEach(t => {
      const g = t.group || 'Default';
      counts.set(g, (counts.get(g) || 0) + 1);
    });

    document.getElementById('groupCount').textContent = `${counts.size} กลุ่ม`;
    const groupKeys = ['all', ...new Set([
      ...Object.keys(GROUP_METADATA).filter(key => counts.has(key)), ...counts.keys()
    ])];
    groupsListEl.innerHTML = groupKeys.map(key => {
      const meta = GROUP_METADATA[key];
      const isSelected = state.selectedGroup === key;
      const count = key === 'all' ? state.tags.length : counts.get(key);

      return `
        <button class="group-btn ${isSelected ? 'is-selected' : ''}" data-group="${escapeHtml(key)}" role="tab" aria-selected="${isSelected}">
          <div class="title-row">
            <span>${escapeHtml(meta?.name || key)}</span>
            <em>${count}</em>
          </div>
          <small>${escapeHtml(meta?.desc || '')}</small>
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

    const restore = tableBodyEl.contains(document.activeElement) ? focusTarget() : null;
    const filtered = getFilteredTags();
    document.getElementById('catalogCounter').textContent = `แสดง ${filtered.length} จาก ${state.tags.length} รายการ`;

    if (filtered.length === 0) {
      const noCatalog = state.tags.length === 0;
      tableBodyEl.innerHTML = `
        <div class="empty-state" role="status">
          <span>${noCatalog ? 'ยังไม่มีคลัง Tag จึงยังแสดงค่าตรวจวัดไม่ได้ เปิดคลัง Tag แล้วรีเฟรชจากไฟล์ที่ได้รับอนุญาต' : 'ไม่พบ Tag ตรงกับเงื่อนไขการค้นหา'}</span>
          <button class="btn ${noCatalog ? 'btn-primary' : 'btn-secondary'}" id="btnResetFilters" style="margin-top:8px">${noCatalog ? 'เปิดคลัง Tag · F5' : 'ล้างตัวกรองทั้งหมด'}</button>
        </div>`;
      document.getElementById('btnResetFilters').onclick = () => {
        if (noCatalog) { sendBridge('key_event', {key: 'F5'}); return; }
        state.selectedGroup = 'all'; state.statusFilter = 'ALL'; state.searchQuery = '';
        state.activeRowIndex = -1; state.lastCheckedIndex = -1;
        const search = document.getElementById('searchInput');
        if (search) search.value = '';
        render();
      };
      if (restore) document.getElementById('tableViewport').focus({ preventScroll: true });
      return;
    }

    const query = state.searchQuery;
    const targetTask = recentTask();
    const quickTitle = targetTask ? `ผูกกับ ${targetTask.id} ทันที` : 'เปิดหน้าจัดการเพื่อสร้าง Task';
    tableBodyEl.innerHTML = filtered.map((tag, idx) => {
      const isChecked = state.checkedTags.has(tag.name);
      const isNavActive = state.activeRowIndex === idx;
      const boundTasks = getTagTasks(tag.name);
      const boundText = boundTasks.map(t => escapeHtml(t.id)).join(', ');

      return `
        <div class="table-row ${isNavActive ? 'is-active-nav' : ''}" role="row" tabindex="0" data-tag-name="${escapeHtml(tag.name)}" data-index="${idx}" aria-selected="${isChecked}">
          <div class="cell-checkbox">
            <input type="checkbox" data-checkbox-name="${escapeHtml(tag.name)}" data-checkbox-index="${idx}" ${isChecked ? 'checked' : ''} aria-label="เลือก ${escapeHtml(tag.name)}">
          </div>
          <div class="cell-tag-name mono" title="${escapeHtml(tag.name)}">${highlightMatch(tag.name, query)}${boundTasks.length ? `<small class="task-count" title="${boundText}"> · ${boundTasks.length} Task</small>` : ''}</div>
          <div class="cell-group" title="${escapeHtml(getGroupName(tag.group))}">${escapeHtml(getGroupName(tag.group))}</div>
          <div class="cell-type mono" title="${escapeHtml(tag.type || 'Word')}">${escapeHtml(tag.type || 'Word')}</div>
          <div class="cell-status" data-status="${getTagStatus(tag)}" style="${tagStatusStyle(tag)}">${tagStatusContent(tag, true)}</div>
          <div class="cell-actions">
            <button class="btn btn-secondary btn-compact btn-quick-task" data-quick-tag="${escapeHtml(tag.name)}" title="${escapeHtml(quickTitle)}" aria-label="${escapeHtml(quickTitle)} ${escapeHtml(tag.name)}">+ Task</button>
            <button class="btn btn-ghost btn-compact btn-inspect" data-inspect-tag="${escapeHtml(tag.name)}" title="ตรวจสอบรายละเอียด" aria-label="ตรวจสอบรายละเอียด ${escapeHtml(tag.name)}">ดู</button>
          </div>
        </div>
      `;
    }).join('');
    if (restore) (restore() || document.getElementById('tableViewport')).focus({ preventScroll: true });
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

  let taskDialogVisible = false;
  function reportTaskDialog() {
    const visible = state.activeModal?.type === 'task_dialog';
    if (taskDialogVisible === visible) return;
    taskDialogVisible = visible;
    window.webkit?.messageHandlers?.f1Presentation?.postMessage(JSON.stringify({taskDialogOpen: visible}));
  }

  function renderModal() {
    reportTaskDialog();
    const overlayEl = document.getElementById('modalOverlay');
    const contentEl = document.getElementById('modalContent');
    if (!overlayEl || !contentEl) return;

    if (!state.activeModal) {
      if (overlayEl.open) {
        overlayEl.close();
        contentEl.replaceChildren();
        document.getElementById('modalToastContainer').replaceChildren();
        (returnModalFocus?.() || document.getElementById('searchInput'))?.focus({ preventScroll: true });
      }
      returnModalFocus = null;
      return;
    }

    const restore = contentEl.contains(document.activeElement) ? focusTarget() : null;
    const modalType = state.activeModal.type;

    if (modalType === 'inspector') {
      renderInspectorModal(contentEl, state.activeModal.tagName);
    } else if (modalType === 'task_dialog') {
      const currentForm = contentEl.querySelector('.modal-card[data-task-id]');
      const draft = currentForm && currentForm.dataset.taskId === state.activeModal.taskId ? readTaskForm() : null;
      renderTaskDialogModal(contentEl, state.activeModal.taskId, draft);
    } else if (modalType === 'bulk_add') {
      renderBulkAddModal(contentEl);
    }
    if (!overlayEl.open) overlayEl.showModal();
    if (!contentEl.contains(document.activeElement)) {
      (restore?.() || contentEl.querySelector('#btnCloseModal'))?.focus({ preventScroll: true });
    }
  }

  function renderInspectorModal(container, tagName) {
    const tag = state.tags.find(t => t.name === tagName);
    if (!tag) {
      container.innerHTML = `<div class="modal-card"><div class="modal-body"><h3 id="modalTitle">ไม่พบข้อมูล Tag</h3><button class="btn" id="btnCloseModal">ปิด</button></div></div>`;
      document.getElementById('btnCloseModal').onclick = closeModal;
      return;
    }

    const boundTasks = getTagTasks(tag.name);
    const statusKey = getTagStatus(tag);

    const taskOptions = state.tasks.map(t =>
      `<option value="${escapeHtml(t.id)}" ${t.id === recentTask()?.id ? 'selected' : ''}>${escapeHtml(t.id)} · ${escapeHtml(t.name)}</option>`
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
            <table style="width:100%;font-size:13.5px;border-collapse:collapse">${rows}</table>
          </div>
        </details>
      `;
    }

    const boundTasksHtml = boundTasks.length === 0
      ? `<div style="color:var(--mut);font-size:13.5px;margin-bottom:8px">Tag นี้ยังไม่ได้ผูกกับ Task ใด</div>`
      : `
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">
          ${boundTasks.map(bt => `
            <span class="badge" style="background:var(--surface-3);color:var(--ink);border:1px solid var(--line);padding:3px 8px;border-radius:4px;display:inline-flex;align-items:center;gap:6px;font-size:13.5px">
              <b>${escapeHtml(bt.id)}</b>: ${escapeHtml(bt.name || '')}
              <button type="button" class="btn-ghost" data-remove-bound-task="${escapeHtml(bt.id)}" data-tag-name="${escapeHtml(tag.name)}" title="เอาออกจาก ${escapeHtml(bt.id)}" aria-label="เอาออกจาก ${escapeHtml(bt.id)}" style="padding:0 2px;cursor:pointer;color:var(--fail)">✕</button>
            </span>
          `).join('')}
        </div>
      `;

    container.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3 class="mono" id="modalTitle">${escapeHtml(tag.name)}</h3>
          <button class="btn btn-ghost icon-button btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body">
          ${statusKey === 'NO' ? `<div class="waiting-guidance"><p>ยังไม่มีหลักฐานอ่าน Tag นี้ ตรวจการตั้งค่า OPC UA ใน F6 ก่อนเริ่มอ่านด้วยตนเอง</p><button type="button" id="btnWaitingF6" class="btn btn-primary">ตั้งค่า OPC UA · F6</button></div>` : ''}
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span class="sub">${escapeHtml(getGroupName(tag.group))} · ${escapeHtml(tag.type || 'Word')}</span>
            <div class="cell-status" id="inspectorStatus" style="${tagStatusStyle(tag)}">${tagStatusContent(tag)}</div>
          </div>

          <dl class="detail-grid">
            <dt>ที่อยู่ PLC / S7 Offset</dt>
            <dd class="mono">${escapeHtml(tag.addr || 'Internal')}</dd>
            <dt>Connection</dt>
            <dd class="mono">${escapeHtml(tag.conn || 'Internal')}</dd>
            <dt>ค่าล่าสุด</dt>
            <dd class="mono" id="inspectorValue">${statusKey !== 'NO' && tag.observed_value != null ? escapeHtml(tag.observed_value) : '—'}</dd>
            <dt>แหล่งข้อมูล</dt>
            <dd id="inspectorSource">${escapeHtml(tag.observation_source || '—')}</dd>
            <dt>เวลาต้นทาง</dt>
            <dd id="inspectorAge">${escapeHtml([tag.observation_at, tag.age_text].filter(Boolean).join(' · ') || '—')}</dd>
            <dt>คำอธิบาย Tag</dt>
            <dd>${escapeHtml(tag.comment || 'ไม่มีคำอธิบาย')}</dd>
          </dl>

          <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--line)">
            <h4 style="margin:0 0 8px 0;font-size:13.5px;font-weight:600">การผูกกับ WinCC Task (${boundTasks.length} Task)</h4>
            ${boundTasksHtml}
            <div class="form-row" style="margin-top:8px">
              <select id="modalTaskSelect" class="in" style="flex:1" aria-label="เลือก Task">${taskOptions}</select>
              <button class="btn ${statusKey === 'NO' ? 'btn-secondary' : 'btn-primary'}" id="btnAssignToTask">เพิ่มเข้า Task นี้</button>
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

    const waitingF6 = document.getElementById('btnWaitingF6');
    if (waitingF6) waitingF6.onclick = () => sendBridge('navigate_f6', {});
    const btnAssign = document.getElementById('btnAssignToTask');
    if (btnAssign) {
      btnAssign.onclick = () => {
        const selTask = document.getElementById('modalTaskSelect').value;
        if (!selTask) {
          openTaskDialog();
          return;
        }
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

  function readTaskForm() {
    return {
      name: document.getElementById('inputTaskName').value,
      cycle_sec: Number(document.getElementById('selectTaskCycle').value),
      action_log: document.getElementById('chkActionLog').checked,
      action_notify: document.getElementById('chkActionNotify').checked,
      active: document.getElementById('chkTaskActive').checked
    };
  }

  function renderTaskDialogModal(container, taskId, draft) {
    let currentTask = state.tasks.find(t => t.id === taskId);
    if (!currentTask && state.tasks.length > 0) {
      currentTask = state.tasks[0];
    }
    if (!currentTask) {
      currentTask = { id: 'TASK-01', name: 'Task ใหม่', cycle_sec: 5, action_log: true, action_notify: false, active: false, tags: [] };
    }
    state.activeModal.taskId = currentTask.id;
    if (draft) currentTask = { ...currentTask, ...draft };
    const cycle = Number(currentTask.cycle_sec);
    const customCycle = Number.isSafeInteger(cycle) && cycle > 0 && ![1, 5, 10, 30, 60].includes(cycle)
      ? `<option value="${cycle}" selected>${cycle} วินาที</option>` : '';

    const taskOptions = state.tasks.map(t =>
      `<option value="${escapeHtml(t.id)}" ${t.id === currentTask.id ? 'selected' : ''}>${escapeHtml(t.id)} · ${escapeHtml(t.name)} (${(t.tags || []).length} Tags)</option>`
    ).join('');

    const assignedTags = currentTask.tags || [];
    const assignedTagsRows = assignedTags.length === 0
      ? `<tr><td colspan="4" style="text-align:center;color:var(--mut);padding:18px">ยังไม่มี Tag ใน Task นี้<br><button class="btn btn-secondary" id="btnChooseTaskTags" style="margin-top:8px">กลับไปเลือก Tag ใน F1</button></td></tr>`
      : assignedTags.map((tn, idx) => {
        const tObj = state.tags.find(x => x.name === tn) || { type: 'Word', group: 'Default' };
        return `
          <tr class="assigned-tag-row" data-assigned-tag="${escapeHtml(tn)}" data-index="${idx}" role="row" tabindex="0">
            <td class="cell-assigned-check">
              <input type="checkbox" class="table-check" data-assigned-checkbox="${escapeHtml(tn)}" aria-label="เลือก ${escapeHtml(tn)}">
            </td>
            <td class="mono cell-assigned-name">${escapeHtml(tn)}</td>
            <td class="cell-assigned-group" style="color:var(--mut)">${escapeHtml(getGroupName(tObj.group))}</td>
            <td class="mono cell-assigned-type" style="color:var(--mut);font-size:13.5px">${escapeHtml(tObj.type || 'Word')}</td>
          </tr>
        `;
      }).join('');

    container.innerHTML = `
      <div class="modal-card wide" data-task-id="${escapeHtml(currentTask.id)}">
        <div class="modal-header">
          <h3 id="modalTitle">งานเฝ้าระวัง</h3>
          <button class="btn btn-ghost icon-button btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body task-dialog-body">
          <!-- Left Column: Task Settings Form -->
          <div class="task-settings-card">
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
              <label for="selectTaskCycle">รอบตรวจวัด</label>
              <select id="selectTaskCycle" class="in">
                <option value="1" ${currentTask.cycle_sec === 1 ? 'selected' : ''}>1 วินาที (High Priority)</option>
                <option value="5" ${currentTask.cycle_sec === 5 ? 'selected' : ''}>5 วินาที (มาตรฐาน WinCC V8.1)</option>
                <option value="10" ${currentTask.cycle_sec === 10 ? 'selected' : ''}>10 วินาที (General Monitoring)</option>
                <option value="30" ${currentTask.cycle_sec === 30 ? 'selected' : ''}>30 วินาที (Slow Sampling)</option>
                <option value="60" ${currentTask.cycle_sec === 60 ? 'selected' : ''}>60 วินาที</option>
                ${customCycle}
              </select>
            </div>

            <div style="background:var(--surface-2);border:1px solid var(--line);border-radius:var(--radius);padding:10px;margin-top:12px">
              <div style="font-weight:600;font-size:13.5px;color:var(--mut);margin-bottom:6px">เมื่อ Task ทำงาน</div>
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
                <button type="button" class="btn btn-ghost" id="btnF6Link" style="padding:2px 8px;font-size:13.5px;color:var(--accent);cursor:pointer;border:1px solid var(--line);border-radius:4px" title="เปิดการตั้งค่าเพื่อกรอก Bot Token และ Chat ID ในแท็บ Telegram">เปิดการตั้งค่า →</button>
              </div>

              <label class="form-check" style="cursor:pointer;display:flex;align-items:center;gap:8px;margin-top:6px;border-top:1px solid var(--line);padding-top:8px">
                <input type="checkbox" id="chkTaskActive" ${currentTask.active ? 'checked' : ''}>
                <span style="font-weight:600">เปิดใช้งาน Task นี้</span>
              </label>
            </div>

          </div>

          <!-- Right Column: Assigned Tags Table -->
          <div class="task-tags-card" style="display:flex;flex-direction:column;min-height:0">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <span style="font-weight:600;font-size:13.5px">Tag ใน Task (${assignedTags.length} รายการ)</span>
              <div style="display:flex;gap:6px">
                <button class="btn btn-secondary" id="btnRemoveSelectedAssigned" style="font-size:13.5px;padding:3px 8px">เอาที่เลือกออก</button>
                <button class="btn btn-secondary" id="btnClearAllAssigned" style="font-size:13.5px;padding:3px 8px">ล้างทั้งหมด</button>
              </div>
            </div>

            <div style="flex:1;max-height:320px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)">
              <table class="assigned-tags-table">
                <thead>
                  <tr>
                    <th style="width:40px;text-align:center" id="thAssignedCheck">
                      <input type="checkbox" id="chkSelectAllAssigned" class="table-check" aria-label="เลือกทั้งหมด">
                    </th>
                    <th style="cursor:pointer" id="thAssignedTagName" title="คลิกเพื่อเลือกทั้งหมด">ชื่อ Tag</th>
                    <th>กลุ่มอุปกรณ์</th>
                    <th>ชนิด</th>
                  </tr>
                </thead>
                <tbody id="assignedTagsTbody">${assignedTagsRows}</tbody>
              </table>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" id="btnCloseModalBottom">ปิดหน้าต่าง</button>
          <button class="btn btn-primary" id="btnSaveTaskForm">บันทึก Task</button>
        </div>
      </div>
    `;

    document.getElementById('btnCloseModal').onclick = closeModal;
    document.getElementById('btnCloseModalBottom').onclick = closeModal;

    const chooseTags = document.getElementById('btnChooseTaskTags');
    if (chooseTags) chooseTags.onclick = closeModal;
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
        const modal = state.activeModal;
        const form = readTaskForm();
        const updatedTask = {
          ...form,
          id: currentTask.id,
          name: form.name.trim() || currentTask.id,
          cycle_sec: form.cycle_sec || 5,
          tags: currentTask.tags || []
        };
        btnSave.disabled = true;
        sendMutatingBridge(
          'save_task',
          { task: updatedTask },
          `บันทึกการตั้งค่า ${currentTask.id} เรียบร้อยแล้ว`, null,
          ok => {
            if (state.activeModal !== modal || modal.taskId !== currentTask.id) return;
            if (ok) closeModal();
            else {
              btnSave.disabled = false;
              btnSave.focus({ preventScroll: true });
            }
          }
        );
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

    let lastAssignedIndex = -1;

    function syncAssignedSelectionUI() {
      const allRows = container.querySelectorAll('.assigned-tag-row');
      let checkedCount = 0;
      allRows.forEach(row => {
        const chk = row.querySelector('[data-assigned-checkbox]');
        const isChecked = !!(chk && chk.checked);
        if (isChecked) checkedCount++;
        row.classList.toggle('is-selected', isChecked);
        row.setAttribute('aria-selected', isChecked ? 'true' : 'false');
      });

      const chkSelectAll = document.getElementById('chkSelectAllAssigned');
      if (chkSelectAll) {
        if (allRows.length === 0) {
          chkSelectAll.checked = false;
          chkSelectAll.indeterminate = false;
        } else if (checkedCount === allRows.length) {
          chkSelectAll.checked = true;
          chkSelectAll.indeterminate = false;
        } else if (checkedCount > 0) {
          chkSelectAll.checked = false;
          chkSelectAll.indeterminate = true;
        } else {
          chkSelectAll.checked = false;
          chkSelectAll.indeterminate = false;
        }
      }

      const btnRemoveSelected = document.getElementById('btnRemoveSelectedAssigned');
      if (btnRemoveSelected) {
        if (checkedCount > 0) {
          btnRemoveSelected.textContent = `เอาที่เลือกออก (${checkedCount})`;
          btnRemoveSelected.classList.remove('btn-secondary');
          btnRemoveSelected.classList.add('btn-fail-active');
        } else {
          btnRemoveSelected.textContent = 'เอาที่เลือกออก';
          btnRemoveSelected.classList.remove('btn-fail-active');
          btnRemoveSelected.classList.add('btn-secondary');
        }
      }
    }

    function toggleAssignedRow(row, isShift, forceState) {
      const chk = row.querySelector('[data-assigned-checkbox]');
      if (!chk) return;
      const rowIdx = parseInt(row.dataset.index, 10);
      const allRows = Array.from(container.querySelectorAll('.assigned-tag-row'));

      if (isShift && lastAssignedIndex >= 0 && lastAssignedIndex < allRows.length) {
        const start = Math.min(lastAssignedIndex, rowIdx);
        const end = Math.max(lastAssignedIndex, rowIdx);
        const targetState = forceState !== undefined ? forceState : !chk.checked;
        for (let i = start; i <= end; i++) {
          const r = allRows[i];
          const c = r.querySelector('[data-assigned-checkbox]');
          if (c) c.checked = targetState;
        }
      } else {
        chk.checked = forceState !== undefined ? forceState : !chk.checked;
        lastAssignedIndex = rowIdx;
      }
      syncAssignedSelectionUI();
    }

    const tbody = container.querySelector('#assignedTagsTbody');
    if (tbody) {
      tbody.onclick = (e) => {
        const row = e.target.closest('.assigned-tag-row');
        if (!row) return;
        if (e.target.type === 'checkbox') {
          toggleAssignedRow(row, e.shiftKey, e.target.checked);
        } else {
          e.preventDefault();
          toggleAssignedRow(row, e.shiftKey);
        }
      };

      tbody.onkeydown = (e) => {
        const row = e.target.closest('.assigned-tag-row');
        if (!row) return;
        if (e.key === ' ' || e.code === 'Space') {
          e.preventDefault();
          toggleAssignedRow(row, e.shiftKey);
        } else if (row && e.key === 'ArrowDown') {
          const next = row.nextElementSibling;
          if (next && next.classList.contains('assigned-tag-row')) {
            e.preventDefault();
            next.focus();
          }
        } else if (row && e.key === 'ArrowUp') {
          const prev = row.previousElementSibling;
          if (prev && prev.classList.contains('assigned-tag-row')) {
            e.preventDefault();
            prev.focus();
          }
        }
      };
    }

    // Select all assigned checkboxes
    const chkSelectAll = document.getElementById('chkSelectAllAssigned');
    const thSelectAll = document.getElementById('thAssignedTagName');
    if (chkSelectAll) {
      chkSelectAll.onchange = () => {
        const boxes = container.querySelectorAll('[data-assigned-checkbox]');
        boxes.forEach(b => b.checked = chkSelectAll.checked);
        syncAssignedSelectionUI();
      };
    }
    if (thSelectAll) {
      thSelectAll.onclick = (e) => {
        if (chkSelectAll && e.target !== chkSelectAll) {
          chkSelectAll.checked = !chkSelectAll.checked;
          chkSelectAll.onchange();
        }
      };
    }

    // Remove selected assigned tags
    const btnRemoveSelected = document.getElementById('btnRemoveSelectedAssigned');
    if (btnRemoveSelected) {
      btnRemoveSelected.onclick = () => {
        const selectedNames = [];
        container.querySelectorAll('[data-assigned-checkbox]:checked').forEach(b => {
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
      `<option value="${escapeHtml(t.id)}" ${t.id === recentTask()?.id ? 'selected' : ''}>${escapeHtml(t.id)} · ${escapeHtml(t.name)} (${(t.tags || []).length} Tags)</option>`
    ).join('');

    container.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3 id="modalTitle">เพิ่ม ${selectedCount} Tag เข้าสู่ Task</h3>
          <button class="btn btn-ghost icon-button btn-close-modal" id="btnCloseModal" aria-label="ปิด">✕</button>
        </div>
        <div class="modal-body">
          <p style="margin:0 0 12px 0;font-size:13.5px;color:var(--ink)">
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

  function openModal(modal) {
    if (!state.activeModal) returnModalFocus = focusTarget();
    state.activeModal = modal;
    renderModal();
  }

  function openInspector(tagName) {
    openModal({ type: 'inspector', tagName });
  }

  function openTaskDialog(taskId) {
    openModal({ type: 'task_dialog', taskId: taskId || recentTask()?.id });
  }

  function openBulkAddDialog() {
    if (state.checkedTags.size === 0) return;
    if (!recentTask()) {
      openTaskDialog();
      return;
    }
    openModal({ type: 'bulk_add' });
  }

  function closeModal() {
    state.activeModal = null;
    renderModal();
  }

  // --- Toast with Undo & Error Support ---
  function showToast(message, undoCallback, isError) {
    const modalToast = document.getElementById('modalToastContainer');
    const pageToast = document.getElementById('toastContainer');
    const toastContainer = document.getElementById('modalOverlay').open ? modalToast : pageToast;
    if (!toastContainer) return;
    modalToast.replaceChildren();
    pageToast.replaceChildren();

    if (state.toastTimeout) {
      clearTimeout(state.toastTimeout);
      state.toastTimeout = null;
    }

    const toastBg = isError ? 'var(--fail-tint)' : 'var(--surface-3)';
    const toastBorder = isError ? 'var(--fail)' : 'var(--line-strong)';
    const toastColor = isError ? 'var(--fail)' : 'var(--ink)';

    toastContainer.innerHTML = `
      <div class="toast-item" role="alert" style="background:${toastBg};border-color:${toastBorder};color:${toastColor}">
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
    document.getElementById('btnRefreshCatalog').addEventListener('click', () => sendBridge('key_event', {key: 'F7'}));
    document.getElementById('modalOverlay').addEventListener('cancel', event => {
      event.preventDefault();
      closeModal();
    });

    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.oninput = (e) => {
        state.searchQuery = e.target.value.trim().toLowerCase();
        state.activeRowIndex = -1;
        state.lastCheckedIndex = -1;
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
        state.activeRowIndex = -1;
        state.lastCheckedIndex = -1;
        render();
        return;
      }

      // Group sidebar clicks
      const groupBtn = e.target.closest('[data-group]');
      if (groupBtn) {
        state.selectedGroup = groupBtn.dataset.group;
        state.activeRowIndex = -1;
        state.lastCheckedIndex = -1;
        render();
        return;
      }

      // Quick + Task button clicks in catalog row
      const quickBtn = e.target.closest('[data-quick-tag]');
      if (quickBtn) {
        e.stopPropagation();
        const tagName = quickBtn.dataset.quickTag;
        const task = recentTask();
        if (!task) {
          openTaskDialog();
          return;
        }
        sendMutatingBridge(
          'add_tag_to_task',
          { tag_name: tagName, task_id: task.id },
          `เพิ่ม ${tagName} เข้า ${task.id} แล้ว`,
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

      // Catalog Table Row Click: Seamless toggling without requiring clicking the small checkbox
      const tableRow = e.target.closest('.table-row');
      if (tableRow && !e.target.closest('.cell-actions')) {
        const tagName = tableRow.dataset.tagName;
        const rowIdx = parseInt(tableRow.dataset.index, 10);
        if (!e.target.matches('input')) tableRow.focus({ preventScroll: true });
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
      // Program Settings shortcuts (F6 or Ctrl+,)
      if (e.key === 'F6' || (e.ctrlKey && (e.key === ',' || e.code === 'Comma'))) {
        e.preventDefault();
        sendBridge('navigate_f6', {});
        return;
      }

      // F1 and F2 shortcuts within Unified Workspace
      if (e.key === 'F2') {
        e.preventDefault();
        openTaskDialog(state.recentTaskId);
        return;
      }
      if (e.key === 'F1') {
        e.preventDefault();
        closeModal();
        return;
      }

      // Other F-keys passed to GTK host
      if (/^F[3-9]$/.test(e.key)) {
        e.preventDefault();
        sendBridge('key_event', { key: e.key });
        return;
      }

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

      if (state.activeModal) return;
      const active = document.activeElement;
      const row = active?.matches('.table-row') ? active : null;
      const viewport = document.getElementById('tableViewport');
      const fromSearch = active === searchInput && e.key === 'ArrowDown';
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') &&
          (row || active === viewport || active === document.body || fromSearch)) {
        const rows = viewport.querySelectorAll('.table-row');
        if (!rows.length) return;
        const delta = e.key === 'ArrowDown' ? 1 : -1;
        const next = row ? rows[Math.max(0, Math.min(rows.length - 1, Number(row.dataset.index) + delta))]
          : rows[delta > 0 ? 0 : rows.length - 1];
        viewport.querySelector('.is-active-nav')?.classList.remove('is-active-nav');
        next.classList.add('is-active-nav');
        state.activeRowIndex = Number(next.dataset.index);
        next.focus({ preventScroll: true });
        next.scrollIntoView({ block: 'nearest' });
        e.preventDefault();
      } else if (row && e.key === 'Enter') {
        openInspector(row.dataset.tagName);
        e.preventDefault();
      } else if (row && (e.key === ' ' || e.code === 'Space')) {
        toggleTagSelection(row.dataset.tagName, Number(row.dataset.index), e.shiftKey);
        e.preventDefault();
      }
    });
  }

  // --- Public API for WebKit Bridge Host ---
  window.F1 = {
    onStateUpdated(newState) {
      if (!newState) return;
      if (newState.tags) state.tags = newState.tags;
      if (newState.tasks) state.tasks = newState.tasks;
      if (newState.recentTaskId) state.recentTaskId = newState.recentTaskId;
      render(true);
    },

    onObservationsUpdated(updates) {
      if (!Array.isArray(updates) || !updates.length) return;
      const byName = new Map(updates.map(update => [update.name, update]));
      let changeFilter = false;
      for (const tag of state.tags) {
        const update = byName.get(tag.name);
        if (!update) continue;
        changeFilter ||= state.statusFilter !== 'ALL' &&
          (getTagStatus(tag) === state.statusFilter) !== (getTagStatus(update) === state.statusFilter);
        Object.assign(tag, update);
      }
      renderKpis();
      if (changeFilter) {
        state.activeRowIndex = -1;
        state.lastCheckedIndex = -1;
        renderCatalogTable();
      } else {
        for (const row of document.querySelectorAll('.table-row')) {
          const update = byName.get(row.dataset.tagName);
          if (!update) continue;
          const cell = row.querySelector('.cell-status');
          cell.setAttribute('style', tagStatusStyle(update));
          cell.dataset.status = getTagStatus(update);
          cell.innerHTML = tagStatusContent(update, true);
        }
      }
      if (state.activeModal?.type === 'inspector') {
        const update = byName.get(state.activeModal.tagName);
        const status = document.getElementById('inspectorStatus');
        if (update && status) {
          status.setAttribute('style', tagStatusStyle(update));
          status.innerHTML = tagStatusContent(update);
          document.getElementById('inspectorValue').textContent = getTagStatus(update) !== 'NO'
            ? update.observed_value ?? '—' : '—';
          document.getElementById('inspectorSource').textContent = update.observation_source || '—';
          document.getElementById('inspectorAge').textContent =
            [update.observation_at, update.age_text].filter(Boolean).join(' · ') || '—';
        }
      }
    },

    onBridgeResponse(resp) {
      if (!resp) return;
      const entry = pendingSuccessMessages[resp.request_id];
      if (entry) delete pendingSuccessMessages[resp.request_id];
      if (resp.ok) {
        if (resp.state) {
          if (resp.state.tags) state.tags = resp.state.tags;
          if (resp.state.tasks) state.tasks = resp.state.tasks;
          if (resp.state.recentTaskId) state.recentTaskId = resp.state.recentTaskId;
        }
        entry?.onResult?.(true);
        render(!entry);
        if (entry) showToast(entry.message, entry.undoCb);
      } else {
        entry?.onResult?.(false);
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
