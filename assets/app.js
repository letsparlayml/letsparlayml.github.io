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

function setText(id, value) {
  const el = byId(id);
  if (el) el.textContent = value ?? '';
}

function fmt(num, digits = 1) {
  const n = Number(num);
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function fmtSigned(num, digits = 1) {
  const n = Number(num);
  if (!Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
}

function uniqueLeagues(games) {
  return [...new Set((games || []).map(g => g.league).filter(Boolean))].sort();
}

function leagueName(g) {
  return g.league || '';
}

function marketSpreadText(game) {
  return Number.isFinite(Number(game.marketSpread)) ? fmtSigned(game.marketSpread) : '—';
}

function marketTotalText(game) {
  return Number.isFinite(Number(game.marketTotal)) ? fmt(game.marketTotal) : '—';
}

function renderGames(games, league = 'ALL') {
  const root = byId('games-grid');
  if (!root) return;
  const filtered = league === 'ALL' ? games : games.filter(g => g.league === league);
  if (!filtered.length) {
    root.innerHTML = '<div class="empty-state">No games found for this league.</div>';
    return;
  }

  root.innerHTML = filtered.map(game => {
    const edgeSpread = Number.isFinite(Number(game.marketSpread)) ? Number(game.modelHomeSpread) - Number(game.marketSpread) : NaN;
    const edgeTotal = Number.isFinite(Number(game.marketTotal)) ? Number(game.modelTotal) - Number(game.marketTotal) : NaN;
    return `
      <article class="game-card">
        <div class="meta-row">
          <span class="tag">${leagueName(game)}</span>
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
          <div class="kpi"><span>Market total</span><strong>${marketTotalText(game)}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model total</span><strong>${fmt(game.modelTotal)}</strong></div>
          <div class="kpi"><span>Spread edge</span><strong>${fmtSigned(edgeSpread)}</strong></div>
          <div class="kpi"><span>Total edge</span><strong>${fmtSigned(edgeTotal)}</strong></div>
        </div>
        <div class="meta-row">
          <span>Confidence: ${game.confidence || '—'}</span>
          <a href="game.html?id=${encodeURIComponent(game.id)}">Open detail</a>
        </div>
      </article>
    `;
  }).join('');
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
      <td>${p.model ?? ''}</td>
      <td>${Number.isFinite(Number(p.edge)) ? fmtSigned(p.edge) : ''}</td>
      <td>${p.confidence || ''}</td>
      <td>${p.note || ''}</td>
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
      <td>${r.status || ''}</td>
    </tr>
  `).join('');
}

function fillHeader(meta, games, props) {
  setText('site-title', meta?.siteTitle || 'Sports Predictions Showcase');
  setText('hero-leagues', Array.isArray(meta?.leagues) ? meta.leagues.join(' • ') : 'NBA • NHL • CBB');
  setText('hero-game-count', String((games || []).length));
  setText('hero-prop-count', String((props || []).length));
  setText('hero-updated', meta?.lastUpdated || '—');
}

function setupLeagueFilter(games) {
  const select = byId('league-filter');
  if (!select) return;
  uniqueLeagues(games).forEach(league => {
    const option = document.createElement('option');
    option.value = league;
    option.textContent = league;
    select.appendChild(option);
  });
  select.addEventListener('change', () => renderGames(games, select.value));
}

(async function init() {
  const root = byId('games-grid');
  try {
    const [meta, games, props, results] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/results.json', [])
    ]);

    fillHeader(meta, games, props);
    setupLeagueFilter(games);
    renderGames(games);
    renderProps(props);
    renderResults(results);
  } catch (err) {
    console.error(err);
    if (root) {
      root.innerHTML = `<div class="empty-state">Failed to load site data: ${err.message || err}</div>`;
    }
  }
})();
