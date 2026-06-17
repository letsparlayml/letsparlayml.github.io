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


function currentDenverDateIso() {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Denver',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).format(new Date());
  } catch (err) {
    return new Date().toISOString().slice(0, 10);
  }
}

function pickPreferredDate(data, league, requestedDate = '') {
  const dates = Array.isArray(data?.dates) ? data.dates.filter(Boolean).slice().sort() : [];
  if (!dates.length) return '';
  const today = currentDenverDateIso();

  if (String(league || '').toUpperCase() === 'MLB') {
    const futureDates = dates.filter(d => d >= today);
    if (requestedDate && requestedDate >= today && dates.includes(requestedDate)) return requestedDate;
    return futureDates[0] || dates[dates.length - 1] || '';
  }

  if (requestedDate && dates.includes(requestedDate)) return requestedDate;
  return data?.targetDate && dates.includes(data.targetDate) ? data.targetDate : (dates[0] || '');
}
function normalizeLookupToken(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}


function normalizeStatToken(value) {
  return String(value || '').toUpperCase().trim();
}

function playerEntriesForSelection(entries, playerId) {
  return (entries || []).filter(e => String(e.playerId) === String(playerId));
}

function canonicalStatForSelection(entries, playerId, stat, league = 'NBA') {
  const raw = normalizeStatToken(stat);
  const playerEntries = playerEntriesForSelection(entries, playerId);
  if (!playerEntries.length) return raw;
  const available = [...new Set(playerEntries.map(e => normalizeStatToken(e.stat)).filter(Boolean))];
  if (available.includes(raw)) return raw;
  if (String(league || '').toUpperCase() === 'MLB') {
    const hasPitcherHa = available.includes('HA');
    const hasBatterH = available.includes('H');
    if (raw === 'H' && hasPitcherHa && !hasBatterH) return 'HA';
    if (raw === 'HA' && hasBatterH && !hasPitcherHa) return 'H';
  }
  return available[0] || raw;
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
    case 'strong v2': return '#7bf1c8';
    case 'good v2': return '#59b4ff';
    case 'partial v2': return '#f8d66d';
    case 'loose v2': return '#ff7e79';
    case 'closest 25%': return '#7bf1c8';
    case 'close 25%': return '#59b4ff';
    case 'mid 25%': return '#f8d66d';
    case 'far 25%': return '#ff7e79';
    default: return '#9db0d0';
  }
}


function similarityMatchKey(item) {
  return [
    String(item?.gameKey || ''),
    String(item?.gameId || ''),
    String(item?.gameDate || item?.label || ''),
    String(item?.opp || ''),
    String(item?.location || ''),
    String(item?.seq || ''),
  ].join('|');
}

function similarityLookupForProp(prop) {
  const games = Array.isArray(prop?.similarityV2?.allGames) ? prop.similarityV2.allGames : (Array.isArray(prop?.similarityV2?.topGames) ? prop.similarityV2.topGames : []);
  const lookup = new Map();
  games.forEach(game => {
    lookup.set(similarityMatchKey(game), game);
    if (game?.gameKey) {
      lookup.set(`gameKey:${String(game.gameKey)}`, game);
    }
    if (game?.gameDate || game?.opp || game?.location) {
      lookup.set([String(game?.gameDate || ''), String(game?.opp || ''), String(game?.location || '')].join('|'), game);
    }
  });
  return lookup;
}

function similarityMatchFromLookup(lookup, item) {
  if (!lookup || !item) return null;
  return lookup.get(similarityMatchKey(item))
    || (item?.gameKey ? lookup.get(`gameKey:${String(item.gameKey)}`) : null)
    || lookup.get([String(item?.gameDate || item?.label || ''), String(item?.opp || ''), String(item?.location || '')].join('|'))
    || null;
}

function similarityBinFromScore(score) {
  const value = Number(score);
  if (!hasNumericValue(value)) return 'all';
  if (value >= 82) return 'Strong v2';
  if (value >= 68) return 'Good v2';
  if (value >= 52) return 'Partial v2';
  return 'Loose v2';
}

function similarityQualityLabel(item) {
  const score = Number(item?.simScoreV2 ?? item?.simScore);
  const rawBin = String(item?.simBinV2 || item?.simBin || '').trim();
  if (rawBin && rawBin.toLowerCase() !== 'all') return rawBin;
  return similarityBinFromScore(score);
}

function gameWithSimilarity(game, profile = null, entry = null) {
  if (!game || !profile || !entry) return game;
  const prop = selectedProfileProp(profile, entry);
  if (!prop) return game;
  const simMatch = similarityMatchFromLookup(similarityLookupForProp(prop), game);
  if (!simMatch) return game;
  return {
    ...game,
    simScoreV2: simMatch?.simScoreV2 ?? game?.simScoreV2,
    simPctV2: simMatch?.simPctV2 ?? game?.simPctV2,
    simBinV2: simMatch?.simBinV2 ?? game?.simBinV2,
    simReasonsV2: simMatch?.simReasonsV2 ?? game?.simReasonsV2,
    simComponentsV2: simMatch?.simComponentsV2 ?? game?.simComponentsV2,
  };
}

function simLabelWithScore(item) {
  const label = similarityQualityLabel(item);
  const score = Number(item?.simScoreV2 ?? item?.simScore);
  return hasNumericValue(score) ? `${label} ${fmt(score, 0)}` : label;
}

function simTitleFromItem(item) {
  const reasons = Array.isArray(item?.simReasonsV2) ? item.simReasonsV2 : [];
  const components = item?.simComponentsV2 || {};
  const componentBits = Object.entries(components)
    .filter(([, value]) => hasNumericValue(Number(value)) && Number(value) > 0)
    .map(([key, value]) => `${key}: ${fmt(Number(value), 0)}`);
  return [...reasons, ...componentBits].join(' • ');
}

function statDisplayLabel(entry, series) {
  const stat = normalizeStatToken(entry?.stat || series?.stat);
  const supplied = entry?.stat_display || entry?.statDisplay || series?.statDisplay || series?.stat_display;
  if (supplied) return String(supplied);
  const labels = {
    PTS: 'Points',
    REB: 'Rebounds',
    AST: 'Assists',
    PRA: 'PRA',
    PR: 'Points + Rebounds',
    PA: 'Points + Assists',
    RA: 'Rebounds + Assists',
    THREEPM: '3PM',
    '3PM': '3PM',
    H: 'Hits',
    HRR: 'Hits + Runs + RBI',
    TB: 'Total Bases',
    K: 'Strikeouts',
    HA: 'Hits Allowed',
    ER: 'Earned Runs',
    BB: 'Walks'
  };
  return labels[stat] || stat || 'Prop';
}

function playerRole(entry, series) {
  return String(entry?.playerType || series?.playerType || entry?.role || series?.role || '').toLowerCase();
}

function contextColumnLabel(entry, series) {
  const role = playerRole(entry, series);
  if (role === 'pitcher') return 'IP';
  if (role === 'batter') return 'AB';
  const league = String(entry?.league || series?.league || '').toUpperCase();
  if (league === 'MLB') return 'AB';
  return 'Min';
}

function updateAnalyzerTableLabels(entry, series) {
  const statLabel = statDisplayLabel(entry, series);
  const contextLabel = contextColumnLabel(entry, series);
  ['analyzer-games-col-4', 'analyzer-similar-col-4'].forEach(id => {
    const node = byId(id);
    if (node) node.textContent = statLabel;
  });
  ['analyzer-games-col-5', 'analyzer-similar-col-5'].forEach(id => {
    const node = byId(id);
    if (node) node.textContent = contextLabel;
  });
  const trendCopy = byId('analyzer-trend-copy');
  if (trendCopy && entry) {
    trendCopy.textContent = `Chart shows ${statLabel} by game for the selected overall/home/away view. The dashed line is the selected comparison line, and recent points are colored by similarity tier when that data is available.`;
  }
}

function updateHero(entry, series, profile = null) {
  const compLine = entryComparisonLine(entry, profile);
  const compProb = entryComparisonProbability(entry, profile);
  const compProp = selectedPropForEntry(profile, entry);
  const compOptionForHero = lineOptionForProp(compProp, entry);
  const compLabel = compOptionForHero?.isClosestAverageLine ? 'near avg' : compOptionForHero?.isComparisonLine ? 'avg' : 'line';
  const model = entry?.pred_anchor ?? entry?.mu_cons ?? series?.modelPred ?? compProp?.modelPred ?? null;
  byId('analyzer-hero-date').textContent = entry?.gameDate || series?.gameDate || '—';
  byId('analyzer-hero-player').textContent = entry?.player || series?.player || '—';
  byId('analyzer-hero-line').textContent = entry ? `${statDisplayLabel(entry, series)} ${hasNumericValue(compLine) ? fmt(compLine, 1) : '—'}${lineOptionForProp(compProp, entry)?.isComparisonLine ? ' avg' : ''}` : '—';
  byId('analyzer-hero-model').textContent = entry ? `${fmt(model, 1)} (${hasNumericValue(model) && hasNumericValue(compLine) ? fmtSigned(model - compLine, 1) : '—'})` : '—';
  byId('analyzer-hero-prob').textContent = entry ? (hasNumericValue(compProb) ? fmtPct(compProb) : (lineOptionForProp(compProp, entry)?.isComparisonLine ? 'vs avg' : '—')) : '—';
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

function renderKpis(entry, series, view, profile = null) {
  const root = byId('analyzer-kpis');
  if (!root) return;
  if (!entry || !series) {
    root.innerHTML = '<div class="empty-state">No analyzer entry selected.</div>';
    return;
  }

  const currentGames = recentWindowGames(series, view);
  const overallGames = filterByView(series.games || [], view);
  const v2Games = profileSimilarityV2Games(profile, entry);
  const similarGames = v2Games.length ? v2Games : (series.similarGames || []);
  const sameOppGames = similarGames.filter(g => (g.opp || '') === (series.opp || ''));

  const compLine = entryComparisonLine(entry, profile);
  const compProb = entryComparisonProbability(entry, profile);
  const compProp = selectedPropForEntry(profile, entry);
  const compOption = lineOptionForProp(compProp, entry);
  const compSource = compOption?.isComparisonLine ? (compOption.source || 'pitcher average') : 'listed line';
  const modelValue = entry.pred_anchor ?? entry.mu_cons ?? series.modelPred ?? compProp?.modelPred ?? null;
  const recentStats = calcStats(currentGames, compLine);
  const overallStats = calcStats(overallGames, compLine);
  const similarStats = calcStats(similarGames, compLine);
  const sameOppStats = calcStats(sameOppGames, compLine);
  const rateLabel = compOption?.isComparisonLine ? 'over avg rate' : 'hit rate';

  root.innerHTML = `
    <article class="hero-card kpi-card">
      <span class="stat-label">Matchup</span>
      <strong>${escapeHtml(series.matchup || `${entry.team || ''} vs ${entry.opp || ''}`)}</strong>
      <p class="muted">${escapeHtml(view === 'overall' ? 'All locations' : view === 'home' ? 'Home sample' : 'Away sample')}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Model edge</span>
      <strong>${hasNumericValue(modelValue) && hasNumericValue(compLine) ? fmtSigned(modelValue - compLine, 1) : '—'}</strong>
      <p class="muted">Model ${fmt(modelValue, 1)} • ${escapeHtml(compSource)} ${fmt(compLine, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Recent ${escapeHtml(rateLabel)}</span>
      <strong>${fmtPct(recentStats.hitRate)}</strong>
      <p class="muted">${recentStats.n} games • avg ${fmt(recentStats.avg, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">Full-sample ${escapeHtml(rateLabel)}</span>
      <strong>${fmtPct(overallStats.hitRate)}</strong>
      <p class="muted">${overallStats.n} games • avg ${fmt(overallStats.avg, 1)}</p>
    </article>
    <article class="hero-card kpi-card">
      <span class="stat-label">${v2Games.length ? 'Similarity v2 average' : 'Closest-match average'}</span>
      <strong>${fmt(similarStats.avg, 1)}</strong>
      <p class="muted">${similarStats.n} games • hit ${fmtPct(similarStats.hitRate)}${v2Games.length ? ' • transparent v2' : ''}</p>
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
      <strong>${hasNumericValue(compProb) ? fmtPct(compProb) : (compProp?.comparisonLine ? 'vs avg' : fmtPct(entry.prob_cons))}</strong>
      <p class="muted">${escapeHtml(compOption?.isComparisonLine ? `${compOption?.isClosestAverageLine ? 'Using closest listed line to pitcher average' : 'Compared to ' + compSource}, not the lowest static prop line.` : (entry.boardDriver || entry.driver_summary || entry.reason_flags || 'No driver text'))}</p>
    </article>
  `;
}

function renderSummary(entry, series, view, profile = null) {
  const body = byId('analyzer-summary-body');
  if (!body) return;
  if (!entry || !series) {
    body.innerHTML = '<tr><td colspan="6">No analyzer entry selected.</td></tr>';
    return;
  }
  const compLine = entryComparisonLine(entry, profile);
  const recentStats = calcStats(recentWindowGames(series, view), compLine);
  const overallStats = calcStats(filterByView(series.games || [], view), compLine);
  const v2Games = profileSimilarityV2Games(profile, entry);
  const similarGames = v2Games.length ? v2Games : (series.similarGames || []);
  const similarStats = calcStats(similarGames, compLine);
  const sameOppStats = calcStats((similarGames || []).filter(g => (g.opp || '') === (series.opp || '')), compLine);
  const rows = [
    ['Recent sample', recentStats],
    ['Full sample', overallStats],
    [v2Games.length ? 'Similarity v2 sample' : 'Closest-match sample', similarStats],
    [v2Games.length ? 'Same opponent inside v2 sample' : 'Same opponent inside closest sample', sameOppStats],
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

function renderTableRows(rootId, games, line, entry = null, series = null, profile = null) {
  const body = byId(rootId);
  const compLine = entryComparisonLine(entry, profile);
  if (hasNumericValue(compLine)) line = compLine;
  if (!body) return;
  if (!(games || []).length) {
    body.innerHTML = '<tr><td colspan="7">No samples available for this view.</td></tr>';
    return;
  }
  const rows = games.map(g => gameWithSimilarity(g, profile, entry)).slice().sort((a, b) => {
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
      <td>${fmt(g.minutes ?? g.contextValue, 1)}</td>
      <td>${hasNumericValue(g.value) ? (g.value >= line ? 'Hit' : 'Miss') : '—'}</td>
      <td><span class="sim-pill" style="--sim-color:${simColor(similarityQualityLabel(g))}" title="${escapeHtml(simTitleFromItem(g))}">${escapeHtml(simLabelWithScore(g))}</span></td>
    </tr>
  `).join('');
}

function renderChart(entry, series, view, profile = null) {
  const root = byId('analyzer-chart');
  if (!root) return;
  if (!entry || !series) {
    root.innerHTML = '<div class="empty-state">No analyzer entry selected.</div>';
    return;
  }
  const games = recentWindowGames(series, view).map(g => gameWithSimilarity(g, profile, entry));
  if (!games.length) {
    root.innerHTML = '<div class="empty-state">No recent games for this view.</div>';
    return;
  }

  const width = 860;
  const height = 320;
  const margin = { top: 18, right: 18, bottom: 48, left: 48 };
  const values = games.map(g => Number(g.value)).filter(Number.isFinite);
  const line = Number(entryComparisonLine(entry, profile));
  const topValue = Math.max(...values, Number.isFinite(line) ? line : 0, 0);
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
      <circle cx="${cx}" cy="${cy}" r="5" fill="${simColor(similarityQualityLabel(g))}" stroke="#0b1220" stroke-width="1.5">
        <title>${escapeHtml(`${g.label || g.gameDate || ''} ${g.opp || ''} ${g.location || ''} — ${fmt(g.value, 1)}${hasNumericValue(g.minutes ?? g.contextValue) ? ` in ${fmt(g.minutes ?? g.contextValue, 1)} ${contextColumnLabel(entry, series)}` : ''} (${simLabelWithScore(g)})`)}</title>
      </circle>
      <text x="${cx}" y="${height - 18}" fill="#9db0d0" font-size="10" text-anchor="middle">${escapeHtml(analyzerDisplayLabel(g))}</text>
    </g>`;
  }).join('');

  const lineY = Number.isFinite(line) ? y(line) : null;
  root.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent prop trend chart">
      ${grid}
      ${Number.isFinite(lineY) ? `<line x1="${margin.left}" x2="${width - margin.right}" y1="${lineY}" y2="${lineY}" stroke="#ff7e79" stroke-width="2" stroke-dasharray="7 6"></line>` : ''}
      <polyline fill="none" stroke="#59b4ff" stroke-width="3" points="${poly}"></polyline>
      ${dots}
    </svg>
  `;
}


const MLB_MULTI_PROP_STAT_ORDER = {
  H: 10,
  TB: 20,
  HRR: 30,
  HR: 40,
  '2B': 50,
  BB: 60,
  K: 70,
  SB: 80,
  ER: 110,
  HA: 120,
  IP: 130,
  OUTS: 140,
};

function sortProfileProps(props) {
  return (props || []).slice().sort((a, b) => {
    const sa = normalizeStatToken(a.stat);
    const sb = normalizeStatToken(b.stat);
    return (MLB_MULTI_PROP_STAT_ORDER[sa] || 999) - (MLB_MULTI_PROP_STAT_ORDER[sb] || 999) || sa.localeCompare(sb);
  });
}


function isPitcherProfile(profile) {
  if (String(profile?.playerType || '').toLowerCase() === 'pitcher') return true;
  const stats = new Set((profile?.availableProps || []).map(prop => normalizeStatToken(prop?.stat)));
  return stats.has('HA') || stats.has('IP') || stats.has('OUTS') || stats.has('ER');
}

function isPitcherProp(prop) {
  const display = String(prop?.statDisplay || prop?.stat_display || '').toLowerCase();
  if (String(prop?.playerType || '').toLowerCase() === 'pitcher') return true;
  if (display.includes('pitcher')) return true;
  const stat = normalizeStatToken(prop?.stat);
  return ['HA', 'IP', 'OUTS'].includes(stat) || (['K', 'BB', 'ER'].includes(stat) && display.includes('pitcher'));
}

function pitcherAverageLineForProp(prop) {
  if (!isPitcherProp(prop)) return null;
  if (hasNumericValue(Number(prop?.comparisonLine))) {
    return {
      line: Number(prop.comparisonLine),
      probability: hasNumericValue(Number(prop?.comparisonProbability)) ? Number(prop.comparisonProbability) : null,
      source: prop?.comparisonLineSource || 'pitcher average',
    };
  }
  if (hasNumericValue(Number(prop?.allGamesAvg))) {
    return { line: Number(prop.allGamesAvg), probability: null, source: 'full sample average' };
  }
  if (hasNumericValue(Number(prop?.recent5Avg))) {
    return { line: Number(prop.recent5Avg), probability: null, source: 'recent average' };
  }
  return null;
}

function patchPitcherLineControl(entry, profile) {
  if (!entry || !isPitcherProfile(profile)) return;
  const lineSelect = byId('analyzer-line');
  if (!lineSelect) return;
  const prop = selectedPropForEntry(profile, entry);
  const avg = pitcherAverageLineForProp(prop);
  if (!prop || !avg || !hasNumericValue(avg.line)) return;
  const option = lineOptionForProp(prop, entry);
  const label = option?.isClosestAverageLine
    ? `${statDisplayLabel(entry, null)} ${fmt(option.line, 1)} • closest to ${avg.source} ${fmt(avg.line, 1)}`
    : `${statDisplayLabel(entry, null)} avg ${fmt(avg.line, 1)} • ${avg.source}`;
  lineSelect.innerHTML = `<option value="${escapeHtml(String(entry.line ?? ''))}">${escapeHtml(label)}</option>`;
}


function closestListedLineToAverage(prop, averageLine) {
  const options = (Array.isArray(prop?.lineOptions) ? prop.lineOptions : [])
    .map(opt => ({
      ...opt,
      lineNumber: Number(opt.line),
      probabilityNumber: Number(opt.probability),
    }))
    .filter(opt => hasNumericValue(opt.lineNumber));

  if (!options.length || !hasNumericValue(averageLine)) return null;

  return options.sort((a, b) => {
    const distance = Math.abs(a.lineNumber - averageLine) - Math.abs(b.lineNumber - averageLine);
    if (distance) return distance;
    const aProb = hasNumericValue(a.probabilityNumber) ? a.probabilityNumber : -1;
    const bProb = hasNumericValue(b.probabilityNumber) ? b.probabilityNumber : -1;
    return bProb - aProb;
  })[0];
}

function lineOptionForProp(prop, selectedEntry = null) {
  // Pitcher pages use the listed line closest to the pitcher's own average.
  // This avoids comparing everything to the lowest alt line while preserving
  // a real model probability from the existing lineOptions.
  const pitcherAverage = pitcherAverageLineForProp(prop);
  if (pitcherAverage && hasNumericValue(pitcherAverage.line)) {
    const closest = closestListedLineToAverage(prop, pitcherAverage.line);
    if (closest) {
      return {
        ...closest,
        line: Number(closest.lineNumber),
        probability: hasNumericValue(closest.probabilityNumber) ? Number(closest.probabilityNumber) : null,
        side: 'closest listed line to pitcher average',
        source: `closest listed line to ${pitcherAverage.source || 'pitcher average'}`,
        averageReference: Number(pitcherAverage.line),
        averageSource: pitcherAverage.source || 'pitcher average',
        isComparisonLine: true,
        isClosestAverageLine: true,
      };
    }
    return {
      line: pitcherAverage.line,
      probability: pitcherAverage.probability,
      side: 'vs pitcher average',
      source: pitcherAverage.source || 'pitcher average',
      averageReference: Number(pitcherAverage.line),
      averageSource: pitcherAverage.source || 'pitcher average',
      isComparisonLine: true,
    };
  }

  const options = Array.isArray(prop?.lineOptions) ? prop.lineOptions : [];
  const selectedStat = normalizeStatToken(selectedEntry?.stat);
  const propStat = normalizeStatToken(prop?.stat);
  const selectedLine = selectedEntry?.line;
  if (selectedEntry && selectedStat === propStat) {
    const exact = options.find(opt => String(opt.line) === String(selectedLine));
    if (exact) return exact;
  }
  const withLine = options.filter(opt => hasNumericValue(Number(opt.line)));
  if (withLine.length) {
    return withLine.slice().sort((a, b) => {
      const ap = hasNumericValue(Number(a.probability)) ? Number(a.probability) : -1;
      const bp = hasNumericValue(Number(b.probability)) ? Number(b.probability) : -1;
      return bp - ap;
    })[0];
  }
  return {};
}

function lineForProfileProp(prop, selectedEntry = null) {
  const option = lineOptionForProp(prop, selectedEntry);
  return hasNumericValue(Number(option?.line)) ? Number(option.line) : null;
}

function probabilityForProfileProp(prop, selectedEntry = null) {
  const option = lineOptionForProp(prop, selectedEntry);
  return hasNumericValue(Number(option?.probability)) ? Number(option.probability) : null;
}

function comparisonLineLabel(prop, selectedEntry = null) {
  const option = lineOptionForProp(prop, selectedEntry);
  if (option?.isComparisonLine) return option.source || 'pitcher average';
  return 'listed line';
}

function selectedPropForEntry(profile, entry) {
  if (!profile || !entry) return null;
  const wanted = normalizeStatToken(entry?.stat);
  return (profile.availableProps || []).find(prop => normalizeStatToken(prop.stat) === wanted) || null;
}

function entryComparisonLine(entry, profile = null) {
  const prop = selectedPropForEntry(profile, entry);
  const line = prop ? lineForProfileProp(prop, entry) : null;
  return hasNumericValue(line) ? line : (hasNumericValue(Number(entry?.line)) ? Number(entry.line) : null);
}

function entryComparisonProbability(entry, profile = null) {
  const prop = selectedPropForEntry(profile, entry);
  const prob = prop ? probabilityForProfileProp(prop, entry) : null;
  return hasNumericValue(prob) ? prob : (hasNumericValue(Number(entry?.prob_cons)) ? Number(entry.prob_cons) : null);
}

function selectedProfileProp(profile, selectedEntry = null) {
  const wanted = normalizeStatToken(selectedEntry?.stat) || normalizeStatToken(profile?.uiHints?.primaryStat);
  const props = sortProfileProps(profile?.availableProps || []);
  return props.find(prop => normalizeStatToken(prop.stat) === wanted) || props[0] || null;
}

function profileSimilarityV2(prop) {
  return prop?.similarityV2 || null;
}

function profileSimilarityV2Games(profile, selectedEntry = null) {
  const prop = selectedProfileProp(profile, selectedEntry);
  const sim = profileSimilarityV2(prop);
  return Array.isArray(sim?.topGames) ? sim.topGames : [];
}

function profileSimilarityV2Stats(profile, selectedEntry = null) {
  const prop = selectedProfileProp(profile, selectedEntry);
  const sim = profileSimilarityV2(prop);
  return { prop, sim, games: Array.isArray(sim?.topGames) ? sim.topGames : [] };
}

function defaultStatsForProfile(profile) {
  const hints = profile?.uiHints?.defaultSelectedStats;
  const available = sortProfileProps(profile?.availableProps).map(p => normalizeStatToken(p.stat));
  const hinted = Array.isArray(hints) ? hints.map(normalizeStatToken).filter(stat => available.includes(stat)) : [];
  return (hinted.length ? hinted : available).slice(0, Math.min(3, available.length));
}

function normalizeProfileSelectedStats(profile, selectedStats) {
  const available = sortProfileProps(profile?.availableProps).map(p => normalizeStatToken(p.stat));
  const selected = Array.isArray(selectedStats) ? selectedStats.map(normalizeStatToken).filter(stat => available.includes(stat)) : [];
  return selected.length ? selected : defaultStatsForProfile(profile);
}

function profileQualityWarningText(profile) {
  const warnings = profile?.dataQuality?.warnings || [];
  return warnings.length ? warnings.join(' | ') : '';
}

function matchupContextPieces(profile) {
  const ctx = profile?.matchupContext || {};
  const summaryPieces = Array.isArray(ctx.summaryPieces) ? ctx.summaryPieces.filter(Boolean) : [];
  if (summaryPieces.length) return summaryPieces;
  return [
    ctx.lineupOrder ? `Order ${ctx.lineupOrder}` : '',
    ctx.handednessText ? ctx.handednessText : '',
    hasNumericValue(ctx.temperatureF) ? `${fmt(ctx.temperatureF, 0)}°F` : '',
    hasNumericValue(ctx.windMph) ? `Wind ${fmt(ctx.windMph, 0)}` : '',
  ].filter(Boolean);
}

function matchupFeatureCards(profile) {
  const ctx = profile?.matchupContext || {};
  const features = Array.isArray(ctx.currentFeatures) ? ctx.currentFeatures : [];
  if (features.length) return features;
  const fallback = [];
  if (ctx.lineupOrder) fallback.push({ label: 'Lineup', value: `Order ${ctx.lineupOrder}`, note: ctx.lineupBand || '' });
  if (ctx.handednessText) fallback.push({ label: 'Handedness', value: ctx.handednessText, note: ctx.handednessBucket || '' });
  if (hasNumericValue(ctx.temperatureF)) fallback.push({ label: 'Temperature', value: `${fmt(ctx.temperatureF, 0)}°F`, note: ctx.temperatureBucket || '' });
  if (hasNumericValue(ctx.windMph)) fallback.push({ label: 'Wind', value: `${fmt(ctx.windMph, 0)} mph`, note: ctx.windBucket || '' });
  return fallback;
}

function matchupReadinessText(profile) {
  const readiness = profile?.matchupFeatureSummary?.similarityReadiness || profile?.matchupContext?.similarityReadiness || {};
  const next = Array.isArray(readiness.nextRequiredInputs) ? readiness.nextRequiredInputs : [];
  if (!next.length) return 'Current context is structured. Historical handedness, pitch mix, park, and weather are still the next inputs.';
  return next.slice(0, 2).join(' • ');
}


function pitcherLineupContext(profile) {
  const ctx = profile?.pitcherLineupContext;
  return ctx && ctx.available ? ctx : null;
}

function handCountText(counts) {
  counts = counts || {};
  const parts = [];
  if (hasNumericValue(Number(counts.R))) parts.push(`${Number(counts.R)} RHB`);
  if (hasNumericValue(Number(counts.L))) parts.push(`${Number(counts.L)} LHB`);
  if (hasNumericValue(Number(counts.S))) parts.push(`${Number(counts.S)} switch`);
  if (!parts.length && hasNumericValue(Number(counts.Unknown))) parts.push(`${Number(counts.Unknown)} unknown`);
  return parts.join(' • ') || 'lineup hands pending';
}

function pressureLabel(value) {
  const text = String(value || 'unknown').toLowerCase();
  if (text === 'high') return 'High';
  if (text === 'medium') return 'Medium';
  if (text === 'low') return 'Low';
  return 'Pending';
}

function pressureClass(value) {
  const text = String(value || '').toLowerCase();
  if (text === 'high') return 'is-risk';
  if (text === 'medium') return 'is-medium';
  if (text === 'low') return 'is-safe';
  return 'is-muted';
}

function lineupPlayerList(players, emptyText = 'No clear standouts') {
  const rows = Array.isArray(players) ? players.filter(Boolean).slice(0, 4) : [];
  if (!rows.length) return `<span class="pitcher-lineup-empty">${escapeHtml(emptyText)}</span>`;
  return rows.map(p => {
    const hand = p.hand ? ` • ${p.hand}` : '';
    const metric = hasNumericValue(Number(p.metric)) ? ` (${fmt(Number(p.metric), 2)})` : '';
    const order = p.order ? `#${p.order} ` : '';
    return `<span>${escapeHtml(`${order}${p.player || 'Player'}${hand}${metric}`)}</span>`;
  }).join('');
}

function pitcherLineupSummary(profile) {
  const ctx = pitcherLineupContext(profile);
  if (!ctx) return '';
  const pitcher = profile?.player || ctx.pitcher || 'This pitcher';
  const opp = ctx.opponentTeam || 'the opposing lineup';
  const hand = ctx.pitcherHand ? `${ctx.pitcherHand}HP` : 'pitcher';
  const counts = handCountText(ctx.lineupHandCounts);
  const side = ctx.sideAdvantageCounts || {};
  const pressure = ctx.lineupPressure || {};
  const pieces = [
    `${pitcher} is a ${hand} facing ${opp}.`,
    `Projected lineup mix: ${counts}.`,
  ];
  if (hasNumericValue(Number(side.opposite)) || hasNumericValue(Number(side.switch))) {
    pieces.push(`${Number(side.opposite || 0)} opposite-side bats and ${Number(side.switch || 0)} switch bats in the projected lineup.`);
  }
  const pressureBits = [];
  if (pressure.contact) pressureBits.push(`contact pressure ${pressureLabel(pressure.contact).toLowerCase()}`);
  if (pressure.power) pressureBits.push(`power pressure ${pressureLabel(pressure.power).toLowerCase()}`);
  if (pressure.strikeoutOpportunity) pressureBits.push(`K opportunity ${pressureLabel(pressure.strikeoutOpportunity).toLowerCase()}`);
  if (pressureBits.length) pieces.push(pressureBits.join(' • ') + '.');
  return pieces.join(' ');
}

function renderPitcherLineupMatchup(profile) {
  const ctx = pitcherLineupContext(profile);
  if (!ctx) return '';
  const pressure = ctx.lineupPressure || {};
  const side = ctx.sideAdvantageCounts || {};
  const topSide = ctx.topThirdSideAdvantageCounts || {};
  return `
    <article class="pitcher-lineup-panel">
      <div class="pitcher-lineup-head">
        <div>
          <span class="stat-label">Opposing lineup matchup</span>
          <strong>${escapeHtml(ctx.pitcherHand ? `${ctx.pitcherHand}HP vs ${ctx.opponentTeam || 'opponent'} projected lineup` : `${ctx.opponentTeam || 'Opponent'} projected lineup`)}</strong>
          <p class="muted">${escapeHtml(handCountText(ctx.lineupHandCounts))}${ctx.lineupSize ? ` • ${ctx.lineupSize} projected bats` : ''}</p>
        </div>
        <div class="pitcher-lineup-counts">
          <span><b>${escapeHtml(String(side.opposite ?? 0))}</b><small>opp-side</small></span>
          <span><b>${escapeHtml(String(side.same ?? 0))}</b><small>same-side</small></span>
          <span><b>${escapeHtml(String(side.switch ?? 0))}</b><small>switch</small></span>
        </div>
      </div>
      <div class="pitcher-pressure-grid">
        <span class="pitcher-pressure-chip ${pressureClass(pressure.contact)}"><em>Contact pressure</em><b>${escapeHtml(pressureLabel(pressure.contact))}</b></span>
        <span class="pitcher-pressure-chip ${pressureClass(pressure.power)}"><em>Power pressure</em><b>${escapeHtml(pressureLabel(pressure.power))}</b></span>
        <span class="pitcher-pressure-chip ${pressureClass(pressure.strikeoutOpportunity)}"><em>K opportunity</em><b>${escapeHtml(pressureLabel(pressure.strikeoutOpportunity))}</b></span>
        <span class="pitcher-pressure-chip ${pressureClass(pressure.walkRisk)}"><em>Walk risk</em><b>${escapeHtml(pressureLabel(pressure.walkRisk))}</b></span>
      </div>
      <div class="pitcher-lineup-splits">
        <div><span class="stat-label">Top third</span><strong>${escapeHtml(handCountText(ctx.topThirdHandCounts))}</strong><small>${escapeHtml(`${Number(topSide.opposite || 0)} opp-side • ${Number(topSide.switch || 0)} switch`)}</small></div>
        <div><span class="stat-label">Middle third</span><strong>${escapeHtml(handCountText(ctx.middleThirdHandCounts))}</strong></div>
        <div><span class="stat-label">Bottom third</span><strong>${escapeHtml(handCountText(ctx.bottomThirdHandCounts))}</strong></div>
      </div>
      <div class="pitcher-lineup-threats">
        <div><span class="stat-label">Contact threats</span>${lineupPlayerList(ctx.contactThreats)}</div>
        <div><span class="stat-label">Power threats</span>${lineupPlayerList(ctx.powerThreats)}</div>
        <div><span class="stat-label">K targets</span>${lineupPlayerList(ctx.strikeoutTargets)}</div>
        <div><span class="stat-label">Walk-risk bats</span>${lineupPlayerList(ctx.walkRiskBats)}</div>
      </div>
      <p class="pitcher-lineup-read">${escapeHtml(pitcherLineupSummary(profile))}</p>
    </article>
  `;
}

function pitcherPropReadableSummary(profile, prop, entry) {
  const name = playerFirstName(profile, entry);
  const stat = normalizeStatToken(prop?.stat);
  const line = lineForProfileProp(prop, entry);
  const prob = probabilityForProfileProp(prop, entry);
  const lineSource = lineOptionForProp(prop, entry)?.isComparisonLine ? (lineOptionForProp(prop, entry)?.source || 'pitcher average') : 'line';
  const model = hasNumericValue(Number(prop?.modelPred)) ? Number(prop.modelPred) : null;
  const sim = prop?.similarityV2 || {};
  const simAvg = hasNumericValue(Number(sim?.avgValue)) ? Number(sim.avgValue) : null;
  const simCount = hasNumericValue(Number(sim?.count)) ? Number(sim.count) : null;
  const ctx = pitcherLineupContext(profile);
  const pressure = ctx?.lineupPressure || {};
  const pieces = [];

  if (stat === 'K') {
    if (hasNumericValue(simAvg)) pieces.push(`${name} has averaged ${fmt(simAvg, 2)} strikeouts across ${simCount || 'the top'} similar starts${hasNumericValue(line) ? (simAvg >= line ? `, above the ${lineSource} ${fmt(line, 1)}` : `, below the ${lineSource} ${fmt(line, 1)}`) : ''}.`);
    if (hasNumericValue(model) && hasNumericValue(line)) pieces.push(`The model projects ${fmt(model, 2)} Ks vs ${lineSource} ${fmt(line, 1)}${hasNumericValue(prob) ? ` (${fmtPct(prob)} probability)` : ''}.`);
    if (pressure.strikeoutOpportunity) pieces.push(`Opposing lineup K opportunity grades ${pressureLabel(pressure.strikeoutOpportunity).toLowerCase()}.`);
  } else if (['HA', 'ER', 'BB'].includes(stat)) {
    const label = stat === 'HA' ? 'hits allowed' : stat === 'ER' ? 'earned runs allowed' : 'walks allowed';
    if (hasNumericValue(simAvg)) pieces.push(`${name} has allowed ${fmt(simAvg, 2)} ${label} across ${simCount || 'the top'} similar starts${hasNumericValue(line) ? (simAvg >= line ? `, over the ${lineSource} ${fmt(line, 1)}` : `, under the ${lineSource} ${fmt(line, 1)}`) : ''}.`);
    if (hasNumericValue(model) && hasNumericValue(line)) pieces.push(`The model is ${model >= line ? 'above' : 'below'} the line at ${fmt(model, 2)} vs ${lineSource} ${fmt(line, 1)}${hasNumericValue(prob) ? ` (${fmtPct(prob)} probability)` : ''}.`);
    if (stat === 'HA' && pressure.contact) pieces.push(`Lineup contact pressure grades ${pressureLabel(pressure.contact).toLowerCase()}.`);
    if (stat === 'ER' && pressure.power) pieces.push(`Lineup power/run-production pressure grades ${pressureLabel(pressure.power).toLowerCase()}.`);
    if (stat === 'BB' && pressure.walkRisk) pieces.push(`Lineup walk pressure grades ${pressureLabel(pressure.walkRisk).toLowerCase()}.`);
  } else if (['IP', 'OUTS'].includes(stat)) {
    if (hasNumericValue(simAvg)) pieces.push(`${name} has averaged ${fmt(simAvg, 2)} ${readableStatName(prop).toLowerCase()} across ${simCount || 'the top'} similar starts.`);
    if (hasNumericValue(model) && hasNumericValue(line)) pieces.push(`The workload model is ${model >= line ? 'above' : 'below'} the line at ${fmt(model, 2)} vs ${lineSource} ${fmt(line, 1)}${hasNumericValue(prob) ? ` (${fmtPct(prob)} probability)` : ''}.`);
    if (pressure.contact || pressure.power) pieces.push(`Lineup pressure: contact ${pressureLabel(pressure.contact).toLowerCase()}, power ${pressureLabel(pressure.power).toLowerCase()}.`);
  }
  return pieces.filter(Boolean).slice(0, 3).join(' ') || '';
}



function readableStatName(propOrStat) {
  const stat = normalizeStatToken(typeof propOrStat === 'string' ? propOrStat : propOrStat?.stat);
  const supplied = typeof propOrStat === 'object' ? (propOrStat?.statDisplay || propOrStat?.stat_display) : '';
  if (supplied) return String(supplied).replace(/\+/g, ' + ');
  const labels = {
    H: 'hits',
    TB: 'total bases',
    HRR: 'hits + runs + RBI',
    HR: 'home runs',
    '2B': 'doubles',
    BB: 'walks',
    K: 'strikeouts',
    SB: 'stolen bases',
    HA: 'hits allowed',
    ER: 'earned runs',
    IP: 'innings',
    OUTS: 'outs',
  };
  return labels[stat] || stat.toLowerCase() || 'prop';
}

function sentenceCase(text) {
  const value = String(text || '').trim();
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : '';
}

function playerFirstName(profile, entry) {
  const name = String(profile?.player || entry?.player || 'This player').trim();
  if (!name || /probable starter tbd/i.test(name)) return 'This player';
  const parts = name.split(/\s+/).filter(Boolean);
  return parts.length ? parts[0] : name;
}

function playerFullName(profile, entry) {
  return String(profile?.player || entry?.player || 'This player').trim() || 'This player';
}

function parsePitchMixFactors(profile) {
  const text = String(profile?.matchupContext?.pitchMixSummary || '').trim();
  const out = { raw: text };
  if (!text) return out;
  const aliasMap = {
    power: 'power',
    pow: 'power',
    tb: 'tb',
    hrr: 'hrr',
    hr: 'hr',
    whiff: 'whiff',
    coverage: 'coverage',
    cov: 'coverage',
  };
  const re = /(power|pow|tb|hrr|hr|whiff|coverage|cov)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?%?)/gi;
  let match;
  while ((match = re.exec(text))) {
    const key = aliasMap[String(match[1]).toLowerCase()] || String(match[1]).toLowerCase();
    let val = String(match[2]);
    const isPct = val.includes('%');
    val = Number(val.replace('%', ''));
    if (Number.isFinite(val)) out[key] = isPct ? val / 100 : val;
  }
  return out;
}

function pitchMixNarrative(profile, stat = '') {
  const factors = parsePitchMixFactors(profile);
  if (!factors.raw) return '';
  const statKey = normalizeStatToken(stat);
  const pieces = [];
  if (hasNumericValue(factors.power)) {
    if (factors.power >= 1.08) pieces.push(`pitch mix leans positive for power (${fmt(factors.power, 2)})`);
    else if (factors.power <= 0.94) pieces.push(`pitch mix is not power-friendly (${fmt(factors.power, 2)})`);
  }
  if (hasNumericValue(factors.tb)) {
    if (factors.tb >= 1.04) pieces.push(`total-bases factor is elevated (${fmt(factors.tb, 2)})`);
    else if (factors.tb <= 0.96) pieces.push(`total-bases factor is muted (${fmt(factors.tb, 2)})`);
    else if (['TB', 'HRR'].includes(statKey)) pieces.push(`total-bases factor is close to neutral (${fmt(factors.tb, 2)})`);
  }
  if (hasNumericValue(factors.hr)) {
    if (factors.hr >= 1.05) pieces.push(`home-run factor has a small boost (${fmt(factors.hr, 2)})`);
    else if (factors.hr <= 0.95) pieces.push(`home-run factor is suppressed (${fmt(factors.hr, 2)})`);
  }
  if (hasNumericValue(factors.whiff)) {
    if (factors.whiff <= 0.90) pieces.push(`whiff risk is lower (${fmt(factors.whiff, 2)})`);
    else if (factors.whiff >= 1.10) pieces.push(`whiff risk is elevated (${fmt(factors.whiff, 2)})`);
  }
  if (!pieces.length && factors.raw) return `Pitch-mix profile is available: ${factors.raw}.`;
  return sentenceCase(pieces.slice(0, 2).join(' and ')) + '.';
}

function lineupNarrative(profile) {
  const ctx = profile?.matchupContext || {};
  const bits = [];
  if (ctx.lineupOrder) bits.push(`projected ${ctx.lineupBand || 'lineup spot'} at order ${ctx.lineupOrder}`);
  if (ctx.handednessText) bits.push(`${ctx.handednessText} handedness look${ctx.handednessBucket ? ` (${ctx.handednessBucket})` : ''}`);
  if (hasNumericValue(ctx.temperatureF) || hasNumericValue(ctx.windMph)) {
    const env = [];
    if (hasNumericValue(ctx.temperatureF)) env.push(`${fmt(ctx.temperatureF, 0)}°F`);
    if (hasNumericValue(ctx.windMph)) env.push(`${fmt(ctx.windMph, 0)} mph wind`);
    bits.push(`${env.join(' and ')} environment`);
  }
  return bits.length ? sentenceCase(bits.join(' • ')) + '.' : '';
}

function propSupportScore(prop, entry) {
  const line = lineForProfileProp(prop, entry);
  const prob = probabilityForProfileProp(prop, entry);
  const model = hasNumericValue(Number(prop?.modelPred)) ? Number(prop.modelPred) : null;
  const simAvg = hasNumericValue(Number(prop?.similarityV2?.avgValue)) ? Number(prop.similarityV2.avgValue) : null;
  const l5 = hasNumericValue(Number(prop?.recent5Avg)) ? Number(prop.recent5Avg) : null;
  let score = 0;
  if (hasNumericValue(prob)) score += prob * 40;
  if (hasNumericValue(model) && hasNumericValue(line)) score += Math.max(-12, Math.min(18, (model - line) * 12));
  if (hasNumericValue(simAvg) && hasNumericValue(line)) score += Math.max(-8, Math.min(14, (simAvg - line) * 5));
  if (hasNumericValue(l5) && hasNumericValue(line)) score += Math.max(-6, Math.min(10, (l5 - line) * 4));
  return score;
}

function propReadableSummary(profile, prop, entry) {
  if (String(profile?.playerType || '').toLowerCase() === 'pitcher') {
    const pitcherSummary = pitcherPropReadableSummary(profile, prop, entry);
    if (pitcherSummary) return pitcherSummary;
  }
  const name = playerFirstName(profile, entry);
  const stat = normalizeStatToken(prop?.stat);
  const statName = readableStatName(prop).toLowerCase();
  const line = lineForProfileProp(prop, entry);
  const prob = probabilityForProfileProp(prop, entry);
  const model = hasNumericValue(Number(prop?.modelPred)) ? Number(prop.modelPred) : null;
  const sim = prop?.similarityV2 || {};
  const simAvg = hasNumericValue(Number(sim?.avgValue)) ? Number(sim.avgValue) : null;
  const simCount = hasNumericValue(Number(sim?.count)) ? Number(sim.count) : null;
  const l5 = hasNumericValue(Number(prop?.recent5Avg)) ? Number(prop.recent5Avg) : null;
  const pieces = [];

  if (hasNumericValue(simAvg)) {
    const linePhrase = hasNumericValue(line)
      ? (simAvg >= line ? `clearing the ${fmt(line, 1)} line` : `below the ${fmt(line, 1)} line`)
      : 'in the similar sample';
    pieces.push(`${name} has averaged ${fmt(simAvg, 2)} ${statName} across ${simCount || 'the top'} similar-game rows, ${linePhrase}.`);
  } else if (hasNumericValue(l5)) {
    pieces.push(`${name}'s recent form shows ${fmt(l5, 2)} ${statName} over the last five games.`);
  }

  if (hasNumericValue(model) && hasNumericValue(line)) {
    const diff = model - line;
    const strength = diff >= 0.5 ? 'clear' : diff >= 0.15 ? 'modest' : diff >= 0 ? 'thin' : 'negative';
    if (diff >= 0) pieces.push(`The model has a ${strength} lean over the line at ${fmt(model, 2)} vs ${fmt(line, 1)}${hasNumericValue(prob) ? ` (${fmtPct(prob)} probability)` : ''}.`);
    else pieces.push(`The model is below the line at ${fmt(model, 2)} vs ${fmt(line, 1)}${hasNumericValue(prob) ? ` (${fmtPct(prob)} probability)` : ''}.`);
  } else if (hasNumericValue(prob)) {
    pieces.push(`Model probability is ${fmtPct(prob)}.`);
  }

  const pitch = pitchMixNarrative(profile, stat);
  if (pitch && ['TB', 'HRR', 'HR', 'H', 'K'].includes(stat)) pieces.push(pitch);
  return pieces.slice(0, 3).join(' ');
}

function buildOverallMatchupRead(profile, selectedProps, entry) {
  const name = playerFullName(profile, entry);
  const ctxLine = String(profile?.playerType || '').toLowerCase() === 'pitcher'
    ? pitcherLineupSummary(profile)
    : lineupNarrative(profile);
  const scored = (selectedProps || [])
    .map(prop => ({ prop, score: propSupportScore(prop, entry) }))
    .sort((a, b) => b.score - a.score);
  const best = scored[0]?.prop;
  const pitch = pitchMixNarrative(profile, best?.stat || selectedProps?.[0]?.stat || '');
  const parts = [];
  if (ctxLine) parts.push(ctxLine);
  if (best) {
    const statName = readableStatName(best).toLowerCase();
    const line = lineForProfileProp(best, entry);
    const model = hasNumericValue(Number(best?.modelPred)) ? Number(best.modelPred) : null;
    const simAvg = hasNumericValue(Number(best?.similarityV2?.avgValue)) ? Number(best.similarityV2.avgValue) : null;
    const prob = probabilityForProfileProp(best, entry);
    const support = [];
    if (hasNumericValue(model) && hasNumericValue(line)) support.push(`model ${fmt(model, 2)} vs ${fmt(line, 1)}`);
    if (hasNumericValue(prob)) support.push(`${fmtPct(prob)} probability`);
    if (hasNumericValue(simAvg)) support.push(`similar-game avg ${fmt(simAvg, 2)}`);
    if (String(profile?.playerType || '').toLowerCase() === 'pitcher') {
      const pitcherRead = pitcherPropReadableSummary(profile, best, entry);
      parts.push(pitcherRead || `${name}'s strongest selected read is ${statName}${support.length ? ` (${support.join(' • ')})` : ''}.`);
    } else {
      parts.push(`${name}'s strongest selected read is ${statName}${support.length ? ` (${support.join(' • ')})` : ''}.`);
    }
  }
  if (pitch && String(profile?.playerType || '').toLowerCase() !== 'pitcher') parts.push(pitch);
  return parts.join(' ');
}

function selectedPropQuickReads(profile, selectedProps, entry) {
  return (selectedProps || [])
    .slice()
    .sort((a, b) => propSupportScore(b, entry) - propSupportScore(a, entry))
    .slice(0, 4)
    .map(prop => {
      const label = readableStatName(prop);
      return `<li><b>${escapeHtml(label)}:</b> ${escapeHtml(propReadableSummary(profile, prop, entry))}</li>`;
    }).join('');
}

function matchupWatchouts(profile, selectedProps, entry) {
  const warnings = [];
  (selectedProps || []).forEach(prop => {
    const stat = normalizeStatToken(prop?.stat);
    const line = lineForProfileProp(prop, entry);
    const prob = probabilityForProfileProp(prop, entry);
    const model = hasNumericValue(Number(prop?.modelPred)) ? Number(prop.modelPred) : null;
    if (!hasNumericValue(line)) warnings.push(`${readableStatName(prop)} line is pending.`);
    if (['HR', 'TB', 'HRR', '2B', 'SB'].includes(stat)) warnings.push(`${readableStatName(prop)} is naturally more volatile than a simple hit prop.`);
    if (hasNumericValue(model) && hasNumericValue(line) && model < line) warnings.push(`${readableStatName(prop)} model projection is below the listed line.`);
    if (hasNumericValue(prob) && prob < 0.5) warnings.push(`${readableStatName(prop)} probability is below 50%.`);
  });
  const unique = Array.from(new Set(warnings)).slice(0, 3);
  return unique.length ? unique : ['Use the selected cards as support, not certainty. Baseball props can swing heavily on one plate appearance.'];
}

function renderMatchupReadPanel(entry, profile, selectedProps) {
  const root = byId('analyzer-matchup-read');
  if (!root) return;
  if (!entry || !profile || !selectedProps?.length) {
    root.innerHTML = '';
    root.hidden = true;
    return;
  }
  root.hidden = false;
  const quickReads = selectedPropQuickReads(profile, selectedProps, entry);
  const watchouts = matchupWatchouts(profile, selectedProps, entry).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  root.innerHTML = `
    <article class="matchup-read-card matchup-read-card-primary">
      <span class="stat-label">Quick model read</span>
      <strong>How this matchup sets up</strong>
      <p>${escapeHtml(buildOverallMatchupRead(profile, selectedProps, entry) || 'The matchup context is available, but the selected props need more supporting data before a clean read can be summarized.')}</p>
    </article>
    <article class="matchup-read-card">
      <span class="stat-label">Selected prop summaries</span>
      <ul class="matchup-read-list">${quickReads || '<li>Select props to generate summaries.</li>'}</ul>
    </article>
    <article class="matchup-read-card matchup-read-card-watch">
      <span class="stat-label">Watch-outs</span>
      <ul class="matchup-read-list">${watchouts}</ul>
    </article>
  `;
}

function profileRowsForView(profile, view) {
  const rows = profile?.combinedGameLog || [];
  return filterByView(rows, view);
}

function statValueFromProfileRow(row, stat) {
  const payload = row?.stats?.[normalizeStatToken(stat)];
  return hasNumericValue(Number(payload?.value)) ? Number(payload.value) : null;
}

function profileContextValueFromRow(row) {
  if (hasNumericValue(Number(row?.minutes))) return Number(row.minutes);

  const statPayloads = Object.values(row?.stats || {});
  const statMinutes = statPayloads
    .map(payload => Number(payload?.minutes))
    .filter(Number.isFinite);
  if (statMinutes.length) return Math.max(...statMinutes);

  const statContextValues = statPayloads
    .map(payload => Number(payload?.contextValue))
    .filter(Number.isFinite);
  if (statContextValues.length) return Math.max(...statContextValues);

  if (hasNumericValue(Number(row?.contextValue))) return Number(row.contextValue);
  return null;
}

function setSinglePropGameLogVisibility(show) {
  const panel = byId('analyzer-game-log-panel');
  if (panel) panel.hidden = !show;
}

function renderSmallProfileChart(profile, prop, line, view) {
  const stat = normalizeStatToken(prop?.stat);
  const rows = profileRowsForView(profile, view).slice(-12);
  const values = rows.map(row => statValueFromProfileRow(row, stat)).filter(hasNumericValue);
  if (!rows.length || !values.length) {
    return '<div class="empty-state">No game-log values available for this prop.</div>';
  }

  const width = 420;
  const height = 180;
  const margin = { top: 14, right: 14, bottom: 32, left: 34 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const topValue = Math.max(...values, hasNumericValue(line) ? line : 0, 1);
  let y1 = Math.max(1, Math.ceil(topValue));
  if ((y1 - topValue) < 0.35) y1 += 1;
  const x = i => margin.left + (rows.length === 1 ? plotW / 2 : (i / (rows.length - 1)) * plotW);
  const y = value => margin.top + plotH - (Number(value) / (y1 || 1)) * plotH;

  const tickValues = Array.from(new Set([0, Math.round(y1 / 2), y1])).sort((a, b) => a - b);
  const grid = tickValues.map(value => {
    const py = y(value);
    return `<g><line x1="${margin.left}" x2="${width - margin.right}" y1="${py}" y2="${py}" stroke="rgba(255,255,255,.08)" /><text x="${margin.left - 8}" y="${py + 4}" fill="#9db0d0" font-size="10" text-anchor="end">${value}</text></g>`;
  }).join('');

  const points = rows.map((row, i) => {
    const value = statValueFromProfileRow(row, stat);
    return hasNumericValue(value) ? `${x(i)},${y(value)}` : '';
  }).filter(Boolean).join(' ');

  const simLookup = similarityLookupForProp(prop);
  const dots = rows.map((row, i) => {
    const value = statValueFromProfileRow(row, stat);
    if (!hasNumericValue(value)) return '';
    const cx = x(i);
    const cy = y(value);
    const label = row.shortLabel || row.label || row.gameDate || '';
    const simMatch = similarityMatchFromLookup(simLookup, row);
    const simBin = similarityQualityLabel(simMatch || {});
    const simScore = simMatch?.simScoreV2 ?? simMatch?.simScore;
    return `<g>
      <circle cx="${cx}" cy="${cy}" r="4.5" fill="${simColor(simBin)}" stroke="#0b1220" stroke-width="1.2">
        <title>${escapeHtml(`${label} ${row.opp || ''}: ${fmt(value, 1)}${simBin ? ` • ${simBin}` : ''}${hasNumericValue(Number(simScore)) ? ` ${fmt(Number(simScore), 0)}` : ''}`)}</title>
      </circle>
      <text x="${cx}" y="${height - 12}" fill="#9db0d0" font-size="9" text-anchor="middle">${escapeHtml(analyzerDisplayLabel({ label }))}</text>
    </g>`;
  }).join('');

  const lineY = hasNumericValue(line) ? y(line) : null;
  const lineSvg = hasNumericValue(lineY)
    ? `<line x1="${margin.left}" x2="${width - margin.right}" y1="${lineY}" y2="${lineY}" stroke="#ff7e79" stroke-width="2" stroke-dasharray="6 5"></line>`
    : '';

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(prop?.statDisplay || stat)} multi-prop chart">
      ${grid}
      ${lineSvg}
      <polyline fill="none" stroke="#59b4ff" stroke-width="3" points="${points}"></polyline>
      ${dots}
    </svg>
  `;
}

function renderProfileSummary(entry, profile, league) {
  const panel = byId('analyzer-multi-prop-panel');
  const root = byId('analyzer-profile-summary');
  if (!panel || !root) return;

  if (String(league || '').toUpperCase() !== 'MLB' || !entry) {
    panel.hidden = true;
    root.innerHTML = '';
    return;
  }

  panel.hidden = false;
  if (!profile) {
    root.innerHTML = `
      <div class="profile-summary-card">
        <span class="stat-label">Player profile</span>
        <strong>Not built yet</strong>
        <p class="muted">Run <code>python build_mlb_player_day_profiles.py --data-dir data --date ${escapeHtml(entry.gameDate || '')}</code> to enable the multi-prop view for this date.</p>
      </div>
    `;
    byId('analyzer-matchup-read').innerHTML = '';
    byId('analyzer-multi-prop-controls').innerHTML = '';
    byId('analyzer-multi-prop-cards').innerHTML = '';
    byId('analyzer-similarity-v2').innerHTML = '';
    byId('analyzer-multi-prop-charts').innerHTML = '';
    byId('analyzer-combined-log-table').innerHTML = '';
    return;
  }

  const contextPieces = matchupContextPieces(profile);
  const featureCards = matchupFeatureCards(profile);
  const qualityWarning = profileQualityWarningText(profile);
  const coverage = profile?.matchupFeatureSummary?.featureCoverage || profile?.matchupContext?.featureCoverage || {};
  const currentReady = ['lineupOrder', 'currentHandedness', 'currentTemperature', 'currentWind'].filter(key => coverage[key]).length;
  const missingForTrueSimilarity = profile?.matchupFeatureSummary?.missingForTrueSimilarity || [];
  root.innerHTML = `
    <article class="profile-summary-card">
      <span class="stat-label">Profile</span>
      <strong>${escapeHtml(profile.player || entry.player || 'Player')}</strong>
      <p class="muted">${escapeHtml(profile.matchup || entry.matchup || '')}</p>
      <div class="profile-quality-line">
        <span class="prop-chip">${profile?.dataQuality?.multiPropReady ? 'Multi-prop ready' : 'Single-prop only'}</span>
        ${qualityWarning ? `<span class="prop-chip multi-prop-warning">${escapeHtml(qualityWarning)}</span>` : '<span class="prop-chip">No profile warnings</span>'}
      </div>
    </article>
    <article class="profile-summary-card profile-summary-card-wide">
      <span class="stat-label">Current matchup context</span>
      <strong>${escapeHtml(contextPieces.join(' • ') || 'Context pending')}</strong>
      <div class="matchup-feature-list">
        ${featureCards.map(feature => `
          <span class="matchup-feature-chip">
            <em>${escapeHtml(feature.label || '')}</em>
            <b>${escapeHtml(feature.value || '—')}</b>
            ${feature.note ? `<small>${escapeHtml(feature.note)}</small>` : ''}
          </span>
        `).join('') || '<span class="matchup-feature-chip"><em>Context</em><b>Pending</b><small>Rebuild with current analyzer data</small></span>'}
      </div>
    </article>
    <article class="profile-summary-card">
      <span class="stat-label">Available props</span>
      <strong>${escapeHtml((profile.availableStats || []).join(', ') || '—')}</strong>
      <p class="muted">${profile?.dataQuality?.availableStatCount ?? 0} stat files combined</p>
    </article>
    <article class="profile-readiness-card">
      <span class="stat-label">Similarity readiness</span>
      <strong>${currentReady}/4 current fields structured</strong>
      <p class="muted">${escapeHtml(matchupReadinessText(profile))}</p>
      ${missingForTrueSimilarity.length ? `<p class="muted multi-prop-warning">Planned historical inputs: ${escapeHtml(missingForTrueSimilarity.join(', '))}</p>` : ''}
    </article>
    ${renderPitcherLineupMatchup(profile)}
  `;
}


function renderSimilarityV2Panel(entry, profile, selectedProps) {
  const root = byId('analyzer-similarity-v2');
  if (!root) return;
  root.className = 'similarity-v2-section';
  if (!entry || !profile) {
    root.innerHTML = '';
    return;
  }

  const props = selectedProps && selectedProps.length ? selectedProps : [selectedProfileProp(profile, entry)].filter(Boolean);
  if (!props.length) {
    root.innerHTML = '<div class="empty-state">Select at least one prop to view similarity details.</div>';
    return;
  }

  const coverage = props.reduce((acc, prop) => {
    const c = prop?.similarityV2?.featureCoverage || {};
    Object.keys(c).forEach(key => { if (c[key]) acc[key] = true; });
    return acc;
  }, {});
  const unavailable = [];
  if (!coverage.historicalHandedness) unavailable.push('historical handedness');
  if (!coverage.historicalPitchMix) unavailable.push('pitch mix');
  if (!coverage.historicalPark) unavailable.push('historical park');
  if (!coverage.historicalWeather) unavailable.push('historical weather');
  const scoredParts = ['opponent', 'home/away', 'lineup/context', 'AB/IP sample', 'recency'];
  if (coverage.historicalHandedness) scoredParts.push('historical handedness');
  if (coverage.historicalPark) scoredParts.push('park');
  if (coverage.historicalWeather) scoredParts.push('weather');
  if (coverage.historicalPitchMix) scoredParts.push('pitch-mix availability');
  const scoredFrom = scoredParts.join(', ');
  const cards = props.map(prop => {
    const stat = normalizeStatToken(prop.stat);
    const sim = profileSimilarityV2(prop);
    if (!sim) {
      return `
        <article class="similarity-v2-card">
          <span class="stat-label">${escapeHtml(prop.statDisplay || stat)}</span>
          <strong>Similarity v2 not built</strong>
          <p class="muted">Rebuild player profiles with the latest builder to add the transparent similarity sample.</p>
        </article>
      `;
    }
    const top = (sim.topGames || [])[0] || {};
    const topReasons = (top.simReasonsV2 || []).slice(0, 4);
    return `
      <article class="similarity-v2-card">
        <div class="similarity-v2-card-head">
          <div>
            <span class="stat-label">${escapeHtml(prop.statDisplay || stat)}</span>
            <strong>Similarity v2: ${fmt(sim.avgScore, 0)} avg score</strong>
          </div>
          <span class="sim-pill" style="--sim-color:${simColor(top.simBinV2)}">${escapeHtml(top.simBinV2 || 'v2')} ${fmt(top.simScoreV2, 0)}</span>
        </div>
        <p class="muted">Top ${sim.count || 0} rows • avg result ${fmt(sim.avgValue, 2)} • scored from ${scoredFrom}.</p>
        <div class="prop-meta">
          ${topReasons.map(reason => `<span class="prop-chip">${escapeHtml(reason)}</span>`).join('') || '<span class="prop-chip">No matched reason text</span>'}
        </div>
      </article>
    `;
  }).join('');

  const simRead = props.map(prop => {
    const sim = profileSimilarityV2(prop);
    return sim ? `${readableStatName(prop)} avg ${fmt(sim.avgValue, 2)} in ${sim.count || 0} similar rows` : '';
  }).filter(Boolean).slice(0, 3).join(' • ');

  root.innerHTML = `
    <div class="similarity-v2-intro">
      <div>
        <span class="stat-label">Similarity v2</span>
        <strong>Similar-game read</strong>
        <p class="muted">${escapeHtml(simRead || `Currently scored from ${scoredFrom}.`)} ${unavailable.length ? `Still missing: ${escapeHtml(unavailable.join(', '))}.` : 'Historical matchup fields are now available for the selected props.'}</p>
      </div>
      <span class="prop-chip">${props.length} selected prop${props.length === 1 ? '' : 's'}</span>
    </div>
    <details class="similarity-v2-details">
      <summary>Show similarity details</summary>
      <div class="similarity-v2-grid">
        ${cards}
      </div>
      ${unavailable.length ? `<p class="muted multi-prop-warning similarity-v2-global-warning">Still planned historical inputs: ${escapeHtml(unavailable.join(', '))}. Once those fields are added to each historical row, this can become a fuller handedness/pitch-mix matchup similarity score.</p>` : '<p class="muted similarity-v2-global-warning">Historical matchup fields are available for the selected props. Pitch-mix scoring still remains a light seed until full pitch-type vectors are added.</p>'}
    </details>
  `;
}

function renderMultiPropProfile(entry, profile, view, selectedStats, league) {
  const isMlb = String(league || '').toUpperCase() === 'MLB';
  setSinglePropGameLogVisibility(!(isMlb && !!profile));
  renderProfileSummary(entry, profile, league);
  if (!isMlb || !entry || !profile) return;

  const controls = byId('analyzer-multi-prop-controls');
  const cardsRoot = byId('analyzer-multi-prop-cards');
  const chartsRoot = byId('analyzer-multi-prop-charts');
  const logRoot = byId('analyzer-combined-log-table');
  if (!controls || !cardsRoot || !chartsRoot || !logRoot) return;

  const props = sortProfileProps(profile.availableProps || []);
  const activeStats = normalizeProfileSelectedStats(profile, selectedStats);
  const selectedSet = new Set(activeStats);

  controls.innerHTML = `
    <div class="multi-prop-controls-head">
      <strong>Choose props to show</strong>
      <span class="muted">Cards, charts, similarity details, and the combined log follow these selections.</span>
    </div>
    ${props.map(prop => {
      const stat = normalizeStatToken(prop.stat);
      return `
        <label class="multi-prop-toggle">
          <input type="checkbox" value="${escapeHtml(stat)}" ${selectedSet.has(stat) ? 'checked' : ''} />
          ${escapeHtml(prop.statDisplay || stat)}
        </label>
      `;
    }).join('')}
  `;

  const selectedProps = props.filter(prop => selectedSet.has(normalizeStatToken(prop.stat)));
  renderMatchupReadPanel(entry, profile, selectedProps);
  cardsRoot.innerHTML = selectedProps.map(prop => {
    const stat = normalizeStatToken(prop.stat);
    const line = lineForProfileProp(prop, entry);
    const prob = probabilityForProfileProp(prop, entry);
    const similar = prop?.similarityV2 || prop?.similarity || {};
    return `
      <article class="multi-prop-card is-selected">
        <span class="stat-label">${escapeHtml(prop.statDisplay || stat)}</span>
        <strong>${hasNumericValue(line) ? `${escapeHtml(prop.statDisplay || stat)} ${fmt(line, 1)}${lineOptionForProp(prop, entry)?.isComparisonLine ? ' avg' : ''}` : 'Line pending'}</strong>
        <div class="prop-meta">
          <span class="prop-chip">Model ${fmt(prop.modelPred, 2)}</span>
          <span class="prop-chip">${lineOptionForProp(prop, entry)?.isComparisonLine ? 'Vs avg' : 'Prob'} ${hasNumericValue(prob) ? fmtPct(prob) : '—'}</span>
          <span class="prop-chip">L5 avg ${fmt(prop.recent5Avg, 2)}</span>
          <span class="prop-chip">Similarity v2 avg ${fmt(similar.avgValue, 2)}</span>
          <span class="prop-chip">${prop.gameCount ?? 0} games</span>
        </div>
        <p class="prop-readable-summary">${escapeHtml(propReadableSummary(profile, prop, entry))}</p>
      </article>
    `;
  }).join('') || '<div class="empty-state">Select at least one prop to show player prop cards.</div>';

  renderSimilarityV2Panel(entry, profile, selectedProps);
  chartsRoot.innerHTML = selectedProps.map(prop => {
    const stat = normalizeStatToken(prop.stat);
    const line = lineForProfileProp(prop, entry);
    const prob = probabilityForProfileProp(prop, entry);
    return `
      <article class="multi-prop-chart-card">
        <h3>${escapeHtml(prop.statDisplay || stat)}</h3>
        <div class="prop-meta">
          <span class="prop-chip">${lineOptionForProp(prop, entry)?.isClosestAverageLine ? 'Near avg' : lineOptionForProp(prop, entry)?.isComparisonLine ? 'Avg' : 'Line'} ${hasNumericValue(line) ? fmt(line, 1) : '—'}</span>${lineOptionForProp(prop, entry)?.isClosestAverageLine && hasNumericValue(Number(lineOptionForProp(prop, entry)?.averageReference)) ? `<span class="prop-chip">Avg ref ${fmt(Number(lineOptionForProp(prop, entry).averageReference), 1)}</span>` : ''}
          <span class="prop-chip">Model ${fmt(prop.modelPred, 2)}</span>
          <span class="prop-chip">${lineOptionForProp(prop, entry)?.isComparisonLine ? 'Vs avg' : 'Prob'} ${hasNumericValue(prob) ? fmtPct(prob) : '—'}</span>
        </div>
        ${renderSmallProfileChart(profile, prop, line, view)}
      </article>
    `;
  }).join('') || '<div class="empty-state">Select at least one prop to chart.</div>';

  const rows = profileRowsForView(profile, view).slice().sort((a, b) => {
    if (Number.isFinite(Number(a.seq)) || Number.isFinite(Number(b.seq))) return Number(b.seq || 0) - Number(a.seq || 0);
    return String(b.gameDate || '').localeCompare(String(a.gameDate || ''));
  }).slice(0, 12);

  if (!rows.length) {
    logRoot.innerHTML = '<div class="empty-state">No combined game log available.</div>';
    return;
  }

  const statHeaders = selectedProps.map(prop => `<th>${escapeHtml(prop.statDisplay || prop.stat)}</th>`).join('');
  const similarityLookupByStat = new Map(selectedProps.map(prop => [normalizeStatToken(prop.stat), similarityLookupForProp(prop)]));
  const statCells = row => selectedProps.map(prop => {
    const value = statValueFromProfileRow(row, prop.stat);
    const line = lineForProfileProp(prop, entry);
    const hitClass = hasNumericValue(value) && hasNumericValue(line) && value >= line ? ' class="good"' : '';
    const lookup = similarityLookupByStat.get(normalizeStatToken(prop.stat));
    const simMatch = similarityMatchFromLookup(lookup, row);
    const simTitle = simMatch ? escapeHtml(simTitleFromItem(simMatch)) : '';
    const simHtml = simMatch
      ? `<span class="mini-sim-dot" style="--sim-color:${simColor(similarityQualityLabel(simMatch))}" title="${simTitle}"></span>`
      : '<span class="mini-sim-dot mini-sim-dot-muted" title="No similarity tier on this row"></span>';
    return `<td${hitClass}><div class="combined-log-stat-cell"><span>${fmt(value, 1)}</span>${simHtml}</div></td>`;
  }).join('');

  logRoot.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Opp</th>
          <th>Loc</th>
          ${statHeaders}
          <th>${escapeHtml(contextColumnLabel(entry, null))}</th>
          <th>Similarity</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            <td>${escapeHtml(row.label || row.gameDate || '')}</td>
            <td>${escapeHtml(row.opp || '')}</td>
            <td>${escapeHtml(row.location || '')}</td>
            ${statCells(row)}
            <td>${fmt(profileContextValueFromRow(row), 1)}</td>
            <td><div class="combined-log-sim-stack">${selectedProps.map(prop => {
              const lookup = similarityLookupByStat.get(normalizeStatToken(prop.stat));
              const simMatch = similarityMatchFromLookup(lookup, row);
              return `<span class="sim-pill sim-pill-compact" style="--sim-color:${simColor(similarityQualityLabel(simMatch || {}))}" title="${escapeHtml(simTitleFromItem(simMatch || {}))}">${escapeHtml(prop.statDisplay || prop.stat)}: ${escapeHtml(simLabelWithScore(simMatch || { simBin: 'all' }))}</span>`;
            }).join('')}</div></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
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
  const selectedDate = pickPreferredDate(data, league, requestedDate);
  const entries = (data.entries || []).filter(e => !selectedDate || e.gameDate === selectedDate);
  const requestedPlayerId = qs('playerId');
  const requestedPlayer = normalizeLookupToken(qs('player'));
  let playerId = requestedPlayerId || '';
  if (!playerId && requestedPlayer) {
    const match = entries.find(e => normalizeLookupToken(e.player) === requestedPlayer);
    playerId = match?.playerId ? String(match.playerId) : '';
  }
  if (!playerId) playerId = entries[0]?.playerId ? String(entries[0].playerId) : '';
  const requestedStat = normalizeStatToken(qs('stat') || '');
  const stat = canonicalStatForSelection(entries, playerId, requestedStat || (entries.find(e => String(e.playerId) === String(playerId))?.stat || ''), league);
  const requestedLine = qs('line') || '';
  const line = requestedLine || String(entries.find(e => String(e.playerId) === String(playerId) && normalizeStatToken(e.stat) === stat)?.line ?? '');
  return { league: String(league || 'NBA').toUpperCase(), date: selectedDate, playerId, stat, line, query: '', player: qs('player') || '' };
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
  const initialLeague = 'MLB';
  const state = {
    config: leagueConfig(initialLeague),
    data: null,
    selection: null,
    view: 'overall',
    profileStats: null,
    bound: false,
  };

  const seriesCache = new Map();
  const profileCache = new Map();
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
    const stat = canonicalStatForSelection(currentEntries(), state.selection.playerId, state.selection.stat, state.config.league);
    state.selection.stat = stat;
    const candidates = currentEntries().filter(e => String(e.playerId) === String(state.selection.playerId) && normalizeStatToken(e.stat) === stat);
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
    const aliasStat = state.config.league === 'MLB' && normalizeStatToken(entry?.stat) === 'H' ? 'ha' : '';
    const aliasFallbackPath = entry?.gameDate && entry?.playerId && aliasStat
      ? `${state.config.detailPrefix}/${entry.gameDate}/${entry.playerId}_${aliasStat}.json`
      : '';
    const pitcherAliasFallbackPath = entry?.gameDate && entry?.playerId && state.config.league === 'MLB' && normalizeStatToken(entry?.stat) === 'HA'
      ? `${state.config.detailPrefix}/${entry.gameDate}/pitcher_${entry.playerId}_ha.json`
      : '';
    const batterFallbackPath = entry?.gameDate && entry?.playerId && state.config.league === 'MLB' && normalizeStatToken(entry?.stat) === 'H'
      ? `${state.config.detailPrefix}/${entry.gameDate}/${entry.playerId}_h.json`
      : '';
    const candidates = [relPath, relPath ? `./${relPath}` : '', fallbackPath, aliasFallbackPath, pitcherAliasFallbackPath, batterFallbackPath].filter(Boolean);
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


  async function selectedProfile(entry) {
    if (!entry || state.config.league !== 'MLB') return null;
    if (!entry?.gameDate || !entry?.playerId) return null;
    const key = `${entry.gameDate}|${entry.playerId}`;
    if (profileCache.has(key)) return profileCache.get(key);
    const path = `${state.config.detailPrefix}/${entry.gameDate}/player_profiles/${entry.playerId}.json`;
    const promise = loadJson(path, null);
    profileCache.set(key, promise);
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

    populateSelect(leagueSelect, ['MLB'], item => item, item => item, 'MLB');

    state.selection.date = pickPreferredDate(state.data, state.config.league, state.selection.date);
    populateSelect(dateSelect, state.data?.dates || [], item => item, item => item, state.selection.date);

    const players = uniquePlayers(currentEntries(), state.selection.query);
    if (!players.some(p => String(p.playerId) === String(state.selection.playerId))) {
      state.selection.playerId = players[0]?.playerId ? String(players[0].playerId) : '';
    }
    populateSelect(playerSelect, players, item => String(item.playerId), item => item.player, state.selection.playerId);

    const stats = [...new Set(currentEntries().filter(e => String(e.playerId) === String(state.selection.playerId)).map(e => normalizeStatToken(e.stat)))].sort();
    state.selection.stat = canonicalStatForSelection(currentEntries(), state.selection.playerId, state.selection.stat, state.config.league);
    if (!stats.includes(state.selection.stat)) {
      state.selection.stat = stats[0] || '';
    }
    populateSelect(statSelect, stats, item => item, item => item, state.selection.stat);

    const lineEntries = currentEntries()
      .filter(e => String(e.playerId) === String(state.selection.playerId) && normalizeStatToken(e.stat) === state.selection.stat)
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
      renderChart(null, null, state.view, null);
      renderSummary(null, null, state.view);
      renderMultiPropProfile(null, null, state.view, [], state.config.league);
      updateAnalyzerTableLabels(null, null);
      renderTableRows('analyzer-games-body', [], null, null, null);
      renderTableRows('analyzer-similar-body', [], null, null, null);
      updateUrl(null, state.selection, state.config.league);
      return;
    }

    setStatus('<div class="status-banner info">Loading analyzer details…</div>');
    renderKpis(entry, null, state.view);
    renderChart(null, null, state.view, null);
    renderSummary(null, null, state.view);
    renderMultiPropProfile(entry, null, state.view, state.profileStats, state.config.league);
    updateAnalyzerTableLabels(entry, null);
    renderTableRows('analyzer-games-body', [], entry?.line, entry, null, null);
    renderTableRows('analyzer-similar-body', [], entry?.line, entry, null, null);

    const [series, profile] = await Promise.all([selectedSeries(entry), selectedProfile(entry)]);
    if (token !== renderToken) return;

    const normalizedProfileStats = profile ? normalizeProfileSelectedStats(profile, state.profileStats) : [];
    if (profile) state.profileStats = normalizedProfileStats;
    patchPitcherLineControl(entry, profile);

    updateHero(entry, series, profile);
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
      renderChart(null, null, state.view, null);
      renderSummary(null, null, state.view);
      updateAnalyzerTableLabels(entry, null);
      renderMultiPropProfile(entry, profile, state.view, normalizedProfileStats, state.config.league);
      renderTableRows('analyzer-games-body', [], entry?.line, entry, null, null);
      renderTableRows('analyzer-similar-body', [], entry?.line, entry, null, null);
      updateUrl(entry, state.selection, state.config.league);
      return;
    }

    renderKpis(entry, series, state.view, profile);
    renderChart(entry, series, state.view, profile);
    renderSummary(entry, series, state.view, profile);
    renderMultiPropProfile(entry, profile, state.view, normalizedProfileStats, state.config.league);
    updateAnalyzerTableLabels(entry, series);
    renderTableRows('analyzer-games-body', recentWindowGames(series || { games: [] }, state.view).slice().reverse(), entry?.line, entry, series, profile);
    const v2SimilarRows = profileSimilarityV2Games(profile, entry);
    renderTableRows('analyzer-similar-body', (v2SimilarRows.length ? v2SimilarRows : (series?.similarGames || [])).slice().reverse(), entry?.line, entry, series, profile);
    updateUrl(entry, state.selection, state.config.league);
  }

  function bind() {
    byId('analyzer-league')?.addEventListener('change', e => {
      state.view = 'overall';
      state.profileStats = null;
      load('MLB');
    });
    byId('analyzer-date')?.addEventListener('change', e => {
      state.selection.date = e.target.value;
      state.profileStats = null;
      render();
    });
    byId('analyzer-search')?.addEventListener('input', e => {
      state.selection.query = e.target.value || '';
      renderControls();
    });
    byId('analyzer-player')?.addEventListener('change', e => {
      state.selection.playerId = e.target.value;
      state.profileStats = null;
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
    byId('analyzer-multi-prop-controls')?.addEventListener('change', () => {
      const checked = Array.from(document.querySelectorAll('#analyzer-multi-prop-controls input[type="checkbox"]:checked'))
        .map(input => normalizeStatToken(input.value))
        .filter(Boolean);
      state.profileStats = checked;
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
