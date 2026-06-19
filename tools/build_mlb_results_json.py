#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_MLB_DATA_DIR = Path(os.environ.get('MLB_DATA_DIR', r'C:\python\mlb_data'))


def clean_str(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    return '' if text.lower() == 'nan' else text


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == '':
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def safe_int(value: Any) -> int | None:
    val = safe_float(value)
    return None if val is None else int(round(val))


def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default



def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')



def load_table_latest(base_dir: Path, table: str) -> pd.DataFrame:
    table_dir = base_dir / table
    parquet_path = table_dir / f'{table}_latest.parquet'
    csv_path = table_dir / f'{table}_latest.csv'
    try:
        if parquet_path.exists():
            return pd.read_parquet(parquet_path)
        if csv_path.exists():
            return pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()



def fetch_live_feed(game_pk: int) -> dict[str, Any] | None:
    url = f'https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live'
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))



def build_fallback_row_from_feed(feed: dict[str, Any]) -> dict[str, Any] | None:
    game_data = feed.get('gameData', {}) or {}
    live = feed.get('liveData', {}) or {}
    linescore = live.get('linescore', {}) or {}
    teams = linescore.get('teams', {}) or {}
    home = (game_data.get('teams', {}) or {}).get('home', {}) or {}
    away = (game_data.get('teams', {}) or {}).get('away', {}) or {}

    game_pk = (game_data.get('game') or {}).get('pk') or game_data.get('gamePk')
    status_detailed = clean_str((game_data.get('status') or {}).get('detailedState'))
    home_total = safe_int((teams.get('home') or {}).get('runs'))
    away_total = safe_int((teams.get('away') or {}).get('runs'))
    innings = linescore.get('innings') or []
    first = innings[0] if innings else {}
    away_1 = safe_int(((first.get('away') or {}).get('runs')))
    home_1 = safe_int(((first.get('home') or {}).get('runs')))
    game_dt = ((game_data.get('datetime') or {}).get('dateTime'))

    return {
        'gamePk': game_pk,
        'gameDate': game_dt,
        'status_detailed': status_detailed,
        'away_team': clean_str(away.get('abbreviation') or away.get('name')),
        'home_team': clean_str(home.get('abbreviation') or home.get('name')),
        'away_total': away_total,
        'home_total': home_total,
        'away_1': away_1,
        'home_1': home_1,
    }



def is_final_status(status: Any) -> bool:
    text = clean_str(status).lower()
    return 'final' in text



def local_game_date(game: dict[str, Any], fallback_iso: str = '') -> str:
    site_date = clean_str(game.get('gameDate'))
    if site_date:
        return site_date
    raw = clean_str(game.get('gameDateTimeUtc')) or clean_str(game.get('gameDateTime')) or fallback_iso
    if not raw:
        return ''
    try:
        ts = pd.to_datetime(raw, utc=True)
        return ts.tz_convert('America/Denver').date().isoformat()
    except Exception:
        return clean_str(raw)[:10]



def ml_result_label(pred_home: float | None, pred_away: float | None, actual_home: int, actual_away: int) -> str:
    if pred_home is None or pred_away is None:
        return 'Pending'
    pred_home_win = pred_home > pred_away
    if actual_home == actual_away:
        return 'Push'
    actual_home_win = actual_home > actual_away
    return 'Win' if pred_home_win == actual_home_win else 'Loss'




def score_pick_team(game: dict[str, Any]) -> str:
    home_score = safe_float(game.get('modelHomeScore'))
    away_score = safe_float(game.get('modelAwayScore'))
    if home_score is None or away_score is None or abs(home_score - away_score) < 1e-12:
        return ''
    return clean_str(game.get('homeTeam') if home_score > away_score else game.get('awayTeam')).upper()


def calibrated_pick(game: dict[str, Any]) -> tuple[str, float | None]:
    away = clean_str(game.get('awayTeam')).upper()
    home = clean_str(game.get('homeTeam')).upper()
    team = clean_str(game.get('calibratedMoneylineTeam') or game.get('calibratedMlTeam')).upper()
    prob = safe_float(
        game.get('calibratedMoneylineWinProb')
        if game.get('calibratedMoneylineWinProb') is not None
        else game.get('calibratedMlWinProb')
    )
    if team in {away, home} and prob is not None:
        return team, max(prob, 1.0 - prob) if prob < 0.5 else prob

    score_team = clean_str(game.get('modelPickTeam')).upper() or score_pick_team(game)
    raw_prob = safe_float(game.get('calibratedModelPickWinProb'))
    if score_team not in {away, home} or raw_prob is None:
        return '', None
    if raw_prob >= 0.5:
        return score_team, raw_prob
    opponent = home if score_team == away else away
    return opponent, 1.0 - raw_prob


def calibrated_result_fields(game: dict[str, Any], actual_home: int, actual_away: int) -> dict[str, Any]:
    calibrated_team, calibrated_prob = calibrated_pick(game)
    score_team = score_pick_team(game)
    away = clean_str(game.get('awayTeam')).upper()
    home = clean_str(game.get('homeTeam')).upper()
    discrepancy = bool(calibrated_team and score_team and calibrated_team != score_team)

    if not calibrated_team or calibrated_prob is None:
        result = 'Pending'
    elif actual_home == actual_away:
        result = f'{calibrated_team} {calibrated_prob * 100:.1f}% Push'
    else:
        actual_winner = home if actual_home > actual_away else away
        result = (
            f'{calibrated_team} {calibrated_prob * 100:.1f}% '
            f'{"Win" if calibrated_team == actual_winner else "Loss"}'
        )

    return {
        'scoreMlPickTeam': score_team,
        'calibratedMlPickTeam': calibrated_team,
        'calibratedMlPickProb': calibrated_prob,
        'calibratedMlDiscrepancy': discrepancy,
        'calibratedMlResult': result,
        'calibratedFlipResult': result if discrepancy else '',
        'calibratedTrackingVersion': 1,
    }


def parse_result_scores(text: Any) -> tuple[int | None, int | None]:
    numbers = re.findall(r'-?\d+(?:\.\d+)?', clean_str(text))
    if len(numbers) < 2:
        return None, None
    try:
        return int(round(float(numbers[-2]))), int(round(float(numbers[-1])))
    except Exception:
        return None, None


def enrich_existing_calibrated_rows(rows: list[dict[str, Any]], games_by_pk: dict[int, dict[str, Any]]) -> int:
    updated = 0
    for row in rows:
        if clean_str(row.get('league')).upper() != 'MLB':
            continue
        game_pk = safe_int(row.get('gamePk'))
        game = games_by_pk.get(game_pk) if game_pk is not None else None
        if not game:
            continue
        actual_away, actual_home = parse_result_scores(row.get('actual'))
        if actual_away is None or actual_home is None:
            continue
        fields = calibrated_result_fields(game, actual_home, actual_away)
        before = {key: row.get(key) for key in fields}
        row.update(fields)
        if any(before.get(key) != value for key, value in fields.items()):
            updated += 1
    return updated


def spread_result_label(game: dict[str, Any], actual_home: int, actual_away: int) -> str:
    market = safe_float(game.get('marketSpread'))
    if market is None:
        return 'Pending'
    away_adjusted = actual_away + market
    label = f"{game.get('awayTeam')} {market:+.1f}"
    if abs(away_adjusted - actual_home) < 1e-9:
        return f'{label} Push'
    away_covers = away_adjusted > actual_home
    pred_home = safe_float(game.get('modelHomeScore'))
    pred_away = safe_float(game.get('modelAwayScore'))
    if pred_home is None or pred_away is None:
        return f'{label} Pending'
    model_pick_away = (pred_away + market) > pred_home
    model_label = f"{game.get('awayTeam')} {market:+.1f}" if model_pick_away else f"{game.get('homeTeam')} {-market:+.1f}"
    return f"{model_label} {'Win' if away_covers == model_pick_away else 'Loss'}"



def total_result_label(game: dict[str, Any], actual_home: int, actual_away: int) -> str:
    total_line = safe_float(game.get('marketTotal'))
    model_total = safe_float(game.get('modelTotal'))
    if total_line is None or model_total is None:
        return 'Pending'
    actual_total = actual_home + actual_away
    lean_over = model_total > total_line
    if abs(actual_total - total_line) < 1e-9:
        return f"{'O' if lean_over else 'U'} {total_line:.1f} Push"
    hit = actual_total > total_line
    return f"{'O' if lean_over else 'U'} {total_line:.1f} {'Win' if hit == lean_over else 'Loss'}"



def nrfi_result_label(game: dict[str, Any], actual_away_1: int | None, actual_home_1: int | None) -> str:
    if actual_away_1 is None or actual_home_1 is None:
        return 'Pending'
    nrfi_prob = safe_float(game.get('nrfiProb'))
    yrfi_prob = safe_float(game.get('yrfiProb'))
    if nrfi_prob is None and yrfi_prob is None:
        return 'Pending'
    if nrfi_prob is None:
        nrfi_prob = 1.0 - yrfi_prob
    if yrfi_prob is None:
        yrfi_prob = 1.0 - nrfi_prob
    pick_nrfi = (nrfi_prob or 0.0) >= (yrfi_prob or 0.0)
    actual_nrfi = (actual_away_1 + actual_home_1) == 0
    return f"{'NRFI' if pick_nrfi else 'YRFI'} {'Win' if actual_nrfi == pick_nrfi else 'Loss'}"



def build_row(game: dict[str, Any], scraped: dict[str, Any]) -> dict[str, Any]:
    home_runs = safe_int(scraped.get('home_total')) or 0
    away_runs = safe_int(scraped.get('away_total')) or 0
    away_1 = safe_int(scraped.get('away_1'))
    home_1 = safe_int(scraped.get('home_1'))
    game_date = local_game_date(game, clean_str(scraped.get('gameDate')))
    row = {
        'date': game_date,
        'league': 'MLB',
        'matchup': f"{game.get('awayTeam')} @ {game.get('homeTeam')}",
        'predicted': (
            f"{game.get('awayTeam')} {safe_float(game.get('modelAwayScore')):.1f} @ {game.get('homeTeam')} {safe_float(game.get('modelHomeScore')):.1f}"
            if safe_float(game.get('modelAwayScore')) is not None and safe_float(game.get('modelHomeScore')) is not None
            else f"{game.get('awayTeam')} @ {game.get('homeTeam')}"
        ),
        'actual': f"{game.get('awayTeam')} {away_runs} @ {game.get('homeTeam')} {home_runs}",
        'mlResult': ml_result_label(
            safe_float(game.get('modelHomeScore')),
            safe_float(game.get('modelAwayScore')),
            home_runs,
            away_runs,
        ),
        'spreadResult': spread_result_label(game, home_runs, away_runs),
        'totalResult': total_result_label(game, home_runs, away_runs),
        'nrfiResult': nrfi_result_label(game, away_1, home_1),
        'marketSpread': safe_float(game.get('marketSpread')),
        'marketTotal': safe_float(game.get('marketTotal')),
        'gamePk': safe_int(game.get('gamePk')),
    }
    row.update(calibrated_result_fields(game, home_runs, away_runs))
    return row



def result_outcome(label: str) -> str | None:
    raw = clean_str(label).lower()
    if 'push' in raw:
        return 'push'
    if 'win' in raw:
        return 'win'
    if 'loss' in raw:
        return 'loss'
    return None



def metric_summary(labels: list[str]) -> dict[str, Any]:
    wins = sum(result_outcome(label) == 'win' for label in labels)
    losses = sum(result_outcome(label) == 'loss' for label in labels)
    pushes = sum(result_outcome(label) == 'push' for label in labels)
    graded = wins + losses
    win_pct = round((wins / graded) * 100, 1) if graded else None
    return {
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'graded': graded,
        'winPct': win_pct,
    }



def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_fields = {
        'ML': 'mlResult',
        'CalML': 'calibratedMlResult',
        'CalFlip': 'calibratedFlipResult',
        'Spread': 'spreadResult',
        'Total': 'totalResult',
    }
    by_league = defaultdict(lambda: {key: [] for key in metric_fields})
    overall = {key: [] for key in metric_fields}

    for row in rows:
        league = clean_str(row.get('league')).upper() or 'UNKNOWN'
        for metric, field in metric_fields.items():
            value = clean_str(row.get(field))
            overall[metric].append(value)
            by_league[league][metric].append(value)

    return {
        'overall': {key: metric_summary(values) for key, values in overall.items()},
        'byLeague': {
            league: {key: metric_summary(values) for key, values in metrics.items()}
            for league, metrics in sorted(by_league.items())
        },
        'rowCount': len(rows),
    }



def build_periods(rows: list[dict[str, Any]], latest_date: date) -> dict[str, Any]:
    period_bounds = {
        'yesterday': (latest_date, latest_date),
        'weekToDate': (latest_date - timedelta(days=latest_date.weekday()), latest_date),
        'monthToDate': (latest_date.replace(day=1), latest_date),
        'yearToDate': (latest_date.replace(month=1, day=1), latest_date),
    }
    periods = {}
    for label, (start_date, end_date) in period_bounds.items():
        period_rows = []
        for row in rows:
            try:
                row_date = datetime.fromisoformat(clean_str(row.get('date'))).date()
            except Exception:
                continue
            if start_date <= row_date <= end_date:
                period_rows.append(row)
        summary = summarize_rows(period_rows)
        periods[label] = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            **summary,
        }
    return periods



def refresh_results_summary(data_dir: Path, history_rows: list[dict[str, Any]]) -> None:
    if not history_rows:
        return
    dated_rows = []
    for row in history_rows:
        try:
            _ = datetime.fromisoformat(clean_str(row.get('date'))).date()
            dated_rows.append(row)
        except Exception:
            continue
    if not dated_rows:
        return
    latest_date = max(datetime.fromisoformat(clean_str(row.get('date'))).date() for row in dated_rows)
    summary_payload = {
        'asOf': latest_date.isoformat(),
        'latestDataDate': latest_date.isoformat(),
        'periods': build_periods(dated_rows, latest_date),
    }
    write_json(data_dir / 'results_summary.json', summary_payload)





def resolve_launch_date(data_dir: Path, explicit_value: str = '') -> str:
    explicit = clean_str(explicit_value)
    if explicit:
        return explicit
    launch_file = data_dir / 'mlb_results_launch_date.txt'
    if launch_file.exists():
        try:
            return clean_str(launch_file.read_text(encoding='utf-8')).splitlines()[0].strip()
        except Exception:
            return ''
    return ''


def strip_mlb_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if clean_str(row.get('league')).upper() != 'MLB']

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build MLB results for the site from local scraper outputs.')
    parser.add_argument('--website-repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--mlb-data-dir', type=Path, default=DEFAULT_MLB_DATA_DIR)
    parser.add_argument('--enable', action='store_true', help='Actually append MLB rows. Default is a safe no-op.')
    parser.add_argument('--live-start-date', default='', help='Optional lower bound YYYY-MM-DD for MLB results tracking.')
    parser.add_argument('--allow-missing-lines', action='store_true', help='Allow result rows even when marketSpread and marketTotal are both missing.')
    parser.add_argument('--allow-statsapi-fallback', action='store_true', help='Fetch final score from live feed if local scraper data is missing.')
    return parser.parse_args()



def main() -> int:
    args = parse_args()
    if not args.enable:
        print('MLB results build skipped: enable flag not set.')
        return 0
    repo = args.website_repo
    data_dir = repo / 'data'
    games_json = load_json(data_dir / 'games.json', [])
    current_results = load_json(data_dir / 'results.json', [])
    results_history = load_json(data_dir / 'results_history.json', [])
    launch_date = resolve_launch_date(data_dir, args.live_start_date)

    games_by_pk = {
        game_pk: game
        for game in games_json
        if (game_pk := safe_int(game.get('gamePk'))) is not None
    }
    calibrated_rows_enriched = enrich_existing_calibrated_rows(results_history, games_by_pk)

    scraper_games = load_table_latest(args.mlb_data_dir, 'games')
    scraper_lookup: dict[int, dict[str, Any]] = {}
    if not scraper_games.empty and 'gamePk' in scraper_games.columns:
        for _, row in scraper_games.iterrows():
            game_pk = safe_int(row.get('gamePk'))
            if game_pk is None:
                continue
            scraper_lookup[game_pk] = row.to_dict()

    if not launch_date:
        history = strip_mlb_rows(results_history)
        display_rows = strip_mlb_rows(current_results if isinstance(current_results, list) else [])
        write_json(data_dir / 'results_history.json', history)
        write_json(data_dir / 'results.json', sort_display_rows(display_rows))
        refresh_results_summary(data_dir, history)
        print('MLB results tracking is paused until data/mlb_results_launch_date.txt is set.')
        return 0

    tracked_gamepks = {
        safe_int(row.get('gamePk'))
        for row in results_history
        if clean_str(row.get('league')).upper() == 'MLB' and safe_int(row.get('gamePk')) is not None
    }
    tracked_keys = {
        (clean_str(row.get('date')), clean_str(row.get('league')).upper(), clean_str(row.get('matchup')))
        for row in results_history if clean_str(row.get('league')).upper() == 'MLB'
    }

    new_rows: list[dict[str, Any]] = []
    for game in games_json:
        if clean_str(game.get('league')).upper() != 'MLB':
            continue
        game_date = local_game_date(game)
        if not game_date or game_date < launch_date:
            continue
        if not args.allow_missing_lines and safe_float(game.get('marketSpread')) is None and safe_float(game.get('marketTotal')) is None:
            continue

        game_pk = safe_int(game.get('gamePk'))
        matchup = f"{game.get('awayTeam')} @ {game.get('homeTeam')}"
        key = (game_date, 'MLB', matchup)
        if (game_pk is not None and game_pk in tracked_gamepks) or key in tracked_keys:
            continue

        scraped = scraper_lookup.get(game_pk) if game_pk is not None else None
        if scraped is None and args.allow_statsapi_fallback and game_pk is not None:
            try:
                feed = fetch_live_feed(game_pk)
                scraped = build_fallback_row_from_feed(feed or {}) if feed else None
            except Exception as exc:
                print(f'[MLB results] fallback fetch failed for {game_pk}: {exc}')
                scraped = None
        if not scraped:
            continue
        if not is_final_status(scraped.get('status_detailed')):
            continue
        if safe_int(scraped.get('home_total')) is None or safe_int(scraped.get('away_total')) is None:
            continue
        new_rows.append(build_row(game, scraped))

    if not new_rows:
        history = results_history
        if calibrated_rows_enriched:
            write_json(data_dir / 'results_history.json', history)
        latest_date = max((clean_str(row.get('date')) for row in history if clean_str(row.get('date'))), default='')
        latest_rows = [row for row in history if clean_str(row.get('date')) == latest_date]
        write_json(data_dir / 'results.json', latest_rows)
        refresh_results_summary(data_dir, history)
        print(
            'No new MLB result rows added. '
            f'Calibrated fields enriched on {calibrated_rows_enriched} existing row(s).'
        )
        if latest_date:
            print(f'Latest results date: {latest_date}')
        return 0

    history = results_history + new_rows
    history.sort(key=lambda row: (clean_str(row.get('date')), clean_str(row.get('league')), clean_str(row.get('matchup')), safe_int(row.get('gamePk')) or 0))
    write_json(data_dir / 'results_history.json', history)

    latest_date = max((clean_str(row.get('date')) for row in history if clean_str(row.get('date'))), default='')
    latest_rows = [row for row in history if clean_str(row.get('date')) == latest_date]
    write_json(data_dir / 'results.json', latest_rows)
    refresh_results_summary(data_dir, history)

    print(f'Added {len(new_rows)} MLB rows; enriched calibrated fields on {calibrated_rows_enriched} existing row(s).')
    print(f'Latest results date: {latest_date}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
