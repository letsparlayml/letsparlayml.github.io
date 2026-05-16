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
  return Number.isFinite(spread) ? spread : NaN;
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
    pitchersBody.innerHTML = pitchers.map(p => {
      const pitcherMeta = [p.team || '', 'Starter', p.hand || ''].filter(Boolean).join(' • ');
      return `
      <tr>
        <td class="name-cell" data-sort="${escapeHtml(String(p.player || ''))}">${playerAnalyzerLink({ ...p, gameDate: game?.gameDate }, 'K')}<span class="subtle-meta">${escapeHtml(pitcherMeta)}</span></td>
        <td data-sort="${escapeHtml(String(p.predIP ?? ''))}">${mlbMetricHtml(p.predIP, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predK ?? ''))}">${mlbMetricHtml(p.predK, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predBB ?? ''))}">${mlbMetricHtml(p.predBB, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predHitsAllowed ?? ''))}">${mlbMetricHtml(p.predHitsAllowed, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predER ?? ''))}">${mlbMetricHtml(p.predER, { digits: 1, mode: 'model' })}</td>
      </tr>
    `;
    }).join('');
  } else {
    pitchersSection.style.display = 'none';
    pitchersBody.innerHTML = '';
  }

  const batters = Array.isArray(detail?.batters) ? detail.batters : [];
  if (batters.length) {
    battersSection.style.display = '';
    battersBody.innerHTML = batters.map(b => {
      const batterMeta = [
        b.team || '',
        (b.order !== undefined && b.order !== null && b.order !== '') ? `#${b.order}` : '',
        [b.batSide || '', b.oppPitchHand ? `vs ${b.oppPitchHand}` : ''].filter(Boolean).join(' ')
      ].filter(Boolean).join(' • ');
      return `
      <tr>
        <td class="name-cell" data-sort="${escapeHtml(String(b.player || ''))}">${playerAnalyzerLink({ ...b, gameDate: game?.gameDate })}<span class="subtle-meta">${escapeHtml(batterMeta)}</span></td>
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
    `;
    }).join('');
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


function archiveMatchKeyFromGame(game) {
  return `${String(game?.gameDate || '').trim()}|${String(game?.awayTeam || '').trim()}|${String(game?.homeTeam || '').trim()}`;
}

function latestArchiveForGame(game, archiveRows) {
  const target = archiveMatchKeyFromGame(game);
  let best = null;
  let bestTs = -1;
  (archiveRows || []).forEach(row => {
    const matchup = archiveMatchup(row);
    const localDate = archiveLocalDate(row) || String(row?.date || '').trim();
    const key = `${localDate}|${String(matchup.away || '').trim()}|${String(matchup.home || '').trim()}`;
    if (key !== target) return;
    const ts = Date.parse(row?.updatedAt || row?.archivedAt || row?.fetchedAtUtc || '') || 0;
    if (!best || ts >= bestTs) {
      best = row;
      bestTs = ts;
    }
  });
  return best;
}

function hydrateGameWithArchive(game, archiveRows) {
  const row = latestArchiveForGame(game, archiveRows);
  if (!row) return game;
  const merged = { ...game };
  if (!hasNumericValue(merged.marketSpread) && hasNumericValue(row?.marketSpread)) merged.marketSpread = Number(row.marketSpread);
  if (!hasNumericValue(merged.marketTotal) && hasNumericValue(row?.marketTotal)) merged.marketTotal = Number(row.marketTotal);
  if (!hasNumericValue(merged.marketAwayML) && hasNumericValue(row?.marketAwayML)) merged.marketAwayML = Number(row.marketAwayML);
  else if (!hasNumericValue(merged.marketAwayML) && hasNumericValue(row?.awayML)) merged.marketAwayML = Number(row.awayML);
  else if (!hasNumericValue(merged.marketAwayML) && hasNumericValue(row?.awayMoneyline)) merged.marketAwayML = Number(row.awayMoneyline);
  if (!hasNumericValue(merged.marketHomeML) && hasNumericValue(row?.marketHomeML)) merged.marketHomeML = Number(row.marketHomeML);
  else if (!hasNumericValue(merged.marketHomeML) && hasNumericValue(row?.homeML)) merged.marketHomeML = Number(row.homeML);
  else if (!hasNumericValue(merged.marketHomeML) && hasNumericValue(row?.homeMoneyline)) merged.marketHomeML = Number(row.homeMoneyline);
  if (!merged.marketLineSource && row?.source) merged.marketLineSource = row.source;
  if (!merged.marketLineUpdated && (row?.updatedAt || row?.archivedAt)) merged.marketLineUpdated = row.updatedAt || row.archivedAt;
  return merged;
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

function giValue(value, digits = 1, fallback = '—') {
  if (!hasNumericValue(value)) return fallback;
  return Number(value).toFixed(digits);
}

function giPct(value, digits = 0, fallback = '—') {
  if (!hasNumericValue(value)) return fallback;
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function giRateText(metric) {
  if (!metric || !metric.sample) return 'No sample';
  const made = Math.round(Number(metric.hitRate || 0) * Number(metric.sample || 0));
  return `${made}/${metric.sample}`;
}

function giSmallMetric(label, value, sub = '') {
  return `
    <div class="gi-mini-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${sub ? `<em>${escapeHtml(sub)}</em>` : ''}
    </div>
  `;
}

function giPlayerNotes(notes) {
  const list = Array.isArray(notes) ? notes.filter(Boolean).slice(0, 4) : [];
  if (!list.length) return '<p class="muted">No research notes found for this player.</p>';
  return `<ul class="gi-note-list">${list.map(n => `<li>${escapeHtml(n)}</li>`).join('')}</ul>`;
}

function giEnsureGameIntelligenceStyles() {
  if (document.getElementById('gi-readable-model-form-style')) return;
  const style = document.createElement('style');
  style.id = 'gi-readable-model-form-style';
  style.textContent = `
    .gi-form-card-note {
      margin: .65rem 0 .75rem;
      color: #b7c9df;
      font-size: .82rem;
      line-height: 1.45;
    }
    .gi-form-games {
      display: grid;
      gap: .65rem;
      margin-top: .75rem;
    }
    .gi-form-game {
      border: 1px solid rgba(148, 163, 184, .16);
      border-radius: 14px;
      background: rgba(15, 23, 42, .42);
      padding: .7rem .75rem;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
    }
    .gi-form-game-head {
      display: grid;
      grid-template-columns: minmax(78px, auto) minmax(86px, auto) minmax(0, 1fr);
      gap: .55rem;
      align-items: center;
      margin-bottom: .55rem;
    }
    .gi-form-date,
    .gi-form-result {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: .22rem .52rem;
      background: rgba(30, 41, 59, .68);
      color: #bcd2ea;
      font-size: .76rem;
      white-space: nowrap;
    }
    .gi-form-result.is-good { color: #bbf7d0; background: rgba(22, 101, 52, .18); border: 1px solid rgba(34,197,94,.18); }
    .gi-form-result.is-bad { color: #fecaca; background: rgba(127, 29, 29, .16); border: 1px solid rgba(248,113,113,.16); }
    .gi-form-matchup {
      color: #e0f2fe;
      font-weight: 850;
      letter-spacing: .01em;
      min-width: 0;
    }
    .gi-form-game-body {
      display: grid;
      grid-template-columns: minmax(145px, .9fr) minmax(145px, .9fr) minmax(240px, 1.25fr);
      gap: .65rem;
      align-items: stretch;
    }
    .gi-form-scorebox,
    .gi-form-explain {
      border: 1px solid rgba(148,163,184,.14);
      border-radius: 12px;
      background: rgba(2, 6, 23, .24);
      padding: .6rem .65rem;
      min-width: 0;
    }
    .gi-form-label {
      display: block;
      color: #7dd3fc;
      font-size: .68rem;
      letter-spacing: .08em;
      text-transform: uppercase;
      margin-bottom: .38rem;
      font-weight: 800;
    }
    .gi-form-score-line {
      display: grid;
      grid-template-columns: minmax(36px, auto) 1fr;
      column-gap: .55rem;
      align-items: baseline;
      padding: .12rem 0;
    }
    .gi-form-score-line b {
      color: #bae6fd;
      font-size: .8rem;
      letter-spacing: .02em;
    }
    .gi-form-score-line strong {
      color: #f8fafc;
      font-size: .94rem;
      font-variant-numeric: tabular-nums;
    }
    .gi-form-explain p {
      margin: 0;
      color: #dbeafe;
      line-height: 1.45;
      font-size: .86rem;
    }
    .gi-form-explain-list {
      display: grid;
      gap: .42rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .gi-form-explain-list li {
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: .5rem;
      color: #dbeafe;
      line-height: 1.35;
      font-size: .84rem;
    }
    .gi-form-explain-list span {
      color: #93c5fd;
      text-transform: uppercase;
      letter-spacing: .06em;
      font-size: .68rem;
      font-weight: 850;
    }
    @media (max-width: 1050px) {
      .gi-form-game-body { grid-template-columns: 1fr 1fr; }
      .gi-form-explain { grid-column: 1 / -1; }
    }
    @media (max-width: 680px) {
      .gi-form-game-head { grid-template-columns: 1fr; gap: .38rem; }
      .gi-form-date,
      .gi-form-result { justify-content: flex-start; width: fit-content; }
      .gi-form-game-body { grid-template-columns: 1fr; }
      .gi-form-explain { grid-column: auto; }
    }
  `;
  document.head.appendChild(style);
}

function giRenderModelForm(report) {
  const forms = report?.modelForm || {};
  const teams = [report?.awayTeam, report?.homeTeam].filter(Boolean);
  if (!teams.length) return '';

  const scoreBox = (label, awayTeam, awayScore, homeTeam, homeScore, digits) => `
    <div class="gi-form-scorebox">
      <span class="gi-form-label">${escapeHtml(label)}</span>
      <div class="gi-form-score-line"><b>${escapeHtml(awayTeam || 'Away')}</b><strong>${escapeHtml(giValue(awayScore, digits))}</strong></div>
      <div class="gi-form-score-line"><b>${escapeHtml(homeTeam || 'Home')}</b><strong>${escapeHtml(giValue(homeScore, digits))}</strong></div>
    </div>
  `;

  return `
    <div class="gi-block">
      <div class="gi-block-head">
        <h3>Model form over last 5 games</h3>
        <p>Recent model accuracy for each team. Rows keep the scoreboard in away/home order and explain how close the model was to that team's actual scoring.</p>
      </div>
      <div class="gi-two-col">
        ${teams.map(team => {
          const f = forms[team] || {};
          const rows = Array.isArray(f.games) ? f.games.slice().reverse() : [];
          const sample = Number(f.sample || rows.length || 0);
          return `
            <div class="gi-card">
              <div class="gi-card-title">
                <strong>${escapeHtml(team)}</strong>
              </div>
              <div class="gi-mini-grid">
                ${giSmallMetric('Winner read', `${f.sideCorrect || 0}/${sample}`, 'correct game winner')}
                ${giSmallMetric('Avg run error', giValue(f.avgTeamRunError ?? f.avgScoreError, 1), 'team runs vs projection')}
                ${giSmallMetric('Close projection', `${f.withinOneFiveCount || 0}/${sample}`, 'within 1.5 team runs')}
                ${giSmallMetric('Bigger misses', `${f.bigMissCount || 0}/${sample}`, 'missed by 1.5+ team runs')}
              </div>
              ${f.coverageNote ? `<p class="gi-form-card-note">${escapeHtml(f.coverageNote)}</p>` : ''}
              <div class="gi-form-games">
                ${rows.map(g => {
                  const away = g.awayTeam || (String(g.matchup || '').split('@')[0] || '').trim();
                  const home = g.homeTeam || (String(g.matchup || '').split('@')[1] || '').trim();
                  const matchup = g.matchup || (away && home ? `${away} @ ${home}` : '');
                  const scoringText = g.teamDiffText || `${team} finished ${giValue(g.teamError,1)} runs away from its own scoring projection.`;
                  const allowedText = g.opponentDiffText || `${team} allowed ${giValue(g.opponentError,1)} runs away from the opponent projection.`;
                  const boardText = g.scoreboardText || `Full scoreboard miss: ${giValue(g.scoreboardError,1)} total runs across both teams.`;
                  const totalText = g.totalText || (g.totalError != null ? `Projected total missed by ${giValue(g.totalError,1)} runs.` : '');
                  const resultClass = g.correctSide ? 'is-good' : 'is-bad';
                  return `
                    <div class="gi-form-game">
                      <div class="gi-form-game-head">
                        <span class="gi-form-date">${escapeHtml(g.date || '')}</span>
                        <span class="gi-form-result ${resultClass}">${escapeHtml(g.correctSide ? 'Correct winner' : 'Missed winner')}</span>
                        <div class="gi-form-matchup">${escapeHtml(matchup)}</div>
                      </div>
                      <div class="gi-form-game-body">
                        ${scoreBox('Model', away, g.predAway, home, g.predHome, 1)}
                        ${scoreBox('Final', away, g.actualAway, home, g.actualHome, 0)}
                        <div class="gi-form-explain">
                          <span class="gi-form-label">What it means for ${escapeHtml(team)}</span>
                          <ul class="gi-form-explain-list">
                            <li><span>Scoring</span><b>${escapeHtml(scoringText)}</b></li>
                            <li><span>Allowed</span><b>${escapeHtml(allowedText)}</b></li>
                            <li><span>Game read</span><b>${escapeHtml(boardText)}</b></li>
                            ${totalText ? `<li><span>Total</span><b>${escapeHtml(totalText)}</b></li>` : ''}
                          </ul>
                        </div>
                      </div>
                    </div>
                  `;
                }).join('') || '<p class="muted">No settled model form found yet.</p>'}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}


function giRenderMovement(report) {
  const mv = report?.predictionMovement || {};
  const bullets = Array.isArray(mv.bullets) ? mv.bullets : [];
  const m = mv.movements || {};
  const title = mv.title || 'What the movement means';
  const description = mv.description || 'First saved record vs latest saved record.';
  const range = mv.firstDate && mv.latestDate ? `${mv.firstDate} → ${mv.latestDate}` : '';
  const away = report?.awayTeam || 'Away';
  const home = report?.homeTeam || 'Home';
  return `
    <div class="gi-block">
      <div class="gi-block-head">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(description)}${range ? ` <span class="gi-range">${escapeHtml(range)}</span>` : ''}</p>
      </div>
      <div class="gi-card">
        ${mv.available ? `
          ${mv.analysis ? `<p class="gi-movement-read">${escapeHtml(mv.analysis)}</p>` : ''}
          <div class="gi-mini-grid">
            ${giSmallMetric(`${away} runs move`, giValue(m.awayScoreDelta, 2))}
            ${giSmallMetric(`${home} runs move`, giValue(m.homeScoreDelta, 2))}
            ${giSmallMetric('Total move', giValue(m.totalDelta, 2))}
            ${mv.awayMarginDelta !== undefined ? giSmallMetric('Margin moved toward', mv.movementToward ? escapeHtml(mv.movementToward) : 'No clear side', `${giValue(mv.awayMarginDelta,2)} run margin change`) : ''}
            ${m.nrfiProbDelta !== undefined ? giSmallMetric('NRFI move', giPct(m.nrfiProbDelta, 1)) : ''}
          </div>
          ${bullets.length ? `<details class="gi-details"><summary>Show movement numbers</summary><ul class="gi-note-list">${bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('')}</ul></details>` : ''}
        ` : `<p class="muted">${escapeHtml(mv.summary || 'Needs saved movement records or at least two builder snapshots.')}</p>`}
      </div>
    </div>
  `;
}


function giRenderPitchers(report) {
  const pitchers = report?.pitchingMatchup || [];
  if (!pitchers.length) return '';
  return `
    <div class="gi-block">
      <div class="gi-block-head">
        <h3>Pitching matchup: last 5 outings</h3>
        <p>Actual recent outing box stats from pitcher logs, not the model projection table below. First-inning runs only show when that outing was a confirmed start.</p>
      </div>
      <div class="gi-two-col">
        ${pitchers.map(p => {
          const s = p.last5Summary || {};
          return `
            <div class="gi-card gi-pitcher-card">
              <div class="gi-card-title">
                <strong>${escapeHtml(p.player || '')}</strong>
                <span>${escapeHtml([p.team, p.location, p.opponent ? `vs ${p.opponent}` : ''].filter(Boolean).join(' • '))}</span>
              </div>
              <div class="gi-mini-grid">
                ${giSmallMetric('Avg IP', giValue(s.avgIP, 1), s.hasOutingLogs || s.hasStartByStartLogs ? `${s.outingsCount || s.startsCount || 0} outings` : 'window data')}
                ${giSmallMetric('Avg K', giValue(s.avgK, 1))}
                ${giSmallMetric('Avg H allowed', giValue(s.avgHitsAllowed, 1))}
                ${giSmallMetric('Avg ER', giValue(s.avgER, 1))}
                ${giSmallMetric('Last 5 1st RA', s.firstInningSamples ? giPct(s.firstInningRunAllowedRate, 0) : '-', s.firstInningSamples ? `${s.firstInningSamples} confirmed starts` : 'hidden for non-start outings')}
                ${s.showOverallFirstInning ? giSmallMetric('Available overall 1st RA', giPct(s.firstInningOverallRunAllowedRate, 0), `${s.firstInningOverallSamples} starts`) : ''}
                ${s.showLocationFirstInning ? giSmallMetric(`Available ${s.firstInningLocation || p.location || 'split'} 1st RA`, giPct(s.firstInningLocationRunAllowedRate, 0), `${s.firstInningLocationSamples} starts`) : ''}
              </div>
              <div class="table-wrap gi-table-wrap">
                ${((p.last5Starts || []).length) ? `
                  <table class="gi-table">
                    <thead><tr><th>Date</th><th>Opp</th><th>IP</th><th>K</th><th>H</th><th>ER</th><th>BB</th><th>1st</th></tr></thead>
                    <tbody>
                      ${(p.last5Starts || []).slice().reverse().map(g => `
                        <tr>
                          <td>${escapeHtml(g.date || '')}</td>
                          <td>${escapeHtml([g.location, g.opponent].filter(Boolean).join(' '))}</td>
                          <td>${giValue(g.ip, 1)}</td>
                          <td>${giValue(g.k, 0)}</td>
                          <td>${giValue(g.hitsAllowed, 0)}</td>
                          <td>${giValue(g.er, 0)}</td>
                          <td>${giValue(g.bb, 0)}</td>
                          <td>${hasNumericValue(g.firstInningRunsAllowed) ? escapeHtml(String(g.firstInningRunsAllowed)) : '-'}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                ` : `
                  <table class="gi-table">
                    <thead><tr><th>Window</th><th>IP</th><th>K</th><th>H</th><th>ER</th><th>BB</th></tr></thead>
                    <tbody>
                      ${(p.aggregateWindows || []).map(w => `
                        <tr>
                          <td>${escapeHtml(w.label || '')}</td>
                          <td>${giValue(w.IP, 1)}</td>
                          <td>${giValue(w.K, 1)}</td>
                          <td>${giValue(w.HA, 1)}</td>
                          <td>${giValue(w.ER, 1)}</td>
                          <td>${giValue(w.BB, 1)}</td>
                        </tr>
                      `).join('') || '<tr><td colspan="6">No recent start logs or analyzer windows found.</td></tr>'}
                    </tbody>
                  </table>
                  <p class="muted gi-note-p">Start-by-start rows were not present for this pitcher in the site data. This table shows analyzer recent windows, not individual starts.</p>
                `}
              </div>
              ${giPlayerNotes(p.flags)}
              ${(p.sameOpponentStarts || []).length ? `
                <p class="gi-inline-note"><strong>Vs ${escapeHtml(p.opponent || 'opponent')} in logs:</strong> ${(p.sameOpponentStarts || []).map(g => `${escapeHtml(g.date || '')}: ${giValue(g.ip,1)} IP, ${giValue(g.er,0)} ER, ${giValue(g.hitsAllowed,0)} H, ${giValue(g.k,0)} K`).join(' • ')}</p>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function giRenderFirstInning(report) {
  const fi = report?.firstInningOutlook || {};
  return `
    <div class="gi-block">
      <div class="gi-block-head">
        <h3>NRFI / YRFI context</h3>
        <p>Model probability plus starter first-inning history when raw inning data is available.</p>
      </div>
      <div class="gi-card">
        <div class="gi-mini-grid">
          ${giSmallMetric('NRFI model', giPct(fi.nrfiProb, 0))}
          ${giSmallMetric('YRFI model', giPct(fi.yrfiProb, 0))}
          ${(fi.pitcherSamples || []).map(p => giSmallMetric(`${p.player || p.team} last 5 1st RA`, p.sample ? giPct(p.runAllowedRate, 0) : (p.nonStartRows ? 'N/A' : 'No local log'), p.sample ? `${p.sample} starts` : (p.nonStartRows ? `${p.nonStartRows} relief/bulk rows` : ''))) .join('')}
          ${(fi.pitcherSamples || []).filter(p => p.showOverallFirstInning).map(p => giSmallMetric(`${p.player || p.team} available overall 1st RA`, giPct(p.overallRunAllowedRate, 0), `${p.overallSamples} starts`)) .join('')}
          ${(fi.pitcherSamples || []).filter(p => p.showLocationFirstInning).map(p => giSmallMetric(`${p.player || p.team} available ${p.location || 'split'} 1st RA`, giPct(p.locationRunAllowedRate, 0), `${p.locationSamples} starts`)) .join('')}
        </div>
        <p class="muted gi-note-p">${escapeHtml(fi.note || '')}</p>
      </div>
    </div>
  `;
}

function giRenderBatterList(title, subtitle, players, mode) {
  const list = Array.isArray(players) ? players : [];
  if (!list.length) return '';
  return `
    <div class="gi-block">
      <div class="gi-block-head">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(subtitle)}</p>
      </div>
      <div class="gi-player-grid">
        ${list.map(p => {
          const m = p.metrics || {};
          const h10 = m.hitsLast10 || {};
          const loc = m.locationHits || {};
          const sim = m.similarHits || {};
          const tb2 = m.tb2Last10 || {};
          const hrr2 = m.hrr2Last10 || {};
          const k10 = m.kLast10 || {};
          return `
            <div class="gi-card gi-batter-card ${mode === 'risk' ? 'is-risk' : 'is-positive'}">
              <div class="gi-card-title">
                <strong>${escapeHtml(p.player || '')}</strong>
                <span>${escapeHtml([p.team, p.location, p.pitchHand ? `vs ${p.pitchHand}HP` : '', p.context].filter(Boolean).join(' • '))}</span>
              </div>
              <div class="gi-mini-grid">
                ${giSmallMetric('Hit L10', giRateText(h10), `${giValue(h10.avg,2)} H/g`)}
                ${giSmallMetric(`${p.location || 'Loc'} hits`, loc.sample ? giRateText(loc) : 'No sample', loc.sample ? `${giValue(loc.avg,2)} H/g` : '')}
                ${giSmallMetric('Similar hits', sim.sample ? giRateText(sim) : 'No sample', sim.sample ? `${giValue(sim.avg,2)} H/g` : '')}
                ${giSmallMetric('2+ TB L10', tb2.sample ? giRateText(tb2) : 'No sample')}
                ${giSmallMetric('2+ HRR L10', hrr2.sample ? giRateText(hrr2) : 'No sample')}
                ${giSmallMetric('K L10', k10.sample ? giValue(k10.avg,2) : 'No sample', k10.sample ? 'per game' : '')}
              </div>
              ${giPlayerNotes(p.notes)}
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function giRenderBatters(report) {
  const br = report?.batterResearch || {};
  return `
    ${giRenderBatterList('Hot bats / positive research signals', 'Recent results, matching location/opponent samples, and similar-game production.', br.positiveSignals || [], 'positive')}
    ${giRenderBatterList('Cold bats / risk flags', 'Actual weak recent hit profiles or strikeout trends — not duplicated model projections.', br.riskFlags || [], 'risk')}
  `;
}

async function renderGameIntelligence(game) {
  const section = byId('game-intelligence-section');
  const body = byId('game-intelligence-body');
  if (!section || !body) return;
  if (String(game?.league || '').toUpperCase() !== 'MLB') {
    section.style.display = 'none';
    return;
  }
  try {
    giEnsureGameIntelligenceStyles();
    const index = await loadJson('data/game_intelligence/index.json', null);
    const reports = index?.reports || [];
    const match = reports.find(r => String(r.gameId || '') === String(game.id || '') || String(r.gamePk || '') === String(game.gamePk || ''));
    if (!match?.path) {
      section.style.display = 'none';
      return;
    }
    const report = await loadJson(match.path, null);
    if (!report) {
      section.style.display = 'none';
      return;
    }
    section.style.display = '';
    body.innerHTML = `
      <div class="gi-hero">
        <div>
          <p class="eyebrow">Research read</p>
          <h3>${escapeHtml(report.headline || 'Game Intelligence')}</h3>
          <p>${escapeHtml(report.quickWriteup || '')}</p>
        </div>
        <div class="gi-coverage">
          <span>Entries analyzed</span>
          <strong>${escapeHtml(String(report?.dataCoverage?.propsAnalyzerEntries || 0))}</strong>
        </div>
      </div>
      ${giRenderModelForm(report)}
      ${giRenderMovement(report)}
      ${giRenderPitchers(report)}
      ${giRenderFirstInning(report)}
      ${giRenderBatters(report)}
    `;
  } catch (err) {
    section.style.display = 'none';
  }
}

(async function init() {
  try {
    const id = qs('id');
    const [gamesRaw, rawProps, rawPropsLab, injuries, archiveRows] = await Promise.all([
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/nba_props_lab.json', null),
      loadJson('data/nba_injuries.json', {}),
      loadJson('data/market_lines_archive.json', [])
    ]);
    const injuryLookup = buildInjuryLookup(injuries);

    const games = (gamesRaw || []).map(g => hydrateGameWithArchive(g, archiveRows));
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
    await renderGameIntelligence(game);
    makeTablesSortable('.sortable-table');
  } catch (err) {
    byId('game-title').textContent = 'Unable to load game';
    byId('game-summary').textContent = err.message || String(err);
  }
})();
