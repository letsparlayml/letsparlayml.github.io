async function loadJson(path, fallback = null) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${path}`);
    return await res.json();
  } catch (err) {
    if (fallback !== null) return fallback;
    throw err;
  }
}

function byId(id) {
  return document.getElementById(id);
}

function hasNumericValue(v) {
  return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
}

function fmt(num, digits = 1) {
  const n = Number(num);
  return Number.isFinite(n) ? n.toFixed(digits) : 'N/A';
}

function fmtSigned(num, digits = 1) {
  const n = Number(num);
  if (!Number.isFinite(n)) return 'N/A';
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
}

function fmtPct(num, digits = 1) {
  const n = Number(num);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : 'N/A';
}

function fmtAmerican(num) {
  const n = Number(num);
  if (!Number.isFinite(n)) return 'N/A';
  return `${n >= 0 ? '+' : ''}${n.toFixed(0)}`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setText(id, value) {
  const el = byId(id);
  if (el) el.textContent = value ?? '';
}

function propCard(prop) {
  return `
    <article class="insight-card">
      <div class="insight-topline">
        <span class="tag">${escapeHtml(prop.stat || '')}</span>
        <span class="muted">${escapeHtml(prop.location || '')}</span>
      </div>
      <h4>${escapeHtml(prop.player || '')}</h4>
      <p class="muted">${escapeHtml(prop.team || '')} vs ${escapeHtml(prop.opp || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Line ${escapeHtml(fmt(prop.line, 1))}</span>
        <span class="mini-chip">Model ${escapeHtml(fmt(prop.pred_anchor ?? prop.mu_cons, 1))}</span>
        <span class="mini-chip">Prob ${escapeHtml(fmtPct(prop.prob_cons))}</span>
      </div>
      <div class="mini-chip-row">
        <span class="mini-chip">L10 ${escapeHtml(fmtPct(prop.hit_r10))}</span>
        <span class="mini-chip">L25 ${escapeHtml(fmtPct(prop.hit_r25))}</span>
        <span class="mini-chip">Min ${escapeHtml(fmt(prop.expMin, 1))}</span>
      </div>
      <p class="insight-copy">${escapeHtml(prop.boardDriver || prop.summary || '')}</p>
    </article>
  `;
}

function roleCard(prop) {
  const gap = Number(prop.trend_gap);
  return `
    <article class="insight-card compact-card">
      <div class="insight-topline">
        <span class="tag">${escapeHtml(prop.stat || '')}</span>
        <span class="muted">${Number.isFinite(gap) ? fmtSigned(gap, 1) : 'N/A'} vs avg</span>
      </div>
      <h4>${escapeHtml(prop.player || '')}</h4>
      <p class="muted">${escapeHtml(prop.team || '')} vs ${escapeHtml(prop.opp || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Line ${escapeHtml(fmt(prop.line, 1))}</span>
        <span class="mini-chip">Model ${escapeHtml(fmt(prop.pred_anchor, 1))}</span>
        <span class="mini-chip">Avg ${escapeHtml(fmt(prop.avg_anchor, 1))}</span>
      </div>
      <p class="insight-copy">${escapeHtml(prop.summary || '')}</p>
    </article>
  `;
}

function renderGrid(rootId, items, role = false, limit = 9) {
  const root = byId(rootId);
  if (!root) return;
  const list = (items || []).slice(0, limit);
  if (!list.length) {
    root.innerHTML = '<div class="empty-state">No props match the current filters.</div>';
    return;
  }
  root.innerHTML = list.map(item => role ? roleCard(item) : propCard(item)).join('');
}

function populateDateOptions(select, dates, targetDate) {
  dates.forEach(date => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = date;
    if (date === targetDate) option.selected = true;
    select.appendChild(option);
  });
}

function populateStatOptions(select, props) {
  select.innerHTML = '<option value="ALL">All</option>';
  [...new Set((props || []).map(p => p.stat).filter(Boolean))].sort().forEach(stat => {
    const option = document.createElement('option');
    option.value = stat;
    option.textContent = stat;
    select.appendChild(option);
  });
}

function filterProps(props) {
  const stat = byId('lab-stat-filter')?.value || 'ALL';
  const q = (byId('lab-search')?.value || '').trim().toLowerCase();
  return (props || []).filter(p => {
    const statOk = stat === 'ALL' || p.stat === stat;
    const searchOk = !q || String(p.player || '').toLowerCase().includes(q);
    return statOk && searchOk;
  });
}

function explorerRow(prop) {
  return `
    <tr>
      <td><strong>${escapeHtml(prop.player || '')}</strong><br /><span class="muted">${escapeHtml(prop.team || '')} • ${escapeHtml(prop.location || '')}</span></td>
      <td>${escapeHtml(prop.matchup || `${prop.team || ''} vs ${prop.opp || ''}`)}</td>
      <td>${escapeHtml(prop.stat || '')}</td>
      <td>${escapeHtml(fmt(prop.line, 1))}</td>
      <td>${escapeHtml(fmt(prop.pred_anchor ?? prop.mu_cons, 1))}</td>
      <td>${escapeHtml(fmt(prop.avg_anchor, 1))}</td>
      <td>${escapeHtml(fmtPct(prop.hit_r10))}</td>
      <td>${escapeHtml(fmtPct(prop.hit_r25))}</td>
      <td>${escapeHtml(fmtPct(prop.prob_cons))}</td>
      <td>${escapeHtml(fmtAmerican(prop.fair_american))}</td>
      <td>${escapeHtml(fmt(prop.expMin, 1))}</td>
      <td>${escapeHtml(prop.summary || '')}</td>
    </tr>
  `;
}

function renderExplorer(props) {
  const body = byId('lab-explorer-body');
  if (!body) return;
  const filtered = filterProps(props);
  if (!filtered.length) {
    body.innerHTML = '<tr><td colspan="12">No props match the current filters.</td></tr>';
    return;
  }
  body.innerHTML = filtered.map(explorerRow).join('');
}

function applyDate(lab, date) {
  const day = lab?.byDate?.[date];
  if (!day) return;
  setText('lab-date-hero', date);
  setText('lab-prop-count', String(day.meta?.propCount || 0));
  setText('lab-consensus-count', String(day.meta?.consensusCount || 0));
  setText('lab-floor-count', String(day.meta?.floorCount || 0));
  setText('lab-ceiling-count', String(day.meta?.ceilingCount || 0));
  populateStatOptions(byId('lab-stat-filter'), day.allProps || []);
  renderGrid('lab-consensus-grid', day.sections?.consensus || [], false, 9);
  renderGrid('lab-floor-grid', day.sections?.floor || [], false, 8);
  renderGrid('lab-consistency-grid', day.sections?.consistency || [], false, 8);
  renderGrid('lab-ceiling-grid', day.sections?.ceiling || [], false, 9);
  renderGrid('lab-role-up-grid', day.sections?.roleUp || [], true, 8);
  renderGrid('lab-role-down-grid', day.sections?.roleDown || [], true, 8);
  renderExplorer(day.allProps || []);
}

(async function init() {
  try {
    const [site, lab] = await Promise.all([
      loadJson('data/site.json', {}),
      loadJson('data/nba_props_lab.json')
    ]);
    const dateSelect = byId('lab-date-filter');
    const statSelect = byId('lab-stat-filter');
    const searchInput = byId('lab-search');
    const targetDate = site?.targetDate || lab.targetDate || lab.dates?.[0];
    populateDateOptions(dateSelect, lab.dates || [], targetDate);
    const rerender = () => applyDate(lab, dateSelect.value);
    dateSelect.addEventListener('change', rerender);
    statSelect.addEventListener('change', () => applyDate(lab, dateSelect.value));
    searchInput.addEventListener('input', () => applyDate(lab, dateSelect.value));
    applyDate(lab, targetDate);
  } catch (err) {
    const root = byId('lab-consensus-grid');
    if (root) root.innerHTML = `<div class="empty-state">Failed to load props lab data: ${escapeHtml(err.message || err)}</div>`;
  }
})();
