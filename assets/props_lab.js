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

function normalizeLookupToken(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeTeamToken(value) {
  return String(value ?? '')
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
    .trim();
}

function canonicalInjuryStatus(value) {
  const raw = String(value ?? '').trim().toLowerCase();
  if (!raw) return '';
  const map = {
    p: 'probable',
    probable: 'probable',
    q: 'questionable',
    questionable: 'questionable',
    gtd: 'questionable',
    out: 'out',
    o: 'out',
    doubtful: 'doubtful',
    d: 'doubtful'
  };
  return map[raw] || raw;
}

function titleCaseWord(value) {
  if (!value) return '';
  return String(value).charAt(0).toUpperCase() + String(value).slice(1).toLowerCase();
}

function buildInjuryLookup(injuryData) {
  const lookup = new Map();
  const players = injuryData?.players || injuryData?.entries || [];
  (players || []).forEach(entry => {
    const playerKey = normalizeLookupToken(entry.player || entry.player_name);
    if (!playerKey) return;

    const teamKey = normalizeTeamToken(entry.team || entry.team_abbr);
    const normalized = {
      status: titleCaseWord(canonicalInjuryStatus(entry.status)),
      note: entry.note || entry.injury_note || '',
      team: entry.team || entry.team_abbr || '',
      lastUpdated: entry.lastUpdated || entry.last_updated || entry.updated_at || '',
      gameDate: entry.gameDate || entry.game_date || ''
    };

    if (teamKey) {
      lookup.set(`${playerKey}|${teamKey}`, normalized);
    }
    if (!lookup.has(`${playerKey}|`)) {
      lookup.set(`${playerKey}|`, normalized);
    }
  });
  return lookup;
}

function getPropInjuryContext(prop, injuryLookup) {
  if (!injuryLookup || !injuryLookup.size) return null;
  const playerKey = normalizeLookupToken(prop?.player);
  if (!playerKey) return null;
  const teamKey = normalizeTeamToken(prop?.team);
  return injuryLookup.get(`${playerKey}|${teamKey}`) || injuryLookup.get(`${playerKey}|`) || null;
}

function decoratePropInjury(prop, injuryLookup) {
  const context = getPropInjuryContext(prop, injuryLookup);
  if (!context) return { ...prop };
  return {
    ...prop,
    injuryStatus: context.status || '',
    injuryNote: context.note || '',
    injuryUpdated: context.lastUpdated || ''
  };
}

function shouldHideProp(prop) {
  const status = canonicalInjuryStatus(prop?.injuryStatus || prop?.playerStatus || '');
  return status === 'out' || status === 'doubtful';
}

function propModelAnchor(prop) {
  const candidates = [prop?.pred_anchor, prop?.mu_cons, prop?.modelPrediction, prop?.model, prop?.prediction];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propLineCutoff(stat) {
  const s = String(stat || '').toUpperCase().trim();
  if (s === 'TPM' || s === '3PM') return 1;
  if (s === 'REB' || s === 'AST') return 2;
  if (s === 'PTS' || s === 'PRA') return 3;
  return 2;
}

function failsLineCutoff(prop) {
  const line = Number(prop?.line);
  const model = propModelAnchor(prop);
  if (!Number.isFinite(line) || !Number.isFinite(model)) return false;
  return line < (model - propLineCutoff(prop?.stat));
}

function applyInjuryContextToList(items, injuryLookup) {
  return (items || [])
    .map(item => decoratePropInjury(item, injuryLookup))
    .filter(item => !shouldHideProp(item))
    .filter(item => !failsLineCutoff(item));
}

function applyInjuryContextToLab(lab, injuryLookup) {
  if (!lab || !lab.byDate) return lab || {};
  const next = JSON.parse(JSON.stringify(lab));
  Object.keys(next.byDate).forEach(date => {
    const day = next.byDate[date];
    day.allProps = applyInjuryContextToList(day.allProps || [], injuryLookup);
    if (day.meta) day.meta.propCount = day.allProps.length;
    Object.keys(day.sections || {}).forEach(key => {
      day.sections[key] = applyInjuryContextToList(day.sections[key] || [], injuryLookup);
    });
  });
  return next;
}

function injuryBadgeHtml(prop) {
  const status = canonicalInjuryStatus(prop?.injuryStatus || prop?.playerStatus || '');
  if (status !== 'probable' && status !== 'questionable') return '';
  return `<span class="injury-badge injury-${status}">${escapeHtml(titleCaseWord(status))}</span>`;
}

function playerBadgeHtml(name, prop) {
  return `<span class="player-with-badge"><span class="player-name-only">${escapeHtml(name || '')}</span>${injuryBadgeHtml(prop)}</span>`;
}

function propTeamValue(prop) {
  return prop?.team || prop?.team_abbr || prop?.teamAbbr || '';
}

function propOppValue(prop) {
  return prop?.opp || prop?.opponent || prop?.opp_abbr || prop?.opponent_abbr || '';
}

function normalizeGameId(a, b) {
  const parts = [normalizeTeamToken(a), normalizeTeamToken(b)].filter(Boolean).sort();
  return parts.join('|');
}

function propGameId(prop) {
  return normalizeGameId(propTeamValue(prop), propOppValue(prop));
}

function propGameLabel(prop) {
  const a = propTeamValue(prop);
  const b = propOppValue(prop);
  if (a && b) {
    const teams = [a, b].sort();
    return `${teams[0]} vs ${teams[1]}`;
  }
  return '';
}

function propAnalyzerHref(prop) {
  const params = new URLSearchParams();
  const date = prop?.date || prop?.gameDate || prop?.targetDate || '';
  if (date) params.set('date', String(date));
  if (prop?.playerId || prop?.PLAYER_ID) {
    params.set('playerId', String(prop.playerId || prop.PLAYER_ID));
  } else if (prop?.player) {
    params.set('player', String(prop.player));
  }
  if (prop?.stat || prop?.stat_display) params.set('stat', String(prop.stat || prop.stat_display).toUpperCase());
  if (prop?.line !== undefined && prop?.line !== null && prop?.line !== '') params.set('line', String(prop.line));
  return `props_analyzer.html?${params.toString()}`;
}

function getFilters() {
  return {
    stat: byId('lab-stat-filter')?.value || 'ALL',
    game: byId('game-filter')?.value || 'ALL',
    query: (byId('lab-search')?.value || '').trim().toLowerCase()
  };
}

function propMatchesFilters(prop, filters = getFilters()) {
  if (shouldHideProp(prop) || failsLineCutoff(prop)) return false;

  const statOk = filters.stat === 'ALL' || String(prop.stat || '').toUpperCase() === filters.stat;
  if (!statOk) return false;

  const gameOk = filters.game === 'ALL' || propGameId(prop) === filters.game;
  if (!gameOk) return false;

  if (!filters.query) return true;

  const haystack = [
    prop.player,
    prop.team,
    prop.opp,
    prop.stat,
    prop.matchup,
    prop.summary,
    prop.boardDriver,
    prop.injuryStatus,
    prop.injuryNote
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return haystack.includes(filters.query);
}

function filterProps(props, filters = getFilters()) {
  return (props || []).filter(prop => propMatchesFilters(prop, filters));
}

function propCard(prop) {
  return `
    <article class="insight-card">
      <div class="insight-topline">
        <span class="tag">${escapeHtml(prop.stat || '')}</span>
        <span class="muted">${escapeHtml(prop.location || '')}</span>
      </div>
      <h4>${playerBadgeHtml(prop.player || '', prop)}</h4>
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
      <div class="insight-card-actions">
        <a class="insight-link" href="${propAnalyzerHref(prop)}">Open analyzer</a>
      </div>
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
      <h4>${playerBadgeHtml(prop.player || '', prop)}</h4>
      <p class="muted">${escapeHtml(prop.team || '')} vs ${escapeHtml(prop.opp || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Line ${escapeHtml(fmt(prop.line, 1))}</span>
        <span class="mini-chip">Model ${escapeHtml(fmt(prop.pred_anchor, 1))}</span>
        <span class="mini-chip">Avg ${escapeHtml(fmt(prop.avg_anchor, 1))}</span>
      </div>
      <p class="insight-copy">${escapeHtml(prop.summary || '')}</p>
      <div class="insight-card-actions">
        <a class="insight-link" href="${propAnalyzerHref(prop)}">Open analyzer</a>
      </div>
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
  if (!select) return;
  select.innerHTML = '';
  (dates || []).forEach(date => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = date;
    if (date === targetDate) option.selected = true;
    select.appendChild(option);
  });
}

function populateStatOptions(select, props, selectedValue = 'ALL') {
  if (!select) return;
  const stats = [...new Set((props || []).map(p => p.stat).filter(Boolean))].sort();
  select.innerHTML = '<option value="ALL">All</option>';
  stats.forEach(stat => {
    const option = document.createElement('option');
    option.value = String(stat).toUpperCase();
    option.textContent = stat;
    select.appendChild(option);
  });
  const desired = String(selectedValue || 'ALL').toUpperCase();
  select.value = stats.map(s => String(s).toUpperCase()).includes(desired) ? desired : 'ALL';
}

function populateGameOptions(select, props, selectedValue = 'ALL') {
  if (!select) return;
  const seen = new Map();
  (props || []).forEach(prop => {
    const id = propGameId(prop);
    const label = propGameLabel(prop);
    if (id && label && !seen.has(id)) {
      seen.set(id, label);
    }
  });

  select.innerHTML = '<option value="ALL">All games</option>';

  Array.from(seen.entries())
    .sort((a, b) => a[1].localeCompare(b[1]))
    .forEach(([id, label]) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = label;
      select.appendChild(option);
    });

  select.value = seen.has(selectedValue) ? selectedValue : 'ALL';
}

function filterBoardItems(items, filters) {
  return filterProps(items || [], filters);
}

function explorerRow(prop) {
  return `
    <tr>
      <td><a class="table-link" href="${propAnalyzerHref(prop)}">${playerBadgeHtml(prop.player || '', prop)}</a><br /><span class="muted">${escapeHtml(prop.team || '')} • ${escapeHtml(prop.location || '')}</span></td>
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

function renderExplorer(props, filters) {
  const body = byId('lab-explorer-body');
  if (!body) return;
  const filtered = filterProps(props, filters);
  if (!filtered.length) {
    body.innerHTML = '<tr><td colspan="12">No props match the current filters.</td></tr>';
    return;
  }
  body.innerHTML = filtered.map(explorerRow).join('');
}

function applyDate(lab, date) {
  const day = lab?.byDate?.[date];
  if (!day) return;

  const currentFilters = getFilters();
  populateStatOptions(byId('lab-stat-filter'), day.allProps || [], currentFilters.stat);
  populateGameOptions(byId('game-filter'), day.allProps || [], currentFilters.game);

  const filters = getFilters();
  const filteredAll = filterProps(day.allProps || [], filters);

  setText('lab-date-hero', date);
  setText('lab-prop-count', `${filteredAll.length}/${String(day.meta?.propCount || 0)}`);
  setText('lab-consensus-count', String(filterBoardItems(day.sections?.consensus || [], filters).length));
  setText('lab-floor-count', String(filterBoardItems(day.sections?.floor || [], filters).length));
  setText('lab-ceiling-count', String(filterBoardItems(day.sections?.ceiling || [], filters).length));

  renderGrid('lab-consensus-grid', filterBoardItems(day.sections?.consensus || [], filters), false, 9);
  renderGrid('lab-floor-grid', filterBoardItems(day.sections?.floor || [], filters), false, 8);
  renderGrid('lab-consistency-grid', filterBoardItems(day.sections?.consistency || [], filters), false, 8);
  renderGrid('lab-ceiling-grid', filterBoardItems(day.sections?.ceiling || [], filters), false, 9);
  renderGrid('lab-role-up-grid', filterBoardItems(day.sections?.roleUp || [], filters), true, 8);
  renderGrid('lab-role-down-grid', filterBoardItems(day.sections?.roleDown || [], filters), true, 8);
  renderExplorer(day.allProps || [], filters);
}

(async function init() {
  try {
    const [site, rawLab, injuries] = await Promise.all([
      loadJson('data/site.json', {}),
      loadJson('data/nba_props_lab.json'),
      loadJson('data/nba_injuries.json', {})
    ]);
    const injuryLookup = buildInjuryLookup(injuries);
    const lab = applyInjuryContextToLab(rawLab, injuryLookup);
    const dateSelect = byId('lab-date-filter');
    const statSelect = byId('lab-stat-filter');
    const gameSelect = byId('game-filter');
    const searchInput = byId('lab-search');

    const dates = lab.dates || [];
    const now = new Date();
    const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const targetDate =
      (dates.includes(todayIso) && todayIso) ||
      (dates.includes(site?.targetDate) && site.targetDate) ||
      (dates.includes(lab?.targetDate) && lab.targetDate) ||
      dates[0];

    populateDateOptions(dateSelect, dates, targetDate);

    const rerender = () => applyDate(lab, dateSelect.value);
    dateSelect?.addEventListener('change', rerender);
    statSelect?.addEventListener('change', rerender);
    gameSelect?.addEventListener('change', rerender);
    searchInput?.addEventListener('input', rerender);

    applyDate(lab, targetDate);
  } catch (err) {
    const root = byId('lab-consensus-grid');
    if (root) root.innerHTML = `<div class="empty-state">Failed to load props lab data: ${escapeHtml(err.message || err)}</div>`;
  }
})();