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


async function loadText(path, fallback = '') {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${path}`);
    return await res.text();
  } catch (err) {
    return fallback;
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

function normalizeSearchText(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function uniqueSortedDates(rows) {
  return Array.from(new Set((rows || []).map(row => String(row?.date || '').trim()).filter(Boolean)))
    .sort((a, b) => b.localeCompare(a));
}

function dedupeRowsByKey(rows, keyFn) {
  const seen = new Map();
  (rows || []).forEach(row => {
    const key = keyFn(row);
    if (key) seen.set(key, row);
  });
  return Array.from(seen.values());
}

function populateDateSelect(select, dates, preferredDate = '', allLabel = 'All dates') {
  if (!select) return;
  const wanted = String(preferredDate || '').trim();
  const options = ['__ALL__', ...dates];
  select.innerHTML = options.map(value => {
    const label = value === '__ALL__' ? allLabel : value;
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }).join('');
  if (wanted && options.includes(wanted)) select.value = wanted;
  else select.value = dates[0] || '__ALL__';
}

function filterRowsByDate(rows, selectedDate) {
  const wanted = String(selectedDate || '').trim();
  if (!wanted || wanted === '__ALL__') return (rows || []).slice();
  return (rows || []).filter(row => String(row?.date || '') === wanted);
}

function currentDateLabel(selectedDate, fallbackLabel = 'All dates') {
  const wanted = String(selectedDate || '').trim();
  return wanted && wanted !== '__ALL__' ? wanted : fallbackLabel;
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
  const spread = Number(game?.awaySpread ?? game?.marketSpread);
  if (!Number.isFinite(spread)) return NaN;
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

function derivedSpreadProbabilityForDisplay(game, edge) {
  const league = String(game?.league || '').toUpperCase();
  const scale = league === 'NBA' ? 0.018 : league === 'NHL' ? 0.075 : 0.060;
  const cap = league === 'NBA' ? 0.67 : 0.68;
  return Math.min(cap, 0.50 + Math.abs(edge) * scale);
}

function derivedTotalProbabilityForDisplay(game, gap) {
  const league = String(game?.league || '').toUpperCase();
  const scale = league === 'NBA' ? 0.012 : league === 'NHL' ? 0.055 : 0.035;
  const cap = league === 'NBA' ? 0.70 : 0.67;
  return Math.min(cap, 0.52 + Math.abs(gap) * scale);
}

function signedLineText(team, line) {
  return `${team || 'Team'} ${fmtSigned(line, 1)}`;
}

function mlbMarketRunLineSignal(game) {
  const spread = marketSpreadForDisplay(game);
  if (!Number.isFinite(spread) || Math.abs(Math.abs(spread) - 1.5) > 0.11) return '';

  let candidates = [];
  if (spread > 0) {
    // Away +1.5 / home -1.5. Show whichever side the model makes more likely.
    candidates = [
      { label: `${game?.homeTeam || 'Home'} -1.5`, prob: coerceProbability(game?.homeMinus1p5Prob) },
      { label: `${game?.awayTeam || 'Away'} +1.5`, prob: coerceProbability(game?.awayPlus1p5Prob) },
    ];
  } else {
    // Away -1.5 / home +1.5. Show whichever side the model makes more likely.
    candidates = [
      { label: `${game?.awayTeam || 'Away'} -1.5`, prob: coerceProbability(game?.awayMinus1p5Prob) },
      { label: `${game?.homeTeam || 'Home'} +1.5`, prob: coerceProbability(game?.homePlus1p5Prob) },
    ];
  }

  const best = candidates
    .filter(item => Number.isFinite(item.prob))
    .sort((a, b) => b.prob - a.prob)[0];
  return best ? `${best.label} ${fmtPct(best.prob, 0)}` : '';
}

function formatAmericanOdds(value) {
  if (!hasNumericValue(value)) return '';
  const rounded = Math.round(Number(value));
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

function lineOddsText(value) {
  const odds = formatAmericanOdds(value);
  return odds ? ` (${odds})` : '';
}


function projectedScoreWinner(game) {
  const awayTeam = String(game?.awayTeam || 'Away').toUpperCase();
  const homeTeam = String(game?.homeTeam || 'Home').toUpperCase();
  const awayScore = Number(game?.modelAwayScore);
  const homeScore = Number(game?.modelHomeScore);
  if (!Number.isFinite(awayScore) || !Number.isFinite(homeScore) || Math.abs(awayScore - homeScore) < 0.0001) {
    return null;
  }
  return {
    team: awayScore > homeScore ? awayTeam : homeTeam,
    awayTeam,
    homeTeam,
    awayScore,
    homeScore,
  };
}

function moneylineLayerExplanation(game, mlPick = null) {
  const pick = mlPick || actualMoneylinePick(game);
  const scoreWinner = projectedScoreWinner(game);
  if (!pick?.team || !scoreWinner || pick.team === scoreWinner.team) return '';

  return `Calibrated ML probability favors ${pick.team}, while the average score projection leans ${scoreWinner.team} ${fmt(scoreWinner.homeScore, 1)}-${fmt(scoreWinner.awayScore, 1)}. The ML pick follows the calibrated chance of winning.`;
}

function actualMoneylinePick(game) {
  const awayTeam = String(game?.awayTeam || 'Away').toUpperCase();
  const homeTeam = String(game?.homeTeam || 'Home').toUpperCase();

  // Preferred unambiguous fields written by the corrected site-data builder.
  let team = String(game?.calibratedMoneylineTeam || '').toUpperCase();
  let prob = coerceProbability(game?.calibratedMoneylineWinProb);

  // Backward-compatible v86n derivation:
  // calibratedModelPickWinProb belongs to modelPickTeam. A probability below
  // 50% means calibration favors the opponent, so flip both team and probability.
  if (![awayTeam, homeTeam].includes(team) || !Number.isFinite(prob)) {
    const rawTeam = String(game?.modelPickTeam || '').toUpperCase();
    const rawProb = coerceProbability(game?.calibratedModelPickWinProb ?? game?.modelMoneylineProb);
    if ([awayTeam, homeTeam].includes(rawTeam) && Number.isFinite(rawProb)) {
      if (rawProb < 0.5) {
        team = rawTeam === awayTeam ? homeTeam : awayTeam;
        prob = 1 - rawProb;
      } else {
        team = rawTeam;
        prob = rawProb;
      }
    }
  }

  // Older-workbook fallback only when calibrated model-pick fields are absent.
  if (![awayTeam, homeTeam].includes(team) || !Number.isFinite(prob)) {
    const awayProb = coerceProbability(game?.awayWinProb);
    const homeProb = coerceProbability(game?.homeWinProb);
    if (Number.isFinite(awayProb) || Number.isFinite(homeProb)) {
      if ((Number.isFinite(awayProb) ? awayProb : -1) >= (Number.isFinite(homeProb) ? homeProb : -1)) {
        team = awayTeam;
        prob = awayProb;
      } else {
        team = homeTeam;
        prob = homeProb;
      }
    }
  }

  // Final display fallback for very old records.
  if (![awayTeam, homeTeam].includes(team)) {
    const scoreWinner = projectedScoreWinner(game);
    team = scoreWinner?.team || awayTeam;
  }

  const odds = team === awayTeam
    ? (game?.marketAwayML ?? game?.awayML ?? game?.awayMoneyline)
    : (game?.marketHomeML ?? game?.homeML ?? game?.homeMoneyline);
  return { team, prob, odds };
}

function exactRunLineProbability(game, side, line) {
  if (!Number.isFinite(line)) return NaN;
  const rounded = Math.round(line * 10) / 10;
  const isAway = side === 'away';
  if (Math.abs(rounded - 1.5) < 0.01) {
    return coerceProbability(isAway ? game?.awayPlus1p5Prob : game?.homePlus1p5Prob);
  }
  if (Math.abs(rounded + 1.5) < 0.01) {
    return coerceProbability(isAway ? game?.awayMinus1p5Prob : game?.homeMinus1p5Prob);
  }
  return NaN;
}

function actualSpreadPick(game) {
  const awaySpread = marketSpreadForDisplay(game);
  if (!Number.isFinite(awaySpread) || game?.spreadLinePairValid === false) return null;
  const homeSpread = hasNumericValue(game?.homeSpread) ? Number(game.homeSpread) : -awaySpread;

  const candidates = [
    {
      side: 'away',
      team: game?.awayTeam || 'Away',
      line: awaySpread,
      odds: game?.awaySpreadOdds,
      prob: exactRunLineProbability(game, 'away', awaySpread),
    },
    {
      side: 'home',
      team: game?.homeTeam || 'Home',
      line: homeSpread,
      odds: game?.homeSpreadOdds,
      prob: exactRunLineProbability(game, 'home', homeSpread),
    },
  ];

  // When exact probabilities exist for both current run-line sides, choose the
  // larger one. This keeps the displayed pick and probability on the same side.
  const exactBest = candidates
    .filter(item => Number.isFinite(item.prob))
    .sort((a, b) => b.prob - a.prob)[0];
  if (exactBest) return exactBest;

  const storedSide = String(game?.spreadPickSide || '').toUpperCase();
  const edge = spreadEdgeForDisplay(game);
  const side = storedSide === 'HOME_SPREAD' ? 'home'
    : storedSide === 'AWAY_SPREAD' ? 'away'
    : (Number.isFinite(edge) && edge > 0 ? 'home' : 'away');
  const fallback = candidates.find(item => item.side === side) || candidates[0];
  const selectedLine = Number(game?.selectedSpreadLine);
  const storedProb = coerceProbability(game?.spreadCoverProbEst ?? game?.modelSpreadPickProb);
  const storedMatchesLine = !Number.isFinite(selectedLine) || Math.abs(selectedLine - fallback.line) < 0.01;
  if (storedMatchesLine && Number.isFinite(storedProb)) fallback.prob = storedProb;
  if (!Number.isFinite(fallback.prob) && Number.isFinite(edge)) {
    fallback.prob = derivedSpreadProbabilityForDisplay(game, edge);
  }
  return fallback;
}

function actualTotalPick(game) {
  const line = Number(game?.marketTotal);
  if (!Number.isFinite(line)) return null;
  const overProb = coerceProbability(game?.marketOverProb);
  const underProb = coerceProbability(game?.marketUnderProb);

  // Exact probabilities for the current market line take precedence over a
  // stored side label. This prevents a side from being paired with the other
  // side's probability.
  let side = '';
  let prob = NaN;
  if (Number.isFinite(overProb) || Number.isFinite(underProb)) {
    if ((Number.isFinite(overProb) ? overProb : -1) >= (Number.isFinite(underProb) ? underProb : -1)) {
      side = 'OVER';
      prob = overProb;
    } else {
      side = 'UNDER';
      prob = underProb;
    }
  }

  if (!side) side = String(game?.totalPickSide || '').toUpperCase();
  if (!['OVER', 'UNDER'].includes(side)) {
    side = Number(game?.modelTotal) >= line ? 'OVER' : 'UNDER';
  }
  if (!Number.isFinite(prob)) {
    const storedProb = coerceProbability(game?.totalPickProbEst ?? game?.modelTotalPickProb);
    if (game?.totalRepriceRequired !== true && Number.isFinite(storedProb)) prob = storedProb;
  }
  if (!Number.isFinite(prob) && Number.isFinite(Number(game?.modelTotal))) {
    prob = derivedTotalProbabilityForDisplay(game, Number(game.modelTotal) - line);
  }
  const odds = side === 'OVER' ? game?.overOdds : game?.underOdds;
  return { side, line, odds, prob };
}

function spreadSignalText(game) {
  const pick = actualSpreadPick(game);
  if (!pick) return 'Line pending';
  const prob = Number.isFinite(pick.prob) ? ` · ${fmtPct(pick.prob, 0)}` : '';
  return `${pick.team} ${fmtSigned(pick.line, 1)}${lineOddsText(pick.odds)}${prob}`;
}

function totalSignalText(game) {
  const pick = actualTotalPick(game);
  if (!pick) return 'Line pending';
  const prob = Number.isFinite(pick.prob) ? ` · ${fmtPct(pick.prob, 0)}` : '';
  return `${pick.side === 'OVER' ? 'Over' : 'Under'} ${fmt(pick.line, 1)}${lineOddsText(pick.odds)}${prob}`;
}

function moneylineSignalText(game) {
  const pick = actualMoneylinePick(game);
  const prob = Number.isFinite(pick.prob) ? ` · ${fmtPct(pick.prob, 0)}` : '';
  return `${pick.team} ML${lineOddsText(pick.odds)}${prob}`;
}

function gameMarketSignalsHtml(game) {
  const mlPick = actualMoneylinePick(game);
  const mlExplanation = moneylineLayerExplanation(game, mlPick);
  return `
    <div class="game-signal-row" aria-label="Model picks at current scraped market lines">
      <span class="game-signal-chip"><b>Calibrated ML pick</b> ${escapeHtml(moneylineSignalText(game))}</span>
      <span class="game-signal-chip"><b>Spread model pick</b> ${escapeHtml(spreadSignalText(game))}</span>
      <span class="game-signal-chip"><b>Total model pick</b> ${escapeHtml(totalSignalText(game))}</span>
    </div>
    ${mlExplanation ? `<p class="game-layer-note">${escapeHtml(mlExplanation)}</p>` : ''}
  `;
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

function fmtAmerican(num) {
  if (!hasNumericValue(num)) return '—';
  const rounded = Math.round(Number(num));
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

function americanToDecimal(num) {
  if (!hasNumericValue(num) || Number(num) === 0) return NaN;
  const value = Number(num);
  return value > 0 ? 1 + value / 100 : 1 + 100 / Math.abs(value);
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
  const spread = Number(game?.awaySpread ?? game?.marketSpread);
  return Number.isFinite(spread) ? spread : NaN;
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
          ${gameMarketSignalsHtml(game)}
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

function normalizeAnalyzerStat(value) {
  const raw = String(value || '').trim().toUpperCase();
  const map = {
    STRIKEOUTS: 'K',
    STRIKEOUT: 'K',
    WALKS: 'BB',
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
    'EARNED RUNS': 'ER',
    EARNEDRUNS: 'ER'
  };
  return map[raw] || raw;
}

function propAnalyzerHref(prop, fallbackStat = '') {
  const params = new URLSearchParams();
  const league = String(prop?.league || 'NBA').toUpperCase();
  if (league) params.set('league', league);
  if (propDateValue(prop)) params.set('date', propDateValue(prop));
  if (prop?.playerId || prop?.PLAYER_ID) params.set('playerId', String(prop.playerId || prop.PLAYER_ID));
  else if (prop?.player || prop?.PLAYER_NAME) params.set('player', String(prop.player || prop.PLAYER_NAME));
  const stat = normalizeAnalyzerStat(prop?.stat || prop?.stat_display || fallbackStat);
  if (stat) params.set('stat', stat);
  if (prop?.line !== undefined && prop?.line !== null && prop?.line !== '') params.set('line', String(prop.line));
  return `props_analyzer.html?${params.toString()}`;
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

  body.innerHTML = visibleProps.map(p => {
    const canLink = ['NBA', 'MLB'].includes(String(p.league || '').toUpperCase());
    const playerHtml = canLink
      ? `<a class="table-link" href="${propAnalyzerHref(p)}">${playerBadgeHtml(p.player || '', p)}</a>`
      : playerBadgeHtml(p.player || '', p);
    return `
    <tr>
      <td>${escapeHtml(p.league || 'NBA')}</td>
      <td>${playerHtml}</td>
      <td>${escapeHtml(p.stat_display || p.stat || '')}</td>
      <td>${escapeHtml(hasNumericValue(p.line) ? fmt(p.line, 1) : (p.line ?? ''))}</td>
      <td>${escapeHtml(hasNumericValue(p.modelPrediction) ? fmt(p.modelPrediction, 1) : (p.modelPrediction ?? ''))}</td>
      <td>${escapeHtml(propProbabilityText(p))}</td>
      <td>${escapeHtml(p.confidence || propConfidenceLabel(p))}</td>
      <td>${escapeHtml(propMatchupText(p))}</td>
    </tr>
  `;}).join('');
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

  if (league === 'CBB' || league === 'NHL') {
    // CBB and NHL results rows are carrying the spread from the AWAY-team perspective.
    // Example: away +1.5  <=> home -1.5
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
  const existing = String(row?.spreadResult || '').trim();
  const label = existing && existing.toLowerCase() !== 'n/a'
    ? existing
    : (inferredSpreadLabel(row) || 'N/A');
  return `<span class="result-badge ${resultBadgeClass(label)}">${escapeHtml(label)}</span>`;
}

function formatTotalResultCell(row) {
  const existing = String(row?.totalResult || '').trim();
  const label = /\d/.test(existing) ? existing : inferredTotalLabel(row) || existing || 'N/A';
  return `<span class="result-badge ${resultBadgeClass(label)}">${escapeHtml(label)}</span>`;
}


function normalizeResultOutcome(value) {
  const s = String(value || '').trim().toLowerCase();
  if (!s) return 'N/A';
  if (s === 'win' || s.endsWith(' win') || s.includes(' win')) return 'Win';
  if (s === 'loss' || s.endsWith(' loss') || s.includes(' loss')) return 'Loss';
  if (s === 'push' || s.endsWith(' push') || s.includes(' push')) return 'Push';
  return 'N/A';
}

function resultBucket(rows, field) {
  let wins = 0, losses = 0, pushes = 0;
  (rows || []).forEach(row => {
    const label = normalizeResultOutcome(row?.[field]);
    if (label === 'Win') wins += 1;
    else if (label === 'Loss') losses += 1;
    else if (label === 'Push') pushes += 1;
  });
  const graded = wins + losses + pushes;
  return {
    wins, losses, pushes, graded,
    winPct: wins + losses ? Number(((wins / (wins + losses)) * 100).toFixed(1)) : null,
  };
}

function summarizeRows(rows) {
  return {
    ML: resultBucket(rows, 'mlResult'),
    CalML: resultBucket(rows, 'calibratedMlResult'),
    CalFlip: resultBucket(rows, 'calibratedFlipResult'),
    Spread: resultBucket(rows, 'spreadResult'),
    Total: resultBucket(rows, 'totalResult'),
  };
}

function recomputeResultsSummaryFromHistory(historyRows, templateSummary = {}) {
  const periods = templateSummary?.periods || {};
  const out = { ...(templateSummary || {}), periods: {} };
  Object.keys(periods).forEach(key => {
    const period = periods[key] || {};
    const start = String(period.startDate || '');
    const end = String(period.endDate || '');
    const subset = (historyRows || []).filter(row => {
      const d = String(row?.date || '');
      return d && (!start || d >= start) && (!end || d <= end);
    });
    const byLeague = {};
    Array.from(new Set(subset.map(r => String(r?.league || '')).filter(Boolean))).sort().forEach(league => {
      byLeague[league] = summarizeRows(subset.filter(r => String(r?.league || '') === league));
    });
    out.periods[key] = {
      ...period,
      overall: summarizeRows(subset),
      byLeague,
      rowCount: subset.length,
    };
  });
  return out;
}

function filterResultsForLaunch(rows, launchDate) {
  const launch = String(launchDate || '').trim();
  return (rows || []).filter(row => {
    if (String(row?.league || '').toUpperCase() !== 'MLB') return true;
    return launch && String(row?.date || '') >= launch;
  });
}

function sortResultsRows(rows) {
  return (rows || []).slice().sort((a, b) => {
    const aKey = `${String(a?.date || '')}|${String(a?.league || '')}|${String(a?.matchup || '')}`;
    const bKey = `${String(b?.date || '')}|${String(b?.league || '')}|${String(b?.matchup || '')}`;
    return bKey.localeCompare(aKey);
  });
}

function selectDisplayResultsRows(resultsRows, historyRows, preferredDate = '') {
  const rowsForDate = (rows, date) => (rows || []).filter(row => String(row?.date || '') === String(date || ''));
  const withPreferredDate = String(preferredDate || '').trim();

  if (withPreferredDate) {
    const historySlice = rowsForDate(historyRows, withPreferredDate);
    if (historySlice.length) return sortResultsRows(historySlice);

    const resultsSlice = rowsForDate(resultsRows, withPreferredDate);
    if (resultsSlice.length) return sortResultsRows(resultsSlice);
  }

  const historyDates = Array.from(new Set((historyRows || []).map(row => String(row?.date || '')).filter(Boolean))).sort();
  const latestHistoryDate = historyDates.length ? historyDates[historyDates.length - 1] : '';
  if (latestHistoryDate) {
    const historySlice = rowsForDate(historyRows, latestHistoryDate);
    if (historySlice.length) return sortResultsRows(historySlice);
  }

  return sortResultsRows(resultsRows || []);
}


function calibratedResultDisplay(row) {
  const label = String(row?.calibratedMlResult || '').trim();
  return label && label.toLowerCase() !== 'pending' ? label : 'N/A';
}

function formatCalibratedResultCell(row) {
  const label = calibratedResultDisplay(row);
  const note = row?.calibratedMlDiscrepancy
    ? '<small class="result-cell-note">Score flip</small>'
    : '';
  return `
    <div class="result-cell-stack">
      <span class="result-badge ${resultBadgeClass(label)}">${escapeHtml(label)}</span>
      ${note}
    </div>
  `;
}


function renderResults(results) {
  const body = byId('results-body');
  if (!body) return;
  const items = Array.isArray(results) ? results : [];
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="9">No game results match this view yet.</td></tr>';
    return;
  }
  body.innerHTML = items.map(r => `
    <tr>
      <td>${escapeHtml(r.date || '')}</td>
      <td>${escapeHtml(r.league || '')}</td>
      <td>${escapeHtml(r.matchup || '')}</td>
      <td>${escapeHtml(r.predicted || '')}</td>
      <td>${escapeHtml(r.actual || '')}</td>
      <td><span class="result-badge ${resultBadgeClass(r.mlResult)}">${escapeHtml(r.mlResult || '')}</span></td>
      <td>${formatCalibratedResultCell(r)}</td>
      <td><span class="result-badge ${resultBadgeClass(r.spreadResult)}">${escapeHtml(r.spreadResult || '')}</span></td>
      <td><span class="result-badge ${resultBadgeClass(r.totalResult)}">${escapeHtml(r.totalResult || '')}</span></td>
    </tr>
  `).join('');
}

function resultRowSearchText(row) {
  return normalizeSearchText([
    row?.date,
    row?.league,
    row?.matchup,
    row?.predicted,
    row?.actual,
    row?.mlResult,
    row?.calibratedMlResult,
    row?.calibratedMlPickTeam,
    row?.calibratedMlDiscrepancy ? 'score flip calibrated flip' : '',
    row?.spreadResult,
    row?.totalResult,
  ].join(' '));
}

function renderResultsViewSummary(rows, context = {}) {
  const root = byId('results-view-summary-grid');
  if (!root) return;
  const dateLabel = context?.dateLabel || 'All dates';
  const query = String(context?.query || '').trim();
  if (!rows.length) {
    root.innerHTML = `<div class="empty-state">No game results match ${escapeHtml(dateLabel)}${query ? ` with search "${escapeHtml(query)}"` : ''}.</div>`;
    return;
  }

  const byLeague = {};
  Array.from(new Set(rows.map(r => String(r?.league || '')).filter(Boolean))).sort().forEach(league => {
    byLeague[league] = summarizeRows(rows.filter(r => String(r?.league || '') === league));
  });
  const leagueOrder = ['NBA', 'MLB', 'NHL', 'CBB'];
  const leagues = [...leagueOrder.filter(league => byLeague[league]), ...Object.keys(byLeague).filter(league => !leagueOrder.includes(league)).sort()];
  const searchLine = query ? `Search: ${escapeHtml(query)}` : 'Search: none';

  root.innerHTML = `
    <article class="summary-card">
      <div class="summary-card-head">
        <div>
          <span class="summary-kicker">Current game-results view</span>
          <h3>${escapeHtml(dateLabel)}</h3>
        </div>
        <span class="summary-rows">${escapeHtml(String(rows.length))} games</span>
      </div>
      <p class="muted summary-inline-note">${searchLine}</p>
      <div class="sport-breakdown-grid">
        ${sportSummaryBlockHtml('Overall', summarizeRows(rows), true)}
        ${leagues.map(league => sportSummaryBlockHtml(league, byLeague[league])).join('')}
      </div>
    </article>
  `;
}

function setupResultsExplorer(resultsRows, historyRows, preferredDate = '') {
  const dateSelect = byId('results-date-filter');
  const searchInput = byId('results-search-input');
  const metaNode = byId('results-view-meta');
  const sourceRows = dedupeRowsByKey([...(historyRows || []), ...(resultsRows || [])], row => `${row?.date || ''}|${row?.league || ''}|${row?.matchup || ''}`);
  const sortedRows = sortResultsRows(sourceRows);
  const dates = uniqueSortedDates(sortedRows);
  populateDateSelect(dateSelect, dates, preferredDate, 'All graded dates');

  const rerender = () => {
    const selectedDate = dateSelect?.value || dates[0] || '__ALL__';
    const query = normalizeSearchText(searchInput?.value || '');
    const dateLabel = currentDateLabel(selectedDate, 'All graded dates');
    const visibleRows = sortResultsRows(
      filterRowsByDate(sortedRows, selectedDate).filter(row => !query || resultRowSearchText(row).includes(query))
    );

    setText('results-date-label', dateLabel);
    if (metaNode) {
      metaNode.textContent = `${visibleRows.length} game${visibleRows.length === 1 ? '' : 's'} shown`;
    }
    renderResultsViewSummary(visibleRows, { dateLabel, query: searchInput?.value || '' });
    renderResults(visibleRows);
  };

  if (dateSelect && !dateSelect.dataset.bound) {
    dateSelect.addEventListener('change', rerender);
    dateSelect.dataset.bound = '1';
  }
  if (searchInput && !searchInput.dataset.bound) {
    searchInput.addEventListener('input', rerender);
    searchInput.dataset.bound = '1';
  }
  rerender();
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
  const metricDefinitions = [
    ['ML', 'ML'],
    ['CalML', 'Cal ML'],
    ['CalFlip', 'Cal flips'],
    ['Spread', 'Spread'],
    ['Total', 'Total'],
  ];
  const visibleMetrics = metricDefinitions.filter(([key]) => {
    if (key === 'ML' || key === 'Spread' || key === 'Total') return true;
    return Number(metrics?.[key]?.graded || 0) > 0;
  });
  return `
    <section class="${classes}">
      <div class="sport-summary-head"><h4>${escapeHtml(label)}</h4></div>
      <div class="sport-summary-metrics">
        ${visibleMetrics.map(([metricName, metricLabel]) => {
          const parts = summaryMetricParts(metrics?.[metricName]);
          return `
            <div class="sport-metric-chip">
              <span>${escapeHtml(metricLabel)}</span>
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


function propStatDisplay(stat) {
  const key = String(stat || '').toUpperCase().trim();
  const map = { H: 'Hits', TB: 'Total Bases', '2B': 'Doubles', HR: 'Home Runs', K: 'Strikeouts', BB: 'Walks', SB: 'Steals', RBI: 'RBI', R: 'Runs', HRR: 'HR+R+RBI', OUTS: 'Outs', IP: 'IP', HA: 'Hits Allowed', ER: 'Earned Runs' };
  return map[key] || key || 'Other';
}

function renderMlbPropResultsSummary(summary, pending) {
  const root = byId('mlb-prop-results-summary-grid');
  if (!root) return;
  const overall = summary?.overall || null;
  const latestSettledDate = summary?.latestSettledDate || '';
  const pendingCount = Array.isArray(pending) ? pending.length : 0;
  const byStat = summary?.byStat || {};
  const orderedStats = ['H','TB','HR','HRR','K','BB','RBI','R','SB','OUTS','IP','HA','ER'];
  const stats = [
    ...orderedStats.filter(stat => byStat[stat]),
    ...Object.keys(byStat).filter(stat => !orderedStats.includes(stat)).sort((a, b) => (Number(byStat[b]?.settled || 0) - Number(byStat[a]?.settled || 0)) || String(a).localeCompare(String(b)))
  ].slice(0, 6);

  if (!overall || !Number(overall.settled || 0)) {
    root.innerHTML = `<div class="empty-state">No settled MLB prop results yet.${pendingCount ? ` ${pendingCount} props are still pending.` : ''}</div>`;
    const label = byId('mlb-prop-results-date-label');
    if (label) label.textContent = latestSettledDate || '—';
    const pendingNode = byId('mlb-prop-results-pending-count');
    if (pendingNode) pendingNode.textContent = String(pendingCount || 0);
    return;
  }

  const overallParts = summaryMetricParts({
    wins: overall.wins,
    losses: overall.losses,
    pushes: overall.pushes,
    graded: overall.decisionCount,
    winPct: overall.winRate != null ? Number(overall.winRate) * 100 : null
  });

  const label = byId('mlb-prop-results-date-label');
  if (label) label.textContent = latestSettledDate || '—';
  const pendingNode = byId('mlb-prop-results-pending-count');
  if (pendingNode) pendingNode.textContent = String(pendingCount || 0);

  root.innerHTML = `
    <article class="summary-card">
      <div class="summary-card-head">
        <div>
          <span class="summary-kicker">MLB props</span>
          <h3>${escapeHtml(latestSettledDate || 'Settled history')}</h3>
        </div>
        <span class="summary-rows">${escapeHtml(String(overall.settled || 0))} settled</span>
      </div>
      <div class="sport-breakdown-grid">
        <section class="sport-summary sport-summary-overall">
          <div class="sport-summary-head"><h4>Overall</h4></div>
          <div class="sport-summary-metrics">
            <div class="sport-metric-chip"><span>Record</span><strong>${escapeHtml(overallParts.record)}</strong><small>${escapeHtml(overallParts.pctText)}</small></div>
            <div class="sport-metric-chip"><span>Pending</span><strong>${escapeHtml(String(pendingCount || 0))}</strong><small>Open props</small></div>
            <div class="sport-metric-chip"><span>Settled</span><strong>${escapeHtml(String(overall.settled || 0))}</strong><small>Tracked props</small></div>
          </div>
        </section>
        ${stats.map(stat => {
          const row = byStat[stat] || {};
          const parts = summaryMetricParts({
            wins: row.wins,
            losses: row.losses,
            pushes: row.pushes,
            graded: row.decisionCount,
            winPct: row.winRate != null ? Number(row.winRate) * 100 : null
          });
          return `
            <section class="sport-summary">
              <div class="sport-summary-head"><h4>${escapeHtml(propStatDisplay(stat))}</h4></div>
              <div class="sport-summary-metrics">
                <div class="sport-metric-chip"><span>Record</span><strong>${escapeHtml(parts.record)}</strong><small>${escapeHtml(parts.pctText)}</small></div>
                <div class="sport-metric-chip"><span>Settled</span><strong>${escapeHtml(String(row.settled || 0))}</strong><small>Rows</small></div>
                <div class="sport-metric-chip"><span>Decisions</span><strong>${escapeHtml(String(row.decisionCount || 0))}</strong><small>Win/Loss only</small></div>
              </div>
            </section>
          `;
        }).join('')}
      </div>
    </article>
  `;
}

function renderMlbPropResults(rows) {
  const body = byId('mlb-prop-results-body');
  if (!body) return;
  const items = Array.isArray(rows)
    ? rows.slice().sort((a, b) => `${b.date || ''}|${b.player || ''}|${b.stat || ''}`.localeCompare(`${a.date || ''}|${a.player || ''}|${a.stat || ''}`))
    : [];
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="8">No settled MLB prop results match this view yet.</td></tr>';
    return;
  }
  body.innerHTML = items.map(r => `
    <tr>
      <td>${escapeHtml(r.date || '')}</td>
      <td>${escapeHtml(r.player || '')}</td>
      <td>${escapeHtml(r.matchup || '')}</td>
      <td>${escapeHtml(propStatDisplay(r.stat))}</td>
      <td>${escapeHtml(fmt(r.line, 1))}</td>
      <td>${escapeHtml(fmt(r.model, 2))}</td>
      <td>${escapeHtml(fmt(r.actual, 1))}</td>
      <td><span class="result-badge ${resultBadgeClass(r.result)}">${escapeHtml(r.result || 'Pending')}</span></td>
    </tr>
  `).join('');
}

function summarizePropResultRows(rows) {
  let wins = 0, losses = 0, pushes = 0;
  (rows || []).forEach(row => {
    const label = normalizeResultOutcome(row?.result);
    if (label === 'Win') wins += 1;
    else if (label === 'Loss') losses += 1;
    else if (label === 'Push') pushes += 1;
  });
  const settled = (rows || []).length;
  const decisionCount = wins + losses + pushes;
  return {
    wins, losses, pushes, settled, decisionCount,
    winRate: wins + losses ? Number((wins / (wins + losses)).toFixed(4)) : null,
  };
}

function isMlbTrackedHomeBoardResultRow(row) {
  const stat = String(row?.stat || '').toUpperCase().trim();
  const board = String(row?.board || '').toLowerCase();
  const line = Number(row?.line);

  // The homepage "Best two-plus total bases" board is strictly a 1.5 TB board.
  // Results should track that same board, not higher alternate TB lines that may
  // exist in the analyzer payload.
  if (stat === 'TB' || board.includes('two-plus total bases')) {
    return Number.isFinite(line) && Math.abs(line - 1.5) < 1e-9;
  }

  return true;
}

function filterMlbTrackedHomeBoardRows(rows) {
  return Array.isArray(rows) ? rows.filter(isMlbTrackedHomeBoardResultRow) : [];
}

function buildMlbPropSummaryFromRows(rows, fallback = {}) {
  const settledRows = filterMlbTrackedHomeBoardRows(rows).filter(row => {
    const label = normalizeResultOutcome(row?.result);
    return label === 'Win' || label === 'Loss' || label === 'Push';
  });

  const byStat = {};
  Array.from(new Set(settledRows.map(row => String(row?.stat || '').toUpperCase().trim()).filter(Boolean))).forEach(stat => {
    byStat[stat] = summarizePropResultRows(settledRows.filter(row => String(row?.stat || '').toUpperCase().trim() === stat));
  });

  const dates = settledRows.map(row => String(row?.date || '').trim()).filter(Boolean).sort();
  return {
    ...fallback,
    latestSettledDate: dates.length ? dates[dates.length - 1] : (fallback?.latestSettledDate || ''),
    overall: summarizePropResultRows(settledRows),
    byStat,
  };
}

function propResultSearchText(row) {
  return normalizeSearchText([
    row?.date,
    row?.player,
    row?.team,
    row?.opp,
    row?.matchup,
    row?.stat,
    propStatDisplay(row?.stat),
    row?.board,
    row?.note,
    row?.result,
    row?.role,
  ].join(' '));
}

function renderMlbPropResultsViewSummary(rows, context = {}) {
  const root = byId('mlb-prop-results-view-summary-grid');
  if (!root) return;
  const dateLabel = context?.dateLabel || 'All settled dates';
  const query = String(context?.query || '').trim();
  const statLabel = String(context?.statLabel || '').trim();

  if (!rows.length) {
    const parts = [dateLabel];
    if (query) parts.push(`search "${query}"`);
    if (statLabel) parts.push(statLabel);
    root.innerHTML = `<div class="empty-state">No settled MLB props match ${escapeHtml(parts.join(' • '))}.</div>`;
    return;
  }

  const overall = summarizePropResultRows(rows);
  const overallParts = summaryMetricParts({
    wins: overall.wins,
    losses: overall.losses,
    pushes: overall.pushes,
    graded: overall.decisionCount,
    winPct: overall.winRate != null ? Number(overall.winRate) * 100 : null,
  });

  const byStat = {};
  Array.from(new Set(rows.map(r => String(r?.stat || '').toUpperCase()).filter(Boolean))).sort().forEach(stat => {
    byStat[stat] = summarizePropResultRows(rows.filter(r => String(r?.stat || '').toUpperCase() === stat));
  });

  const orderedStats = ['H','TB','HR','HRR','K','BB','RBI','R','SB','OUTS','IP','HA','ER'];
  const stats = [...orderedStats.filter(stat => byStat[stat]), ...Object.keys(byStat).filter(stat => !orderedStats.includes(stat)).sort()].slice(0, 6);

  const notes = [];
  if (query) notes.push(`Search: ${escapeHtml(query)}`);
  if (statLabel) notes.push(`Stat: ${escapeHtml(statLabel)}`);
  if (!notes.length) notes.push('Search: none');

  root.innerHTML = `
    <article class="summary-card">
      <div class="summary-card-head">
        <div>
          <span class="summary-kicker">Current MLB prop-results view</span>
          <h3>${escapeHtml(dateLabel)}</h3>
        </div>
        <span class="summary-rows">${escapeHtml(String(rows.length))} props</span>
      </div>
      <p class="muted summary-inline-note">${notes.join(' • ')}</p>
      <div class="sport-breakdown-grid">
        <section class="sport-summary sport-summary-overall">
          <div class="sport-summary-head"><h4>Overall</h4></div>
          <div class="sport-summary-metrics">
            <div class="sport-metric-chip"><span>Record</span><strong>${escapeHtml(overallParts.record)}</strong><small>${escapeHtml(overallParts.pctText)}</small></div>
            <div class="sport-metric-chip"><span>Settled</span><strong>${escapeHtml(String(overall.settled || 0))}</strong><small>Rows</small></div>
            <div class="sport-metric-chip"><span>Decisions</span><strong>${escapeHtml(String(overall.decisionCount || 0))}</strong><small>Win/Loss only</small></div>
          </div>
        </section>
        ${stats.map(stat => {
          const row = byStat[stat] || {};
          const parts = summaryMetricParts({
            wins: row.wins,
            losses: row.losses,
            pushes: row.pushes,
            graded: row.decisionCount,
            winPct: row.winRate != null ? Number(row.winRate) * 100 : null,
          });
          return `
            <section class="sport-summary">
              <div class="sport-summary-head"><h4>${escapeHtml(propStatDisplay(stat))}</h4></div>
              <div class="sport-summary-metrics">
                <div class="sport-metric-chip"><span>Record</span><strong>${escapeHtml(parts.record)}</strong><small>${escapeHtml(parts.pctText)}</small></div>
                <div class="sport-metric-chip"><span>Settled</span><strong>${escapeHtml(String(row.settled || 0))}</strong><small>Rows</small></div>
                <div class="sport-metric-chip"><span>Decisions</span><strong>${escapeHtml(String(row.decisionCount || 0))}</strong><small>Win/Loss only</small></div>
              </div>
            </section>
          `;
        }).join('')}
      </div>
    </article>
  `;
}

function setupMlbPropResultsExplorer(rows, summary, pending) {
  const dateSelect = byId('mlb-prop-results-date-filter');
  const statSelect = byId('mlb-prop-results-stat-filter');
  const searchInput = byId('mlb-prop-results-search-input');
  const metaNode = byId('mlb-prop-results-view-meta');

  const sortedRows = Array.isArray(rows)
    ? rows.slice().sort((a, b) => `${b.date || ''}|${b.player || ''}|${b.stat || ''}`.localeCompare(`${a.date || ''}|${a.player || ''}|${a.stat || ''}`))
    : [];

  const dates = uniqueSortedDates(sortedRows);
  const preferredDate = summary?.latestSettledDate || dates[0] || '';
  populateDateSelect(dateSelect, dates, preferredDate, 'All settled dates');

  if (statSelect) {
    const stats = Array.from(new Set(sortedRows.map(row => String(row?.stat || '').toUpperCase()).filter(Boolean)))
      .sort((a, b) => propStatDisplay(a).localeCompare(propStatDisplay(b)));
    statSelect.innerHTML = [
      '<option value="">All stats</option>',
      ...stats.map(stat => `<option value="${escapeHtml(stat)}">${escapeHtml(propStatDisplay(stat))}</option>`)
    ].join('');
  }

  const rerender = () => {
    const selectedDate = dateSelect?.value || preferredDate || '__ALL__';
    const selectedStat = String(statSelect?.value || '').toUpperCase().trim();
    const query = normalizeSearchText(searchInput?.value || '');
    const dateLabel = currentDateLabel(selectedDate, 'All settled dates');

    const visibleRows = filterRowsByDate(sortedRows, selectedDate).filter(row => {
      if (selectedStat && String(row?.stat || '').toUpperCase() !== selectedStat) return false;
      if (query && !propResultSearchText(row).includes(query)) return false;
      return true;
    });

    const statLabel = selectedStat ? propStatDisplay(selectedStat) : '';
    setText('mlb-prop-results-date-label', dateLabel);

    const pendingNode = byId('mlb-prop-results-pending-count');
    if (pendingNode) pendingNode.textContent = String(Array.isArray(pending) ? pending.length : 0);

    if (metaNode) metaNode.textContent = `${visibleRows.length} prop${visibleRows.length === 1 ? '' : 's'} shown`;

    renderMlbPropResultsViewSummary(visibleRows, {
      dateLabel,
      query: searchInput?.value || '',
      statLabel
    });
    renderMlbPropResults(visibleRows);
  };

  if (dateSelect && !dateSelect.dataset.bound) {
    dateSelect.addEventListener('change', rerender);
    dateSelect.dataset.bound = '1';
  }
  if (statSelect && !statSelect.dataset.bound) {
    statSelect.addEventListener('change', rerender);
    statSelect.dataset.bound = '1';
  }
  if (searchInput && !searchInput.dataset.bound) {
    searchInput.addEventListener('input', rerender);
    searchInput.dataset.bound = '1';
  }

  rerender();
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


function chooseMlbBoardRows(entries, { date, stat, playerType = '', limit = 10, uniqueByPlayer = false, line = null }) {
  const pool = (entries || []).filter(e => String(e?.gameDate || '') === String(date || '') && String(e?.stat || '').toUpperCase() === String(stat).toUpperCase());
  const typed = playerType ? pool.filter(e => String(e?.playerType || '').toLowerCase() === String(playerType).toLowerCase()) : pool;
  let base = typed.length ? typed : pool;
  if (line !== null && line !== undefined) {
    const wantedLine = Number(line);
    base = base.filter(e => {
      const rowLine = Number(e?.line);
      return Number.isFinite(rowLine) && Number.isFinite(wantedLine) && Math.abs(rowLine - wantedLine) < 1e-9;
    });
  }
  if (String(playerType).toLowerCase() === 'pitcher') {
    base = base.filter(e => !/(^|\b)(tbd|to be determined|probable starter tbd)(\b|$)/i.test(String(e?.player || '')));
  }

  const sorted = base.slice().sort((a, b) => {
    if (String(playerType).toLowerCase() === 'pitcher') {
      const predDiff = (Number(b?.pred_anchor ?? b?.mu_cons) || 0) - (Number(a?.pred_anchor ?? a?.mu_cons) || 0);
      if (predDiff) return predDiff;
      const avgDiff = (Number(b?.avg_anchor) || 0) - (Number(a?.avg_anchor) || 0);
      if (avgDiff) return avgDiff;
      return (Number(b?.prob_cons) || -1) - (Number(a?.prob_cons) || -1);
    }
    const probDiff = (Number(b?.prob_cons) || -1) - (Number(a?.prob_cons) || -1);
    if (probDiff) return probDiff;
    return (Number(b?.pred_anchor ?? b?.mu_cons) || 0) - (Number(a?.pred_anchor ?? a?.mu_cons) || 0);
  });

  if (uniqueByPlayer) {
    const grouped = new Map();
    sorted.forEach(item => {
      const key = `${item.playerId || item.player}|${item.stat}`;
      if (grouped.has(key)) return;
      grouped.set(key, item);
    });
    return Array.from(grouped.values()).slice(0, limit);
  }

  const deduped = [];
  const seen = new Set();
  sorted.forEach(item => {
    const key = `${item.playerId || item.player}|${item.stat}|${item.line}`;
    if (seen.has(key)) return;
    seen.add(key);
    deduped.push(item);
  });
  return deduped.slice(0, limit);
}


function mlbBoardDisplayLine(row) {
  const stat = String(row?.stat || '').toUpperCase();
  if (hasNumericValue(row?.line)) return fmt(row.line, 1);
  if (stat === 'H') return '0.5';
  if (stat === 'TB') return '1.5';
  return '—';
}

function mlbBoardTable(title, rows, { showLine = true, showAvg = false, primaryMetric = 'line', primaryLabel = 'Line' } = {}) {
  if (!rows.length) {
    return `<article class="insight-board"><h4>${escapeHtml(title)}</h4><div class="empty-state">No entries available yet.</div></article>`;
  }
  const body = rows.map(row => {
    const primaryValue = primaryMetric === 'average'
      ? (hasNumericValue(row.avg_anchor) ? fmt(row.avg_anchor, 1) : '—')
      : mlbBoardDisplayLine(row);
    return `
    <tr>
      <td><a class="table-link" href="${propAnalyzerHref({ ...row, league: 'MLB', player: row.player, playerId: row.playerId, line: row.line, stat: row.stat })}">${escapeHtml(row.player || '')}</a></td>
      ${showLine ? `<td>${escapeHtml(primaryValue)}</td>` : ''}
      <td>${escapeHtml(hasNumericValue(row.pred_anchor ?? row.mu_cons) ? fmt(row.pred_anchor ?? row.mu_cons, 1) : '—')}</td>
      ${showAvg ? `<td>${escapeHtml(hasNumericValue(row.avg_anchor) ? fmt(row.avg_anchor, 1) : '—')}</td>` : ''}
      <td>${escapeHtml(Number.isFinite(Number(row.prob_cons)) ? `${(Number(row.prob_cons) * 100).toFixed(1)}%` : '—')}</td>
      <td>${escapeHtml(propMatchupText(row))}</td>
    </tr>
  `;
  }).join('');
  return `
    <article class="insight-board">
      <h4>${escapeHtml(title)}</h4>
      <div class="table-wrap compact-table-wrap">
        <table class="compact-table">
          <thead><tr><th>Player</th>${showLine ? `<th>${escapeHtml(primaryLabel)}</th>` : ''}<th>Model</th>${showAvg ? '<th>Avg.</th>' : ''}<th>Prob.</th><th>Matchup</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </article>
  `;
}

function renderMlbHomeBoards(mlbAnalyzer, meta) {
  const root = byId('mlb-home-props-grid');
  if (!root) return;
  const entries = mlbAnalyzer?.entries || [];
  root.innerHTML = [
    mlbBoardTable('Best hits', chooseMlbBoardRows(entries, { date: meta?.targetDate, stat: 'H', playerType: 'batter', limit: 10 })),
    mlbBoardTable('Best two-plus total bases', chooseMlbBoardRows(entries, { date: meta?.targetDate, stat: 'TB', playerType: 'batter', line: 1.5, limit: 10 })),
    mlbBoardTable('Top pitcher strikeouts', chooseMlbBoardRows(entries, { date: meta?.targetDate, stat: 'K', playerType: 'pitcher', limit: 10, uniqueByPlayer: true }), { showLine: true, showAvg: false, primaryMetric: 'average', primaryLabel: 'Avg.' })
  ].join('');
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


function trackingToneClass(tracking) {
  const tone = String(tracking?.tone || tracking?.trend || '').toLowerCase();
  if (tone.includes('hot')) return 'trend-hot';
  if (tone.includes('cold')) return 'trend-cold';
  return 'trend-neutral';
}

function trackingLabel(tracking) {
  if (!tracking) return 'No tracking yet';
  return tracking.label || `${tracking.record || '0-0'} ${tracking.pctText || ''}`.trim() || 'No tracking yet';
}

function trackingTrendText(tracking) {
  if (!tracking) return 'Limited';
  return tracking.trend || 'Limited';
}

function cardProbabilityHtml(card) {
  const prob = coerceProbability(card?.probability);
  if (!Number.isFinite(prob)) {
    if (hasNumericValue(card?.model)) return `<span class="pick-prob-label">Model</span><strong>${escapeHtml(fmt(card.model, 1))}</strong>`;
    return `<span class="pick-prob-label">Signal</span><strong>Model</strong>`;
  }
  return `<span class="pick-prob-label">Probability</span><strong>${escapeHtml(fmtPct(prob, 0))}</strong>`;
}

function isTopPitcherProp(card) {
  const stat = String(card?.stat || '').toUpperCase();
  const category = String(card?.category || card?.title || '').toLowerCase();
  return stat === 'HA' || stat === 'ER' || (stat === 'K' && (category.includes('pitcher') || category.includes('sp')));
}

function topPickPrimaryBaseline(card) {
  if (!isTopPitcherProp(card)) return null;
  return hasNumericValue(card?.average) ? `Avg ${fmt(card.average, 1)}` : null;
}

function topPickCardHtml(card) {
  const tracking = card?.tracking || {};
  const toneClass = trackingToneClass(tracking);
  const matchup = card?.matchup || [card?.team, card?.opp ? `vs ${card.opp}` : ''].filter(Boolean).join(' ');
  const detailBits = [];
  const baseline = topPickPrimaryBaseline(card);
  if (baseline) detailBits.push(baseline);
  else if (hasNumericValue(card?.line)) detailBits.push(`Line ${fmt(card.line, 1)}`);
  if (hasNumericValue(card?.model)) detailBits.push(`Model ${fmt(card.model, 1)}`);
  if (!baseline && hasNumericValue(card?.average)) detailBits.push(`Avg ${fmt(card.average, 1)}`);
  if (hasNumericValue(card?.modelTotal)) detailBits.push(`Model total ${fmt(card.modelTotal, 1)}`);
  const detailHtml = detailBits.length
    ? `<div class="mini-chip-row">${detailBits.map(bit => `<span class="mini-chip">${escapeHtml(bit)}</span>`).join('')}</div>`
    : '';
  const href = card?.href || '#';
  return `
    <article class="top-pick-card ${toneClass}">
      <div class="top-pick-head">
        <span class="tag">${escapeHtml(card?.league || '')}</span>
        <span class="trend-pill ${toneClass}">${escapeHtml(trackingTrendText(tracking))}</span>
      </div>
      <p class="top-pick-category">${escapeHtml(card?.category || card?.title || 'Model pick')}</p>
      <h3>${escapeHtml(card?.pick || card?.title || 'Model signal')}</h3>
      <p class="muted top-pick-matchup">${escapeHtml(matchup || 'Today')}</p>
      <div class="top-pick-metric">${cardProbabilityHtml(card)}</div>
      ${detailHtml}
      <div class="tracking-strip ${toneClass}">
        <span>${escapeHtml(tracking?.scope || 'Recent category')}</span>
        <strong>${escapeHtml(trackingLabel(tracking))}</strong>
      </div>
      <p class="insight-copy">${escapeHtml(card?.reason || 'Model signal from today’s slate.')}</p>
      <a class="button-link button-link-subtle top-pick-link" href="${escapeHtml(href)}">Analyze</a>
    </article>
  `;
}

function renderTopPickPulse(homeTopPicks) {
  const root = byId('home-top-picks-pulse');
  if (!root) return;
  const tracking = homeTopPicks?.trackingSummary || {};
  const propTrackers = Object.entries(tracking?.props || {}).map(([key, value]) => ({ key, ...value }));
  const gameTrackers = Object.entries(tracking?.games || {}).map(([key, value]) => ({ key, ...value }));
  const rows = [...propTrackers, ...gameTrackers]
    .filter(row => row && (row.sample || row.record))
    .slice(0, 7);
  if (!rows.length) {
    root.innerHTML = '<div class="empty-state">No recent top-pick tracking available yet.</div>';
    return;
  }
  root.innerHTML = rows.map(row => `
    <article class="pulse-card ${trackingToneClass(row)}">
      <span>${escapeHtml(row.scope || row.key || 'Category')}</span>
      <strong>${escapeHtml(row.record || '0-0')}</strong>
      <small>${escapeHtml(row.pctText || '—')} • ${escapeHtml(row.trend || 'Limited')}</small>
    </article>
  `).join('');
}

function renderHomeTopPicks(homeTopPicks) {
  const root = byId('home-top-picks-grid');
  if (!root) return;
  const cards = Array.isArray(homeTopPicks?.topCards) ? homeTopPicks.topCards : [];
  setText('hero-top-pick-count', String(cards.length));
  if (!cards.length) {
    root.innerHTML = '<div class="empty-state">No featured top picks are available yet. Run tools/build_home_top_picks_json.py after today’s data is generated.</div>';
    return;
  }
  root.innerHTML = cards.map(topPickCardHtml).join('');
}

function marketValueCardHtml(card) {
  const status = String(card?.valueStatus || 'WATCH').toUpperCase();
  const edge = coerceProbability(card?.probabilityEdge);
  const roi = coerceProbability(card?.expectedRoi);
  const prob = coerceProbability(card?.probability);
  const marketProb = coerceProbability(card?.marketProbability);
  const age = hasNumericValue(card?.marketAgeHours) ? `${fmt(card.marketAgeHours, 1)}h old` : 'age unavailable';
  const book = card?.bookmakerTitle || card?.bookmakerKey || 'Sportsbook';
  return `
    <article class="top-pick-card ${status === 'VALUE' ? 'trend-hot' : ''}">
      <div class="top-pick-head">
        <span class="tag">${escapeHtml(status)}</span>
        <span class="trend-pill">${escapeHtml(book)}</span>
      </div>
      <p class="top-pick-category">${escapeHtml(card?.category || 'Player prop')}</p>
      <h3>${escapeHtml(card?.pick || '')}</h3>
      <p class="muted top-pick-matchup">${escapeHtml(card?.matchup || '')}</p>
      <div class="mini-chip-row">
        <span class="mini-chip">Price ${escapeHtml(fmtAmerican(card?.selectedOdds))}</span>
        <span class="mini-chip">Model ${escapeHtml(Number.isFinite(prob) ? fmtPct(prob, 0) : '—')}</span>
        <span class="mini-chip">Market ${escapeHtml(Number.isFinite(marketProb) ? fmtPct(marketProb, 0) : '—')}</span>
        <span class="mini-chip">Edge ${escapeHtml(Number.isFinite(edge) ? fmtPct(edge, 1) : '—')}</span>
        <span class="mini-chip">ROI ${escapeHtml(Number.isFinite(roi) ? fmtPct(roi, 1) : '—')}</span>
      </div>
      <p class="insight-copy">${escapeHtml(card?.reason || '')}</p>
      <div class="tracking-strip"><span>${escapeHtml(age)}</span><strong>${escapeHtml(card?.probabilitySource || '')}</strong></div>
      <a class="button-link button-link-subtle top-pick-link" href="${escapeHtml(card?.href || '#')}">Analyze</a>
    </article>
  `;
}

function renderHomeMarketValues(homeTopPicks) {
  const section = byId('home-market-value-section');
  const root = byId('home-market-value-grid');
  if (!section || !root) return;
  const cards = Array.isArray(homeTopPicks?.bestValueProps) ? homeTopPicks.bestValueProps : [];
  if (!cards.length) {
    section.hidden = true;
    root.innerHTML = '';
    return;
  }
  section.hidden = false;
  root.innerHTML = cards.slice(0, 8).map(marketValueCardHtml).join('');
}

function compactPickRowHtml(card, options = {}) {
  const prob = coerceProbability(card?.probability);
  const probText = Number.isFinite(prob) ? fmtPct(prob, 0) : (hasNumericValue(card?.model) ? `Model ${fmt(card.model, 1)}` : 'Model');
  const metricValue = options.metric === 'average'
    ? (hasNumericValue(card?.average) ? fmt(card.average, 1) : '—')
    : (card?.line !== null && card?.line !== undefined && card?.line !== '' ? fmt(card.line, 1) : '—');
  return `
    <tr>
      <td><a class="table-link" href="${escapeHtml(card?.href || '#')}">${escapeHtml(card?.player || card?.pick || '')}</a></td>
      <td>${escapeHtml(metricValue)}</td>
      <td>${escapeHtml(hasNumericValue(card?.model) ? fmt(card.model, 1) : '—')}</td>
      ${options.showSeparateAverage ? `<td>${escapeHtml(hasNumericValue(card?.average) ? fmt(card.average, 1) : '—')}</td>` : ''}
      <td>${escapeHtml(probText)}</td>
      <td>${escapeHtml(card?.matchup || '')}</td>
    </tr>
  `;
}

function mlbBoardSnapshotTable(title, rows, options = {}) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const metric = options.metric || 'line';
  const metricLabel = options.metricLabel || (metric === 'average' ? 'Avg.' : 'Line');
  const showSeparateAverage = Boolean(options.showSeparateAverage);
  if (!safeRows.length) {
    return `<article class="insight-board"><h4>${escapeHtml(title)}</h4><div class="empty-state">No entries available yet.</div></article>`;
  }
  return `
    <article class="insight-board">
      <h4>${escapeHtml(title)}</h4>
      <div class="table-wrap compact-table-wrap">
        <table class="compact-table">
          <thead><tr><th>Player</th><th>${escapeHtml(metricLabel)}</th><th>Model</th>${showSeparateAverage ? '<th>Avg.</th>' : ''}<th>Prob.</th><th>Matchup</th></tr></thead>
          <tbody>${safeRows.map(card => compactPickRowHtml(card, { metric, showSeparateAverage })).join('')}</tbody>
        </table>
      </div>
    </article>
  `;
}

function renderMlbHomeBoardsSnapshot(homeTopPicks) {
  const root = byId('mlb-home-props-grid');
  const tabs = byId('mlb-board-tabs');
  if (!root) return;
  const boards = homeTopPicks?.mlbBoards || {};
  const config = [
    { key: 'hits', label: 'Hits', options: { metric: 'line', metricLabel: 'Line', showSeparateAverage: true } },
    { key: 'hrr', label: 'HRR', options: { metric: 'line', metricLabel: 'Line', showSeparateAverage: true } },
    { key: 'totalBases', label: '1.5+ Total Bases', options: { metric: 'line', metricLabel: 'Line', showSeparateAverage: true } },
    { key: 'pitcherKs', label: 'Pitcher Ks', options: { metric: 'average', metricLabel: 'Avg.' } },
    { key: 'pitcherHA', label: 'Pitcher Hits Allowed', options: { metric: 'average', metricLabel: 'Avg.' } },
    { key: 'pitcherERLow', label: 'Lowest SP ER', options: { metric: 'average', metricLabel: 'Avg.' } },
    { key: 'pitcherERHigh', label: 'Highest SP ER', options: { metric: 'average', metricLabel: 'Avg.' } }
  ];
  const available = config.filter(item => Array.isArray(boards[item.key]) && boards[item.key].length);
  if (!available.length) {
    root.innerHTML = '<div class="empty-state">No MLB quick boards available yet.</div>';
    if (tabs) tabs.innerHTML = '';
    return;
  }

  const renderBoard = key => {
    const item = config.find(entry => entry.key === key) || available[0];
    root.innerHTML = mlbBoardSnapshotTable(item.label, boards[item.key] || [], item.options || {});
    if (tabs) {
      [...tabs.querySelectorAll('button')].forEach(btn => btn.classList.toggle('active', btn.dataset.board === item.key));
    }
  };

  if (tabs && !tabs.dataset.bound) {
    tabs.innerHTML = available.map(item => `<button type="button" data-board="${escapeHtml(item.key)}">${escapeHtml(item.label)}</button>`).join('');
    tabs.addEventListener('click', event => {
      const button = event.target.closest('button[data-board]');
      if (!button) return;
      renderBoard(button.dataset.board);
    });
    tabs.dataset.bound = '1';
  }
  renderBoard(available[0].key);
}

function quickGameCardHtml(item) {
  const prob = coerceProbability(item?.probability);
  return `
    <article class="quick-game-card">
      <div class="quick-game-top">
        <span class="tag">${escapeHtml(item?.league || '')}</span>
        <strong>${escapeHtml(Number.isFinite(prob) ? fmtPct(prob, 0) : 'Model')}</strong>
      </div>
      <h3>${escapeHtml(item?.pick || 'Game signal')}</h3>
      <p class="muted">${escapeHtml(item?.matchup || '')}</p>
      <p>${escapeHtml(item?.modelScore || item?.reason || '')}</p>
      <a class="table-link" href="${escapeHtml(item?.href || '#')}">Open game detail</a>
    </article>
  `;
}

function strongestGameBoardSignal(game) {
  const matchup = `${game?.awayTeam || ''} @ ${game?.homeTeam || ''}`.trim();
  const href = `game.html?id=${encodeURIComponent(game?.id || '')}`;
  const candidates = [];

  const ml = actualMoneylinePick(game);
  if (Number.isFinite(ml?.prob) && hasNumericValue(ml?.odds)) {
    candidates.push({
      id: game?.id,
      league: game?.league || 'MLB',
      matchup,
      pick: `ML · ${ml.team}${lineOddsText(ml.odds)}`,
      probability: ml.prob,
      modelScore: moneylineLayerExplanation(game, ml) || `Calibrated win probability ${fmtPct(ml.prob, 0)}`,
      href,
      market: 'ML',
      priced: true,
    });
  }

  const spread = actualSpreadPick(game);
  if (spread && Number.isFinite(spread.prob) && hasNumericValue(spread.odds)) {
    candidates.push({
      id: game?.id,
      league: game?.league || 'MLB',
      matchup,
      pick: `SPREAD · ${spread.team} ${fmtSigned(spread.line, 1)}${lineOddsText(spread.odds)}`,
      probability: spread.prob,
      modelScore: `Cover probability ${fmtPct(spread.prob, 0)}`,
      href,
      market: 'SPREAD',
      priced: true,
    });
  }

  const total = actualTotalPick(game);
  if (total && Number.isFinite(total.prob) && hasNumericValue(total.odds)) {
    const sideText = total.side === 'OVER' ? 'Over' : 'Under';
    candidates.push({
      id: game?.id,
      league: game?.league || 'MLB',
      matchup,
      pick: `TOTAL · ${sideText} ${fmt(total.line, 1)}${lineOddsText(total.odds)}`,
      probability: total.prob,
      modelScore: `Model total ${fmt(game?.modelTotal, 1)} · ${sideText} probability ${fmtPct(total.prob, 0)}`,
      href,
      market: 'TOTAL',
      priced: true,
    });
  }

  if (String(game?.league || '').toUpperCase() === 'MLB') {
    const nrfi = coerceProbability(game?.nrfiProb);
    const yrfi = coerceProbability(game?.yrfiProb);
    if (Number.isFinite(nrfi) || Number.isFinite(yrfi)) {
      const isNrfi = (Number.isFinite(nrfi) ? nrfi : -1) >= (Number.isFinite(yrfi) ? yrfi : -1);
      const probability = isNrfi ? nrfi : yrfi;
      candidates.push({
        id: game?.id,
        league: game?.league || 'MLB',
        matchup,
        pick: isNrfi ? 'NRFI' : 'YRFI',
        probability,
        modelScore: `NRFI ${Number.isFinite(nrfi) ? fmtPct(nrfi, 0) : '—'} / YRFI ${Number.isFinite(yrfi) ? fmtPct(yrfi, 0) : '—'}`,
        href,
        market: isNrfi ? 'NRFI' : 'YRFI',
        priced: false,
      });
    }
  }

  return candidates
    .filter(item => Number.isFinite(item.probability))
    .sort((a, b) => (b.probability - a.probability) || (Number(b.priced) - Number(a.priced)))[0] || null;
}

function renderHighConfidenceGames(homeTopPicks, fallbackGames, meta) {
  const root = byId('high-confidence-games-grid');
  if (!root) return;

  // Recalculate from the current games payload so the board always compares
  // ML, spread, total, and NRFI/YRFI on the same slate and current scraped lines.
  const today = (fallbackGames || [])
    .filter(game => game.gameDate === meta?.targetDate)
    .map(strongestGameBoardSignal)
    .filter(Boolean)
    .sort((a, b) => (b.probability - a.probability) || (Number(b.priced) - Number(a.priced)))
    .slice(0, 8);

  if (today.length) {
    root.innerHTML = today.map(quickGameCardHtml).join('');
    return;
  }

  const cards = Array.isArray(homeTopPicks?.highConfidenceGames) ? homeTopPicks.highConfidenceGames : [];
  root.innerHTML = cards.length
    ? cards.slice(0, 8).map(quickGameCardHtml).join('')
    : '<div class="empty-state">No current game signals available yet.</div>';
}

function parlayItemKey(item) {
  return [item?.gameId || item?.id || item?.matchup || '', item?.player || '', item?.stat || item?.pick || ''].join('|');
}

function parlayGameKey(item) {
  return String(item?.gameId || item?.matchup || item?.id || '').trim();
}

function parlayStat(item) {
  return String(item?.stat || item?.category || item?.type || '').toUpperCase();
}

function parlayPickDirection(item) {
  const text = String(item?.pick || item?.title || '').toLowerCase();
  if (/\bover\b/.test(text)) return 'OVER';
  if (/\bunder\b/.test(text)) return 'UNDER';
  if (/\bnrfi\b/.test(text)) return 'NRFI';
  if (/\byrfi\b/.test(text)) return 'YRFI';
  return '';
}

function parlayPickTeam(item) {
  const text = String(item?.pick || '').trim();
  const match = text.match(/^([A-Z]{2,4})\b/);
  return match ? match[1] : '';
}

function parlayIsProp(item) {
  return Boolean(normalizeLookupToken(item?.player || ''));
}

function parlayIsPlayable(item) {
  if (!item) return false;
  if (item.playable === false || item.actionable === false) return false;
  if (item.priceRequired === true || item.repriceRequired === true) return false;
  if (item.linePairValid === false || item.marketPairValid === false) return false;
  if (item.calibrationRejected === true) return false;

  if (String(item.type || '').toLowerCase() === 'game') {
    // Game candidates must be explicitly approved by the v86n market router.
    return item.playable === true || item.actionable === true;
  }

  if (!parlayIsProp(item)) return false;
  const stat = parlayStat(item);
  // Pitcher boards currently compare projections to averages, not real book lines.
  // Keep those projections visible in Featured Picks, but never treat them as parlay legs.
  if (!['H', 'HRR', 'TB'].includes(stat)) return false;
  return hasNumericValue(item?.line);
}

function parlayTrackingRate(item) {
  const rate = coerceProbability(item?.tracking?.winRate);
  const sample = Number(item?.tracking?.sample || 0);
  return Number.isFinite(rate) && sample > 0 ? { rate, sample } : null;
}

function parlayRecentRate(item) {
  const values = [item?.recentHitRate10, item?.recentHitRate25]
    .map(coerceProbability)
    .filter(Number.isFinite);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function parlayEdgeStrength(item) {
  if (!hasNumericValue(item?.model) || !hasNumericValue(item?.line)) return 0;
  const stat = parlayStat(item);
  const scale = stat === 'H' ? 0.45 : stat === 'TB' ? 1.25 : stat === 'HRR' ? 1.35 : 1;
  return Math.max(-1, Math.min(1, (Number(item.model) - Number(item.line)) / scale));
}

function parlayEffectiveProbability(item) {
  const modelProbability = coerceProbability(item?.probability);
  if (!Number.isFinite(modelProbability)) return NaN;

  let effective = Math.max(0.50, Math.min(0.84, modelProbability));
  const tracking = parlayTrackingRate(item);
  if (tracking) {
    const trackingWeight = Math.min(0.22, tracking.sample / 150);
    const shrunkTracking = 0.50 + (tracking.rate - 0.50) * Math.min(1, tracking.sample / 30);
    effective = effective * (1 - trackingWeight) + shrunkTracking * trackingWeight;
    if (tracking.sample >= 12 && tracking.rate < 0.46) effective -= 0.025;
    if (tracking.sample >= 12 && tracking.rate >= 0.62) effective += 0.012;
  }

  const recent = parlayRecentRate(item);
  if (Number.isFinite(recent)) effective = effective * 0.90 + recent * 0.10;
  effective += parlayEdgeStrength(item) * 0.012;
  return Math.max(0.50, Math.min(0.82, effective));
}

function parlayQualityScore(item, style) {
  const effective = parlayEffectiveProbability(item);
  if (!Number.isFinite(effective)) return -Infinity;
  const tracking = parlayTrackingRate(item);
  const trackingLift = tracking ? Math.max(-0.035, Math.min(0.035, (tracking.rate - 0.50) * 0.14)) : 0;
  const edgeLift = parlayEdgeStrength(item) * (style === 'upside' ? 0.035 : 0.02);
  const typeLift = parlayStat(item) === 'H' && style === 'safe' ? 0.018 : 0;
  return effective + trackingLift + edgeLift + typeLift;
}

function parlayConflict(a, b) {
  const playerA = normalizeLookupToken(a?.player || '');
  const playerB = normalizeLookupToken(b?.player || '');
  if (playerA && playerA === playerB) return true;

  const gameA = parlayGameKey(a);
  const gameB = parlayGameKey(b);
  if (!gameA || gameA !== gameB) return false;

  const statA = parlayStat(a);
  const statB = parlayStat(b);
  const directionA = parlayPickDirection(a);
  const directionB = parlayPickDirection(b);

  // Never stack two versions of the same game market.
  if (statA === statB && ['ML', 'SPREAD', 'TOTAL', 'NRFI', 'YRFI'].includes(statA)) return true;
  if ((directionA === 'NRFI' && directionB === 'YRFI') || (directionA === 'YRFI' && directionB === 'NRFI')) return true;
  if ((directionA === 'OVER' && directionB === 'UNDER') || (directionA === 'UNDER' && directionB === 'OVER')) return true;

  // Moneyline + spread on the same team is duplicate exposure, not diversification.
  if (new Set([statA, statB]).has('ML') && new Set([statA, statB]).has('SPREAD')) {
    const teamA = parlayPickTeam(a);
    const teamB = parlayPickTeam(b);
    if (!teamA || !teamB || teamA === teamB) return true;
  }

  const batterStats = new Set(['H', 'HRR', 'TB']);
  if ((directionA === 'NRFI' && batterStats.has(statB)) || (directionB === 'NRFI' && batterStats.has(statA))) return true;
  if ((directionA === 'UNDER' && (directionB === 'YRFI' || batterStats.has(statB))) ||
      (directionB === 'UNDER' && (directionA === 'YRFI' || batterStats.has(statA)))) return true;
  if ((directionA === 'OVER' && directionB === 'NRFI') || (directionB === 'OVER' && directionA === 'NRFI')) return true;

  return false;
}

function parlayBaseThreshold(style) {
  if (style === 'safe') return 0.62;
  if (style === 'upside') return 0.52;
  return 0.56;
}

function parlayCandidateWeight(item, style, minProb) {
  const effective = parlayEffectiveProbability(item);
  const quality = parlayQualityScore(item, style);
  if (!Number.isFinite(effective) || !Number.isFinite(quality)) return 0;
  const lift = Math.max(0.01, quality - minProb + 0.035);
  const exponent = style === 'safe' ? 3.4 : style === 'upside' ? 1.7 : 2.5;
  return Math.pow(lift, exponent);
}

function weightedPick(items, style, minProb) {
  if (!items.length) return null;
  const ranked = items.slice().sort((a, b) => parlayQualityScore(b, style) - parlayQualityScore(a, style));
  const shortlist = ranked.slice(0, Math.min(10, ranked.length));
  const weights = shortlist.map(item => parlayCandidateWeight(item, style, minProb));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (!Number.isFinite(total) || total <= 0) return shortlist[0];
  let draw = Math.random() * total;
  for (let i = 0; i < shortlist.length; i += 1) {
    draw -= weights[i];
    if (draw <= 0) return shortlist[i];
  }
  return shortlist[shortlist.length - 1];
}

function filterParlayCandidates(pool, { sport, bookmaker, style, minProb }) {
  let candidates = (pool || [])
    .map(item => ({
      ...item,
      probability: coerceProbability(item?.probability),
      effectiveProbability: parlayEffectiveProbability(item),
    }))
    .filter(item => parlayIsPlayable(item) && Number.isFinite(item.probability) && Number.isFinite(item.effectiveProbability));

  if (sport && sport !== 'ALL') candidates = candidates.filter(item => String(item.league || '').toUpperCase() === sport);
  if (bookmaker) candidates = candidates.filter(item => String(item.bookmakerKey || '').toLowerCase() === String(bookmaker).toLowerCase());

  candidates = candidates.filter(item => {
    const tracking = parlayTrackingRate(item);
    if (item.effectiveProbability < minProb) return false;
    if (style === 'safe' && tracking && tracking.sample >= 10 && tracking.rate < 0.50) return false;
    if (style === 'balanced' && tracking && tracking.sample >= 12 && tracking.rate < 0.44 && item.probability < 0.72) return false;
    return true;
  });

  candidates.sort((a, b) => parlayQualityScore(b, style) - parlayQualityScore(a, style));
  return candidates;
}

function sameGameParlayCandidates(candidates, count, style) {
  const groups = new Map();
  candidates.forEach(item => {
    const key = parlayGameKey(item);
    if (!key) return;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  const eligible = Array.from(groups.values())
    .filter(group => group.length >= Math.min(count, 2));
  if (!eligible.length) return [];
  eligible.sort((a, b) => {
    const scoreA = a.slice(0, count).reduce((sum, item) => sum + parlayQualityScore(item, style), 0);
    const scoreB = b.slice(0, count).reduce((sum, item) => sum + parlayQualityScore(item, style), 0);
    return scoreB - scoreA;
  });
  return eligible[0] || [];
}

function selectParlayLegs(pool, { count, sport, bookmaker, style, correlationMode }) {
  const baseMinProb = parlayBaseThreshold(style);
  const thresholds = [baseMinProb, Math.max(0.52, baseMinProb - 0.03), Math.max(0.50, baseMinProb - 0.06)];
  let bestSelection = [];

  for (const minProb of thresholds) {
    const candidates = filterParlayCandidates(pool, { sport, bookmaker, style, minProb });
    const workingPool = correlationMode === 'same-game' ? sameGameParlayCandidates(candidates, count, style) : candidates;
    if (!workingPool.length) continue;

    for (let attempt = 0; attempt < 60; attempt += 1) {
      const selected = [];
      const seen = new Set();
      const usedGames = new Map();
      const usedCategories = new Map();
      let available = workingPool.slice();
      const categoryCap = correlationMode === 'same-game' ? 2 : (count <= 2 ? 1 : count <= 4 ? 2 : 3);

      while (available.length && selected.length < count) {
        const valid = available.filter(item => {
          const key = parlayItemKey(item);
          if (seen.has(key)) return false;
          if (selected.some(existing => parlayConflict(existing, item))) return false;
          const gameKey = parlayGameKey(item);
          const category = parlayStat(item);
          if (correlationMode === 'avoid' && gameKey && usedGames.has(gameKey)) return false;
          if (correlationMode === 'allow' && gameKey && (usedGames.get(gameKey) || 0) >= 2) return false;
          if (category && (usedCategories.get(category) || 0) >= categoryCap) return false;
          return true;
        });
        if (!valid.length) break;
        const choice = weightedPick(valid, style, minProb);
        if (!choice) break;
        selected.push(choice);
        seen.add(parlayItemKey(choice));
        const gameKey = parlayGameKey(choice);
        if (gameKey) usedGames.set(gameKey, (usedGames.get(gameKey) || 0) + 1);
        const category = parlayStat(choice);
        if (category) usedCategories.set(category, (usedCategories.get(category) || 0) + 1);
        available = available.filter(item => parlayItemKey(item) !== parlayItemKey(choice));
      }

      if (selected.length > bestSelection.length ||
          (selected.length === bestSelection.length && selected.reduce((s, x) => s + parlayQualityScore(x, style), 0) > bestSelection.reduce((s, x) => s + parlayQualityScore(x, style), 0))) {
        bestSelection = selected;
      }
      if (selected.length >= count) return selected;
    }
  }

  return bestSelection;
}

function adjustedParlayProbability(legs, correlationMode) {
  if (!legs.length) return NaN;
  const raw = legs.reduce((acc, leg) => acc * parlayEffectiveProbability(leg), 1);
  const gameCounts = new Map();
  const categoryCounts = new Map();
  legs.forEach(leg => {
    const key = parlayGameKey(leg);
    if (key) gameCounts.set(key, (gameCounts.get(key) || 0) + 1);
    const category = parlayStat(leg);
    if (category) categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
  });
  let penalty = correlationMode === 'same-game' ? 0.84 : 0.98;
  gameCounts.forEach(count => {
    if (count > 1) penalty *= Math.pow(0.88, count - 1);
  });
  categoryCounts.forEach(count => {
    if (count > 1) penalty *= Math.pow(0.96, count - 1);
  });
  return raw * penalty;
}

function parlayDecimalPayout(legs) {
  if (!legs.length) return NaN;
  let payout = 1;
  for (const leg of legs) {
    const decimal = americanToDecimal(leg?.selectedOdds);
    if (!Number.isFinite(decimal)) return NaN;
    payout *= decimal;
  }
  return payout;
}

function bookmakerLabel(key, pool) {
  const row = (pool || []).find(item => String(item?.bookmakerKey || '').toLowerCase() === String(key || '').toLowerCase());
  return row?.bookmakerTitle || key || 'Available book';
}

function renderParlayBuilder(homeTopPicks) {
  const output = byId('parlay-builder-output');
  if (!output) return;
  const pool = Array.isArray(homeTopPicks?.parlayPool) ? homeTopPicks.parlayPool : [];
  const controls = {
    count: byId('parlay-leg-count'),
    sport: byId('parlay-sport-filter'),
    bookmaker: byId('parlay-bookmaker-filter'),
    style: byId('parlay-risk-style'),
    correlationMode: byId('parlay-correlation-mode'),
    reroll: byId('parlay-reroll'),
  };

  const books = Array.from(new Set((homeTopPicks?.bookmakers || pool.map(item => item?.bookmakerKey))
    .map(value => String(value || '').toLowerCase()).filter(Boolean)));
  if (controls.bookmaker) {
    const current = controls.bookmaker.value;
    if (books.length) {
      controls.bookmaker.innerHTML = books.map((key, index) => `<option value="${escapeHtml(key)}"${key === current || (!current && index === 0) ? ' selected' : ''}>${escapeHtml(bookmakerLabel(key, pool))}</option>`).join('');
    } else {
      controls.bookmaker.innerHTML = '<option value="">Model watch card</option>';
    }
  }

  const rerender = () => {
    const count = Number(controls.count?.value || 3);
    const sport = controls.sport?.value || 'MLB';
    const bookmaker = controls.bookmaker?.value || '';
    const style = controls.style?.value || 'balanced';
    const correlationMode = controls.correlationMode?.value || 'avoid';
    const minProb = parlayBaseThreshold(style);
    const matchingCandidates = filterParlayCandidates(pool, { sport, bookmaker, style, minProb });
    const legs = selectParlayLegs(pool, { count, sport, bookmaker, style, correlationMode });
    if (!legs.length) {
      output.innerHTML = '<div class="empty-state">No playable MLB candidates meet those filters. Try a broader style or fewer legs.</div>';
      return;
    }
    const estimate = adjustedParlayProbability(legs, correlationMode);
    const decimalPayout = parlayDecimalPayout(legs);
    output.innerHTML = `
      <article class="parlay-card">
        <div class="parlay-card-head">
          <div>
            <p class="eyebrow">Generated MLB card</p>
            <h3>${legs.length}-pick ${style === 'safe' ? 'safer' : style === 'upside' ? 'upside' : 'balanced'} card</h3>
            <p class="muted">${escapeHtml(String(matchingCandidates.length))} playable ${escapeHtml(bookmaker ? bookmakerLabel(bookmaker, pool) : 'model')} candidates passed the price, value, category-form, and conflict filters.</p>
          </div>
          <div class="parlay-prob"><span>Model joint estimate</span><strong>${escapeHtml(Number.isFinite(estimate) ? fmtPct(estimate, 1) : 'N/A')}</strong><small>${escapeHtml(Number.isFinite(decimalPayout) ? `${decimalPayout.toFixed(2)}x listed payout` : 'watch-card only')}</small></div>
        </div>
        <ol class="parlay-leg-list">
          ${legs.map(leg => {
            const adjusted = parlayEffectiveProbability(leg);
            const raw = coerceProbability(leg.probability);
            return `
            <li>
              <div>
                <strong>${escapeHtml(leg.pick || leg.title || '')}</strong>
                <span>${escapeHtml([leg.league, leg.matchup || leg.category, leg.bookmakerTitle || '', hasNumericValue(leg.selectedOdds) ? fmtAmerican(leg.selectedOdds) : '', leg?.tracking?.record ? `Category ${leg.tracking.record}` : ''].filter(Boolean).join(' • '))}</span>
              </div>
              <a href="${escapeHtml(leg.href || '#')}">${escapeHtml(fmtPct(adjusted, 0))}<small> adj.${Number.isFinite(raw) ? ` / ${fmtPct(raw, 0)} model` : ''}</small></a>
            </li>`;
          }).join('')}
        </ol>
        <p class="muted">With market data, all legs use the same selected sportsbook and its exact prices. The builder excludes average-only projections, stale or blocked markets, duplicate player exposure, and contradictory same-game legs.</p>
      </article>
    `;
  };

  Object.values(controls).forEach(control => {
    if (control && !control.dataset.bound) {
      control.addEventListener(control.tagName === 'BUTTON' ? 'click' : 'change', rerender);
      control.dataset.bound = '1';
    }
  });
  rerender();
}


function applySiteFeatures(config) {
  const flags = config?.features || {};
  document.querySelectorAll('[data-site-feature]').forEach(node => {
    const key = node.getAttribute('data-site-feature');
    node.hidden = flags[key] !== true;
  });
}

function activeLeagueSet(config, meta) {
  const values = config?.activeLeagues || meta?.leagues || ['MLB'];
  return new Set(values.map(v => String(v || '').toUpperCase()).filter(Boolean));
}

function fillHeader(meta, todayGames, tomorrowGames, props) {
  setText('site-title', meta?.siteTitle && meta.siteTitle !== 'Sports Predictions Showcase' ? meta.siteTitle : 'Lets Parlay ML');
  setText('hero-leagues', Array.isArray(meta?.leagues) ? meta.leagues.join(' • ') : 'MLB');
  setText('hero-game-count', String((todayGames || []).length));
  setText('hero-next-game-count', String((tomorrowGames || []).length));
  setText('hero-prop-count', String((props || []).length));
  setText('hero-updated', meta?.lastUpdated || '—');
  setText('today-date-label', meta?.targetDate || '');
  setText('today-date-label-full', meta?.targetDate || '');
  setText('tomorrow-date-label', meta?.nextDate || '');
  setText('results-date-label', meta?.resultsDate || meta?.targetDate || '');
}

function setupLeagueFilter(allGames, meta, featureConfig = {}) {
  const select = byId('league-filter');
  if (!select) return;
  const active = activeLeagueSet(featureConfig, meta);
  uniqueLeagues(allGames).filter(league => active.has(String(league).toUpperCase())).forEach(league => {
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
    const [meta, featureConfig, games, rawProps, rawPropsLab, results, resultsSummary, resultsHistory, rawHomeInsights, injuries, mlbPropResults, mlbPropSummary, mlbPropPending, homeTopPicks, mlbResultsLaunchText] = await Promise.all([
      loadJson('data/site.json'),
      loadJson('data/site_features.json', { activeLeagues: ['MLB'], features: {} }),
      loadJson('data/games.json', []),
      loadJson('data/props.json', []),
      loadJson('data/nba_props_lab.json', null),
      loadJson('data/results.json', []),
      loadJson('data/results_summary.json', {}),
      loadJson('data/results_history.json', []),
      loadJson('data/nba_home_insights.json', {}),
      loadJson('data/nba_injuries.json', {}),
      loadJson('data/mlb_prop_results_history.json', []),
      loadJson('data/mlb_prop_results_summary.json', {}),
      loadJson('data/mlb_prop_results_pending.json', []),
      loadJson('data/home_top_picks.json', {}),
      loadText('data/mlb_results_launch_date.txt', '')
    ]);
    applySiteFeatures(featureConfig);
    const activeLeagues = activeLeagueSet(featureConfig, meta);
    const injuryLookup = buildInjuryLookup(injuries);
    const gameLookup = buildGameLookup(games);

    const nbaEnabled = activeLeagues.has('NBA') && featureConfig?.features?.nbaPropsLab === true;
    const propsSource = nbaEnabled ? flattenPropsSource(rawPropsLab) : [];
    const baseProps = (propsSource.length ? propsSource : rawProps).filter(p => activeLeagues.has(String(p?.league || 'MLB').toUpperCase()));

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
    const activeGames = (games || []).filter(g => activeLeagues.has(String(g?.league || '').toUpperCase()));
    const todayGames = activeGames.filter(g => g.gameDate === meta.targetDate);
    const tomorrowGames = activeGames.filter(g => g.gameDate === meta.nextDate);
    const activeMeta = { ...meta, leagues: Array.from(activeLeagues) };
    fillHeader(activeMeta, todayGames, tomorrowGames, todayProps);
    setText('hero-top-pick-count', String(Object.keys(homeTopPicks?.mlbBoards || {}).length));
    setupLeagueFilter(activeGames, meta, featureConfig);
    renderProps(todayProps, 'props-body');
    renderProps(nextProps, 'props-next-body');
    renderTopPickPulse(homeTopPicks);
    renderHomeTopPicks(homeTopPicks);
    renderHomeMarketValues(homeTopPicks);
    renderParlayBuilder(homeTopPicks);
    renderMlbHomeBoardsSnapshot(homeTopPicks);
    renderHighConfidenceGames(homeTopPicks, activeGames, meta);
    if (featureConfig?.features?.nbaQuickLooks === true) {
      renderNbaGameEdges(activeGames, meta);
      renderHomeInsights(homeInsights, meta);
    }
    const mlbResultsLaunchDate = String(mlbResultsLaunchText || '').trim();
    const filteredResults = filterResultsForLaunch(results, mlbResultsLaunchDate);
    const filteredHistory = filterResultsForLaunch(resultsHistory, mlbResultsLaunchDate);
    const effectiveSummary = recomputeResultsSummaryFromHistory(filteredHistory, resultsSummary);

    renderResultsSummary(effectiveSummary);
    setupResultsExplorer(filteredResults, filteredHistory, meta?.resultsDate || '');

    const trackedMlbPropResults = filterMlbTrackedHomeBoardRows(mlbPropResults);
    const trackedMlbPropPending = filterMlbTrackedHomeBoardRows(mlbPropPending);
    const trackedMlbPropSummary = buildMlbPropSummaryFromRows(trackedMlbPropResults, mlbPropSummary);
    renderMlbPropResultsSummary(trackedMlbPropSummary, trackedMlbPropPending);
    setupMlbPropResultsExplorer(trackedMlbPropResults, trackedMlbPropSummary, trackedMlbPropPending);
  } catch (err) {
    console.error(err);
    if (root) root.innerHTML = `<div class="empty-state">Failed to load site data: ${escapeHtml(err.message || err)}</div>`;
  }
})();