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


function isNbaGame(game) {
  return String(game?.league || '').toUpperCase() === 'NBA';
}

function marketSpreadForDisplay(game) {
  const spread = Number(game?.marketSpread);
  if (!Number.isFinite(spread)) return NaN;
  return isNbaGame(game) ? -spread : spread;
}

function modelSpreadForDisplay(game) {
  const away = Number(game?.modelAwayScore);
  const home = Number(game?.modelHomeScore);
  if (Number.isFinite(away) && Number.isFinite(home)) return home - away;
  const fallback = Number(game?.modelHomeSpread);
  return Number.isFinite(fallback) ? fallback : NaN;
}

function spreadTeamLabel(game, awaySpread) {
  if (!Number.isFinite(awaySpread)) return 'N/A';
  if (Math.abs(awaySpread) < 0.05) return 'PK';
  return awaySpread > 0
    ? `${game?.homeTeam || 'Home'} ${fmtSigned(-awaySpread, 2)}`
    : `${game?.awayTeam || 'Away'} ${fmtSigned(awaySpread, 2)}`;
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

function normalizeLookupToken(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeTeamToken(value) {
  return String(value ?? '')
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
    .trim();
}

const NBA_TEAM_TOKEN_MAP = {
  ATL: 'ATL', ATLANTAHAWKS: 'ATL',
  BOS: 'BOS', BOSTONCELTICS: 'BOS',
  BKN: 'BKN', BROOKLYNNETS: 'BKN',
  BRK: 'BKN',
  CHA: 'CHA', CHARLOTTEHORNETS: 'CHA',
  CHI: 'CHI', CHICAGOBULLS: 'CHI',
  CLE: 'CLE', CLEVELANDCAVALIERS: 'CLE',
  DAL: 'DAL', DALLASMAVERICKS: 'DAL',
  DEN: 'DEN', DENVERNUGGETS: 'DEN',
  DET: 'DET', DETROITPISTONS: 'DET',
  GSW: 'GSW', GOLDENSTATEWARRIORS: 'GSW',
  HOU: 'HOU', HOUSTONROCKETS: 'HOU',
  IND: 'IND', INDIANAPACERS: 'IND',
  LAC: 'LAC', LOSANGELESCLIPPERS: 'LAC',
  CLIPPERS: 'LAC',
  LAL: 'LAL', LOSANGELESLAKERS: 'LAL',
  MEM: 'MEM', MEMPHISGRIZZLIES: 'MEM',
  MIA: 'MIA', MIAMIHEAT: 'MIA',
  MIL: 'MIL', MILWAUKEEBUCKS: 'MIL',
  MIN: 'MIN', MINNESOTATIMBERWOLVES: 'MIN',
  NOP: 'NOP', NEWORLEANSPELICANS: 'NOP',
  NO: 'NOP',
  NYK: 'NYK', NEWYORKKNICKS: 'NYK',
  OKC: 'OKC', OKLAHOMACITYTHUNDER: 'OKC',
  ORL: 'ORL', ORLANDOMAGIC: 'ORL',
  PHI: 'PHI', PHILADELPHIAERS: 'PHI',
  PHILADELPHIA76ERS: 'PHI',
  PHX: 'PHX', PHOENIXSUNS: 'PHX',
  POR: 'POR', PORTLANDTRAILBLAZERS: 'POR',
  SAC: 'SAC', SACRAMENTOKINGS: 'SAC',
  SAS: 'SAS', SANANTONIOSPURS: 'SAS',
  SA: 'SAS',
  TOR: 'TOR', TORONTORAPTORS: 'TOR',
  UTA: 'UTA', UTAHJAZZ: 'UTA',
  WAS: 'WAS', WASHINGTONWIZARDS: 'WAS'
};

function canonicalTeamToken(value) {
  const token = normalizeTeamToken(value);
  return NBA_TEAM_TOKEN_MAP[token] || token;
}

function canonicalInjuryStatus(value) {
  const raw = String(value ?? '').trim().toLowerCase();
  if (!raw) return '';
  const map = {
    p: 'probable',
    probable: 'probable',
    q: 'questionable',
    questionable: 'questionable',
    gtd: 'questionable',
    out: 'out',
    o: 'out',
    doubtful: 'doubtful',
    d: 'doubtful'
  };
  return map[raw] || raw;
}

function titleCaseWord(value) {
  if (!value) return '';
  return String(value).charAt(0).toUpperCase() + String(value).slice(1).toLowerCase();
}

function buildInjuryLookup(injuryData) {
  const lookup = new Map();
  const players = injuryData?.players || injuryData?.entries || [];

  (players || []).forEach(entry => {
    const playerKey = normalizeLookupToken(entry.player || entry.player_name);
    if (!playerKey) return;

    const teamKey = canonicalTeamToken(entry.team || entry.team_abbr);
    const normalized = {
      status: titleCaseWord(canonicalInjuryStatus(entry.status)),
      note: entry.note || entry.injury_note || '',
      team: entry.team || entry.team_abbr || '',
      lastUpdated: entry.lastUpdated || entry.last_updated || entry.updated_at || '',
      gameDate: entry.gameDate || entry.game_date || ''
    };

    if (teamKey) lookup.set(`${playerKey}|${teamKey}`, normalized);
    if (!lookup.has(`${playerKey}|`)) lookup.set(`${playerKey}|`, normalized);
  });

  return lookup;
}

function getPropInjuryContext(prop, injuryLookup) {
  if (!injuryLookup || !injuryLookup.size) return null;
  const playerKey = normalizeLookupToken(prop?.player || prop?.PLAYER_NAME || '');
  if (!playerKey) return null;
  const teamKey = canonicalTeamToken(propTeamValue(prop));
  return injuryLookup.get(`${playerKey}|${teamKey}`) || injuryLookup.get(`${playerKey}|`) || null;
}

function decoratePropInjury(prop, injuryLookup) {
  const context = getPropInjuryContext(prop, injuryLookup);
  if (!context) return { ...prop };
  return {
    ...prop,
    injuryStatus: context.status || prop?.injuryStatus || '',
    injuryNote: context.note || prop?.injuryNote || '',
    injuryUpdated: context.lastUpdated || prop?.injuryUpdated || ''
  };
}

function hasListedInjury(prop) {
  return Boolean(canonicalInjuryStatus(prop?.injuryStatus || prop?.playerStatus || prop?.status));
}

function normalizeGameId(a, b) {
  const parts = [canonicalTeamToken(a), canonicalTeamToken(b)].filter(Boolean).sort();
  return parts.join('|');
}

function normalizeGameNumericId(value) {
  const raw = String(value ?? '');
  const match = raw.match(/(\d{7,})/);
  return match ? match[1] : '';
}

function propTeamValue(prop) {
  return (
    prop?.team ||
    prop?.team_abbr ||
    prop?.teamAbbr ||
    prop?.TEAM ||
    prop?.TEAM_ABBR ||
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
    ''
  );
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
  const candidates = [
    prop?.probability,
    prop?.prob,
    prop?.prob_cons,
    prop?.clearProbability,
    prop?.clear_probability
  ];
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

function propLineValue(prop) {
  const n = Number(prop?.line);
  return Number.isFinite(n) ? n : NaN;
}

function propPredictionValue(prop) {
  const candidates = [
    prop?.modelPrediction,
    prop?.prediction,
    prop?.pred_anchor,
    prop?.mu_cons,
    prop?.pred_stat,
    prop?.mu
  ];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propAverageValue(prop) {
  const candidates = [
    prop?.avg_anchor,
    prop?.average,
    prop?.avg
  ];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propLineRatio(prop) {
  const line = propLineValue(prop);
  if (!Number.isFinite(line) || line <= 0) return NaN;

  const avg = propAverageValue(prop);
  if (Number.isFinite(avg) && avg > 0) return line / avg;

  const pred = propPredictionValue(prop);
  if (Number.isFinite(pred) && pred > 0) return line / pred;

  return NaN;
}

function propClosenessScore(prop) {
  const ratio = propLineRatio(prop);
  if (!Number.isFinite(ratio)) return 0;
  const clamped = Math.max(0, Math.min(ratio, 1.25));
  return Math.max(0, 1 - Math.abs(1 - clamped));
}

function propDisplayScore(prop) {
  const prob = Number.isFinite(propProbabilityValue(prop)) ? propProbabilityValue(prop) : 0;
  const closeness = propClosenessScore(prop);
  return prob * 0.55 + closeness * 0.45;
}

function isReasonablePropLine(prop, { ratioFloor = 0.7, probFloor = 0.55 } = {}) {
  const prob = propProbabilityValue(prop);
  if (Number.isFinite(prob) && prob < probFloor) return false;

  const ratio = propLineRatio(prop);
  if (Number.isFinite(ratio)) return ratio >= ratioFloor;

  return true;
}

function pickBestPropVariant(rows) {
  return rows
    .slice()
    .sort((a, b) => {
      const scoreDiff = propDisplayScore(b) - propDisplayScore(a);
      if (scoreDiff) return scoreDiff;

      const probDiff = propProbabilityValue(b) - propProbabilityValue(a);
      if (Number.isFinite(probDiff) && probDiff) return probDiff;

      return propLineValue(b) - propLineValue(a);
    })[0] || null;
}

function selectGameProps(rows, limit = 6) {
  const byPlayerStat = new Map();

  rows.forEach(prop => {
    const key = `${normalizeLookupToken(prop?.player || prop?.PLAYER_NAME || '')}|${String(prop?.stat || prop?.stat_display || '').toUpperCase()}`;
    if (!byPlayerStat.has(key)) byPlayerStat.set(key, []);
    byPlayerStat.get(key).push(prop);
  });

  const deduped = Array.from(byPlayerStat.values())
    .map(group => pickBestPropVariant(group))
    .filter(Boolean);

  const preferred = deduped.filter(prop => isReasonablePropLine(prop, { ratioFloor: 0.7, probFloor: 0.55 }));
  const fallback = deduped.filter(prop => isReasonablePropLine(prop, { ratioFloor: 0.62, probFloor: 0.5 }));

  const chosen = (preferred.length >= limit ? preferred : fallback.length >= limit ? fallback : deduped)
    .slice()
    .sort((a, b) => {
      const scoreDiff = propDisplayScore(b) - propDisplayScore(a);
      if (scoreDiff) return scoreDiff;

      const probDiff = propProbabilityValue(b) - propProbabilityValue(a);
      if (Number.isFinite(probDiff) && probDiff) return probDiff;

      return propLineValue(b) - propLineValue(a);
    })
    .slice(0, limit);

  return chosen;
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

  const labelHtml = labels.map((label, i) =>
    `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#9db0d0" font-size="11">${String(label).slice(5)}</text>`
  ).join('');

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

function renderMovementTable(game, movement) {
  const body = byId('movement-body');
  if (!body) return;

  body.innerHTML = (movement || []).map(row => `
    <tr>
      <td>${escapeHtml(row.date || '')}</td>
      <td>${fmt(row.predictedAway, 2)}</td>
      <td>${fmt(row.predictedHome, 2)}</td>
      <td>${spreadTeamLabel(game, Number.isFinite(Number(row.modelHomeSpread)) ? Number(row.modelHomeSpread) : (Number(row.predictedHome) - Number(row.predictedAway)))}</td>
      <td>${fmt(row.modelTotal, 2)}</td>
    </tr>
  `).join('');
}

function gameIdFromGame(game) {
  return normalizeGameId(game?.awayTeam, game?.homeTeam);
}

function propAnalyzerHref(prop) {
  const params = new URLSearchParams();
  if (propDateValue(prop)) params.set('date', propDateValue(prop));
  if (prop?.playerId || prop?.PLAYER_ID) params.set('playerId', String(prop.playerId || prop.PLAYER_ID));
  if (prop?.stat || prop?.stat_display) params.set('stat', String(prop.stat || prop.stat_display).toUpperCase());
  if (prop?.line !== undefined && prop?.line !== null && prop?.line !== '') params.set('line', String(prop.line));
  return `props_analyzer.html?${params.toString()}`;
}

function renderGameProps(game, propsData, injuryLookup = new Map()) {
  const body = byId('game-props-body');
  const empty = byId('game-props-empty');
  if (!body) return;

  const allRows = flattenPropsData(propsData).map(prop => decoratePropInjury(prop, injuryLookup));
  const gameIdNum = gameNumericId(game);
  const gameDate = game?.gameDate || '';
  const gameTeamMatch = gameIdFromGame(game);

  let rows = [];

  if (gameIdNum) {
    rows = allRows.filter(p => propGameNumericId(p) === gameIdNum);
  }

  if (!rows.length) {
    rows = allRows
      .filter(p => {
        const pDate = propDateValue(p);
        return !gameDate || !pDate || pDate === gameDate;
      })
      .filter(p => normalizeGameId(propTeamValue(p), propOppValue(p)) === gameTeamMatch);
  }

  rows = rows.filter(p => !hasListedInjury(p));
  rows = selectGameProps(rows, 6);

  if (!rows.length) {
    body.innerHTML = '';
    if (empty) empty.style.display = '';
    return;
  }

  if (empty) empty.style.display = 'none';

  body.innerHTML = rows.map(p => `
    <tr>
      <td><a class="table-link" href="${propAnalyzerHref(p)}">${escapeHtml(p.player || p.PLAYER_NAME || '')}</a></td>
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
    const [games, propsData, injuries] = await Promise.all([
      loadJson('data/games.json', []),
      loadJson('data/nba_props_lab.json', null).then(data => data ?? loadJson('data/props.json', [])),
      loadJson('data/nba_injuries.json', {})
    ]);
    const injuryLookup = buildInjuryLookup(injuries);

    const game = (games || []).find(g => g.id === id) || (games || [])[0];
    if (!game) throw new Error('No game records found.');

    document.title = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-league').textContent = game.league || '';
    byId('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-summary').textContent = game.summary || '';
    byId('snapshot-score').textContent = `${fmt(game.modelAwayScore, 2)} - ${fmt(game.modelHomeScore, 2)}`;
    byId('snapshot-spread').textContent = spreadTeamLabel(game, marketSpreadForDisplay(game));
    byId('snapshot-total').textContent = fmt(game.marketTotal, 2);
    byId('snapshot-confidence').textContent = game.confidence || 'N/A';

    renderChart(game.movement || []);
    renderMovementTable(game, game.movement || []);
    renderGameProps(game, propsData, injuryLookup);
  } catch (err) {
    byId('game-title').textContent = 'Unable to load game';
    byId('game-summary').textContent = err.message || String(err);
  }
})();