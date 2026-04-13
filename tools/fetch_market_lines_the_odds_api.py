from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("America/Denver")
BOOK_PRIORITY = [
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
    "basketball_nba": "NBA",
    "icehockey_nhl": "NHL",
    "baseball_mlb": "MLB",
}
TEAM_MAPS = {
    "NBA": {
        "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
        "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
        "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
        "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
        "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
        "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
        "Utah Jazz": "UTA", "Washington Wizards": "WAS",
    },
    "NHL": {
        "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Calgary Flames": "CGY",
        "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ",
        "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
        "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL", "Nashville Predators": "NSH",
        "New Jersey Devils": "NJD", "New York Islanders": "NYI", "New York Rangers": "NYR", "Ottawa Senators": "OTT",
        "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
        "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR", "Utah Hockey Club": "UTA",
        "Utah Mammoth": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Washington Capitals": "WSH",
        "Winnipeg Jets": "WPG",
    },
    "MLB": {
        "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
        "Chicago Cubs": "CHC", "Chicago White Sox": "CHW", "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
        "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
        "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
        "Minnesota Twins": "MIN", "New York Mets": "NYM", "New York Yankees": "NYY", "Athletics": "OAK",
        "Oakland Athletics": "OAK", "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
        "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TBR",
        "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WSN",
    },
}

def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()

def to_float(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None

def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def iso_z(value: str) -> str:
    return value.replace('+00:00', 'Z') if value else ''

def parse_iso(value: str):
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)
    except Exception:
        return None

def local_date_from_iso(value: str) -> str:
    dt = parse_iso(value)
    if dt is None:
        return ''
    return dt.astimezone(DISPLAY_TZ).date().isoformat()

def game_sort_key(row: dict[str, Any]) -> tuple:
    key = clean(row.get('bookmakerKey')).lower()
    try:
        idx = BOOK_PRIORITY.index(key)
    except ValueError:
        idx = len(BOOK_PRIORITY) + 50
    has_spread = row.get('marketSpread') is not None
    has_total = row.get('marketTotal') is not None
    has_ml = row.get('awayMoneyline') is not None and row.get('homeMoneyline') is not None
    return (0 if has_spread else 1, 0 if has_total else 1, 0 if has_ml else 1, idx, key)

def api_get(session: requests.Session, sport_key: str, api_key: str, timeout: int, bookmakers: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h,spreads,totals',
        'oddsFormat': 'american',
        'dateFormat': 'iso',
    }
    if bookmakers:
        params['bookmakers'] = bookmakers
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds'
    resp = session.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f'Unexpected payload for {sport_key}')
    return data

def build_selected_rows(events: list[dict[str, Any]], league: str, now_utc: datetime) -> list[dict[str, Any]]:
    team_map = TEAM_MAPS[league]
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    skipped_live = 0
    for event in events:
        commence = iso_z(clean(event.get('commence_time')))
        commence_dt = parse_iso(commence)
        if commence_dt is not None and commence_dt <= now_utc:
            skipped_live += 1
            continue
        home_full = clean(event.get('home_team'))
        away_full = clean(event.get('away_team'))
        home = team_map.get(home_full, home_full.upper())
        away = team_map.get(away_full, away_full.upper())
        local_date = local_date_from_iso(commence)
        if not away or not home or not local_date:
            continue
        for book in event.get('bookmakers') or []:
            row = {
                'league': league,
                'eventId': clean(event.get('id')),
                'date': local_date,
                'gameDate': commence,
                'awayTeam': away,
                'homeTeam': home,
                'matchup': f'{away} @ {home}',
                'marketSpread': None,
                'marketTotal': None,
                'awayMoneyline': None,
                'homeMoneyline': None,
                'marketAwayML': None,
                'marketHomeML': None,
                'awayML': None,
                'homeML': None,
                'source': f"The Odds API • {clean(book.get('title')) or clean(book.get('key'))}",
                'bookmakerKey': clean(book.get('key')).lower(),
                'bookmakerTitle': clean(book.get('title')),
                'updatedAt': iso_z(clean(book.get('last_update'))),
            }
            for market in book.get('markets') or []:
                mkey = clean(market.get('key'))
                outcomes = {clean(o.get('name')): o for o in (market.get('outcomes') or [])}
                if mkey == 'h2h':
                    row['awayMoneyline'] = to_float((outcomes.get(away_full) or {}).get('price'))
                    row['homeMoneyline'] = to_float((outcomes.get(home_full) or {}).get('price'))
                elif mkey == 'spreads':
                    row['marketSpread'] = to_float((outcomes.get(away_full) or {}).get('point'))
                elif mkey == 'totals':
                    over = outcomes.get('Over') or {}
                    under = outcomes.get('Under') or {}
                    row['marketTotal'] = to_float(over.get('point')) if to_float(over.get('point')) is not None else to_float(under.get('point'))
            row['marketAwayML'] = row['awayMoneyline']
            row['marketHomeML'] = row['homeMoneyline']
            row['awayML'] = row['awayMoneyline']
            row['homeML'] = row['homeMoneyline']
            key = (league, local_date, away, home)
            cur = selected.get(key)
            if cur is None or game_sort_key(row) < game_sort_key(cur):
                selected[key] = row
    rows = sorted(selected.values(), key=lambda r: (r['date'], r['awayTeam'], r['homeTeam']))
    return rows, skipped_live

def apply_to_games(games: list[dict[str, Any]], selected_rows: list[dict[str, Any]], now_utc: datetime):
    lookup = {(r['league'], r['date'], r['awayTeam'], r['homeTeam']): r for r in selected_rows}
    applied = 0
    for g in games:
        game_dt = parse_iso(clean(g.get('gameDateTimeUtc') or g.get('gameDate') or ''))
        if game_dt is not None and game_dt <= now_utc:
            continue
        league = clean(g.get('league')).upper()
        away = clean(g.get('awayTeam')).upper()
        home = clean(g.get('homeTeam')).upper()
        date = clean(g.get('gameDate') or g.get('date'))
        row = lookup.get((league, date, away, home))
        if not row:
            continue
        g['marketSpread'] = row.get('marketSpread')
        g['marketTotal'] = row.get('marketTotal')
        g['marketAwayML'] = row.get('marketAwayML')
        g['marketHomeML'] = row.get('marketHomeML')
        g['marketLineSource'] = row.get('source')
        g['marketLineUpdated'] = row.get('updatedAt') or datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')
        if row.get('gameDate'):
            g['gameDateTimeUtc'] = row['gameDate']
        applied += 1
    return applied

def merge_archive(archive: list[dict[str, Any]], selected_rows: list[dict[str, Any]]):
    same_game = {(r['league'], r['date'], r['awayTeam'], r['homeTeam']) for r in selected_rows}
    cleaned = []
    for row in archive:
        league = clean(row.get('league')).upper()
        away = clean(row.get('awayTeam') or (clean(row.get('matchup')).split('@')[0].strip() if '@' in clean(row.get('matchup')) else '')).upper()
        home = clean(row.get('homeTeam') or (clean(row.get('matchup')).split('@')[1].strip() if '@' in clean(row.get('matchup')) else '')).upper()
        date = clean(row.get('date'))
        source = clean(row.get('source'))
        key = (league, date, away, home)
        if key in same_game and source in {'games.json', 'manual', 'manual_nhl_lines.csv', 'TeamRankings NBA matchup page'}:
            continue
        cleaned.append(row)
    cleaned.extend(selected_rows)
    return cleaned

def main() -> int:
    ap = argparse.ArgumentParser(description='Fetch NBA/NHL/MLB market lines from The Odds API and update site data.')
    ap.add_argument('--api-key', default=os.environ.get('ODDS_API_KEY', ''))
    ap.add_argument('--website-repo', required=True)
    ap.add_argument('--sports', default='basketball_nba,icehockey_nhl,baseball_mlb')
    ap.add_argument('--bookmakers', default='')
    ap.add_argument('--timeout', type=int, default=30)
    args = ap.parse_args()
    if not args.api_key:
        raise SystemExit('Missing API key. Pass --api-key or set ODDS_API_KEY.')

    now_utc = datetime.now(UTC)
    repo = Path(args.website_repo)
    data_dir = repo / 'data'
    games_path = data_dir / 'games.json'
    archive_path = data_dir / 'market_lines_archive.json'
    games = load_json(games_path, [])
    archive = load_json(archive_path, [])
    session = requests.Session()
    session.headers.update({'User-Agent': 'LetsParlayML unified odds fetcher/1.1'})

    all_selected: list[dict[str, Any]] = []
    for sport_key in [s.strip() for s in args.sports.split(',') if s.strip()]:
        league = SPORTS.get(sport_key)
        if not league:
            print(f'[ODDS] skip unknown sport: {sport_key}')
            continue
        events = api_get(session, sport_key, args.api_key, args.timeout, args.bookmakers)
        selected, skipped_live = build_selected_rows(events, league, now_utc)
        all_selected.extend(selected)
        print(f'[ODDS] {league}: fetched {len(events)} events, selected {len(selected)} pregame rows, skipped {skipped_live} live/started events')
        raw_path = data_dir / f'{league.lower()}_market_lines_api.json'
        raw_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')

    applied = apply_to_games(games, all_selected, now_utc)
    merged_archive = merge_archive(archive, all_selected)
    save_json(games_path, games)
    save_json(archive_path, merged_archive)
    print(f'[ODDS] Updated {applied} pregame games in {games_path}')
    print(f'[ODDS] Archive now has {len(merged_archive)} rows in {archive_path}')
    print('[ODDS] Lines now freeze once the scheduled start time has passed.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
