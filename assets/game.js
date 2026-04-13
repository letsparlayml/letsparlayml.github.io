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

function fmtPct(value, digits = 0) {
  if (!hasNumericValue(value)) return 'N/A';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function fmtMoneyline(value) {
  if (!hasNumericValue(value)) return '—';
  const n = Number(value);
  if (Math.abs(n) < 1) return '—';
  return `${n >= 0 ? '+' : ''}${Math.round(n)}`;
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


function probabilityLabelAndValue(point) {
  const coverLabel = point?.marketCoverLabel || point?.favoriteCoverLabel || 'Cover';
  const coverProb = hasNumericValue(point?.marketCoverProb) ? Number(point.marketCoverProb) : Number(point?.favoriteCoverProb);
  const totalLabel = point?.marketTotalLabel || point?.fallbackTotalLabel || 'Over';
  const totalProb = hasNumericValue(point?.marketOverProb) ? Number(point.marketOverProb) : Number(point?.fallbackOverProb);
  return {
    favoriteWinLabel: point?.favoriteWinLabel || 'Favorite win',
    favoriteWinProb: Number(point?.favoriteWinProb),
    nrfiLabel: 'NRFI',
    nrfiProb: Number(point?.nrfiProb),
    coverLabel,
    coverProb,
    totalLabel,
    totalProb
  };
}

function hasProbabilityMovement(movement) {
  return (movement || []).some(point => {
    const meta = probabilityLabelAndValue(point);
    return [meta.favoriteWinProb, meta.nrfiProb, meta.coverProb, meta.totalProb].some(v => Number.isFinite(v));
  });
}

function movementViewConfig(game, movement, mode = 'score') {
  if (mode === 'probability') {
    const sample = probabilityLabelAndValue((movement || []).find(Boolean) || {});
    return {
      mode,
      yAsPercent: true,
      yDigits: 0,
      emptyText: 'No probability movement records available.',
      headers: ['Date', sample.favoriteWinLabel, sample.nrfiLabel, sample.coverLabel, sample.totalLabel],
      series: [
        {
          key: 'favoriteWinProb',
          label: sample.favoriteWinLabel,
          color: '#59b4ff',
          values: (movement || []).map(point => Number(probabilityLabelAndValue(point).favoriteWinProb))
        },
        {
          key: 'nrfiProb',
          label: 'NRFI',
          color: '#7bf1c8',
          values: (movement || []).map(point => Number(probabilityLabelAndValue(point).nrfiProb))
        },
        {
          key: 'coverProb',
          label: sample.coverLabel,
          color: '#f59e0b',
          values: (movement || []).map(point => Number(probabilityLabelAndValue(point).coverProb))
        },
        {
          key: 'totalProb',
          label: sample.totalLabel,
          color: '#c084fc',
          values: (movement || []).map(point => Number(probabilityLabelAndValue(point).totalProb))
        }
      ],
      rowBuilder: row => {
        const meta = probabilityLabelAndValue(row);
        return [
          row?.date || '',
          fmtPct(meta.favoriteWinProb),
          fmtPct(meta.nrfiProb),
          fmtPct(meta.coverProb),
          fmtPct(meta.totalProb)
        ];
      }
    };
  }

  return {
    mode: 'score',
    yAsPercent: false,
    yDigits: 2,
    emptyText: 'No movement records available.',
    headers: ['Date', 'Away pred', 'Home pred', 'Model spread', 'Model total'],
    series: [
      {
        key: 'predictedAway',
        label: 'Away prediction',
        color: '#7bf1c8',
        values: (movement || []).map(d => Number(d.predictedAway))
      },
      {
        key: 'predictedHome',
        label: 'Home prediction',
        color: '#59b4ff',
        values: (movement || []).map(d => Number(d.predictedHome))
      }
    ],
    rowBuilder: row => [
      row?.date || '',
      fmt(row?.predictedAway, 2),
      fmt(row?.predictedHome, 2),
      spreadTeamLabel(game, Number.isFinite(Number(row?.modelHomeSpread)) ? Number(row.modelHomeSpread) : (Number(row?.predictedHome) - Number(row?.predictedAway))),
      fmt(row?.modelTotal, 2)
    ]
  };
}

function setMovementHeaders(headers) {
  const ids = ['movement-head-date', 'movement-head-2', 'movement-head-3', 'movement-head-4', 'movement-head-5'];
  ids.forEach((id, idx) => {
    const el = byId(id);
    if (el) el.textContent = headers[idx] || '';
  });
}

function renderChart(game, movement, mode = 'score') {
  const box = byId('movement-chart');
  if (!box) return;

  const config = movementViewConfig(game, movement, mode);
  const labels = (movement || []).map(d => d.date);
  const seriesList = (config.series || []).map(series => ({
    ...series,
    values: (series.values || []).map(v => Number(v)).filter(v => Number.isFinite(v) || Number.isNaN(v))
  }));
  const chartSeries = seriesList.map(series => ({
    ...series,
    values: (series.values || []).map(v => Number.isFinite(v) ? v : NaN)
  })).filter(series => series.values.some(v => Number.isFinite(v)));

  if (!labels.length || !chartSeries.length) {
    box.innerHTML = `<div class="empty-state">${escapeHtml(config.emptyText)}</div>`;
    return;
  }

  const width = 900;
  const height = 280;
  const pad = 36;
  const all = chartSeries.flatMap(series => series.values).filter(v => Number.isFinite(v));

  if (!all.length) {
    box.innerHTML = `<div class="empty-state">${escapeHtml(config.emptyText)}</div>`;
    return;
  }

  let minY;
  let maxY;
  if (config.yAsPercent) {
    minY = 0;
    maxY = 1;
  } else {
    const rawMin = Math.min(...all);
    const rawMax = Math.max(...all);
    const rawRange = rawMax - rawMin;
    const padY = Math.max(rawRange * 0.2, 0.08);
    minY = rawMin - padY;
    maxY = rawMax + padY;
  }

  const stepX = (width - pad * 2) / Math.max(1, labels.length - 1);
  const x = i => pad + i * stepX;
  const y = v => height - pad - ((v - minY) / (maxY - minY || 1)) * (height - pad * 2);
  const path = series => {
    let built = '';
    series.forEach((v, i) => {
      if (!Number.isFinite(v)) return;
      built += `${built ? ' L' : 'M'} ${x(i)} ${y(v)}`;
    });
    return built;
  };

  const gridCount = 5;
  const grid = Array.from({ length: gridCount }, (_, i) => {
    const ratio = i / (gridCount - 1);
    const val = minY + ratio * (maxY - minY);
    const yy = y(val);
    const label = config.yAsPercent ? fmtPct(val) : fmt(val, config.yDigits || 2);
    return `<line x1="${pad}" x2="${width - pad}" y1="${yy}" y2="${yy}" stroke="rgba(255,255,255,.10)" /><text x="8" y="${yy + 4}" fill="#9db0d0" font-size="11">${escapeHtml(label)}</text>`;
  }).join('');

  const labelHtml = labels.map((label, i) =>
    `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#9db0d0" font-size="11">${String(label).slice(5)}</text>`
  ).join('');

  const points = series =>
    series.values.map((v, i) => Number.isFinite(v) ? `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${series.color}" />` : '').join('');

  const legend = chartSeries.map(series =>
    `<span><span class="legend-dot" style="background:${series.color}"></span>${escapeHtml(series.label)}</span>`
  ).join('');

  const paths = chartSeries.map(series => {
    const d = path(series.values);
    if (!d) return '';
    return `<path d="${d}" fill="none" stroke="${series.color}" stroke-width="3" />${points(series)}`;
  }).join('');

  box.innerHTML = `
    <div class="legend">${legend}</div>
    <svg viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="Prediction movement chart">
      ${grid}
      ${paths}
      ${labelHtml}
    </svg>
  `;
}

function renderMovementTable(game, movement, mode = 'score') {
  const body = byId('movement-body');
  if (!body) return;

  const config = movementViewConfig(game, movement, mode);
  setMovementHeaders(config.headers || []);
  body.innerHTML = (movement || []).map(row => {
    const cells = config.rowBuilder(row);
    return `
      <tr>
        <td>${escapeHtml(cells[0] || '')}</td>
        <td>${escapeHtml(cells[1] || '')}</td>
        <td>${escapeHtml(cells[2] || '')}</td>
        <td>${escapeHtml(cells[3] || '')}</td>
        <td>${escapeHtml(cells[4] || '')}</td>
      </tr>
    `;
  }).join('');
}

function setupMovementToggle(game, movement) {
  const wrap = byId('movement-mode-toggle');
  const scoreBtn = byId('movement-mode-score');
  const probBtn = byId('movement-mode-prob');
  const isMlb = String(game?.league || '').toUpperCase() === 'MLB';
  const showProb = isMlb && hasProbabilityMovement(movement);
  if (!wrap || !scoreBtn || !probBtn) {
    renderChart(game, movement, 'score');
    renderMovementTable(game, movement, 'score');
    return;
  }

  let mode = 'score';
  wrap.style.display = showProb ? '' : 'none';
  probBtn.style.display = showProb ? '' : 'none';

  const render = () => {
    scoreBtn.classList.toggle('is-active', mode === 'score');
    probBtn.classList.toggle('is-active', mode === 'probability');
    renderChart(game, movement, mode);
    renderMovementTable(game, movement, mode);
  };

  scoreBtn.onclick = () => {
    mode = 'score';
    render();
  };
  probBtn.onclick = () => {
    mode = 'probability';
    render();
  };

  render();
}


function gameIdFromGame(game) {
  return normalizeGameId(game?.awayTeam, game?.homeTeam);
}

function normalizeAnalyzerStat(value) {
  const raw = String(value || '').trim().toUpperCase();
  const map = {
    STRIKEOUTS: 'K',
    STRIKEOUT: 'K',
    WALKS: 'BB',
    WALKS: 'BB',
    HITS: 'H',
    HITS: 'H',
    'TOTAL BASES': 'TB',
    TOTALBASES: 'TB',
    'HOME RUNS': 'HR',
    HOMERUNS: 'HR',
    DOUBLES: '2B',
    STEALS: 'SB',
    STOLENBASES: 'SB',
    STOLEN_BASES: 'SB',
    RBI: 'RBI',
    RUNS: 'R',
    'HR+R+RBI': 'HRR',
    HRR: 'HRR',
    IP: 'IP',
    OUTS: 'OUTS',
    'HITS ALLOWED': 'HA',
    EARNEDRUNS: 'ER',
    'EARNED RUNS': 'ER'
  };
  return map[raw] || raw;
}

function propAnalyzerHref(prop, fallbackStat = '') {
  const params = new URLSearchParams();
  const league = String(prop?.league || '').toUpperCase();
  if (league) params.set('league', league);
  if (propDateValue(prop)) params.set('date', propDateValue(prop));
  if (prop?.playerId || prop?.PLAYER_ID) params.set('playerId', String(prop.playerId || prop.PLAYER_ID));
  else if (prop?.player || prop?.PLAYER_NAME) params.set('player', String(prop.player || prop.PLAYER_NAME));
  const stat = normalizeAnalyzerStat(prop?.stat || prop?.stat_display || fallbackStat);
  if (stat) params.set('stat', stat);
  if (prop?.line !== undefined && prop?.line !== null && prop?.line !== '') params.set('line', String(prop.line));
  return `props_analyzer.html?${params.toString()}`;
}

function mlbAnalyzerHref(playerId, gameDate, stat, line = '') {
  const params = new URLSearchParams();
  params.set('league', 'MLB');
  if (gameDate) params.set('date', gameDate);
  if (playerId) params.set('playerId', String(playerId));
  if (stat) params.set('stat', normalizeAnalyzerStat(stat));
  if (line !== '' && line !== null && line !== undefined) params.set('line', String(line));
  return `props_analyzer.html?${params.toString()}`;
}


function mlbFallbackGameProps(detail, gameDate) {
  const batters = Array.isArray(detail?.batters) ? detail.batters : [];
  const rows = [];
  batters.forEach(b => {
    const base = { league: 'MLB', gameDate, player: b.player, playerId: b.playerId, team: b.team };
    const push = (stat, line, model, prob, tag='') => {
      if (!hasNumericValue(model) || !hasNumericValue(prob)) return;
      rows.push({ ...base, stat, line, modelPrediction: model, probability: prob, tag });
    };
    push('H', 0.5, b.predHits, b.probHit, b.batSide ? `${b.batSide} vs ${b.oppPitchHand || ''}`.trim() : '');
    push('TB', 1.5, b.predTB, b.probTB2Plus, '2+ TB');
    push('HR', 0.5, b.predHR, b.probHR, 'HR');
    push('BB', 0.5, b.predBB, b.probBB, 'BB');
    push('K', 0.5, b.predK, b.probK, 'K');
    push('HRR', 1.5, b.predHRR, b.probHRR2Plus, '2+ HRR');
  });
  return rows.sort((a, b) => Number(b.probability || 0) - Number(a.probability || 0));
}

function makeTablesSortable(selector = '.sortable-table') {
  document.querySelectorAll(selector).forEach(table => {
    const tbody = table.tBodies?.[0];
    const headRow = table.tHead?.rows?.[table.tHead.rows.length - 1];
    if (!tbody || !headRow) return;
    Array.from(headRow.cells).forEach((th, index) => {
      if (th.dataset.sortable === 'false') return;
      if (th.dataset.boundSort === '1') return;
      th.dataset.boundSort = '1';
      th.classList.add('sortable-header');
      th.addEventListener('click', () => {
        const currentDir = th.dataset.sortDir === 'asc' ? 'asc' : th.dataset.sortDir === 'desc' ? 'desc' : '';
        Array.from(headRow.cells).forEach(cell => { if (cell !== th) cell.dataset.sortDir = ''; });
        const nextDir = currentDir === 'asc' ? 'desc' : 'asc';
        th.dataset.sortDir = nextDir;
        const rows = Array.from(tbody.rows);
        const type = th.dataset.sortType || 'text';
        rows.sort((ra, rb) => {
          const av = ra.cells[index]?.getAttribute('data-sort') || ra.cells[index]?.textContent || '';
          const bv = rb.cells[index]?.getAttribute('data-sort') || rb.cells[index]?.textContent || '';
          let cmp = 0;
          if (type === 'num') {
            const an = parseFloat(String(av).replace(/[^0-9.+-]/g, ''));
            const bn = parseFloat(String(bv).replace(/[^0-9.+-]/g, ''));
            cmp = (Number.isFinite(an) ? an : -Infinity) - (Number.isFinite(bn) ? bn : -Infinity);
          } else {
            cmp = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
          }
          return nextDir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(row => tbody.appendChild(row));
      });
    });
  });
}

function renderGameProps(game, propsData, injuryLookup = new Map(), mlbDetail = null) {
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

  if (!rows.length && String(game?.league || '').toUpperCase() === 'MLB' && mlbDetail) {
    rows = mlbFallbackGameProps(mlbDetail, game?.gameDate || '').slice(0, 8);
  }

  if (!rows.length) {
    body.innerHTML = '';
    if (empty) empty.style.display = '';
    return;
  }

  if (empty) empty.style.display = 'none';

  body.innerHTML = rows.map(p => {
    const label = escapeHtml(p.player || p.PLAYER_NAME || '');
    const linkable = ['NBA', 'MLB'].includes(String(p?.league || game?.league || '').toUpperCase());
    const playerHtml = linkable
      ? `<a class="table-link" href="${propAnalyzerHref(p)}">${label}</a>`
      : label;

    return `
      <tr>
        <td data-sort="${escapeHtml(String(p.player || p.PLAYER_NAME || ''))}">${playerHtml}</td>
        <td data-sort="${escapeHtml(propTeamValue(p) || '')}">${escapeHtml(propTeamValue(p) || '')}</td>
        <td data-sort="${escapeHtml(p.stat || p.stat_display || '')}">${escapeHtml(p.stat || p.stat_display || '')}</td>
        <td data-sort="${escapeHtml(String(p.line ?? ''))}">${escapeHtml(hasNumericValue(p.line) ? fmt(p.line, 1) : '')}</td>
        <td data-sort="${escapeHtml(String(p.modelPrediction ?? p.prediction ?? p.pred_anchor ?? p.mu_cons ?? p.pred_stat ?? ''))}">${escapeHtml(fmt(p.modelPrediction ?? p.prediction ?? p.pred_anchor ?? p.mu_cons ?? p.pred_stat, 1))}</td>
        <td data-sort="${escapeHtml(String(Number(p.probability ?? p.prob_cons ?? 0) || 0))}">${escapeHtml(propProbabilityText(p))}</td>
        <td>${escapeHtml(p.injuryStatus || p.tag || '')}</td>
      </tr>
    `;
  }).join('');
}

function mergePropCollections(primary, secondary) {
  const merged = [];
  const seen = new Set();

  const addRows = rows => {
    flattenPropsData(rows).forEach(row => {
      const key = [
        normalizeLookupToken(row?.player || row?.PLAYER_NAME || ''),
        String(row?.stat || row?.stat_display || '').toUpperCase(),
        String(propDateValue(row) || ''),
        normalizeGameNumericId(row?.gameId || row?.game_id || row?.GAME_ID || ''),
        hasNumericValue(row?.line) ? Number(row.line).toFixed(3) : String(row?.line || '')
      ].join('|');
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(row);
    });
  };

  addRows(primary);
  addRows(secondary);
  return merged;
}

function metricCard(label, value) {
  return `<div class="hero-card"><span class="stat-label">${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function mlbValueTone(value, mode = 'model') {
  const n = Number(value);
  if (!Number.isFinite(n)) return 'is-muted';
  if (mode === 'prob') {
    if (n >= 0.7) return 'is-hot';
    if (n >= 0.55) return 'is-warm';
    return 'is-cool';
  }
  if (n >= 2.5) return 'is-hot';
  if (n >= 1.2) return 'is-warm';
  return 'is-cool';
}

function mlbMetricHtml(value, { digits = 2, mode = 'model', pct = false } = {}) {
  const text = pct ? fmtPct(value) : fmt(value, digits);
  const cls = mlbValueTone(pct ? Number(value) : Number(value), pct ? 'prob' : mode);
  return `<span class="metric-emphasis ${cls}">${escapeHtml(text)}</span>`;
}

function playerAnalyzerLink(playerObj, fallbackStat = '') {
  const href = propAnalyzerHref({
    league: 'MLB',
    gameDate: playerObj?.gameDate || '',
    player: playerObj?.player || '',
    playerId: playerObj?.playerId || '',
  }, fallbackStat);
  return `<a class="table-link table-link-strong" href="${href}">${escapeHtml(playerObj?.player || '')}</a>`;
}


function metricPairCard(label, modelValue, probValue) {
  return `
    <div class="metric-pair-card">
      <span class="stat-label">${escapeHtml(label)}</span>
      <div class="metric-pair-values">
        <div><small>Model</small><strong>${escapeHtml(modelValue)}</strong></div>
        <div><small>Prob.</small><strong>${escapeHtml(probValue)}</strong></div>
      </div>
    </div>
  `;
}

function mlbPitcherCard(p, gameDate) {
  const label = escapeHtml(p.player || 'Pitcher');
  const href = p.playerId ? mlbAnalyzerHref(p.playerId, gameDate, 'K') : '';
  const title = href ? `<a class="table-link entity-title-link" href="${href}">${label}</a>` : label;
  return `
    <article class="entity-card entity-card-compact">
      <div class="entity-card-head">
        <div>
          <p class="entity-kicker">${escapeHtml(p.team || '')} • ${escapeHtml(p.hand || '') || 'Hand TBD'}</p>
          <h3>${title}</h3>
        </div>
        <span class="entity-chip">${escapeHtml(p.team || '')}</span>
      </div>
      <div class="metric-pill-grid">
        <div class="metric-pill"><span>IP</span><strong>${escapeHtml(fmt(p.predIP, 1))}</strong></div>
        <div class="metric-pill"><span>K</span><strong>${escapeHtml(fmt(p.predK, 1))}</strong></div>
        <div class="metric-pill"><span>BB</span><strong>${escapeHtml(fmt(p.predBB, 1))}</strong></div>
        <div class="metric-pill"><span>Hits</span><strong>${escapeHtml(fmt(p.predHitsAllowed, 1))}</strong></div>
        <div class="metric-pill"><span>ER</span><strong>${escapeHtml(fmt(p.predER, 1))}</strong></div>
      </div>
    </article>
  `;
}

function mlbBatterCard(b, gameDate) {
  const label = escapeHtml(b.player || 'Batter');
  const href = b.playerId ? mlbAnalyzerHref(b.playerId, gameDate, 'H', 0.5) : '';
  const title = href ? `<a class="table-link entity-title-link" href="${href}">${label}</a>` : label;
  const predHrr = hasNumericValue(b.predHRR) ? Number(b.predHRR) : ((Number(b.predHR || 0) || 0) + (Number(b.predRuns || 0) || 0) + (Number(b.predRBI || 0) || 0));
  return `
    <article class="entity-card">
      <div class="entity-card-head">
        <div>
          <p class="entity-kicker">${escapeHtml(b.team || '')} • Order ${escapeHtml(b.order ?? '—')} • ${escapeHtml(b.batSide || 'Batter')}</p>
          <h3>${title}</h3>
        </div>
        <span class="entity-chip">${escapeHtml(b.team || '')}</span>
      </div>
      <div class="metric-pair-grid">
        ${metricPairCard('Hits', fmt(b.predHits, 2), fmtPct(b.probHit))}
        ${metricPairCard('2+ total bases', fmt(b.predTB, 2), fmtPct(b.probTB2Plus))}
        ${metricPairCard('Home run', fmt(b.predHR, 2), fmtPct(b.probHR))}
        ${metricPairCard('Walks', fmt(b.predBB, 2), fmtPct(b.probBB))}
        ${metricPairCard('Strikeouts', fmt(b.predK, 2), fmtPct(b.probK))}
        ${metricPairCard('2+ HRR', fmt(predHrr, 2), fmtPct(b.probHRR2Plus))}
      </div>
    </article>
  `;
}

function renderMlbGameDetails(game, detail) {
  const probabilitySection = byId('mlb-probability-section');
  const probabilityGrid = byId('mlb-probability-grid');
  const pitchersSection = byId('mlb-pitchers-section');
  const pitchersBody = byId('mlb-pitchers-body');
  const battersSection = byId('mlb-batters-section');
  const battersBody = byId('mlb-batters-body');

  if (!probabilitySection || !probabilityGrid || !pitchersSection || !pitchersBody || !battersSection || !battersBody) return;

  const isMlb = String(game?.league || '').toUpperCase() === 'MLB';
  if (!isMlb || !detail) {
    probabilitySection.style.display = 'none';
    pitchersSection.style.display = 'none';
    battersSection.style.display = 'none';
    return;
  }

  const metrics = detail?.metrics || {};
  probabilitySection.style.display = '';
  const coverLabel = metrics.marketCoverLabel || metrics.favoriteCoverLabel || `${game.homeTeam} -1.5`;
  const coverValue = hasNumericValue(metrics.marketCoverProb) ? metrics.marketCoverProb : metrics.favoriteCoverProb;
  const totalLabel = metrics.marketTotalLabel || metrics.fallbackTotalLabel || 'Over';
  const totalValue = hasNumericValue(metrics.marketOverProb) ? metrics.marketOverProb : metrics.fallbackOverProb;
  const cards = [
    metricCard(metrics.favoriteWinLabel || 'Favorite win', fmtPct(metrics.favoriteWinProb)),
    metricCard('NRFI', fmtPct(metrics.nrfiProb)),
    metricCard('YRFI', fmtPct(metrics.yrfiProb)),
    metricCard(coverLabel, fmtPct(coverValue)),
    metricCard(totalLabel, fmtPct(totalValue)),
    metricCard('1-run game', fmtPct(metrics.oneRunGameProb)),
    metricCard('Tie after 9', fmtPct(metrics.tieAfter9Prob)),
    metricCard('F5 total', fmt(metrics.predF5Total, 2))
  ];
  probabilityGrid.innerHTML = cards.join('');

  const pitchers = Array.isArray(detail?.pitchers) ? detail.pitchers : [];
  if (pitchers.length) {
    pitchersSection.style.display = '';
    pitchersBody.innerHTML = pitchers.map(p => `
      <tr>
        <td class="name-cell" data-sort="${escapeHtml(String(p.player || ''))}">${playerAnalyzerLink({ ...p, gameDate: game?.gameDate }, 'K')}<span class="subtle-meta">Starter</span></td>
        <td data-sort="${escapeHtml(String(p.team || ''))}"><span class="team-pill">${escapeHtml(p.team || '')}</span></td>
        <td data-sort="${escapeHtml(String(p.hand || ''))}">${escapeHtml(p.hand || '—')}</td>
        <td data-sort="${escapeHtml(String(p.predIP ?? ''))}">${mlbMetricHtml(p.predIP, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predK ?? ''))}">${mlbMetricHtml(p.predK, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predBB ?? ''))}">${mlbMetricHtml(p.predBB, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predHitsAllowed ?? ''))}">${mlbMetricHtml(p.predHitsAllowed, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predER ?? ''))}">${mlbMetricHtml(p.predER, { digits: 1, mode: 'model' })}</td>
      </tr>
    `).join('');
  } else {
    pitchersSection.style.display = 'none';
    pitchersBody.innerHTML = '';
  }

  const batters = Array.isArray(detail?.batters) ? detail.batters : [];
  if (batters.length) {
    battersSection.style.display = '';
    battersBody.innerHTML = batters.map(b => `
      <tr>
        <td class="name-cell" data-sort="${escapeHtml(String(b.player || ''))}">${playerAnalyzerLink({ ...b, gameDate: game?.gameDate })}<span class="subtle-meta">${escapeHtml([b.batSide || '', b.oppPitchHand ? `vs ${b.oppPitchHand}` : ''].filter(Boolean).join(' • '))}</span></td>
        <td data-sort="${escapeHtml(String(b.team || ''))}"><span class="team-pill">${escapeHtml(b.team || '')}</span></td>
        <td data-sort="${escapeHtml(String(b.order ?? ''))}">${escapeHtml(b.order ?? '—')}</td>
        <td data-sort="${escapeHtml(String(b.predHits ?? ''))}">${mlbMetricHtml(b.predHits, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHit ?? ''))}">${mlbMetricHtml(b.probHit, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predTB ?? ''))}">${mlbMetricHtml(b.predTB, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probTB2Plus ?? ''))}">${mlbMetricHtml(b.probTB2Plus, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predHR ?? ''))}">${mlbMetricHtml(b.predHR, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHR ?? ''))}">${mlbMetricHtml(b.probHR, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predBB ?? ''))}">${mlbMetricHtml(b.predBB, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probBB ?? ''))}">${mlbMetricHtml(b.probBB, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predK ?? ''))}">${mlbMetricHtml(b.predK, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probK ?? ''))}">${mlbMetricHtml(b.probK, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predHRR ?? ''))}">${mlbMetricHtml(b.predHRR, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHRR2Plus ?? ''))}">${mlbMetricHtml(b.probHRR2Plus, { pct: true })}</td>
      </tr>
    `).join('');
  } else {
    battersSection.style.display = 'none';
    battersBody.innerHTML = '';
  }

  makeTablesSortable('.sortable-table');
}

function archiveMatchup(row) {
  const raw = String(row?.matchup || '');
  if (raw.includes('@')) {
    const [away, home] = raw.split('@').map(v => String(v || '').trim().toUpperCase());
    return { away, home };
  }
  return {
    away: String(row?.awayTeam || '').trim().toUpperCase(),
    home: String(row?.homeTeam || '').trim().toUpperCase()
  };
}

function archiveLocalDate(row) {
  if (row?.date) return String(row.date).trim();
  const raw = String(row?.gameDateTimeUtc || row?.gameDate || row?.startTimeUtc || '');
  if (!raw || !raw.includes('T')) return '';
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit' })
      .format(new Date(raw));
  } catch (err) {
    return '';
  }
}

function archiveMoneyline(row, side) {
  const keys = side === 'away'
    ? ['marketAwayML', 'awayML', 'awayMoneyline']
    : ['marketHomeML', 'homeML', 'homeMoneyline'];
  for (const key of keys) {
    if (hasNumericValue(row?.[key])) return Number(row[key]);
  }
  return null;
}

function renderMlbOddsMovement(game, archiveRows) {
  const section = byId('odds-movement-section');
  const cards = byId('odds-movement-cards');
  const body = byId('odds-movement-body');
  if (!section || !cards || !body) return;

  const isMlb = String(game?.league || '').toUpperCase() === 'MLB';
  if (!isMlb) {
    section.style.display = 'none';
    return;
  }

  const rows = (archiveRows || []).filter(row => String(row?.league || '').toUpperCase() === 'MLB').map(row => {
    const matchup = archiveMatchup(row);
    return {
      ...row,
      awayTeamNorm: matchup.away,
      homeTeamNorm: matchup.home,
      localDate: archiveLocalDate(row),
      asOf: row?.updatedAt || row?.archivedAt || row?.marketLineUpdated || ''
    };
  }).filter(row => row.awayTeamNorm === String(game?.awayTeam || '').toUpperCase() && row.homeTeamNorm === String(game?.homeTeam || '').toUpperCase() && (!game?.gameDate || row.localDate === game.gameDate));

  rows.sort((a, b) => new Date(a.asOf || 0) - new Date(b.asOf || 0));
  const snapshots = rows.length ? rows : ((hasNumericValue(game?.marketSpread) || hasNumericValue(game?.marketTotal)) ? [{
    marketSpread: game.marketSpread,
    marketTotal: game.marketTotal,
    awayMoneyline: game.marketAwayML,
    homeMoneyline: game.marketHomeML,
    asOf: game.marketLineUpdated || '',
    source: game.marketLineSource || 'games.json'
  }] : []);

  if (!snapshots.length) {
    section.style.display = 'none';
    return;
  }

  section.style.display = '';
  const opening = snapshots[0];
  const current = snapshots[snapshots.length - 1];
  const spreads = snapshots.map(s => Number(s.marketSpread)).filter(Number.isFinite);
  const totals = snapshots.map(s => Number(s.marketTotal)).filter(Number.isFinite);
  const spreadRange = spreads.length ? `${Math.min(...spreads).toFixed(1)} to ${Math.max(...spreads).toFixed(1)}` : '—';
  const totalRange = totals.length ? `${Math.min(...totals).toFixed(1)} to ${Math.max(...totals).toFixed(1)}` : '—';
  cards.innerHTML = [
    metricCard('Opening spread', hasNumericValue(opening?.marketSpread) ? spreadTeamLabel(game, Number(opening.marketSpread)) : '—'),
    metricCard('Current spread', hasNumericValue(current?.marketSpread) ? spreadTeamLabel(game, Number(current.marketSpread)) : '—'),
    metricCard('Spread range', spreadRange),
    metricCard('Total range', totalRange),
    metricCard('Moneyline now', `${fmtMoneyline(archiveMoneyline(current, 'away'))} / ${fmtMoneyline(archiveMoneyline(current, 'home'))}`),
    metricCard('Snapshots', String(snapshots.length))
  ].join('');

  body.innerHTML = snapshots.map(s => `
    <tr>
      <td>${escapeHtml(String(s.asOf || '').replace('T', ' ').slice(0, 16) || '—')}</td>
      <td>${escapeHtml(hasNumericValue(s.marketSpread) ? spreadTeamLabel(game, Number(s.marketSpread)) : '—')}</td>
      <td>${escapeHtml(hasNumericValue(s.marketTotal) ? fmt(s.marketTotal, 2) : '—')}</td>
      <td>${escapeHtml(fmtMoneyline(archiveMoneyline(s, 'away')))}</td>
      <td>${escapeHtml(fmtMoneyline(archiveMoneyline(s, 'home')))}</td>
      <td>${escapeHtml(s.source || 'Archive')}</td>
    </tr>
  `).join('');
}

(async function init() {
  try {
    const id = qs('id');
    const [games, rawProps, rawPropsLab, injuries, archiveRows] = await Promise.all([
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/nba_props_lab.json', null),
      loadJson('data/nba_injuries.json', {}),
      loadJson('data/market_lines_archive.json', [])
    ]);
    const injuryLookup = buildInjuryLookup(injuries);

    const game = (games || []).find(g => g.id === id) || (games || [])[0];
    if (!game) throw new Error('No game records found.');

    const propsData = mergePropCollections(rawPropsLab, rawProps);
    const mlbDetail = String(game?.league || '').toUpperCase() === 'MLB' && game?.detailPath
      ? await loadJson(game.detailPath, null)
      : null;

    document.title = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-league').textContent = game.league || '';
    byId('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-summary').textContent = game.summary || '';
    byId('snapshot-score').textContent = `${fmt(game.modelAwayScore, 2)} - ${fmt(game.modelHomeScore, 2)}`;
    byId('snapshot-spread').textContent = hasNumericValue(game.marketSpread)
      ? spreadTeamLabel(game, marketSpreadForDisplay(game))
      : 'Pending';
    byId('snapshot-total').textContent = hasNumericValue(game.marketTotal) ? fmt(game.marketTotal, 2) : 'Pending';
    byId('snapshot-confidence').textContent = game.confidence || 'N/A';

    setupMovementToggle(game, game.movement || []);
    renderGameProps(game, propsData, injuryLookup, mlbDetail);
    renderMlbGameDetails(game, mlbDetail);
    renderMlbOddsMovement(game, archiveRows);
    makeTablesSortable('.sortable-table');
  } catch (err) {
    byId('game-title').textContent = 'Unable to load game';
    byId('game-summary').textContent = err.message || String(err);
  }
})();
