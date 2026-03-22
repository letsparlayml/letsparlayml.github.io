async function loadJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function fmt(num) {
  return Number(num).toFixed(1);
}

function uniqueLeagues(games) {
  return [...new Set(games.map(g => g.league))].sort();
}

function renderGames(games, league = 'ALL') {
  const root = document.getElementById('games-grid');
  const filtered = league === 'ALL' ? games : games.filter(g => g.league === league);
  if (!filtered.length) {
    root.innerHTML = '<div class="empty-state">No games found for this league.</div>';
    return;
  }

  root.innerHTML = filtered.map(game => {
    const edgeSpread = game.modelHomeSpread - game.marketSpread;
    const edgeTotal = game.modelTotal - game.marketTotal;
    return `
      <article class="game-card">
        <div class="meta-row">
          <span class="tag">${game.league}</span>
          <span>${game.gameDate}</span>
        </div>
        <div>
          <h3>${game.awayTeam} @ ${game.homeTeam}</h3>
          <p class="muted">${game.summary}</p>
        </div>
        <div class="score-box">
          <div class="score-row"><span>${game.awayTeam}</span><strong>${fmt(game.modelAwayScore)}</strong></div>
          <div class="score-row"><span>${game.homeTeam}</span><strong>${fmt(game.modelHomeScore)}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model spread</span><strong>${fmt(game.modelHomeSpread)}</strong></div>
          <div class="kpi"><span>Spread edge</span><strong>${edgeSpread >= 0 ? '+' : ''}${fmt(edgeSpread)}</strong></div>
          <div class="kpi"><span>Total edge</span><strong>${edgeTotal >= 0 ? '+' : ''}${fmt(edgeTotal)}</strong></div>
        </div>
        <div class="meta-row">
          <span>Confidence: ${game.confidence}</span>
          <a href="game.html?id=${encodeURIComponent(game.id)}">Open detail</a>
        </div>
      </article>
    `;
  }).join('');
}

function renderProps(props) {
  const body = document.getElementById('props-body');
  body.innerHTML = props.map(p => `
    <tr>
      <td>${p.league}</td>
      <td>${p.player}</td>
      <td>${p.stat}</td>
      <td>${p.line}</td>
      <td>${p.model}</td>
      <td>${p.edge >= 0 ? '+' : ''}${p.edge}</td>
      <td>${p.confidence}</td>
      <td>${p.note}</td>
    </tr>
  `).join('');
}

function renderResults(results) {
  const body = document.getElementById('results-body');
  body.innerHTML = results.map(r => `
    <tr>
      <td>${r.date}</td>
      <td>${r.league}</td>
      <td>${r.matchup}</td>
      <td>${r.pick}</td>
      <td>${r.actual}</td>
      <td>${r.status}</td>
    </tr>
  `).join('');
}

function fillHeader(meta, games, props) {
  document.getElementById('site-title').textContent = meta.siteTitle;
  document.getElementById('hero-leagues').textContent = meta.leagues.join(' • ');
  document.getElementById('hero-game-count').textContent = games.length;
  document.getElementById('hero-prop-count').textContent = props.length;
  document.getElementById('hero-updated').textContent = meta.lastUpdated;
}

function setupLeagueFilter(games) {
  const select = document.getElementById('league-filter');
  uniqueLeagues(games).forEach(league => {
    const option = document.createElement('option');
    option.value = league;
    option.textContent = league;
    select.appendChild(option);
  });
  select.addEventListener('change', () => renderGames(games, select.value));
}

(async function init() {
  try {
    const [meta, games, props, results] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json'),
      loadJson('data/props.json'),
      loadJson('data/results.json')
    ]);

    fillHeader(meta, games, props);
    setupLeagueFilter(games);
    renderGames(games);
    renderProps(props);
    renderResults(results);
  } catch (err) {
    document.getElementById('games-grid').innerHTML = `<div class="empty-state">${err.message}</div>`;
  }
})();
