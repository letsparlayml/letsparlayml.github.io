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
  return String(
    p.probabilityText ??
    p.probability_note ??
    p.matchup ??
    p.note ??
    ''
  );
}

function propProbabilityText(p) {
  const candidates = [
    p.probability,
    p.clearProbability,
    p.clear_probability,
    p.prob,
    p.winProbability,
    p.win_probability
  ];

  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return `${n.toFixed(1)}%`;
    }
  }

  const src = probabilitySourceText(p);
  const match = src.match(/(\d+(?:\.\d+)?)%\s*(?:to\s+clear|clear|over|under|hit)?/i);
  return match ? `${Number(match[1]).toFixed(1)}%` : 'N/A';
}

function propMatchupText(p) {
  const src = probabilitySourceText(p);
  if (!src) return 'N/A';
  const cleaned = src
    .replace(/\s*[•\-|–—]\s*\d+(?:\.\d+)?%.*$/i, '')
    .replace(/\s+\d+(?:\.\d+)?%.*$/i, '')
    .trim();
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
    pctText: graded > 0 && winPct !== null && winPct !== undefined ? `${Number(winPct).toFixed(1)}%` : 'N/A',
    gradedText: graded > 0 ? `${graded} graded` : 'No graded plays',
    graded
  };
}

function metricSummaryHtml(label, metric) {
  const parts = summaryMetricParts(metric);

  return `
    <div class="summary-metric">
      <span class="summary-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(parts.record)}</strong>
      <span class="summary-note">${escapeHtml(parts.pctText)} • ${escapeHtml(parts.gradedText)}</span>
    </div>
  `;
}

function sportSummaryBlockHtml(label, metrics, emphasized = false) {
  const classes = emphasized ? 'sport-summary sport-summary-overall' : 'sport-summary';

  return `
    <section class="${classes}">
      <div class="sport-summary-head">
        <h4>${escapeHtml(label)}</h4>
      </div>
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
  switch (key) {
    case 'yesterday':
      return 'Previous day';
    case 'weekToDate':
      return 'Current week';
    case 'monthToDate':
      return 'Current month';
    case 'yearToDate':
      return 'Current year';
    default:
      return key;
  }
}

function renderResultsSummary(summary) {
  const root = byId('results-summary-grid');
  if (!root) return;

  const periods = summary?.periods || {};
  const order = ['yesterday', 'weekToDate', 'monthToDate', 'yearToDate'];
  const leagueOrder = ['NBA', 'NHL', 'CBB'];

  const cards = order
    .filter(key => periods[key])
    .map(key => {
      const period = periods[key];
      const byLeague = period.byLeague || {};
      const leagues = [
        ...leagueOrder.filter(league => byLeague[league]),
        ...Object.keys(byLeague).filter(league => !leagueOrder.includes(league)).sort()
      ];

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
    const [meta, games, props, results, resultsSummary] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/results.json', []),
      loadJson('data/results_summary.json', {})
    ]);

    const todayGames = (games || []).filter(g => g.gameDate === meta.targetDate);
    const tomorrowGames = (games || []).filter(g => g.gameDate === meta.nextDate);

    fillHeader(meta, todayGames, tomorrowGames, props);
    setupLeagueFilter(games, meta);
    renderProps(props);
    renderResultsSummary(resultsSummary);
    renderResults(results);
  } catch (err) {
    console.error(err);
    if (root) {
      root.innerHTML = `<div class="empty-state">Failed to load site data: ${escapeHtml(err.message || err)}</div>`;
    }
  }
})();
