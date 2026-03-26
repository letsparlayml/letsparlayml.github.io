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

function propDateValue(prop) {
  return prop?.gameDate || prop?.date || prop?.propDate || prop?.game_date || '';
}

function filterPropsByDate(props, date) {
  if (!date) return props || [];
  const dated = (props || []).filter(p => propDateValue(p));
  if (!dated.length) return props || [];
  return dated.filter(p => propDateValue(p) === date);
}

function hasNumericValue(v) {
  return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
}

function setText(id, value) {
  const el = byId(id);
  if (el) el.textContent = value ?? '';
}

function isNbaGame(game) {
  return String(game?.league || '').toUpperCase() === 'NBA';
}

function modelSpreadForDisplay(game) {
  if (isNbaGame(game)) {
    const away = Number(game?.modelAwayScore);
    const home = Number(game?.modelHomeScore);
    if (Number.isFinite(away) && Number.isFinite(home)) {
      // NBA cards should display spread from AWAY-team perspective
      return home - away;
    }

    const fallback = Number(game?.modelHomeSpread);
    return Number.isFinite(fallback) ? -fallback : NaN;
  }

  // CBB/NHL: keep existing stored convention
  const stored = Number(game?.modelHomeSpread);
  return Number.isFinite(stored) ? stored : NaN;
}

function marketSpreadForDisplay(game) {
  const spread = Number(game?.marketSpread);
  if (!Number.isFinite(spread)) return NaN;

  // NBA only: convert stored home spread to away-team display
  if (isNbaGame(game)) return -spread;

  // CBB/NHL: keep existing stored convention
  return spread;
}

function spreadEdgeForDisplay(game) {
  const model = modelSpreadForDisplay(game);
  const market = marketSpreadForDisplay(game);
  return Number.isFinite(model) && Number.isFinite(market)
    ? model - market
    : NaN;
}

function spreadTeamLabel(game, awaySpread) {
  if (!Number.isFinite(awaySpread)) return 'N/A';
  if (Math.abs(awaySpread) < 0.05) return 'PK';
  return awaySpread > 0
    ? `${game?.homeTeam || 'Home'} ${fmtSigned(-awaySpread)}`
    : `${game?.awayTeam || 'Away'} ${fmtSigned(awaySpread)}`;
}

function spreadEdgeText(game) {
  const edge = spreadEdgeForDisplay(game);
  if (!Number.isFinite(edge)) return 'N/A';
  if (Math.abs(edge) < 0.05) return 'PK';
  const leanTeam = edge > 0 ? (game?.homeTeam || 'Home') : (game?.awayTeam || 'Away');
  return `${leanTeam} ${Math.abs(edge).toFixed(1)} pts`;
}

function marketSpreadText(game) {
  const spread = marketSpreadForDisplay(game);
  return spreadTeamLabel(game, spread);
}

function modelSpreadText(game) {
  const spread = modelSpreadForDisplay(game);
  return spreadTeamLabel(game, spread);
}

function cardSummaryText(game) {
  const raw = String(game?.summary || 'Model snapshot');
  const spread = marketSpreadForDisplay(game);
  const total = Number(game?.marketTotal);

  return raw
    .replace(
      /Spread line pending/g,
      Number.isFinite(spread) ? `Spread line ${spreadTeamLabel(game, spread)}` : 'Spread line pending'
    )
    .replace(
      /Total line pending/g,
      Number.isFinite(total) ? `Total line ${fmt(total)}` : 'Total line pending'
    );
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

    const teamKey = normalizeTeamToken(entry.team || entry.team_abbr);
    const normalized = {
      status: titleCaseWord(canonicalInjuryStatus(entry.status)),
      note: entry.note || entry.injury_note || '',
      team: entry.team || entry.team_abbr || '',
      lastUpdated: entry.lastUpdated || entry.last_updated || entry.updated_at || '',
      gameDate: entry.gameDate || entry.game_date || ''
    };

    if (teamKey) {
      lookup.set(`${playerKey}|${teamKey}`, normalized);
    }

    // Always create a player-only fallback too
    if (!lookup.has(`${playerKey}|`)) {
      lookup.set(`${playerKey}|`, normalized);
    }
  });
  return lookup;
}

function getPropInjuryContext(prop, injuryLookup) {
  if (!injuryLookup || !injuryLookup.size) return null;
  const playerKey = normalizeLookupToken(prop?.player);
  if (!playerKey) return null;
  const teamKey = normalizeTeamToken(prop?.team);
  return injuryLookup.get(`${playerKey}|${teamKey}`) || injuryLookup.get(`${playerKey}|`) || null;
}

function decoratePropInjury(prop, injuryLookup) {
  const context = getPropInjuryContext(prop, injuryLookup);
  if (!context) return { ...prop };
  return {
    ...prop,
    injuryStatus: context.status || '',
    injuryNote: context.note || '',
    injuryUpdated: context.lastUpdated || ''
  };
}

function shouldHideProp(prop) {
  const status = canonicalInjuryStatus(prop?.injuryStatus || prop?.playerStatus || prop?.status);
  return status === 'out' || status === 'doubtful';
}

function applyInjuryContextToList(items, injuryLookup) {
  return (items || [])
    .map(item => decoratePropInjury(item, injuryLookup))
    .filter(item => !shouldHideProp(item));
}

function applyInjuryContextToHomeInsights(homeInsights, injuryLookup) {
  if (!homeInsights || !homeInsights.byDate) return homeInsights || {};
  const next = JSON.parse(JSON.stringify(homeInsights));
  Object.keys(next.byDate).forEach(date => {
    const day = next.byDate[date];
    Object.keys(day || {}).forEach(key => {
      if (Array.isArray(day[key])) {
        day[key] = applyInjuryContextToList(day[key], injuryLookup);
      }
    });
  });
  return next;
}

function injuryBadgeHtml(prop) {
  const status = canonicalInjuryStatus(prop?.injuryStatus || prop?.playerStatus || '');
  if (status !== 'probable' && status !== 'questionable') return '';
  return `<span class="injury-badge injury-${status}">${escapeHtml(titleCaseWord(status))}</span>`;
}

function playerBadgeHtml(name, prop) {
  return `<span class="player-with-badge"><span class="player-name-only">${escapeHtml(name || '')}</span>${injuryBadgeHtml(prop)}</span>`;
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

function fmtPct(num, digits = 1) {
  const n = Number(num);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : 'N/A';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function uniqueLeagues(games) {
  return [...new Set((games || []).map(g => g.league).filter(Boolean))].sort();
}

function modelAwaySpread(game) {
  const away = Number(game?.modelAwayScore);
  const home = Number(game?.modelHomeScore);
  if (Number.isFinite(away) && Number.isFinite(home)) {
    // Away-team spread perspective for "AWAY @ HOME"
    // positive = away underdog, negative = away favorite
    return home - away;
  }

  const fallback = Number(game?.modelHomeSpread);
  return Number.isFinite(fallback) ? -fallback : NaN;
}

function marketAwaySpread(game) {
  const spread = Number(game?.marketSpread);
  if (!Number.isFinite(spread)) return NaN;

  // Site cards display spreads from the away-team perspective for "AWAY @ HOME".
  // NBA stores home-team spreads, while CBB/NHL are already stored in away-team display form.
  return isNbaGame(game) ? -spread : spread;
}

function marketSpreadText(game) {
  const spread = marketAwaySpread(game);
  return spreadTeamLabel(game, spread);
}

function marketTotalText(game) {
  return hasNumericValue(game.marketTotal) ? fmt(game.marketTotal) : 'N/A';
}

function gameCard(game) {
  const modelSpread = modelSpreadForDisplay(game);
  const marketSpread = marketSpreadForDisplay(game);
  const edgeSpread = spreadEdgeForDisplay(game);
  const edgeTotal = hasNumericValue(game.marketTotal) ? Number(game.modelTotal) - Number(game.marketTotal) : NaN;

  return `
      <article class="game-card">
        <div class="meta-row">
          <span class="tag">${escapeHtml(game.league || '')}</span>
          <span>${escapeHtml(game.gameDate || '')}</span>
        </div>
        <div>
          <h3>${escapeHtml(game.awayTeam)} @ ${escapeHtml(game.homeTeam)}</h3>
          <p class="muted">${escapeHtml(cardSummaryText(game))}</p>
        </div>
        <div class="score-box">
          <div class="score-row"><span>${escapeHtml(game.awayTeam)}</span><strong>${fmt(game.modelAwayScore)}</strong></div>
          <div class="score-row"><span>${escapeHtml(game.homeTeam)}</span><strong>${fmt(game.modelHomeScore)}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model spread</span><strong>${modelSpreadText(game)}</strong></div>
          <div class="kpi"><span>Market spread</span><strong>${marketSpreadText(game)}</strong></div>
          <div class="kpi"><span>Spread edge</span><strong>${spreadEdgeText(game)}</strong></div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><span>Model total</span><strong>${fmt(game.modelTotal)}</strong></div>
          <div class="kpi"><span>Market total</span><strong>${marketTotalText(game)}</strong></div>
          <div class="kpi"><span>Total edge</span><strong>${Number.isFinite(edgeTotal) ? fmtSigned(edgeTotal) : 'N/A'}</strong></div>
        </div>
        <div class="meta-row">
          <span>Confidence: ${escapeHtml(game.confidence || 'N/A')}</span>
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

function probabilitySourceText(p) {
  return String(p.probabilityText ?? p.probability_note ?? p.matchup ?? p.note ?? '');
}

function coerceProbability(value) {
  if (value === null || value === undefined || value === '') return NaN;

  if (typeof value === 'string') {
    const cleaned = value.replace('%', '').trim();
    const n = Number(cleaned);
    if (Number.isFinite(n)) return n > 1 ? n / 100 : n;
    return NaN;
  }

  const n = Number(value);
  if (!Number.isFinite(n)) return NaN;
  return n > 1 ? n / 100 : n;
}

function propProbabilityValue(p) {
  const candidates = [
    p?.prob_cons,
    p?.probability,
    p?.clearProbability,
    p?.clear_probability,
    p?.prob,
    p?.winProbability,
    p?.win_probability
  ];

  let sawZero = false;

  for (const value of candidates) {
    const n = coerceProbability(value);
    if (!Number.isFinite(n)) continue;
    if (n > 0) return n;
    if (n === 0) sawZero = true;
  }

  const src = probabilitySourceText(p);
  const match = src.match(/(\d+(?:\.\d+)?)%\s*(?:to\s+clear|clear|over|under|hit)?/i);
  if (match) {
    const n = Number(match[1]);
    if (Number.isFinite(n)) return n / 100;
  }

  return sawZero ? 0 : NaN;
}

function propProbabilityText(p) {
  const n = propProbabilityValue(p);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : 'N/A';
}

function propMatchupText(p) {
  if (p?.matchup && String(p.matchup).trim()) return String(p.matchup).trim();

  const team = String(p?.team || '').trim();
  const opp = String(p?.opp || '').trim();
  if (team && opp) return `${team} vs ${opp}`;

  const src = probabilitySourceText(p);
  if (!src) return 'N/A';

  const cleaned = src
    .replace(/\s*[•\-|–—]\s*\d+(?:\.\d+)?%.*$/i, '')
    .replace(/\s+\d+(?:\.\d+)?%.*$/i, '')
    .trim();

  return cleaned || 'N/A';
}

function flattenPropsSource(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.props)) return data.props;
  if (Array.isArray(data?.rows)) return data.rows;

  if (data?.byDate && typeof data.byDate === 'object') {
    return Object.entries(data.byDate).flatMap(([date, day]) =>
      (day?.allProps || []).map(prop => ({
        ...prop,
        gameDate: prop?.gameDate || prop?.date || prop?.GAME_DATE || date
      }))
    );
  }

  return [];
}

function normalizeGameNumericId(value) {
  const raw = String(value ?? '');
  const match = raw.match(/(\d{7,})/);
  return match ? match[1] : '';
}

function buildGameLookup(games) {
  const byGameId = new Map();
  const byGameIdDate = new Map();

  (games || []).forEach(game => {
    const gid = normalizeGameNumericId(game?.sourceGameId || game?.id || game?.gameId || '');
    if (!gid) return;

    const date = String(game?.gameDate || '').trim();
    byGameId.set(gid, game);
    if (date) byGameIdDate.set(`${gid}|${date}`, game);
  });

  return { byGameId, byGameIdDate };
}

function resolveGameForProp(prop, gameLookup) {
  const gid = normalizeGameNumericId(prop?.gameId || prop?.game_id || prop?.GAME_ID || '');
  const date = String(propDateValue(prop) || '').trim();
  if (!gid) return null;
  return gameLookup.byGameIdDate.get(`${gid}|${date}`) || gameLookup.byGameId.get(gid) || null;
}

function propModelValue(p) {
  const candidates = [p?.modelPrediction, p?.model, p?.pred_anchor, p?.mu_cons];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propAverageValue(p) {
  const candidates = [p?.avg_anchor, p?.average, p?.avg];
  for (const value of candidates) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

function propLineValue(p) {
  const n = Number(p?.line);
  return Number.isFinite(n) ? n : NaN;
}

function propLineRatio(p) {
  const direct = [p?.line_to_avg, p?.lineToAvg, p?.line_to_pred, p?.lineToPred];
  for (const value of direct) {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) return n;
  }

  const line = propLineValue(p);
  const avg = propAverageValue(p);
  if (Number.isFinite(line) && Number.isFinite(avg) && avg > 0) return line / avg;

  const model = propModelValue(p);
  if (Number.isFinite(line) && Number.isFinite(model) && model > 0) return line / model;

  return NaN;
}

function propClosenessScore(p) {
  const ratio = propLineRatio(p);
  if (!Number.isFinite(ratio)) return 0.45;
  const clamped = Math.max(0, Math.min(ratio, 1.25));
  return Math.max(0, 1 - Math.abs(1 - clamped));
}

function propDisplayScore(p) {
  const prob = Number.isFinite(propProbabilityValue(p)) ? propProbabilityValue(p) : 0;
  const closeness = propClosenessScore(p);
  const stability = Number.isFinite(Number(p?.stability_score)) ? Number(p.stability_score) : 0;
  const minutes = Number.isFinite(Number(p?.minutes_score)) ? Number(p.minutes_score) : 0;
  const agreement = Number.isFinite(Number(p?.agreement_score)) ? Number(p.agreement_score) : 0;

  return prob * 0.50 + closeness * 0.20 + stability * 0.15 + minutes * 0.10 + agreement * 0.05;
}

function isReasonableHomepageProp(p, { probFloor = 0.56, ratioFloor = 0.68 } = {}) {
  const prob = propProbabilityValue(p);
  if (Number.isFinite(prob) && prob < probFloor) return false;

  const ratio = propLineRatio(p);
  if (Number.isFinite(ratio) && ratio < ratioFloor) return false;

  return true;
}

function propConfidenceLabel(p) {
  const prob = propProbabilityValue(p);
  const score = propDisplayScore(p);

  if ((Number.isFinite(prob) && prob >= 0.70) || score >= 0.78) return 'High';
  if ((Number.isFinite(prob) && prob >= 0.60) || score >= 0.66) return 'Medium';
  return 'Lean';
}

function enrichHomepageProp(prop, gameLookup) {
  const game = resolveGameForProp(prop, gameLookup);
  const location = String(prop?.location || '').trim().toLowerCase();

  let team = String(prop?.team || '').trim();
  let opp = String(prop?.opp || '').trim();

  if (game) {
    const away = String(game?.awayTeam || '').trim();
    const home = String(game?.homeTeam || '').trim();

    if (!team) {
      if (location === 'away') team = away;
      else if (location === 'home') team = home;
    }

    if (!opp) {
      if (location === 'away') opp = home;
      else if (location === 'home') opp = away;
    }
  }

  const matchup =
    String(prop?.matchup || '').trim() ||
    (team && opp ? `${team} vs ${opp}` : (game ? `${game.awayTeam} vs ${game.homeTeam}` : ''));

  const model = propModelValue(prop);

  return {
    ...prop,
    gameDate: propDateValue(prop),
    league: prop?.league || game?.league || 'NBA',
    team,
    opp,
    matchup,
    modelPrediction: Number.isFinite(model) ? model : '',
    confidence: prop?.confidence || propConfidenceLabel(prop)
  };
}

function pickBestHomepageVariant(rows) {
  return rows
    .slice()
    .sort((a, b) => {
      const scoreDiff = propDisplayScore(b) - propDisplayScore(a);
      if (scoreDiff) return scoreDiff;

      const probDiff = propProbabilityValue(b) - propProbabilityValue(a);
      if (Number.isFinite(probDiff) && probDiff) return probDiff;

      const modelDiff = propModelValue(b) - propModelValue(a);
      if (Number.isFinite(modelDiff) && modelDiff) return modelDiff;

      return 0;
    })[0] || null;
}

function selectHomepageTopProps(props, limit = 12) {
  const groups = new Map();

  (props || []).forEach(prop => {
    const key = [
      normalizeLookupToken(prop?.player || ''),
      String(prop?.stat || prop?.stat_display || '').toUpperCase(),
      String(prop?.gameDate || ''),
      normalizeGameNumericId(prop?.gameId || prop?.game_id || prop?.GAME_ID || '')
    ].join('|');

    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(prop);
  });

  const deduped = Array.from(groups.values())
    .map(group => pickBestHomepageVariant(group))
    .filter(Boolean);

  const preferred = deduped.filter(p => isReasonableHomepageProp(p, { probFloor: 0.58, ratioFloor: 0.70 }));
  const usable = preferred.length >= Math.min(limit, 6)
    ? preferred
    : deduped.filter(p => isReasonableHomepageProp(p, { probFloor: 0.54, ratioFloor: 0.64 }));

  return (usable.length ? usable : deduped)
    .slice()
    .sort((a, b) => {
      const scoreDiff = propDisplayScore(b) - propDisplayScore(a);
      if (scoreDiff) return scoreDiff;

      const probDiff = propProbabilityValue(b) - propProbabilityValue(a);
      if (Number.isFinite(probDiff) && probDiff) return probDiff;

      return propModelValue(b) - propModelValue(a);
    })
    .slice(0, limit);
}

function renderProps(props, bodyId = 'props-body') {
  const body = byId(bodyId);
  if (!body) return;

  const visibleProps = props || [];
  if (!visibleProps.length) {
    body.innerHTML = '<tr><td colspan="8">No props available.</td></tr>';
    return;
  }

  body.innerHTML = visibleProps.map(p => `
    <tr>
      <td>${escapeHtml(p.league || 'NBA')}</td>
      <td>${playerBadgeHtml(p.player || '', p)}</td>
      <td>${escapeHtml(p.stat_display || p.stat || '')}</td>
      <td>${escapeHtml(hasNumericValue(p.line) ? fmt(p.line, 1) : (p.line ?? ''))}</td>
      <td>${escapeHtml(hasNumericValue(p.modelPrediction) ? fmt(p.modelPrediction, 1) : (p.modelPrediction ?? ''))}</td>
      <td>${escapeHtml(propProbabilityText(p))}</td>
      <td>${escapeHtml(p.confidence || propConfidenceLabel(p))}</td>
      <td>${escapeHtml(propMatchupText(p))}</td>
    </tr>
  `).join('');
}

function resultOutcome(result) {
  const normalized = String(result || '').trim().toLowerCase();
  if (!normalized) return '';
  if (/\bwin\b/.test(normalized)) return 'win';
  if (/\bloss\b/.test(normalized)) return 'loss';
  if (/\bpush\b/.test(normalized)) return 'push';
  if (normalized === 'n/a') return 'na';
  return '';
}

function resultBadgeClass(result) {
  const outcome = resultOutcome(result);
  if (outcome === 'win') return 'badge-win';
  if (outcome === 'loss') return 'badge-loss';
  if (outcome === 'push') return 'badge-push';
  return 'badge-na';
}

function parseResultScoreValues(text) {
  const matches = String(text || '').match(/-?\d+(?:\.\d+)?/g) || [];
  if (matches.length < 2) return [];
  return matches.slice(-2).map(Number).filter(Number.isFinite);
}

function parseMatchupTeams(text) {
  const raw = String(text || '').trim();
  if (!raw) return { away: '', home: '' };
  if (raw.includes('@')) {
    const [away, home] = raw.split('@').map(part => String(part || '').trim());
    return { away, home };
  }
  if (/\bvs\b/i.test(raw)) {
    const [home, away] = raw.split(/\bvs\b/i).map(part => String(part || '').trim());
    return { away, home };
  }
  return { away: '', home: '' };
}

function inferredSpreadLabel(row) {
  const marketSpread = Number(row?.marketSpread);
  if (!Number.isFinite(marketSpread)) return '';

  const league = String(row?.league || '').toUpperCase().trim();
  const predictedVals = parseResultScoreValues(row?.predicted || '');
  const actualVals = parseResultScoreValues(row?.actual || '');
  const teams = parseMatchupTeams(row?.matchup || '');

  const predMargin = predictedVals.length === 2 ? predictedVals[1] - predictedVals[0] : NaN; // home - away
  const actualMargin = actualVals.length === 2 ? actualVals[1] - actualVals[0] : NaN;       // home - away
  if (!Number.isFinite(predMargin)) return '';

  let pickTeam = '';
  let pickLine = marketSpread;
  let resolvedOutcome = '';

  if (league === 'CBB') {
    // CBB results rows are carrying the spread from the AWAY-team perspective.
    // Example: away +7.5  <=> home -7.5
    const predEdge = marketSpread - predMargin;
    if (Math.abs(predEdge) < 1e-9) return 'Push';

    const pickAway = predEdge > 0;
    pickTeam = pickAway ? (teams.away || 'Away') : (teams.home || 'Home');
    pickLine = pickAway ? marketSpread : -marketSpread;

    if (Number.isFinite(actualMargin)) {
      const actualEdge = marketSpread - actualMargin;
      if (Math.abs(actualEdge) < 1e-9) {
        resolvedOutcome = 'Push';
      } else {
        const actualAwayCover = actualEdge > 0;
        resolvedOutcome = actualAwayCover === pickAway ? 'Win' : 'Loss';
      }
    }
  } else {
    // NBA/NHL results rows are carrying the spread from the HOME-team perspective.
    // Example: home -2.5  <=> away +2.5
    const predEdge = predMargin + marketSpread;
    if (Math.abs(predEdge) < 1e-9) return 'Push';

    const pickHome = predEdge > 0;
    pickTeam = pickHome ? (teams.home || 'Home') : (teams.away || 'Away');
    pickLine = pickHome ? marketSpread : -marketSpread;

    if (Number.isFinite(actualMargin)) {
      const actualEdge = actualMargin + marketSpread;
      if (Math.abs(actualEdge) < 1e-9) {
        resolvedOutcome = 'Push';
      } else {
        const actualHomeCover = actualEdge > 0;
        resolvedOutcome = actualHomeCover === pickHome ? 'Win' : 'Loss';
      }
    }
  }

  return `${pickTeam ? `${pickTeam} ` : ''}${fmtSigned(pickLine)}${resolvedOutcome ? ` ${resolvedOutcome}` : ''}`.trim();
}

function inferredTotalLabel(row) {
  const marketTotal = Number(row?.marketTotal);
  if (!Number.isFinite(marketTotal)) return '';

  const existingOutcome = resultOutcome(row?.totalResult || '');
  const predictedVals = parseResultScoreValues(row?.predicted || '');
  const actualVals = parseResultScoreValues(row?.actual || '');
  const predTotal = predictedVals.length === 2 ? predictedVals[0] + predictedVals[1] : NaN;
  const actualTotal = actualVals.length === 2 ? actualVals[0] + actualVals[1] : NaN;

  const side = Number.isFinite(predTotal)
    ? (predTotal > marketTotal ? 'O' : predTotal < marketTotal ? 'U' : '')
    : '';

  let outcome = existingOutcome;
  if (!outcome && Number.isFinite(actualTotal) && side) {
    outcome = actualTotal === marketTotal ? 'push' : (side === 'O' ? actualTotal > marketTotal : actualTotal < marketTotal) ? 'win' : 'loss';
  } else if (!outcome && Number.isFinite(actualTotal) && actualTotal === marketTotal) {
    outcome = 'push';
  }

  return `${side ? `${side} ` : ''}${fmt(marketTotal)}${outcome ? ` ${outcome[0].toUpperCase()}${outcome.slice(1)}` : ''}`.trim();
}

function formatSpreadResultCell(row) {
  const inferred = inferredSpreadLabel(row);
  const label = inferred || 'N/A';
  return `<span class="result-badge ${resultBadgeClass(label)}">${escapeHtml(label)}</span>`;
}

function formatTotalResultCell(row) {
  const existing = String(row?.totalResult || '').trim();
  const label = /\d/.test(existing) ? existing : inferredTotalLabel(row) || existing || 'N/A';
  return `<span class="result-badge ${resultBadgeClass(label)}">${escapeHtml(label)}</span>`;
}

function renderResults(results) {
  const body = byId('results-body');
  if (!body) return;
  body.innerHTML = (results || []).map(r => `
    <tr>
      <td>${escapeHtml(r.date || '')}</td>
      <td>${escapeHtml(r.league || '')}</td>
      <td>${escapeHtml(r.matchup || '')}</td>
      <td>${escapeHtml(r.predicted || r.pick || '')}</td>
      <td>${escapeHtml(r.actual || '')}</td>
      <td><span class="result-badge ${resultBadgeClass(r.mlResult || r.status)}">${escapeHtml(r.mlResult || r.status || 'N/A')}</span></td>
      <td>${formatSpreadResultCell(r)}</td>
      <td>${formatTotalResultCell(r)}</td>
    </tr>
  `).join('');
}

function summaryMetricParts(metric) {
  const wins = Number(metric?.wins || 0);
  const losses = Number(metric?.losses || 0);
  const pushes = Number(metric?.pushes || 0);
  const graded = Number(metric?.graded || 0);
  const winPct = metric?.winPct;
  return {
    record: pushes > 0 ? `${wins}-${losses}-${pushes}` : `${wins}-${losses}`,
    pctText: graded > 0 && winPct !== null && winPct !== undefined ? `${Number(winPct).toFixed(1)}%` : 'N/A'
  };
}

function sportSummaryBlockHtml(label, metrics, emphasized = false) {
  const classes = emphasized ? 'sport-summary sport-summary-overall' : 'sport-summary';
  return `
    <section class="${classes}">
      <div class="sport-summary-head"><h4>${escapeHtml(label)}</h4></div>
      <div class="sport-summary-metrics">
        ${['ML', 'Spread', 'Total'].map(metricName => {
          const parts = summaryMetricParts(metrics?.[metricName]);
          return `
            <div class="sport-metric-chip">
              <span>${escapeHtml(metricName)}</span>
              <strong>${escapeHtml(parts.record)}</strong>
              <small>${escapeHtml(parts.pctText)}</small>
            </div>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function periodTitle(key) {
  return ({ yesterday: 'Previous day', weekToDate: 'Current week', monthToDate: 'Current month', yearToDate: 'Current year' })[key] || key;
}

function renderResultsSummary(summary) {
  const root = byId('results-summary-grid');
  if (!root) return;
  const periods = summary?.periods || {};
  const order = ['yesterday', 'weekToDate', 'monthToDate', 'yearToDate'];
  const leagueOrder = ['NBA', 'NHL', 'CBB'];
  const cards = order.filter(key => periods[key]).map(key => {
    const period = periods[key];
    const byLeague = period.byLeague || {};
    const leagues = [...leagueOrder.filter(league => byLeague[league]), ...Object.keys(byLeague).filter(league => !leagueOrder.includes(league)).sort()];
    return `
      <article class="summary-card">
        <div class="summary-card-head">
          <div>
            <span class="summary-kicker">${escapeHtml(periodTitle(key))}</span>
            <h3>${escapeHtml(period.startDate === period.endDate ? period.endDate : `${period.startDate} to ${period.endDate}`)}</h3>
          </div>
          <span class="summary-rows">${escapeHtml(period.rowCount ?? 0)} games</span>
        </div>
        <div class="sport-breakdown-grid">
          ${sportSummaryBlockHtml('Overall', period.overall, true)}
          ${leagues.map(league => sportSummaryBlockHtml(league, byLeague[league])).join('')}
        </div>
      </article>
    `;
  });
  root.innerHTML = cards.length ? cards.join('') : '<div class="empty-state">No summary results available yet.</div>';
}

function propInsightCard(prop) {
  return `
    <article class="insight-card">
      <div class="insight-topline">
        <span class="tag">${escapeHtml(prop.stat || '')}</span>
        <span class="muted">${escapeHtml(prop.location || '')}</span>
      </div>
      <h4>${playerBadgeHtml(prop.player || '', prop)}</h4>
      <p class="muted">${escapeHtml(prop.team || '')} vs ${escapeHtml(prop.opp || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Line ${escapeHtml(fmt(prop.line, 1))}</span>
        <span class="mini-chip">Model ${escapeHtml(fmt(prop.pred_anchor ?? prop.mu_cons, 1))}</span>
        <span class="mini-chip">Prob ${escapeHtml(fmtPct(prop.prob_cons))}</span>
      </div>
      <p class="insight-copy">${escapeHtml(prop.boardDriver || prop.summary || '')}</p>
    </article>
  `;
}

function roleCard(prop) {
  const gap = Number(prop.trend_gap);
  return `
    <article class="insight-card compact-card">
      <div class="insight-topline">
        <span class="tag">${escapeHtml(prop.stat || '')}</span>
        <span class="muted">${Number.isFinite(gap) ? fmtSigned(gap, 1) : 'N/A'} vs avg</span>
      </div>
      <h4>${playerBadgeHtml(prop.player || '', prop)}</h4>
      <p class="muted">${escapeHtml(prop.team || '')} vs ${escapeHtml(prop.opp || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Line ${escapeHtml(fmt(prop.line, 1))}</span>
        <span class="mini-chip">Model ${escapeHtml(fmt(prop.pred_anchor, 1))}</span>
        <span class="mini-chip">Avg ${escapeHtml(fmt(prop.avg_anchor, 1))}</span>
      </div>
    </article>
  `;
}

function renderInsightGrid(rootId, items, role = false) {
  const root = byId(rootId);
  if (!root) return;
  const visibleItems = applyInjuryContextToList(items || [], new Map());
  if (!visibleItems.length) {
    root.innerHTML = '<div class="empty-state">No props available.</div>';
    return;
  }
  root.innerHTML = visibleItems.map(item => role ? roleCard(item) : propInsightCard(item)).join('');
}

function edgeBoardCard(title, items, kind) {
  if (!items.length) {
    return `<article class="insight-board"><h4>${escapeHtml(title)}</h4><div class="empty-state">No lined NBA games yet.</div></article>`;
  }

  const rows = items.map(item => {
    const edge = kind === 'spread' ? item.spreadEdge : item.totalEdge;
    const market = kind === 'spread' ? marketSpreadForDisplay(item) : Number(item.marketTotal);
    const model = kind === 'spread' ? modelSpreadForDisplay(item) : Number(item.modelTotal);

    return `
      <div class="edge-row">
        <div>
          <strong>${escapeHtml(`${item.awayTeam} @ ${item.homeTeam}`)}</strong>
          <span>${
            kind === 'spread'
              ? `Model ${escapeHtml(spreadTeamLabel(item, model))} vs market ${escapeHtml(spreadTeamLabel(item, market))}`
              : `Model ${escapeHtml(fmt(model))} vs market ${escapeHtml(fmt(market))}`
          }</span>
        </div>
        <strong>${escapeHtml(kind === 'spread' ? spreadEdgeText(item) : (Number.isFinite(edge) ? fmtSigned(edge) : 'N/A'))}</strong>
      </div>
    `;
  }).join('');

  return `<article class="insight-board"><h4>${escapeHtml(title)}</h4>${rows}</article>`;
}

function renderNbaGameEdges(games, meta) {
  const root = byId('nba-game-edges-grid');
  if (!root) return;

  const nba = (games || []).filter(g => g.league === 'NBA' && g.gameDate === meta.targetDate);
  const lined = nba.map(g => ({
    ...g,
    spreadEdge: spreadEdgeForDisplay(g),
    totalEdge: hasNumericValue(g.marketTotal)
      ? Number(g.modelTotal) - Number(g.marketTotal)
      : NaN
  }));

  const spreadTop = lined
    .filter(g => Number.isFinite(g.spreadEdge))
    .sort((a, b) => Math.abs(b.spreadEdge) - Math.abs(a.spreadEdge))
    .slice(0, 4);

  const totalTop = lined
    .filter(g => Number.isFinite(g.totalEdge))
    .sort((a, b) => Math.abs(b.totalEdge) - Math.abs(a.totalEdge))
    .slice(0, 4);

  root.innerHTML = [
    edgeBoardCard('Biggest spread gaps', spreadTop, 'spread'),
    edgeBoardCard('Biggest total gaps', totalTop, 'total')
  ].join('');
}

function renderHomeInsights(homeInsights, meta) {
  const day = homeInsights?.byDate?.[meta.targetDate];
  if (!day) return;
  renderInsightGrid('home-consensus-grid', day.consensusTop);
  renderInsightGrid('home-floor-grid', day.floorTop);
  renderInsightGrid('home-ceiling-grid', day.ceilingTop);
  renderInsightGrid('home-role-up-grid', day.roleUp, true);
  renderInsightGrid('home-role-down-grid', day.roleDown, true);
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
  setText('results-date-label', meta?.resultsDate || meta?.targetDate || '');
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
    const [meta, games, rawProps, rawPropsLab, results, resultsSummary, rawHomeInsights, injuries] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/nba_props_lab.json', null),
      loadJson('data/results.json', []),
      loadJson('data/results_summary.json', {}),
      loadJson('data/nba_home_insights.json', {}),
      loadJson('data/nba_injuries.json', {})
    ]);;
    const injuryLookup = buildInjuryLookup(injuries);
    const gameLookup = buildGameLookup(games);

    const propsSource = flattenPropsSource(rawPropsLab);
    const baseProps = propsSource.length ? propsSource : rawProps;

    const props = applyInjuryContextToList(baseProps, injuryLookup)
      .map(prop => enrichHomepageProp(prop, gameLookup));

    const hasDatedProps = props.some(p => propDateValue(p));

    const todayPool = hasDatedProps
      ? props.filter(p => propDateValue(p) === meta.targetDate)
      : props;

    const nextPool = hasDatedProps
      ? props.filter(p => propDateValue(p) === meta.nextDate)
      : [];

const todayProps = selectHomepageTopProps(todayPool, 12);
const nextProps = selectHomepageTopProps(nextPool, 10);
    const homeInsights = applyInjuryContextToHomeInsights(rawHomeInsights, injuryLookup);
    const todayGames = (games || []).filter(g => g.gameDate === meta.targetDate);
    const tomorrowGames = (games || []).filter(g => g.gameDate === meta.nextDate);
    fillHeader(meta, todayGames, tomorrowGames, todayProps);
    setupLeagueFilter(games, meta);
    renderProps(todayProps, 'props-body');
    renderProps(nextProps, 'props-next-body');
    renderNbaGameEdges(games, meta);
    renderHomeInsights(homeInsights, meta);
    renderResultsSummary(resultsSummary);
    renderResults(results);
  } catch (err) {
    console.error(err);
    if (root) root.innerHTML = `<div class="empty-state">Failed to load site data: ${escapeHtml(err.message || err)}</div>`;
  }
})();