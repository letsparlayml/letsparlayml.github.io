from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

WEBSITE_REPO = Path(__file__).resolve().parents[1]
DATA_DIR = WEBSITE_REPO / 'data'
RESULTS_PATH = DATA_DIR / 'results.json'
HISTORY_PATH = DATA_DIR / 'results_history.json'
SUMMARY_PATH = DATA_DIR / 'results_summary.json'


def parse_scores(text: str) -> list[float]:
    matches = re.findall(r'-?\d+(?:\.\d+)?', str(text or ''))
    if len(matches) < 2:
        return []
    return [float(matches[-2]), float(matches[-1])]


def parse_matchup_teams(text: str) -> tuple[str, str]:
    raw = str(text or '').strip()
    if '@' in raw:
        away, home = [part.strip() for part in raw.split('@', 1)]
        return away, home
    if re.search(r'\bvs\b', raw, flags=re.I):
        home, away = [part.strip() for part in re.split(r'\bvs\b', raw, flags=re.I, maxsplit=1)]
        return away, home
    return 'Away', 'Home'


def infer_spread_label(row: dict) -> str | None:
    try:
        market_spread = float(row.get('marketSpread'))
    except (TypeError, ValueError):
        return None

    predicted_vals = parse_scores(row.get('predicted', ''))
    actual_vals = parse_scores(row.get('actual', ''))
    if len(predicted_vals) != 2 or len(actual_vals) != 2:
        return None

    away_team, home_team = parse_matchup_teams(row.get('matchup', ''))
    pred_margin = predicted_vals[1] - predicted_vals[0]  # home - away
    actual_margin = actual_vals[1] - actual_vals[0]      # home - away
    league = str(row.get('league', '')).upper().strip()

    away_perspective = league in {'CBB', 'NHL'}
    if away_perspective:
        pred_edge = market_spread - pred_margin
        if abs(pred_edge) < 1e-9:
            return 'Push'
        pick_away = pred_edge > 0
        pick_team = away_team if pick_away else home_team
        pick_line = market_spread if pick_away else -market_spread

        actual_edge = market_spread - actual_margin
        if abs(actual_edge) < 1e-9:
            outcome = 'Push'
        else:
            actual_away_cover = actual_edge > 0
            outcome = 'Win' if actual_away_cover == pick_away else 'Loss'
    else:
        pred_edge = pred_margin + market_spread
        if abs(pred_edge) < 1e-9:
            return 'Push'
        pick_home = pred_edge > 0
        pick_team = home_team if pick_home else away_team
        pick_line = market_spread if pick_home else -market_spread

        actual_edge = actual_margin + market_spread
        if abs(actual_edge) < 1e-9:
            outcome = 'Push'
        else:
            actual_home_cover = actual_edge > 0
            outcome = 'Win' if actual_home_cover == pick_home else 'Loss'

    return f'{pick_team} {pick_line:+.1f} {outcome}'


def result_outcome(label: str) -> str | None:
    raw = str(label or '').strip().lower()
    if 'push' in raw:
        return 'push'
    if 'win' in raw:
        return 'win'
    if 'loss' in raw:
        return 'loss'
    return None


def update_rows(rows: list[dict]) -> list[dict]:
    updated = []
    for row in rows:
        next_row = dict(row)
        if str(next_row.get('league', '')).upper().strip() == 'NHL':
            inferred = infer_spread_label(next_row)
            if inferred:
                next_row['spreadResult'] = inferred
        updated.append(next_row)
    return updated


def metric_summary(labels: list[str]) -> dict:
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


def summarize_rows(rows: list[dict]) -> dict:
    by_league = defaultdict(lambda: {'ML': [], 'Spread': [], 'Total': []})
    overall = {'ML': [], 'Spread': [], 'Total': []}

    for row in rows:
        league = str(row.get('league', '')).upper().strip() or 'UNKNOWN'
        ml = row.get('mlResult', '')
        spread = row.get('spreadResult', '')
        total = row.get('totalResult', '')
        overall['ML'].append(ml)
        overall['Spread'].append(spread)
        overall['Total'].append(total)
        by_league[league]['ML'].append(ml)
        by_league[league]['Spread'].append(spread)
        by_league[league]['Total'].append(total)

    return {
        'overall': {k: metric_summary(v) for k, v in overall.items()},
        'byLeague': {league: {k: metric_summary(v) for k, v in metrics.items()} for league, metrics in sorted(by_league.items())},
        'rowCount': len(rows),
    }


def build_periods(rows: list[dict], latest_date: date) -> dict:
    period_bounds = {
        'yesterday': (latest_date, latest_date),
        'weekToDate': (latest_date - timedelta(days=latest_date.weekday()), latest_date),
        'monthToDate': (latest_date.replace(day=1), latest_date),
        'yearToDate': (latest_date.replace(month=1, day=1), latest_date),
    }

    periods = {}
    for label, (start_date, end_date) in period_bounds.items():
        period_rows = [
            row for row in rows
            if start_date <= datetime.fromisoformat(str(row.get('date'))).date() <= end_date
        ]
        summary = summarize_rows(period_rows)
        periods[label] = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            **summary,
        }
    return periods


def main() -> None:
    results_rows = json.loads(RESULTS_PATH.read_text(encoding='utf-8'))
    history_rows = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))

    fixed_results = update_rows(results_rows)
    fixed_history = update_rows(history_rows)

    RESULTS_PATH.write_text(json.dumps(fixed_results, indent=2), encoding='utf-8')
    HISTORY_PATH.write_text(json.dumps(fixed_history, indent=2), encoding='utf-8')

    latest_date = max(datetime.fromisoformat(str(row.get('date'))).date() for row in fixed_history)
    summary_payload = {
        'asOf': latest_date.isoformat(),
        'latestDataDate': latest_date.isoformat(),
        'periods': build_periods(fixed_history, latest_date),
    }
    SUMMARY_PATH.write_text(json.dumps(summary_payload, indent=2), encoding='utf-8')

    print(f'Updated NHL spread labels in {RESULTS_PATH.name}, {HISTORY_PATH.name}, and {SUMMARY_PATH.name}')
    print(f'Latest data date: {latest_date.isoformat()}')


if __name__ == '__main__':
    main()
