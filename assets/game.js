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

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeTeamToken(value) {
  return String(value ?? '')
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
    .trim();
}

function normalizeGameId(a, b) {
  const parts = [normalizeTeamToken(a), normalizeTeamToken(b)].filter(Boolean).sort();
  return parts.join('|');
}

function propTeamValue(prop) {
  return (
    prop?.team ||
    prop?.team_abbr ||
    prop?.teamAbbr ||
    prop?.TEAM ||
    prop?.TEAM_ABBR ||
    prop?.TEAM_NAME_MAP ||
    ''
  );
}

function propOppValue(prop) {
  return (
    prop?.opp ||
    prop?.opponent ||
    prop?.opp_abbr ||
    prop?.opponent_abbr ||
    prop?.OPP ||
    prop?.OPP_ABBR ||
    prop?.OPP_NAME_MAP ||
    ''
  );
}

function normalizeGameNumericId(value) {
  const raw = String(value ?? '');
  const match = raw.match(/(\d{7,})/);
  return match ? match[1] : '';
}

function propGameNumericId(prop) {
  return normalizeGameNumericId(
    prop?.gameId ||
    prop?.game_id ||
    prop?.GAME_ID ||
    ''
  );
}

function gameNumericId(game) {
  return normalizeGameNumericId(game?.id || game?.gameId || game?.GAME_ID || '');
}

function propDateValue(prop) {
  return (
    prop?.gameDate ||
    prop?.date ||
    prop?.GAME_DATE ||
    prop?.game_date ||
    ''
  );
}

function propProbabilityValue(prop) {
  const candidates = [prop?.probability, prop?.prob, prop?.prob_cons, prop?.clearProbability, prop?.clear_probability];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propProbabilityText(prop) {
  const n = propProbabilityValue(prop);
  return Number.isFinite(n) ? `${(n > 1 ? n : n * 100).toFixed(1)}%` : 'N/A';
}

function flattenPropsData(propsData) {
  if (Array.isArray(propsData)) return propsData;
  if (Array.isArray(propsData?.items)) return propsData.items;
  if (Array.isArray(propsData?.props)) return propsData.props;
  if (Array.isArray(propsData?.rows)) return propsData.rows;

  if (propsData?.byDate && typeof propsData.byDate === 'object') {
    return Object.entries(propsData.byDate).flatMap(([date, day]) =>
      (day?.allProps || []).map(prop => ({
        ...prop,
        gameDate: prop?.gameDate || prop?.date || prop?.GAME_DATE || date
      }))
    );
  }

  return [];
}

function renderChart(movement) {
  const box = byId('movement-chart');
  if (!box) return;
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
  const path = series => series.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ');
  const gridCount = 5;
  const grid = Array.from({ length: gridCount }, (_, i) => {
    const ratio = i / (gridCount - 1);
    const val = minY + ratio * (maxY - minY);
    const yy = y(val);
    return `<line x1="${pad}" x2="${width - pad}" y1="${yy}" y2="${yy}" stroke="rgba(255,255,255,.10)" /><text x="8" y="${yy + 4}" fill="#9db0d0" font-size="11">${fmt(val, 2)}</text>`;
  }).join('');
  const labelHtml = labels.map((label, i) => `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#9db0d0" font-size="11">${String(label).slice(5)}</text>`).join('');
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
  const body = byId('movement-body');
  if (!body) return;
  body.innerHTML = (movement || []).map(row => `
    <tr>
      <td>${escapeHtml(row.date || '')}</td>
      <td>${fmt(row.predictedAway, 2)}</td>
      <td>${fmt(row.predictedHome, 2)}</td>
      <td>${fmtSigned(row.modelHomeSpread, 2)}</td>
      <td>${fmt(row.modelTotal, 2)}</td>
    </tr>
  `).join('');
}

function gameIdFromGame(game) {
  return normalizeGameId(game?.awayTeam, game?.homeTeam);
}

function renderGameProps(game, propsData) {
  const body = byId('game-props-body');
  const empty = byId('game-props-empty');
  if (!body) return;

  const allRows = flattenPropsData(propsData);
  const gameIdNum = gameNumericId(game);
  const gameDate = game?.gameDate || '';
  const gameTeamMatch = gameIdFromGame(game);

  let rows = [];

  // First try: exact GAME_ID match
  if (gameIdNum) {
    rows = allRows.filter(p => propGameNumericId(p) === gameIdNum);
  }

  // Fallback: date + normalized matchup
  if (!rows.length) {
    rows = allRows
      .filter(p => {
        const pDate = propDateValue(p);
        return !gameDate || !pDate || pDate === gameDate;
      })
      .filter(p => normalizeGameId(propTeamValue(p), propOppValue(p)) === gameTeamMatch);
  }

  // Final sort + limit
  rows = rows
    .sort((a, b) => {
      const bp = propProbabilityValue(b);
      const ap = propProbabilityValue(a);
      if (Number.isFinite(bp) && Number.isFinite(ap) && bp !== ap) return bp - ap;
      return Number(b?.line || 0) - Number(a?.line || 0);
    })
    .slice(0, 6);

  if (!rows.length) {
    body.innerHTML = '';
    if (empty) empty.style.display = '';
    return;
  }

  if (empty) empty.style.display = 'none';

  body.innerHTML = rows.map(p => `
    <tr>
      <td>${escapeHtml(p.player || p.PLAYER_NAME || '')}</td>
      <td>${escapeHtml(propTeamValue(p) || '')}</td>
      <td>${escapeHtml(p.stat || p.stat_display || '')}</td>
      <td>${escapeHtml(p.line ?? '')}</td>
      <td>${escapeHtml(fmt(p.modelPrediction ?? p.prediction ?? p.pred_anchor ?? p.mu_cons ?? p.pred_stat, 1))}</td>
      <td>${escapeHtml(propProbabilityText(p))}</td>
      <td>${escapeHtml(p.injuryStatus || p.tag || '')}</td>
    </tr>
  `).join('');
}

(async function init() {
  try {
    const id = qs('id');
    const [games, propsData] = await Promise.all([
      loadJson('data/games.json', []),
      loadJson('data/nba_props_lab.json', null).then(data => data ?? loadJson('data/props.json', []))
    ]);
    const game = (games || []).find(g => g.id === id) || (games || [])[0];
    if (!game) throw new Error('No game records found.');
    document.title = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-league').textContent = game.league || '';
    byId('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-summary').textContent = game.summary || '';
    byId('snapshot-score').textContent = `${fmt(game.modelAwayScore, 2)} - ${fmt(game.modelHomeScore, 2)}`;
    byId('snapshot-spread').textContent = fmtSigned(game.marketSpread, 2);
    byId('snapshot-total').textContent = fmt(game.marketTotal, 2);
    byId('snapshot-confidence').textContent = game.confidence || 'N/A';
    renderChart(game.movement || []);
    renderMovementTable(game.movement || []);
    renderGameProps(game, propsData);
  } catch (err) {
    byId('game-title').textContent = 'Unable to load game';
    byId('game-summary').textContent = err.message || String(err);
  }
})();