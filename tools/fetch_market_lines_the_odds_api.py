
from __future__ import annotations

import argparse
import json
import os
import unicodedata
from datetime import datetime, timezone
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


def normalize_team_name(value: Any) -> str:
    """Return a stable lookup key for sportsbook/team names.

    The Odds API can return accented names for some teams, especially
    "Montréal Canadiens". The site schedule/model data uses plain
    abbreviations like MTL, so all team-name matching needs to be accent-
    insensitive instead of relying only on exact strings.
    """
    text = clean(value)
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


def team_lookup_for(league: str) -> dict[str, str]:
    mapping = TEAM_MAPS.get(league, {})
    lookup: dict[str, str] = {}
    for full_name, abbr in mapping.items():
        lookup[clean(full_name)] = abbr
        lookup[normalize_team_name(full_name)] = abbr
        lookup[abbr.upper()] = abbr
    # Explicit alias for Odds API NHL payloads that include the accent.
    if league == 'NHL':
        lookup[normalize_team_name('Montréal Canadiens')] = 'MTL'
    return lookup


def team_abbrev(league: str, value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    lookup = team_lookup_for(league)
    return lookup.get(text) or lookup.get(normalize_team_name(text)) or text.upper()


def outcome_for_team(outcomes: dict[str, dict[str, Any]], team_name: Any) -> dict[str, Any]:
    """Find a sportsbook outcome even if the event/outcome accenting differs."""
    exact = outcomes.get(clean(team_name))
    if exact is not None:
        return exact
    wanted = normalize_team_name(team_name)
    for name, outcome in outcomes.items():
        if normalize_team_name(name) == wanted:
            return outcome
    return {}


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


def local_date_from_iso(value: str) -> str:
    if not value:
        return ''
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.astimezone(DISPLAY_TZ).date().isoformat()


def game_sort_key(row: dict[str, Any]) -> tuple:
    key = clean(row.get('bookmakerKey')).lower()
    try:
        idx = BOOK_PRIORITY.index(key)
    except ValueError:
        idx = len(BOOK_PRIORITY) + 50
    spread_pair = bool(row.get('spreadPricePairValid'))
    total_pair = bool(row.get('totalPricePairValid'))
    has_spread = row.get('awaySpread') is not None and row.get('homeSpread') is not None
    has_total = row.get('marketTotal') is not None
    has_ml = row.get('awayMoneyline') is not None and row.get('homeMoneyline') is not None
    # Select one bookmaker snapshot as a unit. Complete point/price pairs win,
    # then bookmaker priority breaks ties.
    return (0 if spread_pair else 1, 0 if total_pair else 1, 0 if has_ml else 1,
            0 if has_spread else 1, 0 if has_total else 1, idx, key)


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


def build_selected_rows(events: list[dict[str, Any]], league: str) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    now_utc = datetime.now(timezone.utc)
    skipped_started = 0
    for event in events:
        commence = iso_z(clean(event.get('commence_time')))
        try:
            commence_dt = datetime.fromisoformat(commence.replace('Z', '+00:00')) if commence else None
        except Exception:
            commence_dt = None
        if commence_dt is not None and commence_dt <= now_utc:
            skipped_started += 1
            continue

        home_full = clean(event.get('home_team'))
        away_full = clean(event.get('away_team'))
        home = team_abbrev(league, home_full)
        away = team_abbrev(league, away_full)
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
                'marketSpreadPerspective': 'away',
                'awaySpread': None,
                'homeSpread': None,
                'awaySpreadOdds': None,
                'homeSpreadOdds': None,
                'spreadLinePairValid': False,
                'spreadPricePairValid': False,
                'marketTotal': None,
                'totalLinePairValid': False,
                'overOdds': None,
                'underOdds': None,
                'totalPricePairValid': False,
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
            away_point = home_point = over_point = under_point = None
            for market in book.get('markets') or []:
                mkey = clean(market.get('key'))
                outcomes = {clean(o.get('name')): o for o in (market.get('outcomes') or [])}
                if mkey == 'h2h':
                    row['awayMoneyline'] = to_float(outcome_for_team(outcomes, away_full).get('price'))
                    row['homeMoneyline'] = to_float(outcome_for_team(outcomes, home_full).get('price'))
                elif mkey == 'spreads':
                    away_outcome = outcome_for_team(outcomes, away_full)
                    home_outcome = outcome_for_team(outcomes, home_full)
                    away_point = to_float(away_outcome.get('point'))
                    home_point = to_float(home_outcome.get('point'))
                    away_price = to_float(away_outcome.get('price'))
                    home_price = to_float(home_outcome.get('price'))
                    line_pair_valid = (
                        away_point is not None and home_point is not None
                        and abs(away_point + home_point) < 0.001
                    )
                    row['spreadLinePairValid'] = line_pair_valid
                    if line_pair_valid:
                        row['awaySpread'] = away_point
                        row['homeSpread'] = home_point
                        row['marketSpread'] = away_point
                        row['awaySpreadOdds'] = away_price
                        row['homeSpreadOdds'] = home_price
                        row['spreadPricePairValid'] = away_price is not None and home_price is not None
                elif mkey == 'totals':
                    over = outcomes.get('Over') or {}
                    under = outcomes.get('Under') or {}
                    over_point = to_float(over.get('point'))
                    under_point = to_float(under.get('point'))
                    over_price = to_float(over.get('price'))
                    under_price = to_float(under.get('price'))
                    total_pair_valid = (
                        over_point is not None and under_point is not None
                        and abs(over_point - under_point) < 0.001
                    )
                    row['totalLinePairValid'] = total_pair_valid
                    if total_pair_valid:
                        row['marketTotal'] = over_point
                        row['overOdds'] = over_price
                        row['underOdds'] = under_price
                        row['totalPricePairValid'] = over_price is not None and under_price is not None

            row['marketAwayML'] = row['awayMoneyline']
            row['marketHomeML'] = row['homeMoneyline']
            row['awayML'] = row['awayMoneyline']
            row['homeML'] = row['homeMoneyline']
            has_spread_points = row['marketSpread'] is not None
            has_total_point = row['marketTotal'] is not None
            has_ml_pair = row['awayMoneyline'] is not None and row['homeMoneyline'] is not None
            invalid_spread_pair = any(v is not None for v in (away_point, home_point))
            invalid_spread_pair = invalid_spread_pair and not row['spreadLinePairValid']
            invalid_total_pair = any(v is not None for v in (over_point, under_point))
            invalid_total_pair = invalid_total_pair and not row['totalLinePairValid']
            missing_price_for_point = (has_spread_points and not row['spreadPricePairValid']) or (has_total_point and not row['totalPricePairValid'])
            if invalid_spread_pair and invalid_total_pair:
                row['marketPriceStatus'] = 'INVALID_SPREAD_AND_TOTAL_PAIR'
            elif invalid_spread_pair:
                row['marketPriceStatus'] = 'INVALID_SPREAD_PAIR'
            elif invalid_total_pair:
                row['marketPriceStatus'] = 'INVALID_TOTAL_PAIR'
            elif missing_price_for_point:
                row['marketPriceStatus'] = 'PRICE_REQUIRED'
            elif has_ml_pair and (not has_spread_points or row['spreadPricePairValid']) and (not has_total_point or row['totalPricePairValid']):
                row['marketPriceStatus'] = 'COMPLETE'
            else:
                row['marketPriceStatus'] = 'PARTIAL'

            key = (league, local_date, away, home)
            cur = selected.get(key)
            if cur is None or game_sort_key(row) < game_sort_key(cur):
                selected[key] = row

    rows = sorted(selected.values(), key=lambda r: (r['date'], r['awayTeam'], r['homeTeam']))
    if skipped_started:
        print(f'[ODDS] {league}: skipped {skipped_started} started/live events to preserve pregame close')
    return rows

def apply_to_games(games: list[dict[str, Any]], selected_rows: list[dict[str, Any]]):
    lookup = {(r['league'], r['date'], r['awayTeam'], r['homeTeam']): r for r in selected_rows}
    applied = 0
    passthrough = [
        'awayML', 'homeML', 'awayMoneyline', 'homeMoneyline', 'marketAwayML', 'marketHomeML',
        'marketSpread', 'marketSpreadPerspective', 'awaySpread', 'homeSpread',
        'awaySpreadOdds', 'homeSpreadOdds', 'spreadLinePairValid', 'spreadPricePairValid',
        'marketTotal', 'overOdds', 'underOdds', 'totalLinePairValid', 'totalPricePairValid', 'marketPriceStatus',
        'bookmakerKey', 'bookmakerTitle', 'eventId',
    ]
    for g in games:
        league = clean(g.get('league')).upper()
        away = clean(g.get('awayTeam')).upper()
        home = clean(g.get('homeTeam')).upper()
        date = clean(g.get('gameDate') or g.get('date'))
        row = lookup.get((league, date, away, home))
        if not row:
            continue
        for field in passthrough:
            g[field] = row.get(field)
        g['marketLineSource'] = row.get('source')
        g['marketLineUpdated'] = row.get('updatedAt') or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        g['marketUpdatedAt'] = g['marketLineUpdated']
        g['marketLineAgeHours'] = 0.0
        g['marketLineStatus'] = 'CURRENT'
        if row.get('gameDate'):
            g['gameDateTimeUtc'] = row['gameDate']
        applied += 1
    return applied

def merge_archive(archive: list[dict[str, Any]], selected_rows: list[dict[str, Any]]):
    # Preserve every existing historical snapshot. Only replace an exact snapshot
    # identity when the newly fetched row carries richer fields.
    merged = list(archive)
    index: dict[tuple[str, ...], int] = {}
    for i, row in enumerate(merged):
        identity = (
            clean(row.get('league')).upper(), clean(row.get('date')),
            clean(row.get('awayTeam')).upper(), clean(row.get('homeTeam')).upper(),
            clean(row.get('eventId')), clean(row.get('bookmakerKey')).lower(), clean(row.get('updatedAt')),
        )
        index[identity] = i
    for row in selected_rows:
        identity = (
            clean(row.get('league')).upper(), clean(row.get('date')),
            clean(row.get('awayTeam')).upper(), clean(row.get('homeTeam')).upper(),
            clean(row.get('eventId')), clean(row.get('bookmakerKey')).lower(), clean(row.get('updatedAt')),
        )
        if identity in index:
            merged[index[identity]] = {**merged[index[identity]], **row}
        else:
            index[identity] = len(merged)
            merged.append(row)
    return merged

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

    repo = Path(args.website_repo)
    data_dir = repo / 'data'
    games_path = data_dir / 'games.json'
    archive_path = data_dir / 'market_lines_archive.json'
    games = load_json(games_path, [])
    archive = load_json(archive_path, [])
    session = requests.Session()
    session.headers.update({'User-Agent': 'LetsParlayML unified odds fetcher/1.0'})

    all_selected: list[dict[str, Any]] = []
    for sport_key in [s.strip() for s in args.sports.split(',') if s.strip()]:
        league = SPORTS.get(sport_key)
        if not league:
            print(f'[ODDS] skip unknown sport: {sport_key}')
            continue
        events = api_get(session, sport_key, args.api_key, args.timeout, args.bookmakers)
        selected = build_selected_rows(events, league)
        all_selected.extend(selected)
        print(f'[ODDS] {league}: fetched {len(events)} events, selected {len(selected)} rows')
        raw_path = data_dir / f'{league.lower()}_market_lines_api.json'
        raw_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')

    applied = apply_to_games(games, all_selected)
    merged_archive = merge_archive(archive, all_selected)
    save_json(games_path, games)
    save_json(archive_path, merged_archive)
    print(f'[ODDS] Updated {applied} games in {games_path}')
    print(f'[ODDS] Archive now has {len(merged_archive)} rows in {archive_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
