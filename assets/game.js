async function loadJson(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function hasNumericValue(v) {
  return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
}

function fmt(num, digits = 2) {
  return hasNumericValue(num) ? Number(num).toFixed(digits) : 'N/A';
}

function fmtSigned(num, digits = 2) {
  if (!hasNumericValue(num)) return 'N/A';
  const n = Number(num);
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
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
  const pad = 36;
  const all = [...away, ...home].filter(v => Number.isFinite(v));

  if (!all.length) {
    box.innerHTML = '<div class="empty-state">No chartable movement records available.</div>';
    return;
  }

  const rawMin = Math.min(...all);
  const rawMax = Math.max(...all);
  const rawRange = rawMax - rawMin;
  const padY = Math.max(rawRange * 0.2, 0.08);
  const minY = rawMin - padY;
  const maxY = rawMax + padY;

  const stepX = (width - pad * 2) / Math.max(1, labels.length - 1);

  const x = i => pad + i * stepX;
  const y = v => height - pad - ((v - minY) / (maxY - minY || 1)) * (height - pad * 2);

  const path = series =>
    series.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ');

  const gridCount = 5;
  const grid = Array.from({ length: gridCount }, (_, i) => {
    const ratio = i / (gridCount - 1);
    const val = minY + ratio * (maxY - minY);
    const yy = y(val);
    return `
      <line x1="${pad}" x2="${width - pad}" y1="${yy}" y2="${yy}" stroke="rgba(255,255,255,.10)" />
      <text x="8" y="${yy + 4}" fill="#9db0d0" font-size="11">${fmt(val, 2)}</text>
    `;
  }).join('');

  const labelHtml = labels.map((label, i) => {
    const shortLabel = String(label).slice(5);
    return `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#9db0d0" font-size="11">${shortLabel}</text>`;
  }).join('');

  const points = (series, color) =>
    series.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${color}" />`).join('');

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
  if (!body) return;

  body.innerHTML = movement.map(row => `
    <tr>
      <td>${row.date || ''}</td>
      <td>${fmt(row.predictedAway, 2)}</td>
      <td>${fmt(row.predictedHome, 2)}</td>
      <td>${fmtSigned(row.modelHomeSpread, 2)}</td>
      <td>${fmt(row.modelTotal, 2)}</td>
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
    document.getElementById('game-league').textContent = game.league || '';
    document.getElementById('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    document.getElementById('game-summary').textContent = game.summary || '';
    document.getElementById('snapshot-score').textContent = `${fmt(game.modelAwayScore, 2)} - ${fmt(game.modelHomeScore, 2)}`;
    document.getElementById('snapshot-spread').textContent = fmtSigned(game.marketSpread, 2);
    document.getElementById('snapshot-total').textContent = fmt(game.marketTotal, 2);
    document.getElementById('snapshot-confidence').textContent = game.confidence || 'N/A';

    renderChart(game.movement || []);
    renderMovementTable(game.movement || []);
  } catch (err) {
    document.getElementById('game-title').textContent = 'Unable to load game';
    document.getElementById('game-summary').textContent = err.message;
  }
})();
