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

function setText(id, value) {
  const el = byId(id);
  if (el) el.textContent = value ?? '';
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

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function uniqueLeagues(games) {
  return [...new Set((games || []).map(g => g.league).filter(Boolean))].sort();
}

function marketSpreadText(game) {
  return hasNumericValue(game.marketSpread) ? fmtSigned(game.marketSpread) : 'N/A';
}

function marketTotalText(game) {
  return hasNumericValue(game.marketTotal) ? fmt(game.marketTotal) : 'N/A';
}

function gameCard(game) {
  const edgeSpread = hasNumericValue(game.marketSpread) ? Number(game.modelHomeSpread) - Number(game.marketSpread) : NaN;
  const edgeTotal = hasNumericValue(game.marketTotal) ? Number(game.modelTotal) - Number(game.marketTotal) : NaN;
  return `
      <article class="game-card">
        <div class="meta-row">
          <span class="tag">${escapeHtml(game.league || '')}</span>
          <span>${escapeHtml(game.gameDate || '')}</span>
        </div>
        <div>
          <h3>${escapeHtml(game.awayTeam)} @ ${escapeHtml(game.homeTeam)}</h3>
          <p class="muted">${escapeHtml(game.summary || '')}</p>
        </div>
        <div class="score-box">
          <div class="score-row"><span>${escapeHtml(game.awayTeam)}</span><strong>${fmt(game.modelAwayScore)}</strong></div>
          <div class="score-row"><span>${escapeHtml(game.homeTeam)}</span><strong>${fmt(game.modelHomeScore)}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model spread</span><strong>${fmtSigned(game.modelHomeSpread)}</strong></div>
          <div class="kpi"><span>Market spread</span><strong>${marketSpreadText(game)}</strong></div>
          <div class="kpi"><span>Spread edge</span><strong>${Number.isFinite(edgeSpread) ? fmtSigned(edgeSpread) : 'N/A'}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model total</span><strong>${fmt(game.modelTotal)}</strong></div>
          <div class="kpi"><span>Market total</span><strong>${marketTotalText(game)}</strong></div>
          <div class="kpi"><span>Total edge</span><strong>${Number.isFinite(edgeTotal) ? fmtSigned(edgeTotal) : 'N/A'}</strong></div>
        </div>
        <div class="meta-row">
          <span>Confidence: ${escapeHtml(game.confidence || 'N/A')}</span>
          <a href="game.html?id=${encodeURIComponent(game.id)}">Open detail</a>
        </div>
      </article>
    `;
}

function renderGameSection(games, rootId, league = 'ALL') {
  const root = byId(rootId);
  if (!root) return;
  const filtered = league === 'ALL' ? games : games.filter(g => g.league === league);
  if (!filtered.length) {
    root.innerHTML = '<div class="empty-state">No games found for this league.</div>';
    return;
  }
  root.innerHTML = filtered.map(gameCard).join('');
}

function probabilitySourceText(p) {
  return String(p.probabilityText ?? p.probability_note ?? p.matchup ?? p.note ?? '');
}

function propProbabilityText(p) {
  const candidates = [p.probability, p.clearProbability, p.clear_probability, p.prob, p.winProbability, p.win_probability];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return `${n.toFixed(1)}%`;
  }
  const src = probabilitySourceText(p);
  const match = src.match(/(\d+(?:\.\d+)?)%\s*(?:to\s+clear|clear|over|under|hit)?/i);
  return match ? `${Number(match[1]).toFixed(1)}%` : 'N/A';
}

function propMatchupText(p) {
  const src = probabilitySourceText(p);
  if (!src) return 'N/A';
  const cleaned = src.replace(/\s*[•\-|–—]\s*\d+(?:\.\d+)?%.*$/i, '').replace(/\s+\d+(?:\.\d+)?%.*$/i, '').trim();
  return cleaned || 'N/A';
}

function renderProps(props) {
  const body = byId('props-body');
  if (!body) return;
  body.innerHTML = (props || []).map(p => `
    <tr>
      <td>${escapeHtml(p.league || '')}</td>
      <td>${escapeHtml(p.player || '')}</td>
      <td>${escapeHtml(p.stat || '')}</td>
      <td>${escapeHtml(p.line ?? '')}</td>
      <td>${escapeHtml(p.modelPrediction ?? p.model ?? '')}</td>
      <td>${escapeHtml(propProbabilityText(p))}</td>
      <td>${escapeHtml(p.confidence || '')}</td>
      <td>${escapeHtml(propMatchupText(p))}</td>
    </tr>
  `).join('');
}

function resultBadgeClass(result) {
  const normalized = String(result || '').trim().toLowerCase();
  if (normalized === 'win') return 'badge-win';
  if (normalized === 'loss') return 'badge-loss';
  if (normalized === 'push') return 'badge-push';
  return 'badge-na';
}

function renderResults(results) {
  const body = byId('results-body');
  if (!body) return;
  body.innerHTML = (results || []).map(r => `
    <tr>
      <td>${escapeHtml(r.date || '')}</td>
      <td>${escapeHtml(r.league || '')}</td>
      <td>${escapeHtml(r.matchup || '')}</td>
      <td>${escapeHtml(r.predicted || r.pick || '')}</td>
      <td>${escapeHtml(r.actual || '')}</td>
      <td><span class="result-badge ${resultBadgeClass(r.mlResult || r.status)}">${escapeHtml(r.mlResult || r.status || 'N/A')}</span></td>
      <td><span class="result-badge ${resultBadgeClass(r.spreadResult)}">${escapeHtml(r.spreadResult || 'N/A')}</span></td>
      <td><span class="result-badge ${resultBadgeClass(r.totalResult)}">${escapeHtml(r.totalResult || 'N/A')}</span></td>
    </tr>
  `).join('');
}

function summaryMetricParts(metric) {
  const wins = Number(metric?.wins || 0);
  const losses = Number(metric?.losses || 0);
  const pushes = Number(metric?.pushes || 0);
  const graded = Number(metric?.graded || 0);
  const winPct = metric?.winPct;
  return {
    record: pushes > 0 ? `${wins}-${losses}-${pushes}` : `${wins}-${losses}`,
    pctText: graded > 0 && winPct !== null && winPct !== undefined ? `${Number(winPct).toFixed(1)}%` : 'N/A'
  };
}

function sportSummaryBlockHtml(label, metrics, emphasized = false) {
  const classes = emphasized ? 'sport-summary sport-summary-overall' : 'sport-summary';
  return `
    <section class="${classes}">
      <div class="sport-summary-head"><h4>${escapeHtml(label)}</h4></div>
      <div class="sport-summary-metrics">
        ${['ML', 'Spread', 'Total'].map(metricName => {
          const parts = summaryMetricParts(metrics?.[metricName]);
          return `
            <div class="sport-metric-chip">
              <span>${escapeHtml(metricName)}</span>
              <strong>${escapeHtml(parts.record)}</strong>
              <small>${escapeHtml(parts.pctText)}</small>
            </div>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function periodTitle(key) {
  return ({ yesterday: 'Previous day', weekToDate: 'Current week', monthToDate: 'Current month', yearToDate: 'Current year' })[key] || key;
}

function renderResultsSummary(summary) {
  const root = byId('results-summary-grid');
  if (!root) return;
  const periods = summary?.periods || {};
  const order = ['yesterday', 'weekToDate', 'monthToDate', 'yearToDate'];
  const leagueOrder = ['NBA', 'NHL', 'CBB'];
  const cards = order.filter(key => periods[key]).map(key => {
    const period = periods[key];
    const byLeague = period.byLeague || {};
    const leagues = [...leagueOrder.filter(league => byLeague[league]), ...Object.keys(byLeague).filter(league => !leagueOrder.includes(league)).sort()];
    return `
      <article class="summary-card">
        <div class="summary-card-head">
          <div>
            <span class="summary-kicker">${escapeHtml(periodTitle(key))}</span>
            <h3>${escapeHtml(period.startDate === period.endDate ? period.endDate : `${period.startDate} to ${period.endDate}`)}</h3>
          </div>
          <span class="summary-rows">${escapeHtml(period.rowCount ?? 0)} games</span>
        </div>
        <div class="sport-breakdown-grid">
          ${sportSummaryBlockHtml('Overall', period.overall, true)}
          ${leagues.map(league => sportSummaryBlockHtml(league, byLeague[league])).join('')}
        </div>
      </article>
    `;
  });
  root.innerHTML = cards.length ? cards.join('') : '<div class="empty-state">No summary results available yet.</div>';
}

function propInsightCard(prop) {
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
    </article>
  `;
}

function renderInsightGrid(rootId, items, role = false) {
  const root = byId(rootId);
  if (!root) return;
  if (!items || !items.length) {
    root.innerHTML = '<div class="empty-state">No props available.</div>';
    return;
  }
  root.innerHTML = items.map(item => role ? roleCard(item) : propInsightCard(item)).join('');
}

function edgeBoardCard(title, items, kind) {
  if (!items.length) return `<article class="insight-board"><h4>${escapeHtml(title)}</h4><div class="empty-state">No lined NBA games yet.</div></article>`;
  const rows = items.map(item => {
    const edge = kind === 'spread' ? item.spreadEdge : item.totalEdge;
    const market = kind === 'spread' ? item.marketSpread : item.marketTotal;
    const model = kind === 'spread' ? item.modelHomeSpread : item.modelTotal;
    return `
      <div class="edge-row">
        <div>
          <strong>${escapeHtml(`${item.awayTeam} @ ${item.homeTeam}`)}</strong>
          <span>${kind === 'spread' ? `Model ${escapeHtml(fmtSigned(model))} vs market ${escapeHtml(fmtSigned(market))}` : `Model ${escapeHtml(fmt(model))} vs market ${escapeHtml(fmt(market))}`}</span>
        </div>
        <strong>${escapeHtml(fmtSigned(edge))}</strong>
      </div>
    `;
  }).join('');
  return `<article class="insight-board"><h4>${escapeHtml(title)}</h4>${rows}</article>`;
}

function renderNbaGameEdges(games, meta) {
  const root = byId('nba-game-edges-grid');
  if (!root) return;
  const nba = (games || []).filter(g => g.league === 'NBA' && g.gameDate === meta.targetDate);
  const lined = nba.map(g => ({ ...g, spreadEdge: hasNumericValue(g.marketSpread) ? Number(g.modelHomeSpread) - Number(g.marketSpread) : NaN, totalEdge: hasNumericValue(g.marketTotal) ? Number(g.modelTotal) - Number(g.marketTotal) : NaN }));
  const spreadTop = lined.filter(g => Number.isFinite(g.spreadEdge)).sort((a, b) => Math.abs(b.spreadEdge) - Math.abs(a.spreadEdge)).slice(0, 4);
  const totalTop = lined.filter(g => Number.isFinite(g.totalEdge)).sort((a, b) => Math.abs(b.totalEdge) - Math.abs(a.totalEdge)).slice(0, 4);
  root.innerHTML = [edgeBoardCard('Biggest spread gaps', spreadTop, 'spread'), edgeBoardCard('Biggest total gaps', totalTop, 'total')].join('');
}

function renderHomeInsights(homeInsights, meta) {
  const day = homeInsights?.byDate?.[meta.targetDate];
  if (!day) return;
  renderInsightGrid('home-consensus-grid', day.consensusTop);
  renderInsightGrid('home-floor-grid', day.floorTop);
  renderInsightGrid('home-ceiling-grid', day.ceilingTop);
  renderInsightGrid('home-role-up-grid', day.roleUp, true);
  renderInsightGrid('home-role-down-grid', day.roleDown, true);
}

function fillHeader(meta, todayGames, tomorrowGames, props) {
  setText('site-title', meta?.siteTitle || 'Lets Parlay ML');
  setText('hero-leagues', Array.isArray(meta?.leagues) ? meta.leagues.join(' • ') : 'NBA • NHL • CBB');
  setText('hero-game-count', String((todayGames || []).length));
  setText('hero-next-game-count', String((tomorrowGames || []).length));
  setText('hero-prop-count', String((props || []).length));
  setText('hero-updated', meta?.lastUpdated || '—');
  setText('today-date-label', meta?.targetDate || '');
  setText('tomorrow-date-label', meta?.nextDate || '');
  setText('results-date-label', meta?.resultsDate || meta?.targetDate || '');
}

function setupLeagueFilter(allGames, meta) {
  const select = byId('league-filter');
  if (!select) return;
  uniqueLeagues(allGames).forEach(league => {
    const option = document.createElement('option');
    option.value = league;
    option.textContent = league;
    select.appendChild(option);
  });
  const rerender = () => {
    const league = select.value;
    const today = (allGames || []).filter(g => g.gameDate === meta.targetDate);
    const tomorrow = (allGames || []).filter(g => g.gameDate === meta.nextDate);
    renderGameSection(today, 'today-games-grid', league);
    renderGameSection(tomorrow, 'tomorrow-games-grid', league);
  };
  select.addEventListener('change', rerender);
  rerender();
}

(async function init() {
  const root = byId('today-games-grid') || byId('games-grid');
  try {
    const [meta, games, props, results, resultsSummary, homeInsights] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/results.json', []),
      loadJson('data/results_summary.json', {}),
      loadJson('data/nba_home_insights.json', {})
    ]);
    const todayGames = (games || []).filter(g => g.gameDate === meta.targetDate);
    const tomorrowGames = (games || []).filter(g => g.gameDate === meta.nextDate);
    fillHeader(meta, todayGames, tomorrowGames, props);
    setupLeagueFilter(games, meta);
    renderProps(props);
    renderNbaGameEdges(games, meta);
    renderHomeInsights(homeInsights, meta);
    renderResultsSummary(resultsSummary);
    renderResults(results);
  } catch (err) {
    console.error(err);
    if (root) root.innerHTML = `<div class="empty-state">Failed to load site data: ${escapeHtml(err.message || err)}</div>`;
  }
})();
