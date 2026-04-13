#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
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


def team_abbrev(league: str, name: str) -> str:
    val = TEAM_MAP.get(name)
    if val and val[0] == league:
        return val[1]
    return name


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


def extract_event_row(league: str, event: dict[str, Any]) -> dict[str, Any]:
    bookmakers = event.get('bookmakers', []) or []
    picked = pick_bookmaker(bookmakers)
    home = team_abbrev(league, event.get('home_team', ''))
    away = team_abbrev(league, event.get('away_team', ''))
    commence_time = event.get('commence_time') or event.get('commenceTime') or event.get('startTimeUtc') or ''
    local_date, utc_date = normalize_date_strings(commence_time)
    row: dict[str, Any] = {
        'league': league,
        'sport_key': event.get('sport_key'),
        'event_id': event.get('id'),
        'date': local_date,
        'utcDate': utc_date,
        'gameDate': commence_time,
        'startTimeUtc': commence_time,
        'commence_time': commence_time,
        'awayTeam': away,
        'homeTeam': home,
        'marketSpread': None,
        'marketTotal': None,
        'marketAwayML': None,
        'marketHomeML': None,
        'marketSpreadText': None,
        'marketTotalText': None,
        'bookmakerKey': None,
        'bookmakerTitle': None,
        'source': None,
        'updatedAt': None,
        'fetchedAtUtc': now_utc_iso(),
    }
    if not picked:
        return row

    row['bookmakerKey'] = picked.get('key')
    row['bookmakerTitle'] = picked.get('title')
    row['source'] = f"The Odds API • {picked.get('title')}"
    row['updatedAt'] = picked.get('last_update') or row['fetchedAtUtc']

    for outcome in market_outcomes(picked, 'h2h'):
        name = team_abbrev(league, outcome.get('name', ''))
        if name == home:
            row['marketHomeML'] = outcome.get('price')
        elif name == away:
            row['marketAwayML'] = outcome.get('price')

    for outcome in market_outcomes(picked, 'spreads'):
        name = team_abbrev(league, outcome.get('name', ''))
        if name == away:
            row['marketSpread'] = outcome.get('point')
            break

    for outcome in market_outcomes(picked, 'totals'):
        name = str(outcome.get('name', '')).lower()
        if name in ('over', 'under') and row['marketTotal'] is None:
            row['marketTotal'] = outcome.get('point')

    if row['marketSpread'] is not None:
        try:
            row['marketSpreadText'] = f"{float(row['marketSpread']):+g}"
        except Exception:
            row['marketSpreadText'] = str(row['marketSpread'])
    if row['marketTotal'] is not None:
        try:
            row['marketTotalText'] = f"{float(row['marketTotal']):g}"
        except Exception:
            row['marketTotalText'] = str(row['marketTotal'])
    return row


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
        if row.get('marketSpread') is not None:
            game['marketSpread'] = row['marketSpread']
            game['marketSpreadText'] = row.get('marketSpreadText')
        if row.get('marketTotal') is not None:
            game['marketTotal'] = row['marketTotal']
            game['marketTotalText'] = row.get('marketTotalText')
        game['marketHomeML'] = row.get('marketHomeML')
        game['marketAwayML'] = row.get('marketAwayML')
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
