async function loadJson(path, fallback = null) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Unable to load ${path}:`, err);
    return fallback;
  }
}

function byId(id) {
  return document.getElementById(id);
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function hasNumericValue(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

function fmt(num, digits = 1) {
  return hasNumericValue(num) ? Number(num).toFixed(digits) : '—';
}

function fmtPct(num, digits = 1) {
  return hasNumericValue(num) ? `${(Number(num) * 100).toFixed(digits)}%` : '—';
}

function fmtSigned(num, digits = 1) {
  if (!hasNumericValue(num)) return '—';
  return `${num >= 0 ? '+' : ''}${Number(num).toFixed(digits)}`;
}

function fmtAmerican(num) {
  if (!hasNumericValue(num)) return '—';
  const rounded = Math.round(num);
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function analyzerDisplayLabel(point) {
  const label = String(point?.label || point?.shortLabel || point?.gameDate || '');
  if (!label) return '';
  return /^\d{4}-\d{2}-\d{2}$/.test(label) ? label.slice(5) : label;
}

function denverTodayIso() {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Denver',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).formatToParts(new Date());
    const get = type => parts.find(p => p.type === type)?.value || '';
    const year = get('year');
    const month = get('month');
    const day = get('day');
    return year && month && day ? `${year}-${month}-${day}` : '';
  } catch (err) {
    return new Date().toISOString().slice(0, 10);
  }
}

function preferredAvailableDate(dates, requestedDate = '') {
  const list = [...new Set((dates || []).filter(Boolean).map(String))].sort();
  if (!list.length) return '';
  const today = denverTodayIso();

  if (requestedDate && list.includes(String(requestedDate)) && String(requestedDate) >= today) {
    return String(requestedDate);
  }

  const todayExact = list.find(d => d === today);
  if (todayExact) return todayExact;

  const future = list.find(d => d >= today);
  if (future) return future;

  return list[list.length - 1];
}

function leagueConfig(league) {
  const key = String(league || 'NBA').toUpperCase();
  return {
    league: key,
    title: `${key} props analyzer`,
    eyebrow: `${key} props analyzer`,
    indexPath: key === 'MLB' ? 'data/mlb_props_analyzer.json' : 'data/nba_props_analyzer.json',
    detailPrefix: key === 'MLB' ? 'data/mlb_props_analyzer' : 'data/nba_props_analyzer',
    buildCommand: key === 'MLB' ? 'tools/build_mlb_props_analyzer_json.py' : 'tools/build_nba_props_analyzer_json.py',
  };
}

function updateLeagueChrome(config) {
  document.title = `${config.title}`;
  const eyebrow = document.querySelector('.site-header .eyebrow');
  if (eyebrow) eyebrow.textContent = config.eyebrow;
  const title = document.querySelector('.site-header h1');
  if (title) title.textContent = 'Interactive prop matchup view';
  const subhead = document.querySelector('.site-header .subhead');
  if (subhead) {
    subhead.textContent = config.league === 'MLB'
      ? 'Preview MLB mode uses model probabilities plus recent rolling windows and priors. Full game-log detail can be added later when you wire in historical batter results.'
      : 'Use the daily analyzer build to inspect a player’s recent game log, home and away splits, closest matchup sample, and the current model context for the selected line.';
  }
  const labLink = document.querySelector('a[href="props_lab.html"]');
  if (labLink) labLink.textContent = config.league === 'MLB' ? 'NBA props lab' : 'NBA props lab';
}

function normalizeLookupToken(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function median(values) {
  const nums = (values || []).filter(hasNumericValue).slice().sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
}

function std(values) {
  const nums = (values || []).filter(hasNumericValue);
  if (!nums.length) return null;
  const mean = nums.reduce((sum, value) => sum + value, 0) / nums.length;
  const variance = nums.reduce((sum, value) => sum + (value - mean) ** 2, 0) / nums.length;
  return Math.sqrt(variance);
}

function calcStats(games, line) {
  const values = (games || []).map(g => Number(g.value)).filter(Number.isFinite);
  if (!values.length) {
    return { n: 0, avg: null, median: null, std: null, max: null, hitRate: null };
  }
  const hits = values.filter(v => v >= line).length;
  return {
    n: values.length,
    avg: values.reduce((sum, value) => sum + value, 0) / values.length,
    median: median(values),
    std: std(values),
    max: Math.max(...values),
    hitRate: hits / values.length,
  };
}

function simColor(bin) {
  switch (String(bin || '').toLowerCase()) {
    case 'closest 25%': return '#7bf1c8';
    case 'close 25%': return '#59b4ff';
    case 'mid 25%': return '#f8d66d';
    case 'far 25%': return '#ff7e79';
    default: return '#9db0d0';
  }
}

function updateHero(entry, series) {
  byId('analyzer-hero-date').textContent = entry?.gameDate || series?.gameDate || '—';
  byId('analyzer-hero-player').textContent = entry?.player || series?.player || '—';
  byId('analyzer-hero-line').textContent = entry ? `${entry.stat_display || entry.stat} ${fmt(entry.line, 1)}` : '—';
  byId('analyzer-hero-model').textContent = entry ? `${fmt(entry.pred_anchor ?? entry.mu_cons ?? series?.modelPred, 1)} (${fmtSigned((entry.pred_anchor ?? entry.mu_cons ?? series?.modelPred ?? 0) - (entry.line ?? 0), 1)})` : '—';
  byId('analyzer-hero-prob').textContent = entry ? fmtPct(entry.prob_cons) : '—';
}

function setStatus(html) {
  const node = byId('analyzer-status');
  if (node) node.innerHTML = html || '';
}

function filterByView(games, view) {
  const rows = games || [];
  const hasLocation = rows.some(g => Number(g.isHome) === 1 || Number(g.isHome) === 0);
  if (!hasLocation) return rows;
  if (view === 'home') return rows.filter(g => Number(g.isHome) === 1);
  if (view === 'away') return rows.filter(g => Number(g.isHome) === 0);
  return rows;
}

function recentWindowGames(series, view) {
  const list = filterByView(series?.games || [], view);
  const size = Number(series?.recentWindow) || 25;
  return list.slice(-size);
}

function renderKpis(entry, series, view) {
  const root = byId('analyzer-kpis');
  if (!root) return;
  if (!entry || !series) {
    root.innerHTML = '<div class="empty-state">No analyzer entry selected.</div>';
    return;
  }

  const currentGames = recentWindowGames(series, view);
  const overallGames = filterByView(series.games || [], view);
  const similarGames = series.similarGames || [];
  const sameOppGames = similarGames.filter(g => (g.opp || '') === (series.opp || ''));

  const recentStats = calcStats(currentGames, entry.line);
  const overallStats = calcStats(overallGames, entry.line);
  const similarStats = calcStats(similarGames, entry.line);
  const sameOppStats = calcStats(sameOppGames, entry.line);

  root.innerHTML = `
    <article class="hero-card kpi-card">
      <span class="stat-label">Matchup</span>
      <strong>${escapeHtml(series.matchup || `${entry.team || ''} vs ${entry.opp || ''}`)}</strong>
      <p class="muted">${escapeHtml(view === 'overall' ? 'All locations' : view === 'home' ? 'Home sample' : 'Away sample')}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Model edge</span>
      <strong>${fmtSigned((entry.pred_anchor ?? entry.mu_cons ?? series.modelPred ?? 0) - (entry.line ?? 0), 1)}</strong>
      <p class="muted">Model ${fmt(entry.pred_anchor ?? entry.mu_cons ?? series.modelPred, 1)} • line ${fmt(entry.line, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Recent hit rate</span>
      <strong>${fmtPct(recentStats.hitRate)}</strong>
      <p class="muted">${recentStats.n} games • avg ${fmt(recentStats.avg, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Full-sample hit rate</span>
      <strong>${fmtPct(overallStats.hitRate)}</strong>
      <p class="muted">${overallStats.n} games • avg ${fmt(overallStats.avg, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Closest-match average</span>
      <strong>${fmt(similarStats.avg, 1)}</strong>
      <p class="muted">${similarStats.n} most similar games • hit ${fmtPct(similarStats.hitRate)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Same-opp sample</span>
      <strong>${fmt(sameOppStats.avg, 1)}</strong>
      <p class="muted">${sameOppStats.n} games • hit ${fmtPct(sameOppStats.hitRate)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">${escapeHtml(series.contextMetricLabel || entry.contextMetricLabel || 'Expected minutes')}</span>
      <strong>${series.contextMetricValue ?? entry.contextMetricValue ?? fmt(entry.expMin ?? series.expMin, 1)}</strong>
      <p class="muted">Fair odds ${fmtAmerican(entry.fair_american)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Board context</span>
      <strong>${fmtPct(entry.prob_cons)}</strong>
      <p class="muted">${escapeHtml(entry.boardDriver || entry.driver_summary || entry.reason_flags || 'No driver text')}</p>
    </article>
  `;
}

function renderSummary(entry, series, view) {
  const body = byId('analyzer-summary-body');
  if (!body) return;
  if (!entry || !series) {
    body.innerHTML = '<tr><td colspan="6">No analyzer entry selected.</td></tr>';
    return;
  }
  const recentStats = calcStats(recentWindowGames(series, view), entry.line);
  const overallStats = calcStats(filterByView(series.games || [], view), entry.line);
  const similarStats = calcStats(series.similarGames || [], entry.line);
  const sameOppStats = calcStats((series.similarGames || []).filter(g => (g.opp || '') === (series.opp || '')), entry.line);
  const rows = [
    ['Recent sample', recentStats],
    ['Full sample', overallStats],
    ['Closest-match sample', similarStats],
    ['Same opponent inside closest sample', sameOppStats],
  ];
  body.innerHTML = rows.map(([label, stats]) => `
    <tr>
      <td>${escapeHtml(label)}</td>
      <td>${stats.n ?? '—'}</td>
      <td>${fmt(stats.avg, 1)}</td>
      <td>${fmt(stats.median, 1)}</td>
      <td>${fmt(stats.std, 1)}</td>
      <td>${fmtPct(stats.hitRate)}</td>
    </tr>
  `).join('');
}

function renderTableRows(rootId, games, line) {
  const body = byId(rootId);
  if (!body) return;
  if (!(games || []).length) {
    body.innerHTML = '<tr><td colspan="7">No samples available for this view.</td></tr>';
    return;
  }
  const rows = games.slice().sort((a, b) => {
    if (Number.isFinite(Number(a.seq)) || Number.isFinite(Number(b.seq))) {
      return Number(b.seq || 0) - Number(a.seq || 0);
    }
    return String(b.gameDate || '').localeCompare(String(a.gameDate || ''));
  }).slice(0, 12);
  body.innerHTML = rows.map(g => `
    <tr>
      <td>${escapeHtml(g.label || g.gameDate || '')}</td>
      <td>${escapeHtml(g.opp || '')}</td>
      <td>${escapeHtml(g.location || '')}</td>
      <td>${fmt(g.value, 1)}</td>
      <td>${fmt(g.minutes, 1)}</td>
      <td>${hasNumericValue(g.value) ? (g.value >= line ? 'Hit' : 'Miss') : '—'}</td>
      <td><span class="sim-pill" style="--sim-color:${simColor(g.simBin)}">${escapeHtml(g.simBin || 'all')}</span></td>
    </tr>
  `).join('');
}

function renderChart(entry, series, view) {
  const root = byId('analyzer-chart');
  if (!root) return;
  if (!entry || !series) {
    root.innerHTML = '<div class="empty-state">No analyzer entry selected.</div>';
    return;
  }
  const games = recentWindowGames(series, view);
  if (!games.length) {
    root.innerHTML = '<div class="empty-state">No recent games for this view.</div>';
    return;
  }

  const width = 860;
  const height = 320;
  const margin = { top: 18, right: 18, bottom: 48, left: 48 };
  const values = games.map(g => Number(g.value)).filter(Number.isFinite);
  const line = Number(entry.line);
  const topValue = Math.max(...values, line, 0);
  const y0 = 0;
  let y1 = Math.max(1, Math.ceil(topValue));
  if ((y1 - topValue) < 0.6) y1 += 1;
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const x = i => margin.left + (games.length === 1 ? plotW / 2 : (i / (games.length - 1)) * plotW);
  const y = value => margin.top + plotH - ((value - y0) / (y1 - y0 || 1)) * plotH;

  const niceIntegerStep = rawStep => {
    if (!Number.isFinite(rawStep) || rawStep <= 1) return 1;
    const power = 10 ** Math.floor(Math.log10(rawStep));
    const scaled = rawStep / power;
    if (scaled <= 1) return power;
    if (scaled <= 2) return 2 * power;
    if (scaled <= 5) return 5 * power;
    return 10 * power;
  };

  const tickStep = niceIntegerStep((y1 - y0) / 5);
  const ticks = [];
  for (let value = y0; value <= y1; value += tickStep) ticks.push(value);
  if (ticks[ticks.length - 1] !== y1) ticks.push(y1);

  const grid = ticks.map(value => {
    const py = y(value);
    return `<g><line x1="${margin.left}" x2="${width - margin.right}" y1="${py}" y2="${py}" stroke="rgba(255,255,255,.08)" /><text x="${margin.left - 10}" y="${py + 4}" fill="#9db0d0" font-size="11" text-anchor="end">${value}</text></g>`;
  }).join('');

  const poly = games.map((g, i) => `${x(i)},${y(Number(g.value))}`).join(' ');
  const dots = games.map((g, i) => {
    const cx = x(i);
    const cy = y(Number(g.value));
    return `<g>
      <circle cx="${cx}" cy="${cy}" r="5" fill="${simColor(g.simBin)}" stroke="#0b1220" stroke-width="1.5">
        <title>${escapeHtml(`${g.label || g.gameDate || ''} ${g.opp || ''} ${g.location || ''} — ${fmt(g.value, 1)}${hasNumericValue(g.minutes) ? ` in ${fmt(g.minutes, 1)} min` : ''} (${g.simBin || 'all'})`)}</title>
      </circle>
      <text x="${cx}" y="${height - 18}" fill="#9db0d0" font-size="10" text-anchor="middle">${escapeHtml(analyzerDisplayLabel(g))}</text>
    </g>`;
  }).join('');

  const lineY = y(line);
  root.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent prop trend chart">
      ${grid}
      <line x1="${margin.left}" x2="${width - margin.right}" y1="${lineY}" y2="${lineY}" stroke="#ff7e79" stroke-width="2" stroke-dasharray="7 6"></line>
      <polyline fill="none" stroke="#59b4ff" stroke-width="3" points="${poly}"></polyline>
      ${dots}
    </svg>
  `;
}

function syncViewButtons(view) {
  document.querySelectorAll('#analyzer-view-toggle button').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.view === view);
  });
}

function updateUrl(entry, selection, currentLeague) {
  if (!entry && !selection) return;
  const params = new URLSearchParams();
  const league = String(currentLeague || entry?.league || selection?.league || 'NBA').toUpperCase();
  params.set('league', league);
  if (entry?.gameDate || selection?.date) params.set('date', entry?.gameDate || selection?.date);
  if (entry?.playerId || selection?.playerId) params.set('playerId', String(entry?.playerId || selection?.playerId));
  if (!params.get('playerId') && (entry?.player || selection?.player)) params.set('player', String(entry?.player || selection?.player));
  if (entry?.stat || selection?.stat) params.set('stat', String(entry?.stat || selection?.stat).toUpperCase());
  if (entry?.line !== undefined && entry?.line !== null) params.set('line', String(entry.line));
  else if (selection?.line) params.set('line', String(selection.line));
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState({}, '', next);
}

function findInitialState(data, league) {
  const requestedDate = qs('date') || '';
  const resolvedDate = preferredAvailableDate(data?.dates || [], requestedDate || data?.targetDate || '');
  const entries = (data.entries || []).filter(e => !resolvedDate || e.gameDate === resolvedDate);
  const requestedPlayerId = qs('playerId');
  const requestedPlayer = normalizeLookupToken(qs('player'));
  let playerId = requestedPlayerId || '';
  if (!playerId && requestedPlayer) {
    const match = entries.find(e => normalizeLookupToken(e.player) === requestedPlayer);
    playerId = match?.playerId ? String(match.playerId) : '';
  }
  if (!playerId) playerId = entries[0]?.playerId ? String(entries[0].playerId) : '';
  const stat = (qs('stat') || entries.find(e => String(e.playerId) === String(playerId))?.stat || '').toUpperCase();
  const line = qs('line') || String(entries.find(e => String(e.playerId) === String(playerId) && String(e.stat).toUpperCase() === stat)?.line ?? '');
  return { league: String(league || 'NBA').toUpperCase(), date: resolvedDate, playerId, stat, line, query: '', player: qs('player') || '' };
}

function uniquePlayers(entries, query = '') {
  const seen = new Set();
  const q = normalizeLookupToken(query);
  return (entries || []).filter(entry => {
    if (q && !normalizeLookupToken(entry.player).includes(q)) return false;
    const key = `${entry.playerId}|${entry.player}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((a, b) => String(a.player).localeCompare(String(b.player)));
}

function populateSelect(select, items, getValue, getLabel, selectedValue) {
  if (!select) return;
  select.innerHTML = '';
  items.forEach(item => {
    const opt = document.createElement('option');
    opt.value = getValue(item);
    opt.textContent = getLabel(item);
    if (String(opt.value) === String(selectedValue)) opt.selected = true;
    select.appendChild(opt);
  });
  if (!items.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No options';
    select.appendChild(opt);
  }
}

(function init() {
  const initialLeague = String(qs('league') || 'NBA').toUpperCase();
  const state = {
    config: leagueConfig(initialLeague),
    data: null,
    selection: null,
    view: 'overall',
    bound: false,
  };

  const seriesCache = new Map();
  let renderToken = 0;

  async function load(league = state.config.league) {
    state.config = leagueConfig(league);
    updateLeagueChrome(state.config);
    const empty = { targetDate: '', dates: [], entries: [], seriesIndex: {} };
    const data = await loadJson(state.config.indexPath, empty);
    state.data = data || empty;
    state.selection = findInitialState(state.data, state.config.league);
    if (!state.bound) {
      bind();
      state.bound = true;
    }
    render();
  }

  function currentEntries() {
    return (state.data?.entries || []).filter(e => !state.selection.date || e.gameDate === state.selection.date);
  }

  function selectedEntry() {
    const candidates = currentEntries().filter(e => String(e.playerId) === String(state.selection.playerId) && String(e.stat).toUpperCase() === String(state.selection.stat).toUpperCase());
    if (!candidates.length) return null;
    const exact = candidates.find(e => String(e.line) === String(state.selection.line));
    return exact || candidates.sort((a, b) => Number(a.line) - Number(b.line))[0];
  }

  async function selectedSeries(entry) {
    if (!entry) return null;
    if (entry.inlineSeries) return entry.inlineSeries;
    if (!entry?.seriesKey) return null;
    if (seriesCache.has(entry.seriesKey)) return seriesCache.get(entry.seriesKey);
    const relPath = state.data?.seriesIndex?.[entry.seriesKey];
    const fallbackPath = entry?.gameDate && entry?.playerId && entry?.stat
      ? `${state.config.detailPrefix}/${entry.gameDate}/${entry.playerId}_${String(entry.stat).toLowerCase()}.json`
      : '';
    const candidates = [relPath, relPath ? `./${relPath}` : '', fallbackPath].filter(Boolean);
    const promise = (async () => {
      for (const path of candidates) {
        const payload = await loadJson(path, null);
        if (payload) return payload;
      }
      return null;
    })();
    seriesCache.set(entry.seriesKey, promise);
    return await promise;
  }

  function renderStatus(entry, series) {
    if (!state.data?.entries?.length) {
      setStatus(`<div class="status-banner warning">Analyzer data is not built yet. Run <code>${escapeHtml(state.config.buildCommand)}</code> and refresh the page.</div>`);
      return;
    }
    if (!entry) {
      setStatus('<div class="status-banner warning">No matching analyzer entry was found for the current selection.</div>');
      return;
    }
    if (!series) {
      setStatus('<div class="status-banner warning">Analyzer details could not be loaded for this selection. The index loaded, but the detail file was missing or could not be fetched.</div>');
      return;
    }
    const notes = [];
    if (entry.injuryStatus || series.injuryStatus) {
      notes.push(`<div class="status-banner danger">Listed on injury report: <strong>${escapeHtml(entry.injuryStatus || series.injuryStatus)}</strong>${series.injuryNote ? ` — ${escapeHtml(series.injuryNote)}` : ''}</div>`);
    }
    if (series.sampleNote) {
      notes.push(`<div class="status-banner info">${escapeHtml(series.sampleNote)}</div>`);
    }
    if (series.error) {
      notes.push(`<div class="status-banner warning">Historical build note: ${escapeHtml(series.error)}</div>`);
    }
    notes.push(`<div class="status-banner info">${escapeHtml(entry.summary || entry.driver_summary || 'Use the chart and splits below to compare the current line against the recent and closest-match samples.')}</div>`);
    setStatus(notes.join(''));
  }

  function renderControls() {
    const leagueSelect = byId('analyzer-league');
    const dateSelect = byId('analyzer-date');
    const playerSelect = byId('analyzer-player');
    const statSelect = byId('analyzer-stat');
    const lineSelect = byId('analyzer-line');
    const searchInput = byId('analyzer-search');

    populateSelect(leagueSelect, ['NBA', 'MLB'], item => item, item => item, state.config.league);
    populateSelect(dateSelect, state.data?.dates || [], item => item, item => item, state.selection.date);

    const players = uniquePlayers(currentEntries(), state.selection.query);
    if (!players.some(p => String(p.playerId) === String(state.selection.playerId))) {
      state.selection.playerId = players[0]?.playerId ? String(players[0].playerId) : '';
    }
    populateSelect(playerSelect, players, item => String(item.playerId), item => item.player, state.selection.playerId);

    const stats = [...new Set(currentEntries().filter(e => String(e.playerId) === String(state.selection.playerId)).map(e => String(e.stat).toUpperCase()))].sort();
    if (!stats.includes(String(state.selection.stat).toUpperCase())) {
      state.selection.stat = stats[0] || '';
    }
    populateSelect(statSelect, stats, item => item, item => item, state.selection.stat);

    const lineEntries = currentEntries()
      .filter(e => String(e.playerId) === String(state.selection.playerId) && String(e.stat).toUpperCase() === String(state.selection.stat).toUpperCase())
      .sort((a, b) => Number(a.line) - Number(b.line));
    if (!lineEntries.some(e => String(e.line) === String(state.selection.line))) {
      state.selection.line = lineEntries[0] ? String(lineEntries[0].line) : '';
    }
    populateSelect(lineSelect, lineEntries, item => String(item.line), item => `${item.stat_display || item.stat} ${fmt(item.line, 1)} • ${fmtPct(item.prob_cons)}`, state.selection.line);

    if (searchInput) searchInput.value = state.selection.query || '';
  }

  async function render() {
    const token = ++renderToken;
    renderControls();
    syncViewButtons(state.view);
    const entry = selectedEntry();
    updateHero(entry, null);
    if (!entry) {
      renderStatus(null, null);
      renderKpis(null, null, state.view);
      renderChart(null, null, state.view);
      renderSummary(null, null, state.view);
      renderTableRows('analyzer-games-body', [], null);
      renderTableRows('analyzer-similar-body', [], null);
      updateUrl(null, state.selection, state.config.league);
      return;
    }

    setStatus('<div class="status-banner info">Loading analyzer details…</div>');
    renderKpis(entry, null, state.view);
    renderChart(null, null, state.view);
    renderSummary(null, null, state.view);
    renderTableRows('analyzer-games-body', [], entry?.line);
    renderTableRows('analyzer-similar-body', [], entry?.line);

    const series = await selectedSeries(entry);
    if (token !== renderToken) return;

    updateHero(entry, series);
    renderStatus(entry, series);
    if (!series) {
      renderKpis(entry, {
        games: [],
        similarGames: [],
        matchup: entry.matchup || `${entry.team || ''} vs ${entry.opp || ''}`,
        modelPred: entry.pred_anchor ?? entry.mu_cons ?? null,
        expMin: entry.expMin ?? null,
        opp: entry.opp || '',
        error: 'Analyzer detail file could not be loaded.'
      }, state.view);
      renderChart(null, null, state.view);
      renderSummary(null, null, state.view);
      renderTableRows('analyzer-games-body', [], entry?.line);
      renderTableRows('analyzer-similar-body', [], entry?.line);
      updateUrl(entry, state.selection, state.config.league);
      return;
    }

    renderKpis(entry, series, state.view);
    renderChart(entry, series, state.view);
    renderSummary(entry, series, state.view);
    renderTableRows('analyzer-games-body', recentWindowGames(series || { games: [] }, state.view).slice().reverse(), entry?.line);
    renderTableRows('analyzer-similar-body', (series?.similarGames || []).slice().reverse(), entry?.line);
    updateUrl(entry, state.selection, state.config.league);
  }

  function bind() {
    byId('analyzer-league')?.addEventListener('change', e => {
      state.view = 'overall';
      load(e.target.value || 'NBA');
    });
    byId('analyzer-date')?.addEventListener('change', e => {
      state.selection.date = e.target.value;
      render();
    });
    byId('analyzer-search')?.addEventListener('input', e => {
      state.selection.query = e.target.value || '';
      renderControls();
    });
    byId('analyzer-player')?.addEventListener('change', e => {
      state.selection.playerId = e.target.value;
      render();
    });
    byId('analyzer-stat')?.addEventListener('change', e => {
      state.selection.stat = e.target.value;
      render();
    });
    byId('analyzer-line')?.addEventListener('change', e => {
      state.selection.line = e.target.value;
      render();
    });
    document.querySelectorAll('#analyzer-view-toggle button').forEach(btn => {
      btn.addEventListener('click', () => {
        state.view = btn.dataset.view || 'overall';
        render();
      });
    });
  }

  load(initialLeague);
})();
