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
          <span class="tag">${game.league || ''}</span>
          <span>${game.gameDate || ''}</span>
        </div>
        <div>
          <h3>${game.awayTeam} @ ${game.homeTeam}</h3>
          <p class="muted">${game.summary || ''}</p>
        </div>
        <div class="score-box">
          <div class="score-row"><span>${game.awayTeam}</span><strong>${fmt(game.modelAwayScore)}</strong></div>
          <div class="score-row"><span>${game.homeTeam}</span><strong>${fmt(game.modelHomeScore)}</strong></div>
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
          <span>Confidence: ${game.confidence || 'N/A'}</span>
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

function renderProps(props) {
  const body = byId('props-body');
  if (!body) return;

  body.innerHTML = (props || []).map(p => `
    <tr>
      <td>${p.league || ''}</td>
      <td>${p.player || ''}</td>
      <td>${p.stat || ''}</td>
      <td>${p.line ?? ''}</td>
      <td>${p.modelPrediction ?? p.model ?? ''}</td>
      <td>${Number.isFinite(Number(p.probability)) ? `${Number(p.probability).toFixed(1)}%` : 'N/A'}</td>
      <td>${p.confidence || ''}</td>
      <td>${p.matchup || p.note || ''}</td>
    </tr>
  `).join('');
}

function renderResults(results) {
  const body = byId('results-body');
  if (!body) return;

  body.innerHTML = (results || []).map(r => `
    <tr>
      <td>${r.date || ''}</td>
      <td>${r.league || ''}</td>
      <td>${r.matchup || ''}</td>
      <td>${r.predicted || r.pick || ''}</td>
      <td>${r.actual || ''}</td>
      <td>${r.mlResult || r.status || 'N/A'}</td>
      <td>${r.spreadResult || 'N/A'}</td>
      <td>${r.totalResult || 'N/A'}</td>
    </tr>
  `).join('');
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
  setText('results-date-label', meta?.resultsDate || '');
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
    const [meta, games, props, results] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/results.json', [])
    ]);

    const todayGames = (games || []).filter(g => g.gameDate === meta.targetDate);
    const tomorrowGames = (games || []).filter(g => g.gameDate === meta.nextDate);

    fillHeader(meta, todayGames, tomorrowGames, props);
    setupLeagueFilter(games, meta);
    renderProps(props);
    renderResults(results);
  } catch (err) {
    console.error(err);
    if (root) {
      root.innerHTML = `<div class="empty-state">Failed to load site data: ${err.message || err}</div>`;
    }
  }
})();
