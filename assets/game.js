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

function fmtSpreadPrice(value) {
  return hasNumericValue(value) ? fmtMoneyline(value) : '—';
}

function spreadWithPrice(game, awaySpread, awayOdds, homeOdds) {
  const label = spreadTeamLabel(game, Number(awaySpread));
  if (label === 'N/A') return label;
  const selectedOdds = Number(awaySpread) > 0 ? homeOdds : awayOdds;
  return hasNumericValue(selectedOdds) ? `${label} (${fmtMoneyline(selectedOdds)})` : label;
}

function totalWithPrices(total, overOdds, underOdds) {
  if (!hasNumericValue(total)) return '—';
  const label = fmt(total, 2);
  if (!hasNumericValue(overOdds) && !hasNumericValue(underOdds)) return label;
  return `${label} (O ${fmtMoneyline(overOdds)} / U ${fmtMoneyline(underOdds)})`;
}


function isNbaGame(game) {
  return String(game?.league || '').toUpperCase() === 'NBA';
}

function marketSpreadForDisplay(game) {
  const spread = Number(game?.awaySpread ?? game?.marketSpread);
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
    push('2B', 0.5, b.predDoubles, b.probDouble, 'Double');
    push('BB', 0.5, b.predBB, b.probBB, 'BB');
    push('K', 0.5, b.predK, b.probK, 'K');
    push('SB', 0.5, b.predSB, b.probSB, 'Stolen base');
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


function sortPropsForUseCase(rows) {
  return (rows || []).slice().sort((a, b) => {
    const scoreDiff = propDisplayScore(b) - propDisplayScore(a);
    if (scoreDiff) return scoreDiff;
    return propProbabilityValue(b) - propProbabilityValue(a);
  });
}

function propShortLabel(prop) {
  const stat = normalizeAnalyzerStat(prop?.stat || prop?.stat_display || '');
  const line = hasNumericValue(prop?.line) ? ` ${fmt(prop.line, 1)}` : '';
  return `${gamePropStatLabel(stat)}${line}`;
}

function propBucketItem(prop, profileMap = new Map()) {
  const stat = normalizeAnalyzerStat(prop?.stat || prop?.stat_display || '');
  const profile = profileMap.get(String(prop?.playerId || prop?.PLAYER_ID || '')) || null;
  const sim = gamePropSimilaritySummary(profile, stat);
  const href = propAnalyzerHref(prop);
  const reason = propQuickRead(prop, profile);
  return `
    <li>
      <div>
        <a class="table-link table-link-strong" href="${href}">${escapeHtml(prop?.player || prop?.PLAYER_NAME || '')}</a>
        <span>${escapeHtml(propTeamValue(prop) || '')} • ${escapeHtml(propShortLabel(prop))}</span>
      </div>
      <strong>${escapeHtml(propProbabilityText(prop))}</strong>
      <small>${escapeHtml(sim.avg !== null ? `similar avg ${fmt(sim.avg, 2)}` : reason)}</small>
    </li>
  `;
}

function renderGamePropBuckets(rows, game, profileMap = new Map()) {
  const root = byId('game-prop-buckets');
  if (!root) return;
  const props = sortPropsForUseCase(rows || []);
  if (!props.length) {
    root.innerHTML = '';
    return;
  }

  const saferStats = new Set(['H', 'BB']);
  const upsideStats = new Set(['TB', 'HRR', '2B', 'SB', 'HR']);
  const pitcherStats = new Set(['K', 'ER', 'HA', 'IP', 'OUTS']);

  const lowerVariance = props.filter(p => saferStats.has(normalizeAnalyzerStat(p.stat || p.stat_display))).slice(0, 3);
  const upside = props.filter(p => upsideStats.has(normalizeAnalyzerStat(p.stat || p.stat_display))).slice(0, 3);
  const pitcher = props.filter(p => pitcherStats.has(normalizeAnalyzerStat(p.stat || p.stat_display))).slice(0, 3);

  const fallbackWatch = props
    .filter(p => {
      const stat = normalizeAnalyzerStat(p.stat || p.stat_display);
      const prob = propProbabilityValue(p);
      return ['HR', 'SB', '2B', 'HRR', 'TB'].includes(stat) && (!Number.isFinite(prob) || prob < .62);
    })
    .slice(0, 3);

  const buckets = [
    {
      title: 'Safer building blocks',
      note: 'Start here for props that rely less on one swing or one run-scoring event.',
      rows: lowerVariance.length ? lowerVariance : props.slice(0, 3),
      cls: 'is-safe'
    },
    {
      title: 'Upside / ladder angles',
      note: 'Better for higher payout ideas, but naturally more volatile.',
      rows: upside.length ? upside : props.slice(0, 3),
      cls: 'is-medium'
    },
    {
      title: pitcher.length ? 'Pitcher angles' : 'Use with caution',
      note: pitcher.length ? 'Starter props and pitcher-side reads for this matchup.' : 'Good to see, but not as clean as the strongest model/profile spots.',
      rows: pitcher.length ? pitcher : fallbackWatch,
      cls: 'is-risk'
    }
  ].filter(bucket => bucket.rows && bucket.rows.length);

  const modelLean = game?.summary || '';
  root.innerHTML = `
    <div class="game-plan-card">
      <div>
        <span class="summary-kicker">How to use this game</span>
        <h3>Prop path</h3>
        <p>${escapeHtml(modelLean || 'Use the buckets below to separate safer props from upside and higher-variance angles.')}</p>
      </div>
      <div class="game-plan-pill-row">
        <span>1. Start with safer props</span>
        <span>2. Check similarity</span>
        <span>3. Add upside only if the profile supports it</span>
      </div>
    </div>
    <div class="game-prop-bucket-grid">
      ${buckets.map(bucket => `
        <article class="game-prop-bucket ${bucket.cls}">
          <div class="game-prop-card-top">
            <h3>${escapeHtml(bucket.title)}</h3>
            <span class="prop-risk-pill ${bucket.cls}">${escapeHtml(bucket.cls === 'is-safe' ? 'Cleaner' : bucket.cls === 'is-risk' ? 'Caution' : 'Upside')}</span>
          </div>
          <p class="muted">${escapeHtml(bucket.note)}</p>
          <ul>
            ${bucket.rows.map(prop => propBucketItem(prop, profileMap)).join('')}
          </ul>
        </article>
      `).join('')}
    </div>
  `;
}


async function renderGameProps(game, propsData, injuryLookup = new Map(), mlbDetail = null) {
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
  rows = selectGameProps(rows, 10);

  if (!rows.length && String(game?.league || '').toUpperCase() === 'MLB' && mlbDetail) {
    rows = mlbFallbackGameProps(mlbDetail, game?.gameDate || '').slice(0, 8);
  }

  if (!rows.length) {
    body.innerHTML = '';
    renderGamePropBuckets([], game, new Map());
    if (empty) empty.style.display = '';
    return;
  }

  if (empty) empty.style.display = 'none';

  const profileMap = String(game?.league || '').toUpperCase() === 'MLB'
    ? await loadProfilesForProps(rows, game?.gameDate || '')
    : new Map();
  renderGamePropCards(rows, game, profileMap);
  renderGamePropBuckets(rows, game, profileMap);

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
        <td data-sort="${escapeHtml(String(propDisplayScore(p) || 0))}">${escapeHtml(gamePropScoreLabel(p))}</td>
        <td>${escapeHtml(propQuickRead(p, profileMap.get(String(p.playerId || p.PLAYER_ID || '')) || null))}</td>
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


function gamePropStatLabel(stat) {
  const key = String(stat || '').toUpperCase();
  return {
    H: 'Hits',
    TB: 'Total Bases',
    HRR: 'Hits + Runs + RBI',
    HR: 'Home Runs',
    '2B': 'Doubles',
    BB: 'Walks',
    K: 'Strikeouts',
    SB: 'Stolen Bases',
    ER: 'Earned Runs',
    HA: 'Hits Allowed',
    IP: 'Innings',
    OUTS: 'Outs'
  }[key] || String(stat || 'Prop');
}

function gamePropRiskLabel(stat) {
  const key = String(stat || '').toUpperCase();
  if (key === 'H') return { label: 'Lower variance', cls: 'is-safe' };
  if (['TB', 'HRR', 'SB', '2B'].includes(key)) return { label: 'Medium variance', cls: 'is-medium' };
  if (['HR', 'K', 'ER', 'BB'].includes(key)) return { label: 'Higher variance', cls: 'is-risk' };
  return { label: 'Context play', cls: 'is-medium' };
}

function gamePropModelEdge(prop) {
  const model = propPredictionValue(prop);
  const line = propLineValue(prop);
  return Number.isFinite(model) && Number.isFinite(line) ? model - line : NaN;
}

function gamePropScoreLabel(prop) {
  const raw = propDisplayScore(prop);
  if (!Number.isFinite(raw)) return '—';
  return `${Math.round(raw * 100)}`;
}

function gamePropProfileProp(profile, stat) {
  const key = normalizeAnalyzerStat(stat);
  const props = Array.isArray(profile?.availableProps) ? profile.availableProps : [];
  return props.find(p => normalizeAnalyzerStat(p.stat) === key) || null;
}

function gamePropSimilaritySummary(profile, stat) {
  const prop = gamePropProfileProp(profile, stat);
  const sim = prop?.similarityV2 || prop?.similarity || null;
  const avg = Number(sim?.avgValue);
  const count = Number(sim?.count || sim?.totalHistoricalRows || 0);
  const score = Number(sim?.avgScore || sim?.maxScore);
  const featureCoverage = sim?.featureCoverage || {};
  const parts = [];
  if (Number.isFinite(avg)) parts.push(`similar avg ${fmt(avg, 2)}`);
  if (Number.isFinite(score)) parts.push(`sim score ${fmt(score, 0)}`);
  if (featureCoverage?.historicalHandedness) parts.push('hand match scored');
  if (featureCoverage?.historicalPitchMix) parts.push('pitch mix scored');
  return {
    text: parts.length ? parts.join(' • ') : 'similarity pending',
    avg: Number.isFinite(avg) ? avg : null,
    count: Number.isFinite(count) ? count : 0,
    score: Number.isFinite(score) ? score : null,
    prop
  };
}

async function loadGamePropProfile(gameDate, playerId) {
  if (!gameDate || !playerId || String(playerId).toLowerCase() === 'none') return null;
  const safeId = String(playerId).replace(/[^A-Za-z0-9_.-]/g, '_');
  return await loadJson(`data/mlb_props_analyzer/${gameDate}/player_profiles/${safeId}.json`, null);
}

async function loadProfilesForProps(rows, gameDate) {
  const ids = [...new Set((rows || []).map(p => p.playerId || p.PLAYER_ID).filter(Boolean).map(String))].slice(0, 16);
  const pairs = await Promise.all(ids.map(async id => [id, await loadGamePropProfile(gameDate, id)]));
  return new Map(pairs.filter(([, profile]) => profile));
}

function propQuickRead(prop, profile = null) {
  const stat = normalizeAnalyzerStat(prop?.stat || prop?.stat_display || '');
  const model = propPredictionValue(prop);
  const line = propLineValue(prop);
  const prob = propProbabilityValue(prop);
  const edge = gamePropModelEdge(prop);
  const sim = gamePropSimilaritySummary(profile, stat);
  const pieces = [];
  if (Number.isFinite(edge)) {
    if (edge >= 0.75) pieces.push(`model is well over the line by ${fmt(edge, 2)}`);
    else if (edge >= 0.25) pieces.push(`model clears the line by ${fmt(edge, 2)}`);
    else if (edge >= 0) pieces.push(`model is only slightly over the line`);
    else pieces.push(`model is below the line`);
  }
  if (Number.isFinite(prob)) pieces.push(`${propProbabilityText(prop)} projection`);
  if (sim.avg !== null) pieces.push(`similar games avg ${fmt(sim.avg, 2)}`);
  const risk = gamePropRiskLabel(stat);
  if (risk.cls === 'is-risk') pieces.push('high-variance prop');
  return pieces.join(' • ') || (prop?.tag || 'Model-supported prop');
}

function renderGamePropCards(rows, game, profileMap = new Map()) {
  const root = byId('game-prop-cards');
  if (!root) return;
  if (!rows.length) {
    root.innerHTML = '<div class="empty-state">No prop cards available for this matchup.</div>';
    return;
  }

  const cards = rows.slice(0, 6).map((p, index) => {
    const stat = normalizeAnalyzerStat(p.stat || p.stat_display || '');
    const profile = profileMap.get(String(p.playerId || p.PLAYER_ID || '')) || null;
    const risk = gamePropRiskLabel(stat);
    const sim = gamePropSimilaritySummary(profile, stat);
    const edge = gamePropModelEdge(p);
    const href = propAnalyzerHref(p);
    const cardRole = index === 0 ? 'Best overall angle' : risk.cls === 'is-safe' ? 'Safer angle' : risk.cls === 'is-risk' ? 'Upside angle' : 'Matchup angle';

    return `
      <article class="game-prop-card ${escapeHtml(risk.cls)}">
        <div class="game-prop-card-top">
          <span class="summary-kicker">${escapeHtml(cardRole)}</span>
          <span class="prop-risk-pill ${escapeHtml(risk.cls)}">${escapeHtml(risk.label)}</span>
        </div>
        <h3><a class="table-link table-link-strong" href="${href}">${escapeHtml(p.player || p.PLAYER_NAME || '')}</a></h3>
        <p class="muted">${escapeHtml(propTeamValue(p) || '')} • ${escapeHtml(gamePropStatLabel(stat))} ${hasNumericValue(p.line) ? fmt(p.line, 1) : ''}</p>
        <div class="game-prop-metrics">
          <div><span>Model</span><strong>${escapeHtml(fmt(propPredictionValue(p), 2))}</strong></div>
          <div><span>Prob.</span><strong>${escapeHtml(propProbabilityText(p))}</strong></div>
          <div><span>Edge</span><strong>${escapeHtml(Number.isFinite(edge) ? fmt(edge, 2) : '—')}</strong></div>
          <div><span>Score</span><strong>${escapeHtml(gamePropScoreLabel(p))}</strong></div>
        </div>
        <p class="game-prop-read">${escapeHtml(propQuickRead(p, profile))}</p>
        <div class="game-prop-tags">
          <span>${escapeHtml(sim.text)}</span>
          ${p.tag || p.injuryStatus ? `<span>${escapeHtml(p.injuryStatus || p.tag || '')}</span>` : ''}
        </div>
      </article>
    `;
  }).join('');

  root.innerHTML = cards;
}



function loadProfilesForPlayers(players, gameDate) {
  const ids = [...new Set((players || []).map(p => p?.playerId || p?.PLAYER_ID).filter(Boolean).map(String))].slice(0, 30);
  return Promise.all(ids.map(async id => [id, await loadGamePropProfile(gameDate, id)]))
    .then(pairs => new Map(pairs.filter(([, profile]) => profile)));
}

function preferredLineForStat(stat) {
  const key = normalizeAnalyzerStat(stat);
  const preferred = {
    H: 0.5,
    TB: 1.5,
    HRR: 1.5,
    HR: 0.5,
    '2B': 0.5,
    BB: 0.5,
    K: 0.5,
    SB: 0.5,
    HA: 4.5,
    ER: 2.5,
    IP: 5.5,
    OUTS: 15.5,
  };
  return Object.prototype.hasOwnProperty.call(preferred, key) ? preferred[key] : null;
}

function profileLineOptionForStat(profileProp) {
  const stat = normalizeAnalyzerStat(profileProp?.stat);
  const preferredLine = preferredLineForStat(stat);
  const options = Array.isArray(profileProp?.lineOptions) ? profileProp.lineOptions : [];
  const numeric = options
    .map(opt => ({ ...opt, probabilityNumber: Number(opt.probability), lineNumber: Number(opt.line) }))
    .filter(opt => Number.isFinite(opt.probabilityNumber) && Number.isFinite(opt.lineNumber));

  if (numeric.length && Number.isFinite(preferredLine)) {
    const exact = numeric.find(opt => Math.abs(opt.lineNumber - preferredLine) < 0.001);
    if (exact) return exact;
    const noEasierThanPreferred = numeric.filter(opt => opt.lineNumber >= preferredLine);
    if (noEasierThanPreferred.length) {
      return noEasierThanPreferred.sort((a, b) => {
        const distance = Math.abs(a.lineNumber - preferredLine) - Math.abs(b.lineNumber - preferredLine);
        if (distance) return distance;
        return b.probabilityNumber - a.probabilityNumber;
      })[0];
    }
  }

  if (numeric.length) {
    return numeric.sort((a, b) => b.probabilityNumber - a.probabilityNumber)[0];
  }
  return {};
}

function profilePropAngle(profileProp) {
  if (!profileProp) return null;
  const stat = normalizeAnalyzerStat(profileProp.stat);
  const option = profileLineOptionForStat(profileProp);
  const line = Number(option.line);
  const probability = Number(option.probability);
  const model = Number(profileProp.modelPred);
  const sim = profileProp?.similarityV2 || {};
  const simAvg = Number(sim.avgValue);
  const simScore = Number(sim.avgScore || sim.maxScore);
  const edge = Number.isFinite(model) && Number.isFinite(line) ? model - line : NaN;
  const risk = gamePropRiskLabel(stat);
  const score =
    (Number.isFinite(probability) ? probability * 100 : 0) +
    (Number.isFinite(edge) ? Math.max(-8, Math.min(18, edge * 8)) : 0) +
    (Number.isFinite(simAvg) && Number.isFinite(line) ? Math.max(-6, Math.min(12, (simAvg - line) * 5)) : 0) +
    (Number.isFinite(simScore) ? Math.min(10, simScore / 10) : 0) -
    (risk.cls === 'is-risk' ? 5 : risk.cls === 'is-medium' ? 2 : 0);
  return {
    stat,
    label: gamePropStatLabel(stat),
    line,
    probability,
    model,
    edge,
    simAvg,
    simScore,
    risk,
    score,
    hrefStat: stat
  };
}

function bestProfileAngle(profile, preferredStats = []) {
  const props = Array.isArray(profile?.availableProps) ? profile.availableProps : [];
  const angles = props.map(profilePropAngle).filter(Boolean);
  if (!angles.length) return null;
  const preferred = angles.filter(a => preferredStats.includes(a.stat));
  return (preferred.length ? preferred : angles).sort((a, b) => b.score - a.score)[0];
}

function batterFallbackAngles(b) {
  const predHrr = hasNumericValue(b.predHRR) ? Number(b.predHRR) : ((Number(b.predHR || 0) || 0) + (Number(b.predRuns || 0) || 0) + (Number(b.predRBI || 0) || 0));
  return [
    { stat: 'H', label: 'Hits', line: 0.5, model: Number(b.predHits), probability: Number(b.probHit), risk: gamePropRiskLabel('H') },
    { stat: 'TB', label: 'Total Bases', line: 1.5, model: Number(b.predTB), probability: Number(b.probTB2Plus), risk: gamePropRiskLabel('TB') },
    { stat: 'HRR', label: 'Hits + Runs + RBI', line: 1.5, model: predHrr, probability: Number(b.probHRR2Plus), risk: gamePropRiskLabel('HRR') },
    { stat: 'HR', label: 'Home Runs', line: 0.5, model: Number(b.predHR), probability: Number(b.probHR), risk: gamePropRiskLabel('HR') },
    { stat: '2B', label: 'Doubles', line: 0.5, model: Number(b.predDoubles), probability: Number(b.probDouble), risk: gamePropRiskLabel('2B') },
    { stat: 'BB', label: 'Walks', line: 0.5, model: Number(b.predBB), probability: Number(b.probBB), risk: gamePropRiskLabel('BB') },
    { stat: 'K', label: 'Strikeouts', line: 0.5, model: Number(b.predK), probability: Number(b.probK), risk: gamePropRiskLabel('K') },
    { stat: 'SB', label: 'Stolen Bases', line: 0.5, model: Number(b.predSB), probability: Number(b.probSB), risk: gamePropRiskLabel('SB') }
  ].filter(a => Number.isFinite(a.model) && Number.isFinite(a.probability))
   .map(a => ({ ...a, edge: Number.isFinite(a.line) ? a.model - a.line : NaN, score: (a.probability * 100) + Math.max(-8, Math.min(16, (a.model - a.line) * 8)) - (a.risk.cls === 'is-risk' ? 5 : a.risk.cls === 'is-medium' ? 2 : 0) }));
}

function bestBatterAngle(b, profile = null) {
  const prof = bestProfileAngle(profile, ['H', 'TB', 'HRR', 'SB', '2B']);
  if (prof) return prof;
  const fallback = batterFallbackAngles(b);
  return fallback.sort((a, b) => b.score - a.score)[0] || null;
}

function angleSummary(player, angle, profile = null) {
  if (!angle) return 'No clear prop angle found yet.';
  const pieces = [];
  if (Number.isFinite(angle.model) && Number.isFinite(angle.line)) {
    const edge = angle.model - angle.line;
    if (edge >= 0.75) pieces.push(`${angle.label} has a strong model edge over ${fmt(angle.line, 1)}`);
    else if (edge >= 0.2) pieces.push(`${angle.label} clears the ${fmt(angle.line, 1)} line`);
    else pieces.push(`${angle.label} is close to the line`);
  }
  if (Number.isFinite(angle.probability)) pieces.push(`${fmtPct(angle.probability)} projection`);
  if (Number.isFinite(angle.simAvg)) pieces.push(`similar rows avg ${fmt(angle.simAvg, 2)}`);
  if (Number.isFinite(angle.simScore)) pieces.push(`similarity ${fmt(angle.simScore, 0)}`);
  if (angle.risk?.cls === 'is-risk') pieces.push('use as upside, not safest angle');
  return pieces.join(' • ');
}

function renderBatterAngleBoard(batters, gameDate, profileMap) {
  const root = byId('mlb-batter-angle-board');
  if (!root) return;
  const angles = (batters || []).map(b => {
    const profile = profileMap.get(String(b.playerId || '')) || null;
    const angle = bestBatterAngle(b, profile);
    return { b, profile, angle };
  }).filter(row => row.angle).sort((a, b) => Number(b.angle.score || 0) - Number(a.angle.score || 0)).slice(0, 6);

  if (!angles.length) {
    root.innerHTML = '';
    return;
  }

  root.innerHTML = `
    <div class="batter-angle-head">
      <div>
        <span class="summary-kicker">Batter prop focus</span>
        <h3>Best individual matchup angles</h3>
      </div>
      <p>Uses model edge, probability, player-profile similarity, and prop volatility to narrow the full table.</p>
    </div>
    <div class="batter-angle-grid">
      ${angles.map(({ b, profile, angle }) => {
        const href = b.playerId ? mlbAnalyzerHref(b.playerId, gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
        const name = href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(b.player || '')}</a>` : escapeHtml(b.player || '');
        return `
          <article class="batter-angle-card ${escapeHtml(angle.risk?.cls || '')}">
            <div class="game-prop-card-top">
              <span class="summary-kicker">${escapeHtml(angle.label)}</span>
              <span class="prop-risk-pill ${escapeHtml(angle.risk?.cls || '')}">${escapeHtml(angle.risk?.label || 'Angle')}</span>
            </div>
            <h4>${name}</h4>
            <p class="muted">${escapeHtml([b.team, b.order ? `Order ${b.order}` : '', b.batSide && b.oppPitchHand ? `${b.batSide} vs ${b.oppPitchHand}` : ''].filter(Boolean).join(' • '))}</p>
            <div class="game-prop-metrics">
              <div><span>Line</span><strong>${escapeHtml(Number.isFinite(angle.line) ? fmt(angle.line, 1) : '—')}</strong></div>
              <div><span>Model</span><strong>${escapeHtml(fmt(angle.model, 2))}</strong></div>
              <div><span>Prob.</span><strong>${escapeHtml(fmtPct(angle.probability))}</strong></div>
              <div><span>Score</span><strong>${escapeHtml(Number.isFinite(angle.score) ? String(Math.round(angle.score)) : '—')}</strong></div>
            </div>
            <p class="game-prop-read">${escapeHtml(angleSummary(b.player, angle, profile))}</p>
          </article>
        `;
      }).join('')}
    </div>
  `;
}


function allBatterAngles(b, profile = null) {
  const profileProps = Array.isArray(profile?.availableProps)
    ? profile.availableProps.map(profilePropAngle).filter(Boolean)
    : [];
  const fallbackAngles = batterFallbackAngles(b);
  const byStat = new Map();
  [...fallbackAngles, ...profileProps].forEach(angle => {
    if (!angle?.stat) return;
    const key = normalizeAnalyzerStat(angle.stat);
    const current = byStat.get(key);
    if (!current || Number(angle.score || 0) > Number(current.score || 0)) byStat.set(key, angle);
  });
  return Array.from(byStat.values()).filter(angle => Number.isFinite(Number(angle.probability)) || Number.isFinite(Number(angle.model)));
}

function renderBatterPropExplorer(batters, gameDate, profileMap, activeStat = 'BEST') {
  const root = byId('mlb-batter-prop-explorer');
  if (!root) return;
  const statOrder = ['BEST', 'H', 'TB', 'HRR', 'HR', '2B', 'BB', 'K', 'SB'];
  const selected = normalizeAnalyzerStat(activeStat || root.dataset.activeStat || 'BEST') || 'BEST';
  root.dataset.activeStat = selected;

  const rows = [];
  (batters || []).forEach(b => {
    const profile = profileMap.get(String(b.playerId || '')) || null;
    const angles = selected === 'BEST'
      ? [bestBatterAngle(b, profile)].filter(Boolean)
      : allBatterAngles(b, profile).filter(angle => normalizeAnalyzerStat(angle.stat) === selected);
    angles.forEach(angle => rows.push({ b, profile, angle }));
  });

  rows.sort((a, b) => Number(b.angle?.score || 0) - Number(a.angle?.score || 0));
  const topRows = rows.slice(0, selected === 'BEST' ? 8 : 10);

  root.innerHTML = `
    <div class="batter-explorer-head">
      <div>
        <span class="summary-kicker">All prop finder</span>
        <h3>Find the best angle by prop type</h3>
        <p class="muted">Use this before the full table. It keeps the same model projections, but sorts the board into readable prop cards.</p>
      </div>
    </div>
    <div class="batter-prop-tabs" role="tablist" aria-label="Batter prop filters">
      ${statOrder.map(stat => `
        <button type="button" class="${stat === selected ? 'is-active' : ''}" data-batter-prop-stat="${escapeHtml(stat)}">
          ${escapeHtml(stat === 'BEST' ? 'Best' : gamePropStatLabel(stat))}
        </button>
      `).join('')}
    </div>
    <div class="batter-prop-explorer-grid">
      ${topRows.length ? topRows.map(({ b, profile, angle }, index) => {
        const href = b.playerId ? mlbAnalyzerHref(b.playerId, gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
        const name = href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(b.player || '')}</a>` : escapeHtml(b.player || '');
        const context = [b.team, b.order ? `Order ${b.order}` : '', b.batSide && b.oppPitchHand ? `${b.batSide} vs ${b.oppPitchHand}` : ''].filter(Boolean).join(' • ');
        return `
          <article class="batter-prop-explorer-card ${escapeHtml(angle.risk?.cls || '')}">
            <div class="game-prop-card-top">
              <span class="summary-kicker">${escapeHtml(index === 0 ? 'Top result' : angle.label)}</span>
              <span class="prop-risk-pill ${escapeHtml(angle.risk?.cls || '')}">${escapeHtml(angle.risk?.label || 'Angle')}</span>
            </div>
            <h4>${name}</h4>
            <p class="muted">${escapeHtml(context)}</p>
            <div class="game-prop-metrics">
              <div><span>Prop</span><strong>${escapeHtml(angle.label)}</strong></div>
              <div><span>Line</span><strong>${escapeHtml(Number.isFinite(angle.line) ? fmt(angle.line, 1) : '—')}</strong></div>
              <div><span>Model</span><strong>${escapeHtml(fmt(angle.model, 2))}</strong></div>
              <div><span>Prob.</span><strong>${escapeHtml(fmtPct(angle.probability))}</strong></div>
            </div>
            <p class="game-prop-read">${escapeHtml(angleSummary(b.player, angle, profile))}</p>
          </article>
        `;
      }).join('') : '<div class="empty-state">No players found for this prop type in this matchup.</div>'}
    </div>
  `;

  root.querySelectorAll('[data-batter-prop-stat]').forEach(btn => {
    btn.addEventListener('click', () => {
      renderBatterPropExplorer(batters, gameDate, profileMap, btn.dataset.batterPropStat || 'BEST');
    });
  });
}



function angleStrengthLabel(angle) {
  const score = Number(angle?.score);
  if (!Number.isFinite(score)) return { label: 'Unrated', cls: 'is-muted' };
  if (score >= 86) return { label: 'Strong', cls: 'is-strong' };
  if (score >= 76) return { label: 'Solid', cls: 'is-solid' };
  if (score >= 62) return { label: 'Thin', cls: 'is-thin' };
  return { label: 'Low', cls: 'is-low' };
}

function angleSimilarityLabel(angle) {
  const avg = Number(angle?.simAvg);
  const score = Number(angle?.simScore);
  if (Number.isFinite(score)) return `Sim ${fmt(score, 0)}`;
  if (Number.isFinite(avg)) return `Sim avg ${fmt(avg, 2)}`;
  return 'Profile pending';
}

function batterRowMeta(b, profile = null) {
  const angle = bestBatterAngle(b, profile);
  const strength = angleStrengthLabel(angle);
  const risk = angle?.risk || gamePropRiskLabel(angle?.stat || '');
  return {
    angle,
    strength,
    risk,
    team: String(b?.team || ''),
    stat: normalizeAnalyzerStat(angle?.stat || ''),
    score: Number(angle?.score),
    isStrong: Number(angle?.score) >= 76,
    isLowerVariance: risk?.cls === 'is-safe',
    isUpside: ['is-medium', 'is-risk'].includes(risk?.cls || ''),
  };
}

function batterRowAttributes(b, profile = null) {
  const meta = batterRowMeta(b, profile);
  return [
    `data-batter-team="${escapeHtml(meta.team)}"`,
    `data-angle-stat="${escapeHtml(meta.stat || '')}"`,
    `data-angle-risk="${escapeHtml(meta.risk?.cls || '')}"`,
    `data-angle-strength="${escapeHtml(meta.strength?.cls || '')}"`,
    `data-angle-score="${escapeHtml(Number.isFinite(meta.score) ? String(meta.score) : '')}"`
  ].join(' ');
}

function renderBatterTableTools(batters, profileMap = new Map()) {
  const root = byId('mlb-batter-table-tools');
  if (!root) return;
  const rows = (batters || []).map(b => {
    const profile = profileMap.get(String(b.playerId || '')) || null;
    return { b, profile, meta: batterRowMeta(b, profile) };
  });
  if (!rows.length) {
    root.innerHTML = '';
    return;
  }

  const strongCount = rows.filter(r => r.meta.isStrong).length;
  const lowerCount = rows.filter(r => r.meta.isLowerVariance).length;
  const upsideCount = rows.filter(r => r.meta.isUpside).length;
  const teams = [...new Set(rows.map(r => r.meta.team).filter(Boolean))];

  root.innerHTML = `
    <div class="batter-table-tools-head">
      <div>
        <span class="summary-kicker">Full table controls</span>
        <h3>Filter the full batter board</h3>
        <p class="muted">Use quick filters to cut the wide table down to the most useful rows.</p>
      </div>
      <div class="batter-table-counts">
        <span>${escapeHtml(`${strongCount} strong/solid`)}</span>
        <span>${escapeHtml(`${lowerCount} lower-variance`)}</span>
        <span>${escapeHtml(`${upsideCount} upside`)}</span>
      </div>
    </div>
    <div class="batter-table-filter-row" role="group" aria-label="Batter table filters">
      <button type="button" class="is-active" data-batter-table-filter="all">All</button>
      <button type="button" data-batter-table-filter="strong">Strong/Solid</button>
      <button type="button" data-batter-table-filter="lower">Lower variance</button>
      <button type="button" data-batter-table-filter="upside">Upside</button>
      ${teams.map(team => `<button type="button" data-batter-table-filter="team:${escapeHtml(team)}">${escapeHtml(team)}</button>`).join('')}
    </div>
  `;

  root.dataset.activeFilter = 'all';

  root.querySelectorAll('[data-batter-table-filter]').forEach(button => {
    button.addEventListener('click', () => {
      root.dataset.activeFilter = button.dataset.batterTableFilter || 'all';
      root.querySelectorAll('[data-batter-table-filter]').forEach(btn => btn.classList.toggle('is-active', btn === button));
      applyBatterTableFilter(button.dataset.batterTableFilter || 'all');
    });
  });
}

function applyBatterTableFilter(filter = 'all') {
  const body = byId('mlb-batters-body');
  if (!body) return;
  Array.from(body.querySelectorAll('tr')).forEach(row => {
    const risk = row.dataset.angleRisk || '';
    const strength = row.dataset.angleStrength || '';
    const team = row.dataset.batterTeam || '';
    let show = true;
    if (filter === 'strong') show = ['is-strong', 'is-solid'].includes(strength);
    else if (filter === 'lower') show = risk === 'is-safe';
    else if (filter === 'upside') show = ['is-medium', 'is-risk'].includes(risk);
    else if (filter.startsWith('team:')) show = team === filter.slice(5);
    row.style.display = show ? '' : 'none';
  });
}

function batterAngleCell(b, profile, gameDate) {
  const angle = bestBatterAngle(b, profile);
  if (!angle) return '—';
  const href = b.playerId ? mlbAnalyzerHref(b.playerId, gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
  const label = `${angle.label}${Number.isFinite(angle.line) ? ` ${fmt(angle.line, 1)}` : ''}`;
  const summary = angleSummary(b.player, angle, profile);
  const strength = angleStrengthLabel(angle);
  const risk = angle.risk || gamePropRiskLabel(angle.stat);
  return `
    <div class="best-angle-cell enhanced-angle-cell">
      <div class="angle-cell-top">
        ${href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(label)}</a>` : `<strong>${escapeHtml(label)}</strong>`}
        <span class="angle-strength-pill ${escapeHtml(strength.cls)}">${escapeHtml(strength.label)}</span>
        <span class="prop-risk-pill ${escapeHtml(risk.cls || '')}">${escapeHtml(risk.label || 'Angle')}</span>
      </div>
      <span>${escapeHtml(summary)}</span>
      <div class="angle-cell-meta">
        <small>${escapeHtml(angleSimilarityLabel(angle))}</small>
        <small>${escapeHtml(Number.isFinite(angle.score) ? `Score ${Math.round(angle.score)}` : 'Score pending')}</small>
      </div>
    </div>
  `;
}

function playerIdFromResearchPlayer(p, profileMap = new Map()) {
  if (p?.playerId) return String(p.playerId);
  const wanted = normalizeLookupToken(p?.player || '');
  for (const [id, profile] of profileMap.entries()) {
    if (normalizeLookupToken(profile?.player || '') === wanted) return String(id);
  }
  return '';
}

function giProfileInsight(p, profileMap, mode) {
  const playerId = playerIdFromResearchPlayer(p, profileMap);
  const profile = playerId ? profileMap.get(playerId) : null;
  const angle = bestProfileAngle(profile, mode === 'risk' ? ['H', 'TB', 'HRR', 'K'] : ['H', 'TB', 'HRR', 'SB', '2B']);
  if (!angle) return '';
  const href = profile?.playerId ? mlbAnalyzerHref(profile.playerId, profile.gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
  const label = `${angle.label}${Number.isFinite(angle.line) ? ` ${fmt(angle.line, 1)}` : ''}`;
  return `
    <div class="gi-profile-insight ${mode === 'risk' ? 'is-risk' : 'is-positive'}">
      <span>${escapeHtml(mode === 'risk' ? 'Profile warning' : 'Best profile angle')}</span>
      <strong>${href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(label)}</a>` : escapeHtml(label)}</strong>
      <p>${escapeHtml(angleSummary(profile?.player || p?.player || '', angle, profile))}</p>
    </div>
  `;
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
        ${metricPairCard('Doubles', fmt(b.predDoubles, 2), fmtPct(b.probDouble))}
        ${metricPairCard('Walks', fmt(b.predBB, 2), fmtPct(b.probBB))}
        ${metricPairCard('Strikeouts', fmt(b.predK, 2), fmtPct(b.probK))}
        ${metricPairCard('Stolen bases', fmt(b.predSB, 2), fmtPct(b.probSB))}
        ${metricPairCard('2+ HRR', fmt(predHrr, 2), fmtPct(b.probHRR2Plus))}
      </div>
    </article>
  `;
}


function signedRunText(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${fmt(n, 2)}`;
}

function gameFavoriteSide(game, metrics = {}) {
  const away = String(game?.awayTeam || '').trim();
  const home = String(game?.homeTeam || '').trim();
  if (String(metrics.favoriteWinLabel || '').includes(away)) return away;
  if (String(metrics.favoriteWinLabel || '').includes(home)) return home;
  const awayScore = Number(game?.modelAwayScore);
  const homeScore = Number(game?.modelHomeScore);
  if (Number.isFinite(awayScore) && Number.isFinite(homeScore)) return awayScore >= homeScore ? away : home;
  return metrics.favoriteWinLabel || 'Model side';
}

function renderGameQuickRead(game, detail = null) {
  const root = byId('game-quick-read');
  if (!root) return;
  const metrics = detail?.metrics || {};
  const awayScore = Number(game?.modelAwayScore);
  const homeScore = Number(game?.modelHomeScore);
  const modelTotal = Number.isFinite(awayScore) && Number.isFinite(homeScore) ? awayScore + homeScore : Number(metrics.predTotal);
  const marketTotal = Number(game?.marketTotal);
  const totalEdge = Number.isFinite(modelTotal) && Number.isFinite(marketTotal) ? modelTotal - marketTotal : NaN;
  const favorite = gameFavoriteSide(game, metrics);
  const favoriteProb = Number(metrics.favoriteWinProb);
  const nrfi = Number(metrics.nrfiProb);
  const coverLabel = metrics.marketCoverLabel || metrics.favoriteCoverLabel || 'Run line';
  const coverProb = Number(hasNumericValue(metrics.marketCoverProb) ? metrics.marketCoverProb : metrics.favoriteCoverProb);

  const totalText = Number.isFinite(totalEdge)
    ? `${totalEdge >= 0 ? 'Model leans higher scoring than market' : 'Model leans lower scoring than market'} by ${signedRunText(totalEdge)} runs`
    : 'Total read pending';

  const sideText = Number.isFinite(favoriteProb)
    ? `${favorite} is the model side at ${fmtPct(favoriteProb)}`
    : `${favorite} is the model side`;

  const inningText = Number.isFinite(nrfi)
    ? `${nrfi >= .55 ? 'NRFI is the stronger first-inning side' : 'YRFI / early scoring has more support'} at ${fmtPct(nrfi)} NRFI`
    : 'First-inning read pending';

  const propText = Number.isFinite(totalEdge) && totalEdge > 0.4
    ? 'Run environment supports RBI, HRR, and total-bases angles more than usual.'
    : Number.isFinite(totalEdge) && totalEdge < -0.4
      ? 'Lower run environment makes simple hit/contact props cleaner than RBI-dependent props.'
      : 'Balanced run environment: use player-level matchup support to separate props.';

  root.innerHTML = `
    <article>
      <span class="summary-kicker">Game read</span>
      <strong>${escapeHtml(sideText)}</strong>
      <p>${escapeHtml(coverLabel)} ${Number.isFinite(coverProb) ? fmtPct(coverProb) : 'pending'} • Confidence ${escapeHtml(game?.confidence || 'N/A')}</p>
    </article>
    <article>
      <span class="summary-kicker">Run environment</span>
      <strong>${escapeHtml(Number.isFinite(modelTotal) ? fmt(modelTotal, 2) : 'Pending')}</strong>
      <p>${escapeHtml(totalText)}</p>
    </article>
    <article>
      <span class="summary-kicker">First inning</span>
      <strong>${escapeHtml(Number.isFinite(nrfi) ? fmtPct(nrfi) : 'Pending')}</strong>
      <p>${escapeHtml(inningText)}</p>
    </article>
    <article>
      <span class="summary-kicker">Prop approach</span>
      <strong>Use the profile cards first</strong>
      <p>${escapeHtml(propText)}</p>
    </article>
  `;
}

function renderMlbProbabilityRead(game, detail = null) {
  const root = byId('mlb-probability-read');
  if (!root) return;
  const metrics = detail?.metrics || {};
  const favorite = gameFavoriteSide(game, metrics);
  const favoriteProb = Number(metrics.favoriteWinProb);
  const nrfi = Number(metrics.nrfiProb);
  const yrfi = Number(metrics.yrfiProb);
  const oneRun = Number(metrics.oneRunGameProb);
  const tie = Number(metrics.tieAfter9Prob);
  const coverLabel = metrics.marketCoverLabel || metrics.favoriteCoverLabel || 'Run line';
  const coverProb = Number(hasNumericValue(metrics.marketCoverProb) ? metrics.marketCoverProb : metrics.favoriteCoverProb);
  const totalLabel = metrics.marketTotalLabel || metrics.fallbackTotalLabel || 'Total';
  const totalProb = Number(hasNumericValue(metrics.marketOverProb) ? metrics.marketOverProb : metrics.fallbackOverProb);

  const bullets = [];
  if (Number.isFinite(favoriteProb)) bullets.push(`${favorite} win probability is ${fmtPct(favoriteProb)}.`);
  if (Number.isFinite(coverProb)) bullets.push(`${coverLabel} is ${fmtPct(coverProb)}, so the run-line read is ${coverProb >= .58 ? 'actionable' : 'thin'}.`);
  if (Number.isFinite(totalProb)) bullets.push(`${totalLabel} is ${fmtPct(totalProb)}, which ${totalProb >= .55 ? 'adds support to game-environment props' : 'does not strongly push the total'}.`);
  if (Number.isFinite(nrfi) && Number.isFinite(yrfi)) bullets.push(`${nrfi >= yrfi ? 'NRFI' : 'YRFI'} has the stronger first-inning read.`);
  if (Number.isFinite(oneRun) || Number.isFinite(tie)) bullets.push(`Close-game indicators: one-run ${Number.isFinite(oneRun) ? fmtPct(oneRun) : '—'}${Number.isFinite(tie) ? `, tie after 9 ${fmtPct(tie)}` : ''}.`);

  root.innerHTML = bullets.length
    ? `<strong>Probability read</strong><ul>${bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('')}</ul>`
    : '';
}



function pitcherFallbackAngles(p) {
  const angles = [
    { stat: 'K', label: 'Strikeouts', line: null, model: Number(p.predK), probability: null, risk: gamePropRiskLabel('K') },
    { stat: 'HA', label: 'Hits Allowed', line: null, model: Number(p.predHitsAllowed), probability: null, risk: gamePropRiskLabel('HA') },
    { stat: 'ER', label: 'Earned Runs', line: null, model: Number(p.predER), probability: null, risk: gamePropRiskLabel('ER') },
    { stat: 'IP', label: 'Innings', line: null, model: Number(p.predIP), probability: null, risk: gamePropRiskLabel('IP') },
    { stat: 'BB', label: 'Walks Allowed', line: null, model: Number(p.predBB), probability: null, risk: gamePropRiskLabel('BB') }
  ].filter(a => Number.isFinite(a.model));

  return angles.map(a => {
    let score = 0;
    if (a.stat === 'K') score = a.model * 10;
    else if (a.stat === 'IP') score = a.model * 8;
    else if (a.stat === 'ER') score = Math.max(0, 45 - a.model * 9);
    else if (a.stat === 'HA') score = Math.max(0, 40 - a.model * 4);
    else if (a.stat === 'BB') score = Math.max(0, 32 - a.model * 8);
    return { ...a, score, hrefStat: a.stat };
  });
}

function bestPitcherAngle(p, profile = null) {
  const prof = bestProfileAngle(profile, ['K', 'HA', 'ER', 'IP', 'BB']);
  if (prof) return prof;
  const fallback = pitcherFallbackAngles(p);
  return fallback.sort((a, b) => Number(b.score || 0) - Number(a.score || 0))[0] || null;
}

function pitcherAngleSummary(p, angle, profile = null) {
  if (!angle) return 'No clear pitcher angle found yet.';
  const pieces = [];
  if (angle.stat === 'K') {
    if (Number.isFinite(angle.model) && angle.model >= 6) pieces.push(`${angle.label} projection is elevated at ${fmt(angle.model, 1)}`);
    else if (Number.isFinite(angle.model)) pieces.push(`${angle.label} projection is ${fmt(angle.model, 1)}`);
  } else if (angle.stat === 'ER') {
    if (Number.isFinite(angle.model) && angle.model <= 2.2) pieces.push(`run-prevention profile is strong at ${fmt(angle.model, 1)} ER`);
    else if (Number.isFinite(angle.model)) pieces.push(`earned-run risk is ${fmt(angle.model, 1)}`);
  } else if (angle.stat === 'HA') {
    if (Number.isFinite(angle.model)) pieces.push(`hits-allowed projection is ${fmt(angle.model, 1)}`);
  } else if (angle.stat === 'IP') {
    if (Number.isFinite(angle.model)) pieces.push(`workload projection is ${fmt(angle.model, 1)} IP`);
  } else if (Number.isFinite(angle.model)) {
    pieces.push(`${angle.label} model is ${fmt(angle.model, 1)}`);
  }
  if (Number.isFinite(angle.probability)) pieces.push(`${fmtPct(angle.probability)} projection`);
  if (Number.isFinite(angle.simAvg)) pieces.push(`similar rows avg ${fmt(angle.simAvg, 2)}`);
  if (Number.isFinite(angle.simScore)) pieces.push(`similarity ${fmt(angle.simScore, 0)}`);
  if (Number.isFinite(p?.predHitsAllowed) && Number(p.predHitsAllowed) >= 6) pieces.push('watch batter hit props against him');
  if (Number.isFinite(p?.predER) && Number(p.predER) <= 2) pieces.push('supports run-prevention angle');
  return pieces.join(' • ');
}

function pitcherQuickRole(p) {
  const k = Number(p?.predK);
  const er = Number(p?.predER);
  const ha = Number(p?.predHitsAllowed);
  if (Number.isFinite(k) && k >= 6) return { label: 'K upside', cls: 'is-medium' };
  if (Number.isFinite(er) && er <= 2) return { label: 'Run prevention', cls: 'is-safe' };
  if (Number.isFinite(ha) && ha >= 6) return { label: 'Contact risk', cls: 'is-risk' };
  return { label: 'Pitcher read', cls: 'is-medium' };
}


function pitcherRowMeta(p, profile = null) {
  const angle = bestPitcherAngle(p, profile);
  const role = pitcherQuickRole(p);
  const team = String(p?.team || '');
  const score = Number(angle?.score);
  return {
    angle,
    role,
    team,
    isK: role.label === 'K upside' || normalizeAnalyzerStat(angle?.stat) === 'K',
    isRunPrevention: role.label === 'Run prevention' || normalizeAnalyzerStat(angle?.stat) === 'ER',
    isContactRisk: role.label === 'Contact risk' || Number(p?.predHitsAllowed) >= 6,
    score,
  };
}

function pitcherRowAttributes(p, profile = null) {
  const meta = pitcherRowMeta(p, profile);
  return [
    `data-pitcher-team="${escapeHtml(meta.team)}"`,
    `data-pitcher-role="${escapeHtml(meta.role?.label || '')}"`,
    `data-pitcher-role-class="${escapeHtml(meta.role?.cls || '')}"`,
    `data-pitcher-k="${meta.isK ? '1' : '0'}"`,
    `data-pitcher-run-prevention="${meta.isRunPrevention ? '1' : '0'}"`,
    `data-pitcher-contact-risk="${meta.isContactRisk ? '1' : '0'}"`,
    `data-pitcher-score="${escapeHtml(Number.isFinite(meta.score) ? String(meta.score) : '')}"`
  ].join(' ');
}

function renderPitcherTableTools(pitchers, profileMap = new Map()) {
  const root = byId('mlb-pitcher-table-tools');
  if (!root) return;
  const rows = (pitchers || []).map(p => {
    const profile = profileMap.get(String(p.playerId || '')) || null;
    return { p, profile, meta: pitcherRowMeta(p, profile) };
  });
  if (!rows.length) {
    root.innerHTML = '';
    return;
  }

  const kCount = rows.filter(r => r.meta.isK).length;
  const runCount = rows.filter(r => r.meta.isRunPrevention).length;
  const contactCount = rows.filter(r => r.meta.isContactRisk).length;
  const teams = [...new Set(rows.map(r => r.meta.team).filter(Boolean))];

  root.innerHTML = `
    <div class="batter-table-tools-head">
      <div>
        <span class="summary-kicker">Pitcher table controls</span>
        <h3>Filter pitcher projections</h3>
        <p class="muted">Narrow the starter table by strikeout upside, run prevention, or contact risk.</p>
      </div>
      <div class="batter-table-counts">
        <span>${escapeHtml(`${kCount} K upside`)}</span>
        <span>${escapeHtml(`${runCount} run prevention`)}</span>
        <span>${escapeHtml(`${contactCount} contact risk`)}</span>
      </div>
    </div>
    <div class="batter-table-filter-row" role="group" aria-label="Pitcher table filters">
      <button type="button" class="is-active" data-pitcher-table-filter="all">All</button>
      <button type="button" data-pitcher-table-filter="k">K upside</button>
      <button type="button" data-pitcher-table-filter="run">Run prevention</button>
      <button type="button" data-pitcher-table-filter="contact">Contact risk</button>
      ${teams.map(team => `<button type="button" data-pitcher-table-filter="team:${escapeHtml(team)}">${escapeHtml(team)}</button>`).join('')}
    </div>
  `;

  root.dataset.activeFilter = 'all';

  root.querySelectorAll('[data-pitcher-table-filter]').forEach(button => {
    button.addEventListener('click', () => {
      root.dataset.activeFilter = button.dataset.pitcherTableFilter || 'all';
      root.querySelectorAll('[data-pitcher-table-filter]').forEach(btn => btn.classList.toggle('is-active', btn === button));
      applyPitcherTableFilter(button.dataset.pitcherTableFilter || 'all');
    });
  });
}

function applyPitcherTableFilter(filter = 'all') {
  const body = byId('mlb-pitchers-body');
  if (!body) return;
  Array.from(body.querySelectorAll('tr')).forEach(row => {
    const team = row.dataset.pitcherTeam || '';
    let show = true;
    if (filter === 'k') show = row.dataset.pitcherK === '1';
    else if (filter === 'run') show = row.dataset.pitcherRunPrevention === '1';
    else if (filter === 'contact') show = row.dataset.pitcherContactRisk === '1';
    else if (filter.startsWith('team:')) show = team === filter.slice(5);
    row.style.display = show ? '' : 'none';
  });
}


function pitcherAngleCell(p, profile, gameDate) {
  const angle = bestPitcherAngle(p, profile);
  if (!angle) return '—';
  const href = p.playerId ? mlbAnalyzerHref(p.playerId, gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
  const label = `${angle.label}${Number.isFinite(angle.line) ? ` ${fmt(angle.line, 1)}` : ''}`;
  const summary = pitcherAngleSummary(p, angle, profile);
  return `
    <div class="best-angle-cell">
      ${href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(label)}</a>` : `<strong>${escapeHtml(label)}</strong>`}
      <span>${escapeHtml(summary)}</span>
    </div>
  `;
}

function renderPitcherAngleBoard(pitchers, gameDate, profileMap = new Map()) {
  const root = byId('mlb-pitcher-angle-board');
  if (!root) return;
  const rows = (pitchers || []).map(p => {
    const profile = profileMap.get(String(p.playerId || '')) || null;
    const angle = bestPitcherAngle(p, profile);
    const role = pitcherQuickRole(p);
    return { p, profile, angle, role };
  }).filter(row => row.angle);

  if (!rows.length) {
    root.innerHTML = '';
    return;
  }

  const sorted = rows.slice().sort((a, b) => Number(b.angle?.score || 0) - Number(a.angle?.score || 0));
  root.innerHTML = `
    <div class="pitcher-angle-head">
      <div>
        <span class="summary-kicker">Pitcher prop focus</span>
        <h3>Starter angles</h3>
        <p class="muted">Quickly separate strikeout upside, run-prevention support, and contact risk.</p>
      </div>
    </div>
    <div class="pitcher-angle-grid">
      ${sorted.map(({ p, profile, angle, role }) => {
        const href = p.playerId ? mlbAnalyzerHref(p.playerId, gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '') : '';
        const name = href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(p.player || '')}</a>` : escapeHtml(p.player || '');
        return `
          <article class="pitcher-angle-card ${escapeHtml(role.cls || '')}">
            <div class="game-prop-card-top">
              <span class="summary-kicker">${escapeHtml(role.label)}</span>
              <span class="prop-risk-pill ${escapeHtml(role.cls || '')}">${escapeHtml(angle.label || 'Angle')}</span>
            </div>
            <h4>${name}</h4>
            <p class="muted">${escapeHtml([p.team, p.hand ? `${p.hand}HP` : '', 'Starter'].filter(Boolean).join(' • '))}</p>
            <div class="game-prop-metrics">
              <div><span>IP</span><strong>${escapeHtml(fmt(p.predIP, 1))}</strong></div>
              <div><span>K</span><strong>${escapeHtml(fmt(p.predK, 1))}</strong></div>
              <div><span>Hits</span><strong>${escapeHtml(fmt(p.predHitsAllowed, 1))}</strong></div>
              <div><span>ER</span><strong>${escapeHtml(fmt(p.predER, 1))}</strong></div>
            </div>
            <p class="game-prop-read">${escapeHtml(pitcherAngleSummary(p, angle, profile))}</p>
          </article>
        `;
      }).join('')}
    </div>
  `;
}


async function renderMlbGameDetails(game, detail) {
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
  renderMlbProbabilityRead(game, detail);

  const pitchers = Array.isArray(detail?.pitchers) ? detail.pitchers : [];
  const pitcherProfileMap = pitchers.length ? await loadProfilesForPlayers(pitchers, game?.gameDate || '') : new Map();
  renderPitcherAngleBoard(pitchers, game?.gameDate || '', pitcherProfileMap);
  renderPitcherTableTools(pitchers, pitcherProfileMap);
  if (pitchers.length) {
    pitchersSection.style.display = '';
    pitchersBody.innerHTML = pitchers.map(p => {
      const profile = pitcherProfileMap.get(String(p.playerId || '')) || null;
      const pitcherMeta = [p.team || '', 'Starter', p.hand || ''].filter(Boolean).join(' • ');
      return `
      <tr class="pitcher-projection-row ${escapeHtml(pitcherRowMeta(p, profile).role.cls || '')}" ${pitcherRowAttributes(p, profile)}>
        <td class="name-cell" data-sort="${escapeHtml(String(p.player || ''))}">${playerAnalyzerLink({ ...p, gameDate: game?.gameDate }, 'K')}<span class="subtle-meta">${escapeHtml(pitcherMeta)}</span></td>
        <td data-sort="${escapeHtml(String(p.predIP ?? ''))}">${mlbMetricHtml(p.predIP, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predK ?? ''))}">${mlbMetricHtml(p.predK, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predBB ?? ''))}">${mlbMetricHtml(p.predBB, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predHitsAllowed ?? ''))}">${mlbMetricHtml(p.predHitsAllowed, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(p.predER ?? ''))}">${mlbMetricHtml(p.predER, { digits: 1, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(bestPitcherAngle(p, profile)?.score ?? ''))}">${pitcherAngleCell(p, profile, game?.gameDate || '')}</td>
      </tr>
    `;
    }).join('');
  } else {
    pitchersSection.style.display = 'none';
    pitchersBody.innerHTML = '';
    const pitcherBoard = byId('mlb-pitcher-angle-board');
    if (pitcherBoard) pitcherBoard.innerHTML = '';
    const pitcherTools = byId('mlb-pitcher-table-tools');
    if (pitcherTools) pitcherTools.innerHTML = '';
  }

  const batters = Array.isArray(detail?.batters) ? detail.batters : [];
  const batterProfileMap = batters.length ? await loadProfilesForPlayers(batters, game?.gameDate || '') : new Map();
  renderBatterAngleBoard(batters, game?.gameDate || '', batterProfileMap);
  renderBatterPropExplorer(batters, game?.gameDate || '', batterProfileMap);
  renderBatterTableTools(batters, batterProfileMap);
  if (batters.length) {
    battersSection.style.display = '';
    battersBody.innerHTML = batters.map(b => {
      const profile = batterProfileMap.get(String(b.playerId || '')) || null;
      const batterMeta = [
        b.team || '',
        (b.order !== undefined && b.order !== null && b.order !== '') ? `#${b.order}` : '',
        [b.batSide || '', b.oppPitchHand ? `vs ${b.oppPitchHand}` : ''].filter(Boolean).join(' ')
      ].filter(Boolean).join(' • ');
      return `
      <tr class="batter-projection-row ${escapeHtml(batterRowMeta(b, profile).strength.cls)}" ${batterRowAttributes(b, profile)}>
        <td class="name-cell" data-sort="${escapeHtml(String(b.player || ''))}">${playerAnalyzerLink({ ...b, gameDate: game?.gameDate })}<span class="subtle-meta">${escapeHtml(batterMeta)}</span></td>
        <td data-sort="${escapeHtml(String(b.predHits ?? ''))}">${mlbMetricHtml(b.predHits, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHit ?? ''))}">${mlbMetricHtml(b.probHit, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predTB ?? ''))}">${mlbMetricHtml(b.predTB, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probTB2Plus ?? ''))}">${mlbMetricHtml(b.probTB2Plus, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predHR ?? ''))}">${mlbMetricHtml(b.predHR, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHR ?? ''))}">${mlbMetricHtml(b.probHR, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predDoubles ?? ''))}">${mlbMetricHtml(b.predDoubles, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probDouble ?? ''))}">${mlbMetricHtml(b.probDouble, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predBB ?? ''))}">${mlbMetricHtml(b.predBB, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probBB ?? ''))}">${mlbMetricHtml(b.probBB, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predK ?? ''))}">${mlbMetricHtml(b.predK, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probK ?? ''))}">${mlbMetricHtml(b.probK, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predSB ?? ''))}">${mlbMetricHtml(b.predSB, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probSB ?? ''))}">${mlbMetricHtml(b.probSB, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(b.predHRR ?? ''))}">${mlbMetricHtml(b.predHRR, { digits: 2, mode: 'model' })}</td>
        <td data-sort="${escapeHtml(String(b.probHRR2Plus ?? ''))}">${mlbMetricHtml(b.probHRR2Plus, { pct: true })}</td>
        <td data-sort="${escapeHtml(String(bestBatterAngle(b, profile)?.score ?? ''))}">${batterAngleCell(b, profile, game?.gameDate || '')}</td>
      </tr>
    `;
    }).join('');
  } else {
    battersSection.style.display = 'none';
    battersBody.innerHTML = '';
    const tools = byId('mlb-batter-table-tools');
    if (tools) tools.innerHTML = '';
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

function archiveAwaySpread(row) {
  return hasNumericValue(row?.awaySpread) ? Number(row.awaySpread)
    : (hasNumericValue(row?.marketSpread) ? Number(row.marketSpread) : null);
}

function archiveSpreadOdds(row, side) {
  const keys = side === 'away'
    ? ['awaySpreadOdds', 'awaySpreadPrice']
    : ['homeSpreadOdds', 'homeSpreadPrice'];
  for (const key of keys) {
    if (hasNumericValue(row?.[key])) return Number(row[key]);
  }
  return null;
}

function archiveTotalOdds(row, side) {
  const keys = side === 'over' ? ['overOdds', 'overPrice'] : ['underOdds', 'underPrice'];
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
  const archivedAwaySpread = archiveAwaySpread(row);
  if (!hasNumericValue(merged.awaySpread) && hasNumericValue(archivedAwaySpread)) merged.awaySpread = Number(archivedAwaySpread);
  if (!hasNumericValue(merged.marketSpread) && hasNumericValue(merged.awaySpread)) merged.marketSpread = Number(merged.awaySpread);
  if (!hasNumericValue(merged.homeSpread) && hasNumericValue(row?.homeSpread)) merged.homeSpread = Number(row.homeSpread);
  if (!hasNumericValue(merged.awaySpreadOdds) && hasNumericValue(archiveSpreadOdds(row, 'away'))) merged.awaySpreadOdds = archiveSpreadOdds(row, 'away');
  if (!hasNumericValue(merged.homeSpreadOdds) && hasNumericValue(archiveSpreadOdds(row, 'home'))) merged.homeSpreadOdds = archiveSpreadOdds(row, 'home');
  if (!hasNumericValue(merged.marketTotal) && hasNumericValue(row?.marketTotal)) merged.marketTotal = Number(row.marketTotal);
  if (!hasNumericValue(merged.overOdds) && hasNumericValue(archiveTotalOdds(row, 'over'))) merged.overOdds = archiveTotalOdds(row, 'over');
  if (!hasNumericValue(merged.underOdds) && hasNumericValue(archiveTotalOdds(row, 'under'))) merged.underOdds = archiveTotalOdds(row, 'under');
  ['spreadLinePairValid', 'spreadPricePairValid', 'totalLinePairValid', 'totalPricePairValid', 'marketPriceStatus', 'marketSpreadPerspective', 'bookmakerKey', 'bookmakerTitle'].forEach(key => {
    if ((merged[key] === undefined || merged[key] === null || merged[key] === '') && row?.[key] !== undefined) merged[key] = row[key];
  });
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
      asOf: row?.updatedAt || row?.archivedAt || row?.marketLineUpdated || '',
      awaySpread: archiveAwaySpread(row),
      awaySpreadOdds: archiveSpreadOdds(row, 'away'),
      homeSpreadOdds: archiveSpreadOdds(row, 'home'),
      overOdds: archiveTotalOdds(row, 'over'),
      underOdds: archiveTotalOdds(row, 'under')
    };
  }).filter(row => row.awayTeamNorm === String(game?.awayTeam || '').toUpperCase() && row.homeTeamNorm === String(game?.homeTeam || '').toUpperCase() && (!game?.gameDate || row.localDate === game.gameDate));

  rows.sort((a, b) => new Date(a.asOf || 0) - new Date(b.asOf || 0));
  const snapshots = rows.length ? rows : ((hasNumericValue(game?.awaySpread ?? game?.marketSpread) || hasNumericValue(game?.marketTotal)) ? [{
    awaySpread: game.awaySpread ?? game.marketSpread,
    marketSpread: game.awaySpread ?? game.marketSpread,
    awaySpreadOdds: game.awaySpreadOdds,
    homeSpreadOdds: game.homeSpreadOdds,
    marketTotal: game.marketTotal,
    overOdds: game.overOdds,
    underOdds: game.underOdds,
    awayMoneyline: game.marketAwayML ?? game.awayML,
    homeMoneyline: game.marketHomeML ?? game.homeML,
    asOf: game.marketLineUpdated || game.marketUpdatedAt || '',
    source: game.marketLineSource || game.marketSource || 'games.json'
  }] : []);

  if (!snapshots.length) {
    section.style.display = 'none';
    return;
  }

  section.style.display = '';
  const opening = snapshots[0];
  const current = snapshots[snapshots.length - 1];
  const spreads = snapshots.map(s => Number(s.awaySpread ?? s.marketSpread)).filter(Number.isFinite);
  const totals = snapshots.map(s => Number(s.marketTotal)).filter(Number.isFinite);
  const spreadRange = spreads.length ? `${Math.min(...spreads).toFixed(1)} to ${Math.max(...spreads).toFixed(1)}` : '—';
  const totalRange = totals.length ? `${Math.min(...totals).toFixed(1)} to ${Math.max(...totals).toFixed(1)}` : '—';
  cards.innerHTML = [
    metricCard('Opening spread', hasNumericValue(opening?.awaySpread ?? opening?.marketSpread) ? spreadWithPrice(game, Number(opening.awaySpread ?? opening.marketSpread), opening.awaySpreadOdds, opening.homeSpreadOdds) : '—'),
    metricCard('Current spread', hasNumericValue(current?.awaySpread ?? current?.marketSpread) ? spreadWithPrice(game, Number(current.awaySpread ?? current.marketSpread), current.awaySpreadOdds, current.homeSpreadOdds) : '—'),
    metricCard('Spread range', spreadRange),
    metricCard('Total range', totalRange),
    metricCard('Moneyline now', `${fmtMoneyline(archiveMoneyline(current, 'away'))} / ${fmtMoneyline(archiveMoneyline(current, 'home'))}`),
    metricCard('Snapshots', String(snapshots.length))
  ].join('');

  body.innerHTML = snapshots.map(s => `
    <tr>
      <td>${escapeHtml(String(s.asOf || '').replace('T', ' ').slice(0, 16) || '—')}</td>
      <td>${escapeHtml(hasNumericValue(s.awaySpread ?? s.marketSpread) ? spreadWithPrice(game, Number(s.awaySpread ?? s.marketSpread), s.awaySpreadOdds, s.homeSpreadOdds) : '—')}</td>
      <td>${escapeHtml(hasNumericValue(s.marketTotal) ? totalWithPrices(s.marketTotal, s.overOdds, s.underOdds) : '—')}</td>
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

function giRenderBatterCard(p, mode, profileMap = new Map()) {
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
      ${giProfileInsight(p, profileMap, mode)}
      ${giPlayerNotes(p.notes)}
    </div>
  `;
}

function giRenderBatterList(title, subtitle, players, mode, profileMap = new Map()) {
  const list = Array.isArray(players) ? players : [];
  if (!list.length) return '';
  const primary = list.slice(0, 4);
  const more = list.slice(4);
  return `
    <div class="gi-block gi-batter-block ${mode === 'risk' ? 'is-risk' : 'is-positive'}">
      <div class="gi-block-head">
        <div>
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(subtitle)}</p>
        </div>
        <span class="gi-count-pill">${escapeHtml(`${list.length} signal${list.length === 1 ? '' : 's'}`)}</span>
      </div>
      <div class="gi-player-grid gi-player-grid-priority">
        ${primary.map(p => giRenderBatterCard(p, mode, profileMap)).join('')}
      </div>
      ${more.length ? `
        <details class="gi-more-details">
          <summary>Show ${more.length} more ${mode === 'risk' ? 'risk flag' : 'matchup fit'}${more.length === 1 ? '' : 's'}</summary>
          <div class="gi-player-grid gi-player-grid-secondary">
            ${more.map(p => giRenderBatterCard(p, mode, profileMap)).join('')}
          </div>
        </details>
      ` : ''}
    </div>
  `;
}

function giRenderBatters(report, profileMap = new Map()) {
  const br = report?.batterResearch || {};
  return `
    ${giRenderBatterList('Best matchup fits / positive research signals', 'Recent form plus profile-aware prop angles, similar-game support, and matchup context.', br.positiveSignals || [], 'positive', profileMap)}
    ${giRenderBatterList('Risk flags / cold bats', 'Weak recent hit profiles, strikeout trends, or lower-confidence profile angles.', br.riskFlags || [], 'risk', profileMap)}
  `;
}


function giResearchPlayerAngle(p, profileMap = new Map(), preferredStats = ['H', 'TB', 'HRR', 'SB', '2B']) {
  const playerId = playerIdFromResearchPlayer(p, profileMap);
  const profile = playerId ? profileMap.get(playerId) : null;
  const angle = bestProfileAngle(profile, preferredStats);
  return { playerId, profile, angle };
}

function giTakeawayItem(p, profileMap = new Map(), mode = 'contact') {
  const preferred = mode === 'risk'
    ? ['K', 'HR', 'HRR', 'TB', 'H']
    : mode === 'power'
      ? ['TB', 'HRR', 'HR', '2B']
      : mode === 'speed'
        ? ['SB']
        : ['H', 'BB', 'TB'];
  const { profile, angle } = giResearchPlayerAngle(p, profileMap, preferred);
  const fallbackName = p?.player || profile?.player || '';
  const href = profile?.playerId && angle
    ? mlbAnalyzerHref(profile.playerId, profile.gameDate, angle.hrefStat || angle.stat, Number.isFinite(angle.line) ? angle.line : '')
    : '';
  const metric = p?.metrics || {};
  const h10 = metric.hitsLast10 || {};
  const sim = metric.similarHits || {};
  const title = angle
    ? `${angle.label}${Number.isFinite(angle.line) ? ` ${fmt(angle.line, 1)}` : ''}`
    : (mode === 'risk' ? 'Risk flag' : 'Research signal');
  const sub = angle
    ? angleSummary(fallbackName, angle, profile)
    : [
        h10?.sample ? `Hit L10 ${giRateText(h10)}` : '',
        sim?.sample ? `similar hits ${giRateText(sim)}` : '',
        Array.isArray(p?.notes) && p.notes.length ? p.notes[0] : ''
      ].filter(Boolean).join(' • ');

  return `
    <li>
      <div>
        <strong>${href ? `<a class="table-link table-link-strong" href="${href}">${escapeHtml(fallbackName)}</a>` : escapeHtml(fallbackName)}</strong>
        <span>${escapeHtml([p?.team, p?.location, p?.pitchHand ? `vs ${p.pitchHand}HP` : ''].filter(Boolean).join(' • '))}</span>
      </div>
      <em>${escapeHtml(title)}</em>
      <small>${escapeHtml(sub || 'Profile support pending')}</small>
    </li>
  `;
}

function giTopResearchPlayers(list, profileMap, mode, limit = 3) {
  const rows = (Array.isArray(list) ? list : []).map(p => {
    const preferred = mode === 'risk'
      ? ['K', 'HR', 'HRR', 'TB', 'H']
      : mode === 'power'
        ? ['TB', 'HRR', 'HR', '2B']
        : mode === 'speed'
          ? ['SB']
          : ['H', 'BB', 'TB'];
    const { angle } = giResearchPlayerAngle(p, profileMap, preferred);
    const score = Number(angle?.score);
    const metrics = p?.metrics || {};
    const h10 = metrics.hitsLast10 || {};
    const sim = metrics.similarHits || {};
    const fallbackScore =
      (Number(h10.rate || 0) * 50) +
      (Number(sim.rate || 0) * 35) +
      (Array.isArray(p?.notes) ? Math.min(10, p.notes.length * 2) : 0);
    return { p, angle, score: Number.isFinite(score) ? score : fallbackScore };
  });
  return rows
    .filter(row => row.p)
    .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
    .slice(0, limit)
    .map(row => row.p);
}

function giRenderResearchTakeaways(report, profileMap = new Map()) {
  const br = report?.batterResearch || {};
  const positives = Array.isArray(br.positiveSignals) ? br.positiveSignals : [];
  const risks = Array.isArray(br.riskFlags) ? br.riskFlags : [];
  if (!positives.length && !risks.length) return '';

  const contact = giTopResearchPlayers(positives, profileMap, 'contact', 3);
  const power = giTopResearchPlayers(positives, profileMap, 'power', 3);
  const speed = giTopResearchPlayers(positives, profileMap, 'speed', 2)
    .filter(p => {
      const { angle } = giResearchPlayerAngle(p, profileMap, ['SB']);
      return angle && normalizeAnalyzerStat(angle.stat) === 'SB';
    });
  const risk = giTopResearchPlayers(risks, profileMap, 'risk', 3);

  const cards = [
    {
      title: 'Contact fits',
      note: 'Cleaner player props that rely less on one swing.',
      mode: 'contact',
      rows: contact,
      cls: 'is-positive'
    },
    {
      title: 'Power / production fits',
      note: 'Better for total bases, HRR, doubles, and longshot power ideas.',
      mode: 'power',
      rows: power,
      cls: 'is-upside'
    },
    speed.length ? {
      title: 'Speed angle',
      note: 'Stolen-base support when the player profile points that way.',
      mode: 'speed',
      rows: speed,
      cls: 'is-speed'
    } : null,
    {
      title: 'Main risk flags',
      note: 'Players where the research or profile suggests caution.',
      mode: 'risk',
      rows: risk,
      cls: 'is-risk'
    }
  ].filter(card => card && card.rows && card.rows.length);

  if (!cards.length) return '';

  return `
    <div class="gi-block gi-takeaway-block">
      <div class="gi-block-head">
        <div>
          <h3>Research takeaways</h3>
          <p>Quick summary of where the batter research points before opening the detailed hot/cold cards.</p>
        </div>
      </div>
      <div class="gi-takeaway-grid">
        ${cards.map(card => `
          <article class="gi-takeaway-card ${escapeHtml(card.cls)}">
            <div class="game-prop-card-top">
              <h4>${escapeHtml(card.title)}</h4>
              <span class="gi-count-pill">${escapeHtml(`${card.rows.length} shown`)}</span>
            </div>
            <p class="muted">${escapeHtml(card.note)}</p>
            <ul>
              ${card.rows.map(p => giTakeawayItem(p, profileMap, card.mode)).join('')}
            </ul>
          </article>
        `).join('')}
      </div>
    </div>
  `;
}


async function renderGameIntelligence(game, detail = null) {
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
    const battersForProfiles = Array.isArray(detail?.batters) ? detail.batters : [];
    const giProfileMap = battersForProfiles.length ? await loadProfilesForPlayers(battersForProfiles, game?.gameDate || '') : new Map();
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
      ${giRenderResearchTakeaways(report, giProfileMap)}
      ${giRenderModelForm(report)}
      ${giRenderMovement(report)}
      ${giRenderPitchers(report)}
      ${giRenderFirstInning(report)}
      ${giRenderBatters(report, giProfileMap)}
    `;
  } catch (err) {
    section.style.display = 'none';
  }
}


function setupGameJumpNavActive() {
  const links = Array.from(document.querySelectorAll('.game-jump-inner a[href^="#"]'));
  if (!links.length || !('IntersectionObserver' in window)) return;
  const sections = links
    .map(link => {
      const id = String(link.getAttribute('href') || '').replace('#', '');
      const section = id ? document.getElementById(id) : null;
      return section ? { link, section } : null;
    })
    .filter(Boolean);

  const setActive = id => {
    sections.forEach(({ link, section }) => {
      const active = section.id === id;
      link.classList.toggle('is-active', active);
      if (active && typeof link.scrollIntoView === 'function') {
        link.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      }
    });
  };

  const observer = new IntersectionObserver(entries => {
    const visible = entries
      .filter(entry => entry.isIntersecting)
      .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top))[0];
    if (visible?.target?.id) setActive(visible.target.id);
  }, { rootMargin: '-22% 0px -65% 0px', threshold: [0, .2, .45] });

  sections.forEach(({ section }) => observer.observe(section));
}

function setupTableScrollHints() {
  const update = () => {
    document.querySelectorAll('.table-wrap').forEach(wrap => {
      const hasOverflow = wrap.scrollWidth > wrap.clientWidth + 12;
      wrap.classList.toggle('is-scrollable', hasOverflow);
    });
  };
  update();
  window.addEventListener('resize', update, { passive: true });
  setTimeout(update, 250);
  setTimeout(update, 900);
}

function setupDetailsLazyScrollHints() {
  document.querySelectorAll('.game-deep-details, .gi-more-details').forEach(detail => {
    detail.addEventListener('toggle', () => {
      if (detail.open) setTimeout(setupTableScrollHints, 60);
    }, { passive: true });
  });
}

function setupGamePagePolish() {
  setupGameJumpNavActive();
  setupTableScrollHints();
  setupDetailsLazyScrollHints();
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

    const propsData = String(game?.league || '').toUpperCase() === 'MLB' ? rawProps : mergePropCollections(rawPropsLab, rawProps);
    const mlbDetail = String(game?.league || '').toUpperCase() === 'MLB' && game?.detailPath
      ? await loadJson(game.detailPath, null)
      : null;

    document.title = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-league').textContent = game.league || '';
    byId('game-title').textContent = `${game.awayTeam} @ ${game.homeTeam}`;
    byId('game-summary').textContent = game.summary || '';
    byId('snapshot-score').textContent = `${fmt(game.modelAwayScore, 2)} - ${fmt(game.modelHomeScore, 2)}`;
    const marketStatus = String(game.marketLineStatus || game.market_line_status || '').toUpperCase();
    const staleSuffix = marketStatus.includes('STALE') ? ' • stale' : '';
    const displaySpread = marketSpreadForDisplay(game);
    byId('snapshot-spread').textContent = Number.isFinite(displaySpread)
      ? `${spreadWithPrice(game, displaySpread, game.awaySpreadOdds, game.homeSpreadOdds)}${staleSuffix}`
      : 'Pending';
    byId('snapshot-total').textContent = hasNumericValue(game.marketTotal)
      ? `${totalWithPrices(game.marketTotal, game.overOdds, game.underOdds)}${staleSuffix}`
      : 'Pending';
    byId('snapshot-confidence').textContent = game.confidence || 'N/A';
    renderGameQuickRead(game, mlbDetail);

    setupMovementToggle(game, game.movement || []);
    await renderGameProps(game, propsData, injuryLookup, mlbDetail);
    await renderMlbGameDetails(game, mlbDetail);
    renderMlbOddsMovement(game, archiveRows);
    await renderGameIntelligence(game, mlbDetail);
    makeTablesSortable('.sortable-table');
    setupGamePagePolish();
  } catch (err) {
    byId('game-title').textContent = 'Unable to load game';
    byId('game-summary').textContent = err.message || String(err);
  }
})();
