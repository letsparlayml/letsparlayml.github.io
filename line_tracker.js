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

function hasNum(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}

function toNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmtNumber(value, digits = 1) {
  return hasNum(value) ? Number(value).toFixed(digits) : '—';
}

function fmtSpread(value) {
  return hasNum(value) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(1)}` : '—';
}

function fmtMoneyline(value) {
  if (!hasNum(value)) return '—';
  const n = Number(value);
  if (Math.abs(n) < 1) return '—';
  return `${n >= 0 ? '+' : ''}${Math.round(n)}`;
}

function hasMeaningfulMoneyline(value) {
  return hasNum(value) && Math.abs(Number(value)) >= 1;
}

function fmtSigned(value, digits = 1) {
  return hasNum(value) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}` : '—';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const DISPLAY_TZ = 'America/Denver';

function toDate(value) {
  if (!value) return null;
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

function localDateFromIso(value) {
  const dt = toDate(value);
  if (!dt) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: DISPLAY_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(dt);
  const lookup = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

function fmtStart(value, fallbackDate = '') {
  const dt = toDate(value);
  if (dt) {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: DISPLAY_TZ,
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    }).format(dt);
  }
  if (fallbackDate) {
    const plain = new Date(`${fallbackDate}T12:00:00`);
    if (!Number.isNaN(plain.getTime())) {
      return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(plain);
    }
    return fallbackDate;
  }
  return '—';
}

function fmtStamp(value) {
  const dt = toDate(value);
  if (!dt) return '—';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: DISPLAY_TZ,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(dt);
}

function parseMatchup(matchup) {
  const raw = String(matchup || '');
  if (!raw.includes('@')) return { awayTeam: '', homeTeam: '' };
  const [away, home] = raw.split('@').map(v => v.trim());
  return { awayTeam: away || '', homeTeam: home || '' };
}

function normalizeArchiveRow(row) {
  const parsed = parseMatchup(row?.matchup);
  const awayTeam = String(row?.awayTeam || parsed.awayTeam || '').toUpperCase();
  const homeTeam = String(row?.homeTeam || parsed.homeTeam || '').toUpperCase();
  const rawStart = row?.startTimeUtc || row?.commence_time || row?.commenceTime || row?.gameDateTimeUtc || row?.gameDate || row?.eventStartUtc || row?.start || '';
  const startTimeUtc = String(rawStart || '').includes('T') ? String(rawStart) : '';
  const localDate = String(row?.date || (startTimeUtc ? localDateFromIso(startTimeUtc) : '') || '').trim();
  const utcDate = startTimeUtc ? new Date(startTimeUtc).toISOString().slice(0, 10) : String(row?.utcDate || localDate || '').trim();
  const asOf = row?.updatedAt || row?.archivedAt || row?.fetchedAtUtc || row?.marketLineUpdated || '';
  return {
    league: String(row?.league || '').toUpperCase(),
    awayTeam,
    homeTeam,
    localDate,
    utcDate,
    matchup: `${awayTeam} @ ${homeTeam}`,
    startTimeUtc,
    asOf,
    source: row?.bookmakerTitle ? `The Odds API • ${row.bookmakerTitle}` : (row?.source || 'Archive'),
    awaySpread: toNum(row?.marketSpread),
    total: toNum(row?.marketTotal),
    awayML: toNum(row?.marketAwayML ?? row?.awayML ?? row?.awayMoneyline),
    homeML: toNum(row?.marketHomeML ?? row?.homeML ?? row?.homeMoneyline),
  };
}

function normalizeGame(game) {
  const league = String(game?.league || '').toUpperCase();
  const awayTeam = String(game?.awayTeam || '').toUpperCase();
  const homeTeam = String(game?.homeTeam || '').toUpperCase();
  const rawStart = game?.gameDateTimeUtc || game?.startTimeUtc || game?.gameDate || '';
  const startTimeUtc = String(rawStart || '').includes('T') ? String(rawStart) : '';
  const modelAwayScore = toNum(game?.modelAwayScore);
  const modelHomeScore = toNum(game?.modelHomeScore);
  return {
    id: String(game?.id || `${league}-${game?.gameDate || ''}-${awayTeam}-${homeTeam}`),
    league,
    date: String(game?.gameDate || (startTimeUtc ? localDateFromIso(startTimeUtc) : '') || ''),
    awayTeam,
    homeTeam,
    matchup: `${awayTeam} @ ${homeTeam}`,
    startTimeUtc,
    modelAwaySpread: hasNum(modelAwayScore) && hasNum(modelHomeScore) ? (modelHomeScore - modelAwayScore) : null,
    modelTotal: toNum(game?.modelTotal),
    marketSpread: toNum(game?.marketSpread),
    marketTotal: toNum(game?.marketTotal),
    marketAwayML: toNum(game?.marketAwayML),
    marketHomeML: toNum(game?.marketHomeML),
    marketLineUpdated: String(game?.marketLineUpdated || ''),
  };
}

function sameGame(archiveRow, game) {
  if (archiveRow.league !== game.league) return false;
  if (archiveRow.awayTeam !== game.awayTeam || archiveRow.homeTeam !== game.homeTeam) return false;
  if (!game.date) return true;
  if (archiveRow.localDate === game.date || archiveRow.utcDate === game.date) return true;
  if (!archiveRow.localDate && archiveRow.startTimeUtc) return localDateFromIso(archiveRow.startTimeUtc) === game.date;
  return false;
}

function meaningfulSnapshot(snapshot) {
  return [snapshot.awaySpread, snapshot.total, snapshot.awayML, snapshot.homeML].some(hasNum);
}

function pickCurrentSnapshot(snapshots, startTimeUtc) {
  if (!snapshots.length) return null;
  const now = new Date();
  const start = toDate(startTimeUtc);
  const cutoff = start && now > start ? start : now;
  const eligible = snapshots.filter(s => {
    const asOf = toDate(s.asOf);
    return !asOf || asOf <= cutoff;
  });
  return (eligible.length ? eligible : snapshots).slice().sort((a, b) => {
    const aTime = toDate(a.asOf)?.getTime() || 0;
    const bTime = toDate(b.asOf)?.getTime() || 0;
    return aTime - bTime;
  }).at(-1) || null;
}

function valueRange(snapshots, key) {
  const nums = snapshots.map(s => toNum(s[key])).filter(hasNum);
  if (!nums.length) return { min: null, max: null };
  return { min: Math.min(...nums), max: Math.max(...nums) };
}

function buildTrackerEntries(games, archiveRows) {
  const normalizedArchive = (archiveRows || []).map(normalizeArchiveRow).filter(r => r.league && r.awayTeam && r.homeTeam);
  return (games || [])
    .map(normalizeGame)
    .filter(g => ['NBA', 'NHL', 'MLB'].includes(g.league))
    .map(game => {
      let snapshots = normalizedArchive.filter(row => sameGame(row, game) && meaningfulSnapshot(row));
      snapshots.sort((a, b) => {
        const aTime = toDate(a.asOf)?.getTime() || 0;
        const bTime = toDate(b.asOf)?.getTime() || 0;
        return aTime - bTime;
      });

      if (!snapshots.length) {
        const currentSpread = toNum(game.marketSpread);
        const currentTotal = toNum(game.marketTotal);
        if (hasNum(currentSpread) || hasNum(currentTotal) || hasNum(game.marketAwayML) || hasNum(game.marketHomeML)) {
          snapshots = [{
            league: game.league,
            awayTeam: game.awayTeam,
            homeTeam: game.homeTeam,
            localDate: game.date,
            utcDate: game.date,
            matchup: game.matchup,
            startTimeUtc: game.startTimeUtc,
            asOf: game.marketLineUpdated || '',
            source: 'games.json',
            awaySpread: currentSpread,
            total: currentTotal,
            awayML: toNum(game.marketAwayML),
            homeML: toNum(game.marketHomeML),
          }];
        }
      }

      const current = pickCurrentSnapshot(snapshots, game.startTimeUtc);
      const opening = snapshots[0] || null;
      const resolvedStartTimeUtc = game.startTimeUtc || opening?.startTimeUtc || current?.startTimeUtc || '';
      const started = !!(toDate(resolvedStartTimeUtc) && new Date() >= toDate(resolvedStartTimeUtc));
      const closing = started ? current : null;
      const spreadRange = valueRange(snapshots, 'awaySpread');
      const totalRange = valueRange(snapshots, 'total');
      const openSpread = opening?.awaySpread ?? null;
      const currentSpread = current?.awaySpread ?? game.marketSpread ?? null;
      const openTotal = opening?.total ?? null;
      const currentTotal = current?.total ?? game.marketTotal ?? null;
      const currentAwayML = hasMeaningfulMoneyline(current?.awayML) ? current.awayML : (hasMeaningfulMoneyline(game.marketAwayML) ? game.marketAwayML : null);
      const currentHomeML = hasMeaningfulMoneyline(current?.homeML) ? current.homeML : (hasMeaningfulMoneyline(game.marketHomeML) ? game.marketHomeML : null);
      const displayDate = game.date || opening?.localDate || current?.localDate || opening?.utcDate || current?.utcDate || (resolvedStartTimeUtc ? localDateFromIso(resolvedStartTimeUtc) : '');
      return {
        ...game,
        date: displayDate,
        startTimeUtc: resolvedStartTimeUtc,
        snapshots,
        snapshotCount: snapshots.length,
        firstSeenAt: opening?.asOf || '',
        latestSeenAt: current?.asOf || '',
        opening,
        current,
        closing,
        started,
        currentAwayML,
        currentHomeML,
        bestAwaySpread: spreadRange.max,
        bestHomeSpread: spreadRange.min,
        bestOverTotal: totalRange.min,
        bestUnderTotal: totalRange.max,
        spreadMove: hasNum(openSpread) && hasNum(currentSpread) ? Math.abs(currentSpread - openSpread) : 0,
        totalMove: hasNum(openTotal) && hasNum(currentTotal) ? Math.abs(currentTotal - openTotal) : 0,
        spreadEdgeOpen: hasNum(game.modelAwaySpread) && hasNum(openSpread) ? (game.modelAwaySpread - openSpread) : null,
        spreadEdgeCurrent: hasNum(game.modelAwaySpread) && hasNum(currentSpread) ? (game.modelAwaySpread - currentSpread) : null,
        totalEdgeOpen: hasNum(game.modelTotal) && hasNum(openTotal) ? (game.modelTotal - openTotal) : null,
        totalEdgeCurrent: hasNum(game.modelTotal) && hasNum(currentTotal) ? (game.modelTotal - currentTotal) : null,
      };
    })
    .filter(entry => entry.snapshotCount > 0)
    .sort((a, b) => {
      const aTime = toDate(a.startTimeUtc)?.getTime() || Number.MAX_SAFE_INTEGER;
      const bTime = toDate(b.startTimeUtc)?.getTime() || Number.MAX_SAFE_INTEGER;
      return aTime - bTime || a.matchup.localeCompare(b.matchup);
    });
}


function gameDetailHref(entry) {
  const params = new URLSearchParams();
  if (entry?.id) params.set('id', entry.id);
  return `game.html?${params.toString()}`;
}

const state = {
  entries: [],
  selectedId: '',
};

function filteredEntries() {
  const league = byId('tracker-league-filter')?.value || 'ALL';
  const date = byId('tracker-date-filter')?.value || 'ALL';
  const sort = byId('tracker-sort-filter')?.value || 'start';

  let rows = state.entries.slice();
  if (league !== 'ALL') rows = rows.filter(r => r.league === league);
  if (date !== 'ALL') rows = rows.filter(r => r.date === date);

  const sorters = {
    start: (a, b) => (toDate(a.startTimeUtc)?.getTime() || Number.MAX_SAFE_INTEGER) - (toDate(b.startTimeUtc)?.getTime() || Number.MAX_SAFE_INTEGER),
    spreadMove: (a, b) => (b.spreadMove || 0) - (a.spreadMove || 0),
    totalMove: (a, b) => (b.totalMove || 0) - (a.totalMove || 0),
    spreadEdge: (a, b) => Math.abs(b.spreadEdgeCurrent || 0) - Math.abs(a.spreadEdgeCurrent || 0),
    totalEdge: (a, b) => Math.abs(b.totalEdgeCurrent || 0) - Math.abs(a.totalEdgeCurrent || 0),
    snapshots: (a, b) => (b.snapshotCount || 0) - (a.snapshotCount || 0),
  };
  rows.sort(sorters[sort] || sorters.start);
  return rows;
}

function setHero(entries) {
  byId('tracker-hero-games').textContent = String(entries.length);
  byId('tracker-hero-leagues').textContent = Array.from(new Set(entries.map(e => e.league))).join(' • ') || '—';
  byId('tracker-hero-snapshots').textContent = String(entries.reduce((sum, entry) => sum + (entry.snapshotCount || 0), 0));
  const spreadMover = entries.slice().sort((a, b) => (b.spreadMove || 0) - (a.spreadMove || 0))[0];
  const totalMover = entries.slice().sort((a, b) => (b.totalMove || 0) - (a.totalMove || 0))[0];
  byId('tracker-hero-spread-move').textContent = spreadMover ? `${spreadMover.matchup} (${fmtSigned(spreadMover.spreadMove)})` : '—';
  byId('tracker-hero-total-move').textContent = totalMover ? `${totalMover.matchup} (${fmtSigned(totalMover.totalMove)})` : '—';
}

function populateFilters(entries) {
  const leagueSel = byId('tracker-league-filter');
  const dateSel = byId('tracker-date-filter');
  if (leagueSel && leagueSel.options.length <= 1) {
    Array.from(new Set(entries.map(e => e.league))).sort().forEach(league => {
      const opt = document.createElement('option');
      opt.value = league;
      opt.textContent = league;
      leagueSel.appendChild(opt);
    });
  }
  if (dateSel && dateSel.options.length <= 1) {
    Array.from(new Set(entries.map(e => e.date))).sort().forEach(date => {
      const opt = document.createElement('option');
      opt.value = date;
      opt.textContent = date;
      dateSel.appendChild(opt);
    });
  }
}

function summaryCard(label, title, rows) {
  return `
    <div class="summary-card">
      <div class="summary-card-head">
        <div>
          <span class="summary-kicker">${escapeHtml(label)}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
      </div>
      <div class="summary-rows">${rows.map(row => `<div>${row}</div>`).join('')}</div>
    </div>
  `;
}

function renderSummary(entries) {
  const grid = byId('tracker-summary-grid');
  if (!grid) return;
  const spreadMover = entries.slice().sort((a, b) => (b.spreadMove || 0) - (a.spreadMove || 0))[0];
  const totalMover = entries.slice().sort((a, b) => (b.totalMove || 0) - (a.totalMove || 0))[0];
  const spreadEdge = entries.slice().sort((a, b) => Math.abs(b.spreadEdgeCurrent || 0) - Math.abs(a.spreadEdgeCurrent || 0))[0];
  const totalEdge = entries.slice().sort((a, b) => Math.abs(b.totalEdgeCurrent || 0) - Math.abs(a.totalEdgeCurrent || 0))[0];

  const cards = [];
  if (spreadMover) {
    cards.push(summaryCard('Spread movement', spreadMover.matchup, [
      `Open ${fmtSpread(spreadMover.opening?.awaySpread)} → ${spreadMover.started ? 'Close' : 'Current'} ${fmtSpread(spreadMover.current?.awaySpread ?? spreadMover.marketSpread)}`,
      `Best away ${fmtSpread(spreadMover.bestAwaySpread)} • Best home ${fmtSpread(spreadMover.bestHomeSpread)}`,
      `Move ${fmtSigned(spreadMover.spreadMove)}`,
    ]));
  }
  if (totalMover) {
    cards.push(summaryCard('Total movement', totalMover.matchup, [
      `Open ${fmtNumber(totalMover.opening?.total)} → ${totalMover.started ? 'Close' : 'Current'} ${fmtNumber(totalMover.current?.total ?? totalMover.marketTotal)}`,
      `Best over ${fmtNumber(totalMover.bestOverTotal)} • Best under ${fmtNumber(totalMover.bestUnderTotal)}`,
      `Move ${fmtSigned(totalMover.totalMove)}`,
    ]));
  }
  if (spreadEdge) {
    cards.push(summaryCard('Spread edge now', spreadEdge.matchup, [
      `Model away spread ${fmtSpread(spreadEdge.modelAwaySpread)}`,
      `Current line ${fmtSpread(spreadEdge.current?.awaySpread ?? spreadEdge.marketSpread)}`,
      `Edge ${fmtSigned(spreadEdge.spreadEdgeCurrent)}`,
    ]));
  }
  if (totalEdge) {
    cards.push(summaryCard('Total edge now', totalEdge.matchup, [
      `Model total ${fmtNumber(totalEdge.modelTotal)}`,
      `Current total ${fmtNumber(totalEdge.current?.total ?? totalEdge.marketTotal)}`,
      `Edge ${fmtSigned(totalEdge.totalEdgeCurrent)}`,
    ]));
  }

  grid.innerHTML = cards.join('');
}


function resolveMoneylineText(entry) {
  const away = hasMeaningfulMoneyline(entry.currentAwayML) ? entry.currentAwayML : (hasMeaningfulMoneyline(entry.opening?.awayML) ? entry.opening.awayML : (hasMeaningfulMoneyline(entry.marketAwayML) ? entry.marketAwayML : null));
  const home = hasMeaningfulMoneyline(entry.currentHomeML) ? entry.currentHomeML : (hasMeaningfulMoneyline(entry.opening?.homeML) ? entry.opening.homeML : (hasMeaningfulMoneyline(entry.marketHomeML) ? entry.marketHomeML : null));
  if (!hasMeaningfulMoneyline(away) && !hasMeaningfulMoneyline(home)) return '— / —';
  return `${fmtMoneyline(away)} / ${fmtMoneyline(home)}`;
}

function renderTable(entries) {
  const body = byId('tracker-body');
  if (!body) return;
  if (!entries.length) {
    body.innerHTML = '<tr><td colspan="11">No tracked line history is available for the current filters.</td></tr>';
    return;
  }
  body.innerHTML = entries.map(entry => {
    const selected = entry.id === state.selectedId ? ' tracker-row-selected' : '';
    const mlText = resolveMoneylineText(entry);
    return `
      <tr class="tracker-row${selected}" data-entry-id="${escapeHtml(entry.id)}">
        <td>${escapeHtml(fmtStart(entry.startTimeUtc, entry.date || ''))}</td>
        <td>${escapeHtml(entry.league)}</td>
        <td><div class="tracker-link-stack"><button class="tracker-link" type="button" data-entry-id="${escapeHtml(entry.id)}">${escapeHtml(entry.matchup)}</button><a class="tracker-detail-link" href="${gameDetailHref(entry)}">Open detail</a></div></td>
        <td>${escapeHtml(String(entry.snapshotCount || 0))}</td>
        <td>${escapeHtml(fmtSpread(entry.opening?.awaySpread))} → ${escapeHtml(fmtSpread(entry.current?.awaySpread ?? entry.marketSpread))}</td>
        <td>${escapeHtml(fmtSpread(entry.bestHomeSpread))} to ${escapeHtml(fmtSpread(entry.bestAwaySpread))}</td>
        <td>Model ${escapeHtml(fmtSpread(entry.modelAwaySpread))}<br><span class="muted">Now ${escapeHtml(fmtSigned(entry.spreadEdgeCurrent))}</span></td>
        <td>${escapeHtml(fmtNumber(entry.opening?.total))} → ${escapeHtml(fmtNumber(entry.current?.total ?? entry.marketTotal))}</td>
        <td>${escapeHtml(fmtNumber(entry.bestOverTotal))} to ${escapeHtml(fmtNumber(entry.bestUnderTotal))}</td>
        <td>Model ${escapeHtml(fmtNumber(entry.modelTotal))}<br><span class="muted">Now ${escapeHtml(fmtSigned(entry.totalEdgeCurrent))}</span></td>
        <td>${escapeHtml(mlText)}</td>
      </tr>
    `;
  }).join('');
}

function renderDetail(entry) {
  const title = byId('tracker-detail-title');
  const subhead = byId('tracker-detail-subhead');
  const cards = byId('tracker-detail-cards');
  const body = byId('tracker-detail-body');
  if (!entry) {
    if (title) title.textContent = 'Select a game';
    if (subhead) subhead.textContent = 'Click a matchup in the table to inspect the full pregame snapshot timeline.';
    if (cards) cards.innerHTML = '';
    if (body) body.innerHTML = '<tr><td colspan="6">No game selected.</td></tr>';
    return;
  }
  if (title) title.textContent = entry.matchup;
  if (subhead) subhead.textContent = `${entry.league} • ${fmtStart(entry.startTimeUtc, entry.date || '')} • ${entry.snapshotCount} pregame snapshots`;
  if (cards) {
    cards.innerHTML = [
      summaryCard('Spread', 'Opening vs current', [
        `Open ${fmtSpread(entry.opening?.awaySpread)} → ${entry.started ? 'Close' : 'Current'} ${fmtSpread(entry.current?.awaySpread ?? entry.marketSpread)}`,
        `Best away ${fmtSpread(entry.bestAwaySpread)} • Best home ${fmtSpread(entry.bestHomeSpread)}`,
        `Model ${fmtSpread(entry.modelAwaySpread)} • Edge now ${fmtSigned(entry.spreadEdgeCurrent)}`,
      ]),
      summaryCard('Total', 'Opening vs current', [
        `Open ${fmtNumber(entry.opening?.total)} → ${entry.started ? 'Close' : 'Current'} ${fmtNumber(entry.current?.total ?? entry.marketTotal)}`,
        `Best over ${fmtNumber(entry.bestOverTotal)} • Best under ${fmtNumber(entry.bestUnderTotal)}`,
        `Model ${fmtNumber(entry.modelTotal)} • Edge now ${fmtSigned(entry.totalEdgeCurrent)}`,
      ]),
      summaryCard('Moneyline', 'Latest pregame prices', [
        `Away ${fmtMoneyline(entry.currentAwayML)} • Home ${fmtMoneyline(entry.currentHomeML)}`,
        `First seen ${escapeHtml(fmtStamp(entry.firstSeenAt))}`,
        `Last seen ${escapeHtml(fmtStamp(entry.latestSeenAt))}`,
      ]),
    ].join('');
  }
  if (body) {
    body.innerHTML = entry.snapshots.map(snapshot => `
      <tr>
        <td>${escapeHtml(fmtStamp(snapshot.asOf))}</td>
        <td>${escapeHtml(fmtSpread(snapshot.awaySpread))}</td>
        <td>${escapeHtml(fmtNumber(snapshot.total))}</td>
        <td>${escapeHtml(fmtMoneyline(snapshot.awayML))}</td>
        <td>${escapeHtml(fmtMoneyline(snapshot.homeML))}</td>
        <td>${escapeHtml(snapshot.source || 'Archive')}</td>
      </tr>
    `).join('');
  }
}

function attachHandlers() {
  ['tracker-league-filter', 'tracker-date-filter', 'tracker-sort-filter'].forEach(id => {
    byId(id)?.addEventListener('change', () => {
      const rows = filteredEntries();
      renderSummary(rows);
      renderTable(rows);
      const selected = rows.find(entry => entry.id === state.selectedId) || rows[0] || null;
      state.selectedId = selected?.id || '';
      renderTable(rows);
      renderDetail(selected);
    });
  });
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-entry-id]');
    if (!button) return;
    const id = button.getAttribute('data-entry-id');
    if (!id) return;
    const entry = filteredEntries().find(item => item.id === id) || state.entries.find(item => item.id === id);
    if (!entry) return;
    state.selectedId = id;
    renderTable(filteredEntries());
    renderDetail(entry);
  });
}

async function init() {
  const [games, archive] = await Promise.all([
    loadJson('data/games.json', []),
    loadJson('data/market_lines_archive.json', []),
  ]);
  state.entries = buildTrackerEntries(games, archive);
  populateFilters(state.entries);
  setHero(state.entries);
  attachHandlers();
  const rows = filteredEntries();
  renderSummary(rows);
  state.selectedId = rows[0]?.id || '';
  renderTable(rows);
  renderDetail(rows[0] || null);
}

init().catch((err) => {
  console.error(err);
  const body = byId('tracker-body');
  if (body) body.innerHTML = '<tr><td colspan="11">Failed to load line-tracker data.</td></tr>';
});
