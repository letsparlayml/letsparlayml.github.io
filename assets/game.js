async function loadJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function fmt(num) {
  return Number(num).toFixed(1);
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function renderChart(movement) {
  const box = document.getElementById('movement-chart');
  if (!movement || !movement.length) {
    box.innerHTML = '<div class="empty-state">No movement records available.</div>';
    return;
  }

  const labels = movement.map(d => d.date);
  const away = movement.map(d => Number(d.predictedAway));
  const home = movement.map(d => Number(d.predictedHome));
  const width = 900;
  const height = 280;
  const pad = 32;
  const all = [...away, ...home];
  const minY = Math.min(...all) - 2;
  const maxY = Math.max(...all) + 2;
  const stepX = (width - pad * 2) / Math.max(1, labels.length - 1);

  const x = i => pad + i * stepX;
  const y = v => height - pad - ((v - minY) / (maxY - minY || 1)) * (height - pad * 2);
  const path = series => series.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ');

  const labelHtml = labels.map((label, i) => `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#9db0d0" font-size="11">${label.slice(5)}</text>`).join('');
  const grid = Array.from({ length: 5 }, (_, i) => {
    const val = minY + (i / 4) * (maxY - minY);
    const yy = y(val);
    return `
      <line x1="${pad}" x2="${width - pad}" y1="${yy}" y2="${yy}" stroke="rgba(255,255,255,.10)" />
      <text x="8" y="${yy + 4}" fill="#9db0d0" font-size="11">${fmt(val)}</text>
    `;
  }).join('');

  const points = (series, color) => series.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${color}" />`).join('');

  box.innerHTML = `
    <div class="legend">
      <span><span class="legend-dot" style="background:#7bf1c8"></span>Away prediction</span>
      <span><span class="legend-dot" style="background:#59b4ff"></span>Home prediction</span>
    </div>
    <svg viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="Prediction movement chart">
      ${grid}
      <path d="${path(away)}" fill="none" stroke="#7bf1c8" stroke-width="3" />
      <path d="${path(home)}" fill="none" stroke="#59b4ff" stroke-width="3" />
      ${points(away, '#7bf1c8')}
      ${points(home, '#59b4ff')}
      ${labelHtml}
    </svg>
  `;
}

function renderMovementTable(movement) {
  const body = document.getElementById('movement-body');
  body.innerHTML = movement.map(row => `
    <tr>
      <td>${row.date}</td>
      <td>${fmt(row.predictedAway)}</td>
      <td>${fmt(row.predictedHome)}</td>
      <td>${fmt(row.modelHomeSpread)}</td>
      <td>${fmt(row.marketSpread)}</td>
      <td>${fmt(row.modelTotal)}</td>
      <td>${fmt(row.marketTotal)}</td>
      <td>${row.note || ''}</td>
    </tr>
  `).join('');
}

(async function init() {
  try {
    const id = qs('id');
    const games = await loadJson('data/games.json');
    const game = games.find(g => g.id === id) || games[0];
    if (!game) throw new Error('No game records found.');

    document.title = `${game.awayTeam} @ ${game.homeTeam}`;
    document.getElementById('game-league').textContent = game.league;
    document.getElementById('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    document.getElementById('game-summary').textContent = game.summary;
    document.getElementById('snapshot-score').textContent = `${fmt(game.modelAwayScore)} - ${fmt(game.modelHomeScore)}`;
    document.getElementById('snapshot-spread').textContent = fmt(game.marketSpread);
    document.getElementById('snapshot-total').textContent = fmt(game.marketTotal);
    document.getElementById('snapshot-confidence').textContent = game.confidence;

    renderChart(game.movement);
    renderMovementTable(game.movement);
  } catch (err) {
    document.getElementById('game-title').textContent = 'Unable to load game';
    document.getElementById('game-summary').textContent = err.message;
  }
})();
