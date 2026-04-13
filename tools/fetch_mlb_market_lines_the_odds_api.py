
"""
set ODDS_API_KEY=YOUR_KEY_HERE
python C:\Docs\letsparlayml.github.io\tools\fetch_mlb_market_lines_the_odds_api.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from zoneinfo import ZoneInfo

API_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
DEFAULT_OUTPUT_DIR = Path(r"C:\python\mlb_model_outputs")
DEFAULT_REPO_DATA_DIR = Path(r"C:\Docs\letsparlayml.github.io\data")
DISPLAY_TZ = ZoneInfo("America/Denver")
DEFAULT_BOOK_PRIORITY = [
    "draftkings", "fanduel", "betmgm", "caesars", "espnbet", "betrivers", "pinnacle", "bet365",
]
TEAM_TO_ABBR = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CHW", "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM", "New York Yankees": "NYY", "Athletics": "OAK",
    "Oakland Athletics": "OAK", "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WSN",
}

@dataclass
class PredictionGame:
    game_pk: int | None
    away_team: str
    home_team: str
    local_date: str
    commence_ts: pd.Timestamp | None


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        out = float(value)
        if pd.isna(out):
            return None
        return out
    except Exception:
        return None


def iso_z(ts: pd.Timestamp | None) -> str:
    if ts is None or pd.isna(ts):
        return ""
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def full_to_abbr(team_name: str) -> str:
    return TEAM_TO_ABBR.get(clean_str(team_name), clean_str(team_name).upper())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch MLB market lines from The Odds API and write site-ready files.")
    parser.add_argument("--api-key", default=os.environ.get("ODDS_API_KEY", ""))
    parser.add_argument("--regions", default="us")
    parser.add_argument("--markets", default="h2h,spreads,totals")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--repo-data-dir", default=str(DEFAULT_REPO_DATA_DIR))
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def get_json(url: str, params: dict[str, Any], timeout: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "LetsParlayML MLB line fetcher/1.0"})
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected API payload shape; expected a list of events.")
    return payload, dict(response.headers)


def load_prediction_games(output_dir: Path) -> list[PredictionGame]:
    files = sorted(output_dir.glob("game_predictions_*.csv"))
    games: list[PredictionGame] = []
    for path in files:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        for _, row in df.iterrows():
            away_team = clean_str(row.get("away_team"))
            home_team = clean_str(row.get("home_team"))
            if not away_team or not home_team:
                continue
            raw_dt = row.get("gameDate")
            ts = pd.to_datetime(raw_dt, errors="coerce", utc=True)
            local_date = ""
            if not pd.isna(ts):
                local_date = ts.tz_convert(DISPLAY_TZ).date().isoformat()
            if not local_date:
                tgd = pd.to_datetime(row.get("target_game_date"), errors="coerce")
                if not pd.isna(tgd):
                    local_date = tgd.date().isoformat()
            games.append(PredictionGame(
                game_pk=int(row.get("gamePk")) if safe_float(row.get("gamePk")) is not None else None,
                away_team=away_team, home_team=home_team, local_date=local_date, commence_ts=None if pd.isna(ts) else ts,
            ))
    return games


def assign_game_pk(event_ts: pd.Timestamp | None, away_abbr: str, home_abbr: str, local_date: str, prediction_games: list[PredictionGame]) -> int | None:
    candidates = [g for g in prediction_games if g.away_team == away_abbr and g.home_team == home_abbr and g.local_date == local_date]
    if not candidates:
        return None
    if len(candidates) == 1 or event_ts is None:
        return candidates[0].game_pk
    best_game = None
    best_delta = None
    for game in candidates:
        if game.commence_ts is None:
            if best_game is None:
                best_game = game
            continue
        delta = abs((game.commence_ts - event_ts).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_game = game
    return None if best_game is None else best_game.game_pk


def outcome_lookup(market: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in market.get("outcomes") or []:
        name = clean_str(item.get("name"))
        if name:
            lookup[name] = item
    return lookup


def selected_sort_key(bookmaker_key: str, has_spread: bool, has_total: bool, has_ml: bool):
    try:
        idx = DEFAULT_BOOK_PRIORITY.index(bookmaker_key)
    except ValueError:
        idx = len(DEFAULT_BOOK_PRIORITY) + 50
    return (0 if has_spread else 1, 0 if has_total else 1, 0 if has_ml else 1, idx, bookmaker_key)


def build_rows(events: list[dict[str, Any]], prediction_games: list[PredictionGame]):
    raw_rows = []
    selected_map: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = clean_str(event.get("id"))
        commence_ts = pd.to_datetime(event.get("commence_time"), errors="coerce", utc=True)
        commence_iso = iso_z(None if pd.isna(commence_ts) else commence_ts)
        local_date = commence_ts.tz_convert(DISPLAY_TZ).date().isoformat() if not pd.isna(commence_ts) else ''
        home_full = clean_str(event.get("home_team"))
        away_full = clean_str(event.get("away_team"))
        home_abbr = full_to_abbr(home_full)
        away_abbr = full_to_abbr(away_full)
        matchup = f"{away_abbr} @ {home_abbr}"
        game_pk = assign_game_pk(None if pd.isna(commence_ts) else commence_ts, away_abbr, home_abbr, local_date, prediction_games)
        for book in event.get("bookmakers") or []:
            book_key = clean_str(book.get("key"))
            book_title = clean_str(book.get("title"))
            updated_ts = pd.to_datetime(book.get("last_update"), errors="coerce", utc=True)
            updated_iso = iso_z(None if pd.isna(updated_ts) else updated_ts)
            away_ml = home_ml = None
            away_spread_point = away_spread_price = None
            home_spread_point = home_spread_price = None
            total_point = over_price = under_price = None
            for market in book.get("markets") or []:
                mkey = clean_str(market.get("key"))
                outcomes = outcome_lookup(market)
                if mkey == 'h2h':
                    away_ml = safe_float((outcomes.get(away_full) or {}).get('price'))
                    home_ml = safe_float((outcomes.get(home_full) or {}).get('price'))
                elif mkey == 'spreads':
                    away = outcomes.get(away_full) or {}
                    home = outcomes.get(home_full) or {}
                    away_spread_point = safe_float(away.get('point'))
                    away_spread_price = safe_float(away.get('price'))
                    home_spread_point = safe_float(home.get('point'))
                    home_spread_price = safe_float(home.get('price'))
                elif mkey == 'totals':
                    over = outcomes.get('Over') or {}
                    under = outcomes.get('Under') or {}
                    total_point = safe_float(over.get('point'))
                    if total_point is None:
                        total_point = safe_float(under.get('point'))
                    over_price = safe_float(over.get('price'))
                    under_price = safe_float(under.get('price'))
            row = {
                'league': 'MLB',
                'gamePk': game_pk,
                'eventId': event_id,
                'date': local_date,
                'gameDate': commence_iso,
                'awayTeam': away_abbr,
                'homeTeam': home_abbr,
                'matchup': matchup,
                'marketSpread': away_spread_point,
                'marketTotal': total_point,
                'awayMoneyline': away_ml,
                'homeMoneyline': home_ml,
                'awaySpreadPrice': away_spread_price,
                'homeSpreadPrice': home_spread_price,
                'overPrice': over_price,
                'underPrice': under_price,
                'source': f'The Odds API • {book_title or book_key}',
                'bookmakerKey': book_key,
                'bookmakerTitle': book_title,
                'updatedAt': updated_iso,
            }
            raw_rows.append(row)
            has_spread = away_spread_point is not None
            has_total = total_point is not None
            has_ml = away_ml is not None and home_ml is not None
            game_key = str(game_pk) if game_pk is not None else f"{local_date}|{matchup}|{commence_iso}"
            current = selected_map.get(game_key)
            if current is None or selected_sort_key(book_key, has_spread, has_total, has_ml) < current['__sort_key']:
                chosen = dict(row)
                chosen['__sort_key'] = selected_sort_key(book_key, has_spread, has_total, has_ml)
                selected_map[game_key] = chosen
    selected_rows = []
    for row in selected_map.values():
        row = dict(row)
        row.pop('__sort_key', None)
        if row.get('gamePk') in (None, ''):
            digest = hashlib.md5(f"{row['date']}|{row['matchup']}|{row['gameDate']}".encode('utf-8')).hexdigest()[:12]
            row['syntheticGameKey'] = f'mlb-{digest}'
        selected_rows.append(row)
    selected_rows.sort(key=lambda x: (clean_str(x.get('date')), clean_str(x.get('gameDate')), clean_str(x.get('matchup'))))
    raw_rows.sort(key=lambda x: (clean_str(x.get('date')), clean_str(x.get('gameDate')), clean_str(x.get('bookmakerKey')), clean_str(x.get('matchup'))))
    return selected_rows, raw_rows


def merge_archive(existing: list[dict[str, Any]], mlb_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> str:
        matchup = clean_str(row.get('matchup'))
        if not matchup and clean_str(row.get('awayTeam')) and clean_str(row.get('homeTeam')):
            matchup = f"{clean_str(row.get('awayTeam'))} @ {clean_str(row.get('homeTeam'))}"
        return f"{clean_str(row.get('date'))}|{clean_str(row.get('league')).upper()}|{matchup}"
    merged = {key(r): dict(r) for r in existing if isinstance(r, dict)}
    for row in mlb_rows:
        merged[key(row)] = dict(row)
    out = list(merged.values())
    out.sort(key=lambda r: (clean_str(r.get('date')), clean_str(r.get('league')), clean_str(r.get('matchup'))))
    return out


def write_outputs(selected_rows, raw_rows, output_dir: Path, repo_data_dir: Path | None):
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_csv = output_dir / 'mlb_market_lines.csv'
    raw_json = output_dir / 'mlb_market_lines_raw.json'
    archive_json = output_dir / 'mlb_market_lines_archive.json'
    pd.DataFrame(selected_rows).to_csv(selected_csv, index=False)
    raw_json.write_text(json.dumps(raw_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    archive_json.write_text(json.dumps(selected_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    if repo_data_dir is not None:
        repo_data_dir.mkdir(parents=True, exist_ok=True)
        (repo_data_dir / 'mlb_market_lines.csv').write_text(selected_csv.read_text(encoding='utf-8'), encoding='utf-8')
        (repo_data_dir / 'mlb_market_lines_archive.json').write_text(json.dumps(selected_rows, ensure_ascii=False, indent=2), encoding='utf-8')
        shared_archive_path = repo_data_dir / 'market_lines_archive.json'
        existing = []
        if shared_archive_path.exists():
            try:
                existing = json.loads(shared_archive_path.read_text(encoding='utf-8'))
            except Exception:
                existing = []
        merged = merge_archive(existing, selected_rows)
        shared_archive_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> int:
    args = parse_args()
    if not args.api_key:
        raise SystemExit('Missing API key. Pass --api-key or set ODDS_API_KEY.')
    output_dir = Path(args.output_dir)
    repo_data_dir = Path(args.repo_data_dir) if args.repo_data_dir else None
    params = {
        'apiKey': args.api_key,
        'regions': args.regions,
        'markets': args.markets,
        'oddsFormat': 'american',
        'dateFormat': 'iso',
    }
    if clean_str(args.bookmakers):
        params['bookmakers'] = clean_str(args.bookmakers)
    events, headers = get_json(API_URL, params=params, timeout=args.timeout)
    prediction_games = load_prediction_games(output_dir)
    selected_rows, raw_rows = build_rows(events, prediction_games)
    write_outputs(selected_rows, raw_rows, output_dir, repo_data_dir)
    print(f'Fetched {len(events)} MLB events.')
    print(f'Wrote {len(selected_rows)} selected market-line rows to {output_dir / "mlb_market_lines.csv"}')
    if repo_data_dir is not None:
        print(f'Mirrored dedicated MLB line files into {repo_data_dir}')
    used = headers.get('x-requests-used')
    remaining = headers.get('x-requests-remaining')
    if used or remaining:
        print(f'API usage headers: used={used or "?"} remaining={remaining or "?"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
