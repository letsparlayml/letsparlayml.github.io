#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

API_BASE = "https://api.the-odds-api.com/v4"
DISPLAY_TZ = "America/Denver"
PREFERRED_BOOKS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "caesars",
    "espnbet",
    "betrivers",
    "pinnacle",
    "bet365",
]
SPORTS = {
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",
    "MLB": "baseball_mlb",
}
TEAM_MAP = {
    # NBA
    "Atlanta Hawks": ("NBA", "ATL"),
    "Boston Celtics": ("NBA", "BOS"),
    "Brooklyn Nets": ("NBA", "BKN"),
    "Charlotte Hornets": ("NBA", "CHA"),
    "Chicago Bulls": ("NBA", "CHI"),
    "Cleveland Cavaliers": ("NBA", "CLE"),
    "Dallas Mavericks": ("NBA", "DAL"),
    "Denver Nuggets": ("NBA", "DEN"),
    "Detroit Pistons": ("NBA", "DET"),
    "Golden State Warriors": ("NBA", "GSW"),
    "Houston Rockets": ("NBA", "HOU"),
    "Indiana Pacers": ("NBA", "IND"),
    "LA Clippers": ("NBA", "LAC"),
    "Los Angeles Clippers": ("NBA", "LAC"),
    "Los Angeles Lakers": ("NBA", "LAL"),
    "LA Lakers": ("NBA", "LAL"),
    "Memphis Grizzlies": ("NBA", "MEM"),
    "Miami Heat": ("NBA", "MIA"),
    "Milwaukee Bucks": ("NBA", "MIL"),
    "Minnesota Timberwolves": ("NBA", "MIN"),
    "New Orleans Pelicans": ("NBA", "NOP"),
    "New York Knicks": ("NBA", "NYK"),
    "Oklahoma City Thunder": ("NBA", "OKC"),
    "Orlando Magic": ("NBA", "ORL"),
    "Philadelphia 76ers": ("NBA", "PHI"),
    "Phoenix Suns": ("NBA", "PHX"),
    "Portland Trail Blazers": ("NBA", "POR"),
    "Sacramento Kings": ("NBA", "SAC"),
    "San Antonio Spurs": ("NBA", "SAS"),
    "Toronto Raptors": ("NBA", "TOR"),
    "Utah Jazz": ("NBA", "UTA"),
    "Washington Wizards": ("NBA", "WAS"),

    # NHL
    "Anaheim Ducks": ("NHL", "ANA"),
    "Boston Bruins": ("NHL", "BOS"),
    "Buffalo Sabres": ("NHL", "BUF"),
    "Calgary Flames": ("NHL", "CGY"),
    "Carolina Hurricanes": ("NHL", "CAR"),
    "Chicago Blackhawks": ("NHL", "CHI"),
    "Colorado Avalanche": ("NHL", "COL"),
    "Columbus Blue Jackets": ("NHL", "CBJ"),
    "Dallas Stars": ("NHL", "DAL"),
    "Detroit Red Wings": ("NHL", "DET"),
    "Edmonton Oilers": ("NHL", "EDM"),
    "Florida Panthers": ("NHL", "FLA"),
    "Los Angeles Kings": ("NHL", "LAK"),
    "Minnesota Wild": ("NHL", "MIN"),
    "Montreal Canadiens": ("NHL", "MTL"),
    "Nashville Predators": ("NHL", "NSH"),
    "New Jersey Devils": ("NHL", "NJD"),
    "New York Islanders": ("NHL", "NYI"),
    "New York Rangers": ("NHL", "NYR"),
    "Ottawa Senators": ("NHL", "OTT"),
    "Philadelphia Flyers": ("NHL", "PHI"),
    "Pittsburgh Penguins": ("NHL", "PIT"),
    "San Jose Sharks": ("NHL", "SJS"),
    "Seattle Kraken": ("NHL", "SEA"),
    "St. Louis Blues": ("NHL", "STL"),
    "St Louis Blues": ("NHL", "STL"),
    "Tampa Bay Lightning": ("NHL", "TBL"),
    "Toronto Maple Leafs": ("NHL", "TOR"),
    "Utah Hockey Club": ("NHL", "UTA"),
    "Utah Mammoth": ("NHL", "UTA"),
    "Vancouver Canucks": ("NHL", "VAN"),
    "Vegas Golden Knights": ("NHL", "VGK"),
    "Washington Capitals": ("NHL", "WSH"),
    "Winnipeg Jets": ("NHL", "WPG"),

    # MLB
    "Arizona Diamondbacks": ("MLB", "ARI"),
    "Atlanta Braves": ("MLB", "ATL"),
    "Baltimore Orioles": ("MLB", "BAL"),
    "Boston Red Sox": ("MLB", "BOS"),
    "Chicago Cubs": ("MLB", "CHC"),
    "Chicago White Sox": ("MLB", "CHW"),
    "Cincinnati Reds": ("MLB", "CIN"),
    "Cleveland Guardians": ("MLB", "CLE"),
    "Colorado Rockies": ("MLB", "COL"),
    "Detroit Tigers": ("MLB", "DET"),
    "Houston Astros": ("MLB", "HOU"),
    "Kansas City Royals": ("MLB", "KCR"),
    "Los Angeles Angels": ("MLB", "LAA"),
    "Los Angeles Dodgers": ("MLB", "LAD"),
    "Miami Marlins": ("MLB", "MIA"),
    "Milwaukee Brewers": ("MLB", "MIL"),
    "Minnesota Twins": ("MLB", "MIN"),
    "New York Mets": ("MLB", "NYM"),
    "New York Yankees": ("MLB", "NYY"),
    "Athletics": ("MLB", "OAK"),
    "Oakland Athletics": ("MLB", "OAK"),
    "Philadelphia Phillies": ("MLB", "PHI"),
    "Pittsburgh Pirates": ("MLB", "PIT"),
    "San Diego Padres": ("MLB", "SDP"),
    "Seattle Mariners": ("MLB", "SEA"),
    "San Francisco Giants": ("MLB", "SFG"),
    "St. Louis Cardinals": ("MLB", "STL"),
    "St Louis Cardinals": ("MLB", "STL"),
    "Tampa Bay Rays": ("MLB", "TBR"),
    "Texas Rangers": ("MLB", "TEX"),
    "Toronto Blue Jays": ("MLB", "TOR"),
    "Washington Nationals": ("MLB", "WSN"),
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_key(cli_key: Optional[str], key_file: Optional[str]) -> Optional[str]:
    if cli_key:
        return cli_key.strip()
    env_key = os.environ.get('ODDS_API_KEY', '').strip()
    if env_key:
        return env_key
    candidates: List[Path] = []
    if key_file:
        candidates.append(Path(key_file))
    candidates.extend([
        Path(r'C:\python\secrets\the_odds_api_key.txt'),
        Path(r'C:\python\secrets\odds_api_key.txt'),
    ])
    for path in candidates:
        try:
            if path.exists():
                txt = path.read_text(encoding='utf-8').strip()
                if txt:
                    return txt
        except Exception:
            continue
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Fetch NBA/NHL/MLB moneyline, spread, and total lines from The Odds API.')
    p.add_argument('--api-key', default=None)
    p.add_argument('--key-file', default=None)
    p.add_argument('--website-repo', required=True)
    p.add_argument('--sports', default='NBA,NHL,MLB')
    p.add_argument('--bookmakers', default=','.join(PREFERRED_BOOKS))
    p.add_argument('--regions', default='us')
    p.add_argument('--markets', default='h2h,spreads,totals')
    p.add_argument('--odds-format', default='american', choices=['american', 'decimal'])
    p.add_argument('--date-format', default='iso', choices=['iso', 'unix'])
    p.add_argument('--timeout', type=int, default=30)
    return p.parse_args()


def normalize_team_name(value: Any) -> str:
    """Return a stable lookup key for sportsbook/team names.

    The Odds API can return accented names for some teams, especially
    "Montréal Canadiens". The site schedule/model data uses plain
    abbreviations like MTL, so team matching needs to be accent-insensitive.
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    for old, repl in {
        '\u2019': "'",
        '\u2018': "'",
        '\u201c': '"',
        '\u201d': '"',
        '&': ' and ',
        '.': ' ',
    }.items():
        text = text.replace(old, repl)
    return ' '.join(text.upper().split())


def team_abbrev(league: str, name: str) -> str:
    raw = "" if name is None else str(name).strip()
    if not raw:
        return ""
    for full_name, val in TEAM_MAP.items():
        mapped_league, abbr = val
        if mapped_league != league:
            continue
        if raw == full_name or normalize_team_name(raw) == normalize_team_name(full_name) or raw.upper() == abbr:
            return abbr
    if league == 'NHL' and normalize_team_name(raw) == normalize_team_name('Montréal Canadiens'):
        return 'MTL'
    return raw.upper()


def odds_get(api_key: str, sport_key: str, *, bookmakers: str, regions: str, markets: str, odds_format: str, date_format: str, timeout: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    url = f'{API_BASE}/sports/{sport_key}/odds'
    params: Dict[str, Any] = {
        'apiKey': api_key,
        'markets': markets,
        'oddsFormat': odds_format,
        'dateFormat': date_format,
    }
    if bookmakers.strip():
        params['bookmakers'] = bookmakers.strip()
    else:
        params['regions'] = regions.strip() or 'us'
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json(), dict(resp.headers)


def pick_bookmaker(bookmakers: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not bookmakers:
        return None
    by_key = {str(b.get('key', '')).lower(): b for b in bookmakers}
    for pref in PREFERRED_BOOKS:
        if pref in by_key:
            return by_key[pref]
    return bookmakers[0]


def market_outcomes(bookmaker: dict[str, Any], key: str) -> list[dict[str, Any]]:
    for market in bookmaker.get('markets', []) or []:
        if market.get('key') == key:
            return market.get('outcomes', []) or []
    return []


def normalize_date_strings(commence_time: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(str(commence_time).replace('Z', '+00:00'))
    utc_date = dt.astimezone(timezone.utc).date().isoformat()
    try:
        from zoneinfo import ZoneInfo
        local_date = dt.astimezone(ZoneInfo(DISPLAY_TZ)).date().isoformat()
    except Exception:
        local_date = utc_date
    return local_date, utc_date


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == '':
            return None
        return float(value)
    except Exception:
        return None


def _book_priority(key: Any) -> int:
    value = str(key or '').lower()
    try:
        return PREFERRED_BOOKS.index(value)
    except ValueError:
        return len(PREFERRED_BOOKS) + 50


def extract_event_row(league: str, event: dict[str, Any]) -> dict[str, Any]:
    home_full = event.get('home_team', '')
    away_full = event.get('away_team', '')
    home = team_abbrev(league, home_full)
    away = team_abbrev(league, away_full)
    commence_time = event.get('commence_time') or event.get('commenceTime') or event.get('startTimeUtc') or ''
    local_date, utc_date = normalize_date_strings(commence_time)
    fetched_at = now_utc_iso()

    def base_row() -> dict[str, Any]:
        return {
            'league': league,
            'sport_key': event.get('sport_key'),
            'event_id': event.get('id'),
            'eventId': event.get('id'),
            'date': local_date,
            'utcDate': utc_date,
            'gameDate': commence_time,
            'startTimeUtc': commence_time,
            'commence_time': commence_time,
            'awayTeam': away,
            'homeTeam': home,
            'matchup': f'{away} @ {home}',
            'marketSpread': None,
            'marketSpreadPerspective': 'away',
            'awaySpread': None,
            'homeSpread': None,
            'awaySpreadOdds': None,
            'homeSpreadOdds': None,
            'spreadLinePairValid': False,
            'spreadPricePairValid': False,
            'marketTotal': None,
            'overOdds': None,
            'underOdds': None,
            'totalLinePairValid': False,
            'totalPricePairValid': False,
            'awayML': None,
            'homeML': None,
            'awayMoneyline': None,
            'homeMoneyline': None,
            'marketAwayML': None,
            'marketHomeML': None,
            'marketSpreadText': None,
            'marketTotalText': None,
            'bookmakerKey': None,
            'bookmakerTitle': None,
            'source': None,
            'updatedAt': None,
            'fetchedAtUtc': fetched_at,
            'marketPriceStatus': 'PARTIAL',
        }

    candidates: list[dict[str, Any]] = []
    for book in event.get('bookmakers', []) or []:
        row = base_row()
        row['bookmakerKey'] = book.get('key')
        row['bookmakerTitle'] = book.get('title')
        row['source'] = f"The Odds API • {book.get('title') or book.get('key')}"
        row['updatedAt'] = book.get('last_update') or fetched_at

        for outcome in market_outcomes(book, 'h2h'):
            name = team_abbrev(league, outcome.get('name', ''))
            if name == home:
                row['homeMoneyline'] = _safe_float(outcome.get('price'))
            elif name == away:
                row['awayMoneyline'] = _safe_float(outcome.get('price'))

        away_point = home_point = away_price = home_price = None
        for outcome in market_outcomes(book, 'spreads'):
            name = team_abbrev(league, outcome.get('name', ''))
            if name == away:
                away_point = _safe_float(outcome.get('point'))
                away_price = _safe_float(outcome.get('price'))
            elif name == home:
                home_point = _safe_float(outcome.get('point'))
                home_price = _safe_float(outcome.get('price'))
        spread_valid = away_point is not None and home_point is not None and abs(away_point + home_point) < 0.001
        row['spreadLinePairValid'] = spread_valid
        if spread_valid:
            row['marketSpread'] = row['awaySpread'] = away_point
            row['homeSpread'] = home_point
            row['awaySpreadOdds'] = away_price
            row['homeSpreadOdds'] = home_price
            row['spreadPricePairValid'] = away_price is not None and home_price is not None

        over_point = under_point = over_price = under_price = None
        for outcome in market_outcomes(book, 'totals'):
            name = str(outcome.get('name', '')).strip().lower()
            if name == 'over':
                over_point = _safe_float(outcome.get('point'))
                over_price = _safe_float(outcome.get('price'))
            elif name == 'under':
                under_point = _safe_float(outcome.get('point'))
                under_price = _safe_float(outcome.get('price'))
        total_valid = over_point is not None and under_point is not None and abs(over_point - under_point) < 0.001
        row['totalLinePairValid'] = total_valid
        if total_valid:
            row['marketTotal'] = over_point
            row['overOdds'] = over_price
            row['underOdds'] = under_price
            row['totalPricePairValid'] = over_price is not None and under_price is not None

        row['awayML'] = row['awayMoneyline']
        row['homeML'] = row['homeMoneyline']
        row['marketAwayML'] = row['awayMoneyline']
        row['marketHomeML'] = row['homeMoneyline']
        has_spread = row['awaySpread'] is not None
        has_total = row['marketTotal'] is not None
        has_ml = row['awayMoneyline'] is not None and row['homeMoneyline'] is not None
        invalid_spread = (away_point is not None or home_point is not None) and not spread_valid
        invalid_total = (over_point is not None or under_point is not None) and not total_valid
        if invalid_spread and invalid_total:
            row['marketPriceStatus'] = 'INVALID_SPREAD_AND_TOTAL_PAIR'
        elif invalid_spread:
            row['marketPriceStatus'] = 'INVALID_SPREAD_PAIR'
        elif invalid_total:
            row['marketPriceStatus'] = 'INVALID_TOTAL_PAIR'
        elif (has_spread and not row['spreadPricePairValid']) or (has_total and not row['totalPricePairValid']):
            row['marketPriceStatus'] = 'PRICE_REQUIRED'
        elif has_ml and (not has_spread or row['spreadPricePairValid']) and (not has_total or row['totalPricePairValid']):
            row['marketPriceStatus'] = 'COMPLETE'

        if row['marketSpread'] is not None:
            row['marketSpreadText'] = f"{float(row['marketSpread']):+g}"
        if row['marketTotal'] is not None:
            row['marketTotalText'] = f"{float(row['marketTotal']):g}"
        candidates.append(row)

    if not candidates:
        return base_row()

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            0 if row.get('spreadPricePairValid') else 1,
            0 if row.get('totalPricePairValid') else 1,
            0 if row.get('awayMoneyline') is not None and row.get('homeMoneyline') is not None else 1,
            _book_priority(row.get('bookmakerKey')),
        )

    return min(candidates, key=sort_key)

def read_games(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def match_rows_to_games(rows: list[dict[str, Any]], games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for game in games:
        league = str(game.get('league', '')).upper()
        if league not in SPORTS:
            continue
        away = str(game.get('awayTeam', '')).upper()
        home = str(game.get('homeTeam', '')).upper()
        date = str(game.get('gameDate', ''))
        by_key.setdefault((league, date, away, home), []).append(game)

    matched: list[dict[str, Any]] = []
    for row in rows:
        league = str(row.get('league', '')).upper()
        away = str(row.get('awayTeam', '')).upper()
        home = str(row.get('homeTeam', '')).upper()
        candidates = by_key.get((league, str(row.get('date', '')), away, home), [])
        if not candidates:
            candidates = by_key.get((league, str(row.get('utcDate', '')), away, home), [])
        if candidates:
            chosen = candidates[0]
            if len(candidates) > 1:
                event_time = str(row.get('startTimeUtc', '') or row.get('gameDate', '') or '')
                def score(g: dict[str, Any]) -> tuple[int, str]:
                    gdt = str(g.get('gameDateTimeUtc', '') or '')
                    return (0 if gdt == event_time else 1, gdt)
                chosen = sorted(candidates, key=score)[0]
            row['id'] = chosen.get('id')
            row['gamePk'] = chosen.get('gamePk')
        matched.append(row)
    return matched


def update_games_json(games_path: Path, rows: list[dict[str, Any]]) -> dict[str, int]:
    games = read_games(games_path)
    counts = {'NBA': 0, 'NHL': 0, 'MLB': 0}
    lookup = {}
    for row in rows:
        key = (str(row.get('league', '')).upper(), str(row.get('date', '')), str(row.get('awayTeam', '')).upper(), str(row.get('homeTeam', '')).upper())
        lookup[key] = row
        lookup[(str(row.get('league', '')).upper(), str(row.get('utcDate', '')), str(row.get('awayTeam', '')).upper(), str(row.get('homeTeam', '')).upper())] = row
    changed = False
    for game in games:
        league = str(game.get('league', '')).upper()
        if league not in counts:
            continue
        key = (league, str(game.get('gameDate', '')), str(game.get('awayTeam', '')).upper(), str(game.get('homeTeam', '')).upper())
        row = lookup.get(key)
        if not row:
            continue
        for field in (
            'marketSpread', 'marketSpreadPerspective', 'awaySpread', 'homeSpread',
            'awaySpreadOdds', 'homeSpreadOdds', 'spreadLinePairValid', 'spreadPricePairValid',
            'marketTotal', 'overOdds', 'underOdds', 'totalLinePairValid', 'totalPricePairValid',
            'marketPriceStatus', 'awayML', 'homeML', 'awayMoneyline', 'homeMoneyline',
            'marketAwayML', 'marketHomeML', 'bookmakerKey', 'bookmakerTitle', 'eventId'
        ):
            game[field] = row.get(field)
        if row.get('marketSpread') is not None:
            game['marketSpreadText'] = row.get('marketSpreadText')
        if row.get('marketTotal') is not None:
            game['marketTotalText'] = row.get('marketTotalText')
        game['marketLineSource'] = row.get('source')
        game['marketLineUpdated'] = row.get('updatedAt') or row.get('fetchedAtUtc')
        if row.get('startTimeUtc') and not game.get('gameDateTimeUtc'):
            game['gameDateTimeUtc'] = row.get('startTimeUtc')
        counts[league] += 1
        changed = True
    if changed:
        games_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding='utf-8')
    return counts


def append_archive(path: Path, rows: list[dict[str, Any]]) -> None:
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            existing = []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append({
            **row,
            'startTimeUtc': row.get('startTimeUtc') or row.get('commence_time') or row.get('gameDate') or '',
            'commence_time': row.get('startTimeUtc') or row.get('commence_time') or row.get('gameDate') or '',
            'archivedAt': row.get('fetchedAtUtc') or now_utc_iso(),
        })

    combined = existing + normalized_rows
    dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in combined:
        key = (
            row.get('league'),
            row.get('event_id'),
            row.get('bookmakerKey'),
            row.get('updatedAt') or row.get('fetchedAtUtc') or row.get('archivedAt'),
        )
        dedup[key] = row
    final_rows = list(dedup.values())
    final_rows.sort(key=lambda r: (
        str(r.get('league', '')),
        str(r.get('date', '')),
        str(r.get('awayTeam', '')),
        str(r.get('homeTeam', '')),
        str(r.get('updatedAt') or r.get('fetchedAtUtc') or r.get('archivedAt') or ''),
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(final_rows, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames = list(rows[0].keys())
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    key = load_key(args.api_key, args.key_file)
    if not key:
        raise SystemExit('No Odds API key found. Set ODDS_API_KEY or save it in C:\\python\\secrets\\the_odds_api_key.txt')

    website_repo = Path(args.website_repo)
    games_path = website_repo / 'data' / 'games.json'
    archive_path = website_repo / 'data' / 'market_lines_archive.json'
    combined_csv = website_repo / 'data' / 'game_lines_odds_api.csv'

    sports = [s.strip().upper() for s in args.sports.split(',') if s.strip()]
    rows: list[dict[str, Any]] = []
    credit_total = 0
    for league in sports:
        sport_key = SPORTS.get(league)
        if not sport_key:
            continue
        events, headers = odds_get(
            key,
            sport_key,
            bookmakers=args.bookmakers,
            regions=args.regions,
            markets=args.markets,
            odds_format=args.odds_format,
            date_format=args.date_format,
            timeout=args.timeout,
        )
        rows.extend(extract_event_row(league, event) for event in events)
        try:
            credit_total += int(headers.get('x-requests-last', '0') or '0')
        except Exception:
            pass
        remaining = headers.get('x-requests-remaining', '?')
        used = headers.get('x-requests-used', '?')
        last = headers.get('x-requests-last', '?')
        print(f'[{league}] fetched {len(events)} events; last call credits: {last}; remaining: {remaining}; used total: {used}')

    games = read_games(games_path)
    rows = match_rows_to_games(rows, games)
    append_archive(archive_path, rows)
    write_csv(combined_csv, rows)

    mlb_rows = [r for r in rows if r.get('league') == 'MLB']
    if mlb_rows:
        write_csv(website_repo / 'data' / 'mlb_market_lines.csv', mlb_rows)

    counts = update_games_json(games_path, rows)
    print(f'Updated games.json -> {games_path}')
    print(f'NBA applied: {counts.get("NBA", 0)}')
    print(f'NHL applied: {counts.get("NHL", 0)}')
    print(f'MLB applied: {counts.get("MLB", 0)}')
    print(f'Wrote combined archive -> {archive_path}')
    print(f'Wrote combined CSV -> {combined_csv}')
    if mlb_rows:
        print(f'Wrote MLB CSV -> {website_repo / "data" / "mlb_market_lines.csv"}')
    print(f'Approx credits used this run: {credit_total}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
