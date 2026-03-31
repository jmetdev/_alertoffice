// Edit Group Modal Logic
const editModalEl = document.getElementById('edit-group-modal');
const editModal = new window.bootstrap.Modal(editModalEl);
const editForm = document.getElementById('edit-group-form');
const editName = document.getElementById('edit-name');
const editDescription = document.getElementById('edit-description');
const editExtension = document.getElementById('edit-extension');
const editDevicesInput = document.getElementById('edit-devices-input');
const editSelectedEl = document.getElementById('edit-selected-devices');
const editResultsEl = document.getElementById('edit-search-results');
const editSearchBtn = document.getElementById('edit-search-btn');
const editSearchInput = document.getElementById('edit-device-search');
const editDeviceTable = document.getElementById('edit-device-table');
const editError = document.getElementById('edit-error');
const editAction = document.getElementById('edit-action');
const editTestBtn = document.getElementById('edit-test-btn');
let editSelected = new Set();
let editDebounceTimer = null;
let activeGroupId = null;
/** Latest device_ips / status_map / reachability from GET /api/groups/:id (for table refresh) */
let editGroupDeviceCache = { device_ips: {}, status_map: {}, reachability: {} };

function renderEditSelected() {
  editSelectedEl.innerHTML = '';
  if (editSelected.size === 0) {
    editSelectedEl.innerHTML = '<li class="list-group-item text-muted">No devices selected</li>';
  } else {
    Array.from(editSelected).sort().forEach((name) => {
      const li = document.createElement('li');
      li.className = 'list-group-item d-flex justify-content-between align-items-center';
      li.textContent = name;
      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn btn-sm btn-outline-danger';
      removeBtn.textContent = 'Remove';
      removeBtn.onclick = () => {
        editSelected.delete(name);
        editDevicesInput.value = JSON.stringify(Array.from(editSelected));
        renderEditSelected();
        renderEditDeviceTable();
      };
      li.appendChild(removeBtn);
      editSelectedEl.appendChild(li);
    });
  }
  editDevicesInput.value = JSON.stringify(Array.from(editSelected));
  updateEditResultMarks();
}

function formatReachability(r) {
  if (!r || r.http_ok === null || r.http_ok === undefined) {
    return '—';
  }
  if (r.http_ok === true) {
    return `200 ${r.http_status != null ? '(' + r.http_status + ')' : ''}`.trim();
  }
  const st = r.http_status != null ? String(r.http_status) : '';
  const err = r.http_error ? String(r.http_error) : 'not 200';
  return st ? `${st} — ${err}` : err;
}

function formatCucmWeb(r) {
  if (!r) return '—';
  if (r.web_access_label) return String(r.web_access_label);
  if (r.tkwebaccess != null && r.tkwebaccess !== '') return `tk=${r.tkwebaccess}`;
  if (r.axl_error) return `AXL: ${r.axl_error}`;
  return '—';
}

function renderEditDeviceTable(ipMap, statusMap, reachMap) {
  const ips = ipMap !== undefined ? ipMap : editGroupDeviceCache.device_ips;
  const stats = statusMap !== undefined ? statusMap : editGroupDeviceCache.status_map;
  const reach = reachMap !== undefined ? reachMap : editGroupDeviceCache.reachability;
  editDeviceTable.innerHTML = '';
  if (editSelected.size === 0) {
    editDeviceTable.innerHTML = '<tr><td colspan="5" class="text-muted">No devices selected</td></tr>';
  } else {
    Array.from(editSelected).sort().forEach((name) => {
      const tr = document.createElement('tr');
      const ip = ips[name] || 'Not found';
      const status = stats[name] || 'Unknown';
      const r = reach[name];
      const httpCol = formatReachability(r);
      const cucmCol = formatCucmWeb(r);
      tr.innerHTML = `<td>${name}</td><td>${ip}</td><td>${status}</td><td>${httpCol}</td><td>${cucmCol}</td>`;
      editDeviceTable.appendChild(tr);
    });
  }
}

function updateEditResultMarks() {
  const items = editResultsEl.querySelectorAll('[data-device]');
  items.forEach((item) => {
    const deviceName = item.dataset.device;
    const isSelected = editSelected.has(deviceName);
    const check = item.querySelector('.selected-check');
    if (check) {
      check.textContent = isSelected ? '✓' : '';
    }
    item.disabled = isSelected;
    item.classList.toggle('disabled', isSelected);
  });
}

async function searchEditDevices() {
  const q = editSearchInput.value.trim();
  editResultsEl.innerHTML = '';
  if (q.length < 3) return;
  editResultsEl.innerHTML = '<div class="text-muted">Searching...</div>';
  const res = await fetch(`/api/devices?q=${encodeURIComponent(q)}`);
  const data = await res.json();
  editResultsEl.innerHTML = '';
  if (!data.length) {
    const empty = document.createElement('div');
    empty.className = 'text-muted';
    empty.textContent = 'No devices found';
    editResultsEl.appendChild(empty);
    return;
  }
  data.forEach((row) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'list-group-item list-group-item-action';
    item.dataset.device = row.device_name;
    const title = document.createElement('div');
    title.className = 'fw-bold';
    title.textContent = row.device_name;
    const meta = document.createElement('div');
    meta.className = 'text-muted small';
    const pool = row.device_pool || 'No device pool';
    const desc = row.description || 'No description';
    meta.textContent = `${pool} • ${desc}`;
    const check = document.createElement('div');
    check.className = 'selected-check text-success fw-bold';
    check.textContent = editSelected.has(row.device_name) ? '✓' : '';
    item.appendChild(title);
    item.appendChild(meta);
    item.appendChild(check);
    item.onclick = () => {
      editSelected.add(row.device_name);
      renderEditSelected();
      renderEditDeviceTable();
    };
    editResultsEl.appendChild(item);
  });
  updateEditResultMarks();
}

function debouncedEditSearch() {
  if (editDebounceTimer) {
    clearTimeout(editDebounceTimer);
  }
  editDebounceTimer = setTimeout(searchEditDevices, 300);
}

editSearchBtn.addEventListener('click', searchEditDevices);
editSearchInput.addEventListener('input', debouncedEditSearch);
editSearchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    searchEditDevices();
  }
});

document.querySelectorAll('[data-group-id]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const groupId = btn.dataset.groupId;
    activeGroupId = groupId;
    editError.classList.add('d-none');
    editError.textContent = '';
    editAction.classList.add('d-none');
    editAction.textContent = '';
    const res = await fetch(`/api/groups/${groupId}`);
    if (!res.ok) {
      editError.textContent = 'Unable to load group details.';
      editError.classList.remove('d-none');
      return;
    }
    const data = await res.json();
    editGroupDeviceCache = {
      device_ips: data.device_ips || {},
      status_map: data.status_map || {},
      reachability: data.reachability || {},
    };
    const group = data.group;
    editForm.action = `/groups/${group.id}/edit`;
    editName.value = group.name || '';
    editDescription.value = group.description || '';
    editExtension.value = group.extension || '';
    editSelected = new Set(group.devices || []);
    renderEditSelected();
    renderEditDeviceTable(data.device_ips, data.status_map, data.reachability);
    editModal.show();
  });
});

editTestBtn.addEventListener('click', async () => {
  if (!activeGroupId) return;
  editAction.classList.add('d-none');
  editAction.textContent = '';
  editAction.classList.remove('alert-info', 'alert-danger', 'alert-success');
  const extension = (editExtension.value || '8888').trim();
  editTestBtn.disabled = true;
  try {
    const res = await fetch(`/api/groups/${activeGroupId}/dial`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ extension })
    });
    const data = await res.json();
    if (!res.ok) {
      editAction.textContent = data.error || 'Unable to send command.';
      editAction.classList.add('alert-danger');
      editAction.classList.remove('d-none');
      return;
    }
    editAction.textContent = `Queued dial to ${data.device_count} phones (ext ${data.extension}).`;
    editAction.classList.add('alert-success');
    editAction.classList.remove('d-none');
  } finally {
    editTestBtn.disabled = false;
  }
});
