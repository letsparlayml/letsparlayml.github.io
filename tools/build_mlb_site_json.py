from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_WEBSITE_REPO = Path(r"C:\python\letsparlayml.github.io")
DEFAULT_MLB_OUTPUT_DIR = Path(r"C:\python\mlb_model_outputs")


def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def safe_float(value: Any):
    try:
        if pd.isna(value):
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def safe_int(value: Any):
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except Exception:
        return None


def iso_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return ""
    return ts.date().isoformat()


def iso_datetime_utc(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return ""
    return ts.isoformat().replace('+00:00', 'Z')


def pct_text(prob: Any) -> str:
    val = safe_float(prob)
    if val is None:
        return ""
    return f"{round(val * 100):.0f}%"


def confidence_label(prob_values: list[float | None]) -> str:
    vals = [v for v in prob_values if isinstance(v, (int, float))]
    if not vals:
        return "Low"
    peak = max(vals)
    if peak >= 0.72:
        return "High"
    if peak >= 0.60:
        return "Medium"
    return "Low"


def market_line_from_market_name(name: str):
    raw = clean_str(name).lower()
    if raw == 'hit':
        return 0.5
    if raw == 'hr':
        return 0.5
    if raw == '2+ total bases':
        return 1.5
    if '1.5' in raw:
        return 1.5
    return None


def market_stat_display(name: str) -> str:
    raw = clean_str(name)
    lowered = raw.lower()
    if lowered == 'hit':
        return 'Hits'
    if lowered == 'hr':
        return 'HR'
    if lowered == '2+ total bases':
        return '2+ Total Bases'
    if lowered == 'hrr over 1.5':
        return 'HRR'
    return raw


def prop_confidence(prob: float | None) -> str:
    if prob is None:
        return 'Low'
    if prob >= 0.78:
        return 'High'
    if prob >= 0.66:
        return 'Medium'
    return 'Low'


def build_summary(row: pd.Series) -> str:
    parts: list[str] = []
    home = clean_str(row.get('home_team'))
    away = clean_str(row.get('away_team'))
    home_win = safe_float(row.get('home_win_prob'))
    away_win = safe_float(row.get('away_win_prob'))
    nrfi = safe_float(row.get('nrfi_prob'))
    home_m15 = safe_float(row.get('home_minus1p5_prob'))
    away_m15 = safe_float(row.get('away_minus1p5_prob'))
    home_p15 = safe_float(row.get('home_plus1p5_prob'))
    away_p15 = safe_float(row.get('away_plus1p5_prob'))
    over75 = safe_float(row.get('over_7p5_prob'))
    over85 = safe_float(row.get('over_8p5_prob'))

    if nrfi is not None:
        parts.append(f"NRFI {pct_text(nrfi)}")

    if home_win is not None or away_win is not None:
        if (home_win or 0) >= (away_win or 0):
            parts.append(f"{home} win {pct_text(home_win)}")
        else:
            parts.append(f"{away} win {pct_text(away_win)}")

    rl_options = []
    if home_m15 is not None:
        rl_options.append((home_m15, f"{home} -1.5 {pct_text(home_m15)}"))
    if away_m15 is not None:
        rl_options.append((away_m15, f"{away} -1.5 {pct_text(away_m15)}"))
    if home_p15 is not None:
        rl_options.append((home_p15, f"{home} +1.5 {pct_text(home_p15)}"))
    if away_p15 is not None:
        rl_options.append((away_p15, f"{away} +1.5 {pct_text(away_p15)}"))
    if rl_options:
        rl_options.sort(key=lambda x: x[0], reverse=True)
        parts.append(rl_options[0][1])

    totals = []
    if over75 is not None:
        totals.append((over75, f"Over 7.5 {pct_text(over75)}"))
        totals.append((1 - over75, f"Under 7.5 {pct_text(1 - over75)}"))
    if over85 is not None:
        totals.append((over85, f"Over 8.5 {pct_text(over85)}"))
        totals.append((1 - over85, f"Under 8.5 {pct_text(1 - over85)}"))
    if totals:
        totals.sort(key=lambda x: x[0], reverse=True)
        parts.append(totals[0][1])

    return ' • '.join(parts[:4]) or 'MLB model preview'


def build_movement(row: pd.Series) -> list[dict[str, Any]]:
    return [{
        'date': iso_date(row.get('forecast_generated_date')) or iso_date(row.get('target_game_date')),
        'predictedAway': safe_float(row.get('pred_away_runs')),
        'predictedHome': safe_float(row.get('pred_home_runs')),
        'modelHomeSpread': safe_float(row.get('pred_home_runs')) - safe_float(row.get('pred_away_runs')) if safe_float(row.get('pred_home_runs')) is not None and safe_float(row.get('pred_away_runs')) is not None else None,
        'marketSpread': None,
        'modelTotal': safe_float(row.get('pred_total')),
        'marketTotal': None,
        'nrfiProb': safe_float(row.get('nrfi_prob')),
        'homeWinProb': safe_float(row.get('home_win_prob')),
        'awayWinProb': safe_float(row.get('away_win_prob')),
        'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
        'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
        'over7p5Prob': safe_float(row.get('over_7p5_prob')),
        'over8p5Prob': safe_float(row.get('over_8p5_prob')),
        'note': 'Snapshot'
    }]


def trimmed_pitcher_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    if df is None or df.empty:
        return out
    sort_cols = [c for c in ['is_home', 'team', 'player_name'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, True, True][:len(sort_cols)])
    for _, row in df.iterrows():
        item = {
            'playerId': safe_int(row.get('player_id')),
            'player': clean_str(row.get('player_name') or row.get('fullName')),
            'team': clean_str(row.get('team')),
            'opponent': clean_str(row.get('opponent')),
            'hand': clean_str(row.get('pitchHand')),
            'isHome': bool(row.get('is_home')) if clean_str(row.get('is_home')) != '' else None,
            'predOuts': safe_float(row.get('pred_outs')),
            'predIP': safe_float(row.get('pred_ip')),
            'predK': safe_float(row.get('pred_k')),
            'predBB': safe_float(row.get('pred_bb')),
            'predHitsAllowed': safe_float(row.get('pred_hits_allowed')),
            'predER': safe_float(row.get('pred_er')),
        }
        out.append(item)
    return out


def batter_sort_score(row: pd.Series) -> float:
    order = safe_float(row.get('projected_batting_order'))
    order_bonus = 20 - order if order is not None else 0
    prob_hit = safe_float(row.get('prob_hit')) or 0
    prob_tb2 = safe_float(row.get('prob_tb2plus')) or 0
    prob_hr = safe_float(row.get('prob_hr')) or 0
    return order_bonus + prob_hit * 10 + prob_tb2 * 8 + prob_hr * 12


def trimmed_batter_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    if df is None or df.empty:
        return out
    sort_df = df.copy()
    sort_df['__score__'] = sort_df.apply(batter_sort_score, axis=1)
    sort_df = sort_df.sort_values(['team', 'projected_batting_order', '__score__', 'player_name'], ascending=[True, True, False, True], na_position='last')
    for _, row in sort_df.iterrows():
        item = {
            'playerId': safe_int(row.get('player_id')),
            'player': clean_str(row.get('player_name')),
            'team': clean_str(row.get('team')),
            'opponent': clean_str(row.get('opponent')),
            'order': safe_int(row.get('projected_batting_order') if clean_str(row.get('projected_batting_order')) != '' else row.get('batting_order')),
            'batSide': clean_str(row.get('batSide')),
            'oppPitchHand': clean_str(row.get('opp_pitch_hand') or row.get('oppPitchHand') or row.get('pitchHand')),
            'predHits': safe_float(row.get('pred_hits')),
            'predTB': safe_float(row.get('pred_total_bases')),
            'predDoubles': safe_float(row.get('pred_doubles')),
            'predHR': safe_float(row.get('pred_hr')),
            'predK': safe_float(row.get('pred_k')),
            'predBB': safe_float(row.get('pred_bb')),
            'predRBI': safe_float(row.get('pred_rbi')),
            'predRuns': safe_float(row.get('pred_runs')),
            'predSB': safe_float(row.get('pred_sb')),
            'probHit': safe_float(row.get('prob_hit')),
            'probTB2Plus': safe_float(row.get('prob_tb2plus')),
            'probDouble': safe_float(row.get('prob_double')),
            'probHR': safe_float(row.get('prob_hr')),
            'probK': safe_float(row.get('prob_k')),
            'probBB': safe_float(row.get('prob_bb')),
            'probSB': safe_float(row.get('prob_sb')),
        }
        out.append(item)
    return out


def build_game_lookup(game_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    lookup = {}
    for _, row in game_df.iterrows():
        game_date = iso_date(row.get('target_game_date') or row.get('gameDate'))
        home = clean_str(row.get('home_team'))
        away = clean_str(row.get('away_team'))
        game_pk = safe_int(row.get('gamePk'))
        if game_date and home and away:
            lookup[(game_date, home, away)] = {'gamePk': game_pk, 'homeTeam': home, 'awayTeam': away}
            lookup[(game_date, away, home)] = {'gamePk': game_pk, 'homeTeam': home, 'awayTeam': away}
    return lookup


def build_props_from_workbook(workbook_path: Path | None, game_lookup: dict[tuple[str, str, str], dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not workbook_path or not workbook_path.exists():
        return []
    xls = pd.ExcelFile(workbook_path)
    sheet_name = 'All_Picks' if 'All_Picks' in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet_name)
    if df.empty:
        return []

    sort_cols = [c for c in ['over_prob', 'over_prob_pct', 'projection'] if c in df.columns]
    ascending = [False] * len(sort_cols)
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    rows = []
    for _, row in df.head(limit).iterrows():
        game_date = iso_date(row.get('gameDate'))
        team = clean_str(row.get('team'))
        opp = clean_str(row.get('opponent'))
        lookup = game_lookup.get((game_date, team, opp), {})
        over_prob = safe_float(row.get('over_prob'))
        item = {
            'league': 'MLB',
            'gameDate': game_date,
            'gameId': lookup.get('gamePk'),
            'player': clean_str(row.get('player_name')),
            'team': team,
            'opp': opp,
            'stat': market_stat_display(row.get('market')),
            'stat_display': market_stat_display(row.get('market')),
            'line': market_line_from_market_name(row.get('market')),
            'modelPrediction': safe_float(row.get('projection')),
            'probability': over_prob,
            'confidence': prop_confidence(over_prob),
            'note': f"{team} vs {opp} • {pct_text(over_prob)} to clear",
        }
        rows.append(item)
    return rows


def build_game_objects(game_df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[str]]:
    games = []
    by_pk: dict[int, dict[str, Any]] = {}
    dates = sorted({iso_date(v) for v in game_df.get('target_game_date', []) if iso_date(v)})
    for _, row in game_df.sort_values(['target_game_date', 'gameDate', 'home_team', 'away_team']).iterrows():
        game_pk = safe_int(row.get('gamePk'))
        target_date = iso_date(row.get('target_game_date') or row.get('gameDate'))
        game_time = iso_datetime_utc(row.get('gameDate'))
        home_runs = safe_float(row.get('pred_home_runs'))
        away_runs = safe_float(row.get('pred_away_runs'))
        model_spread = (home_runs - away_runs) if home_runs is not None and away_runs is not None else None
        obj = {
            'id': f"mlb-{game_pk}",
            'gamePk': game_pk,
            'league': 'MLB',
            'gameDate': target_date,
            'gameDateTimeUtc': game_time,
            'awayTeam': clean_str(row.get('away_team')),
            'homeTeam': clean_str(row.get('home_team')),
            'marketSpread': None,
            'marketTotal': None,
            'modelAwayScore': away_runs,
            'modelHomeScore': home_runs,
            'modelHomeSpread': model_spread,
            'modelTotal': safe_float(row.get('pred_total')),
            'homeWinProb': safe_float(row.get('home_win_prob')),
            'awayWinProb': safe_float(row.get('away_win_prob')),
            'nrfiProb': safe_float(row.get('nrfi_prob')),
            'yrfiProb': safe_float(row.get('yrfi_prob')),
            'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
            'awayPlus1p5Prob': safe_float(row.get('away_plus1p5_prob')),
            'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
            'homePlus1p5Prob': safe_float(row.get('home_plus1p5_prob')),
            'favoriteMinus1p5Prob': safe_float(row.get('favorite_minus1p5_prob')),
            'underdogPlus1p5Prob': safe_float(row.get('underdog_plus1p5_prob')),
            'over7p5Prob': safe_float(row.get('over_7p5_prob')),
            'over8p5Prob': safe_float(row.get('over_8p5_prob')),
            'oneRunGameProb': safe_float(row.get('one_run_game_prob')),
            'homeBy1Prob': safe_float(row.get('home_by_1_prob')),
            'awayBy1Prob': safe_float(row.get('away_by_1_prob')),
            'tieAfter9Prob': safe_float(row.get('tie_after9_prob')),
            'medianTotal': safe_float(row.get('median_total')),
            'medianMargin': safe_float(row.get('median_margin')),
            'confidence': confidence_label([
                safe_float(row.get('nrfi_prob')),
                safe_float(row.get('home_win_prob')),
                safe_float(row.get('away_win_prob')),
                safe_float(row.get('home_minus1p5_prob')),
                safe_float(row.get('away_minus1p5_prob')),
                safe_float(row.get('over_7p5_prob')),
                safe_float(row.get('over_8p5_prob')),
            ]),
            'summary': build_summary(row),
            'movement': build_movement(row),
            'marketSpreadText': 'Pending',
            'marketTotalText': 'Pending',
            'marketLineSource': '',
            'marketLineUpdated': '',
            'detailPath': f"data/mlb_game_details/{target_date}/{game_pk}.json"
        }
        games.append(obj)
        if game_pk is not None:
            by_pk[game_pk] = obj
    return games, by_pk, dates


def build_game_details(game_df: pd.DataFrame, pitcher_df: pd.DataFrame, batter_df: pd.DataFrame, by_pk: dict[int, dict[str, Any]], out_root: Path) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    pitcher_groups = dict(tuple(pitcher_df.groupby('gamePk', sort=False))) if not pitcher_df.empty else {}
    batter_groups = dict(tuple(batter_df.groupby('gamePk', sort=False))) if not batter_df.empty else {}

    for game_pk, game in by_pk.items():
        row = game_df.loc[game_df['gamePk'] == game_pk].iloc[0]
        detail = {
            'gamePk': game_pk,
            'league': 'MLB',
            'gameDate': game.get('gameDate'),
            'gameDateTimeUtc': game.get('gameDateTimeUtc'),
            'awayTeam': game.get('awayTeam'),
            'homeTeam': game.get('homeTeam'),
            'metrics': {
                'homeWinProb': game.get('homeWinProb'),
                'awayWinProb': game.get('awayWinProb'),
                'nrfiProb': game.get('nrfiProb'),
                'yrfiProb': game.get('yrfiProb'),
                'homeMinus1p5Prob': game.get('homeMinus1p5Prob'),
                'awayPlus1p5Prob': game.get('awayPlus1p5Prob'),
                'awayMinus1p5Prob': game.get('awayMinus1p5Prob'),
                'homePlus1p5Prob': game.get('homePlus1p5Prob'),
                'over7p5Prob': game.get('over7p5Prob'),
                'over8p5Prob': game.get('over8p5Prob'),
                'oneRunGameProb': game.get('oneRunGameProb'),
                'tieAfter9Prob': game.get('tieAfter9Prob'),
                'medianTotal': game.get('medianTotal'),
                'medianMargin': game.get('medianMargin'),
                'predHomeF5': safe_float(row.get('pred_home_f5')),
                'predAwayF5': safe_float(row.get('pred_away_f5')),
                'predF5Total': safe_float(row.get('pred_f5_total')),
            },
            'pitchers': trimmed_pitcher_rows(pitcher_groups.get(game_pk, pd.DataFrame())),
            'batters': trimmed_batter_rows(batter_groups.get(game_pk, pd.DataFrame())),
        }
        out_path = out_root / game.get('gameDate') / f'{game_pk}.json'
        write_json(out_path, detail)


def find_latest(pattern: str, root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = list(root.rglob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build local-preview MLB site JSON files.')
    parser.add_argument('--website-repo', type=Path, default=DEFAULT_WEBSITE_REPO)
    parser.add_argument('--mlb-output-dir', type=Path, default=DEFAULT_MLB_OUTPUT_DIR)
    parser.add_argument('--game-csv', type=Path)
    parser.add_argument('--pitcher-csv', type=Path)
    parser.add_argument('--batter-csv', type=Path)
    parser.add_argument('--picks-workbook', type=Path)
    parser.add_argument('--top-props-limit', type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.website_repo
    data_dir = repo / 'data'

    game_csv = args.game_csv or find_latest('game_predictions_*.csv', args.mlb_output_dir)
    pitcher_csv = args.pitcher_csv or find_latest('pitcher_predictions_*.csv', args.mlb_output_dir)
    batter_csv = args.batter_csv or find_latest('batter_predictions_*.csv', args.mlb_output_dir)
    workbook = args.picks_workbook or find_latest('top_batter_picks*.xlsx', args.mlb_output_dir)

    if not game_csv or not game_csv.exists():
        raise SystemExit('Could not find an MLB game_predictions CSV.')
    if not pitcher_csv or not pitcher_csv.exists():
        raise SystemExit('Could not find an MLB pitcher_predictions CSV.')
    if not batter_csv or not batter_csv.exists():
        raise SystemExit('Could not find an MLB batter_predictions CSV.')

    game_df = pd.read_csv(game_csv)
    pitcher_df = pd.read_csv(pitcher_csv)
    batter_df = pd.read_csv(batter_csv)

    mlb_games, by_pk, mlb_dates = build_game_objects(game_df)
    build_game_details(game_df, pitcher_df, batter_df, by_pk, data_dir / 'mlb_game_details')

    existing_games = load_json(data_dir / 'games.json', [])
    keep_games = [g for g in existing_games if clean_str(g.get('league')).upper() != 'MLB']
    combined_games = keep_games + mlb_games
    combined_games.sort(key=lambda g: (clean_str(g.get('gameDate')), clean_str(g.get('league')), clean_str(g.get('awayTeam')), clean_str(g.get('homeTeam'))))
    write_json(data_dir / 'games.json', combined_games)

    existing_props = load_json(data_dir / 'props.json', [])
    keep_props = [p for p in existing_props if clean_str(p.get('league')).upper() != 'MLB']
    game_lookup = build_game_lookup(game_df)
    mlb_props = build_props_from_workbook(workbook, game_lookup, args.top_props_limit)
    combined_props = keep_props + mlb_props
    write_json(data_dir / 'props.json', combined_props)

    site = load_json(data_dir / 'site.json', {})
    leagues = [clean_str(x).upper() for x in site.get('leagues', []) if clean_str(x)]
    if 'MLB' not in leagues:
        leagues.append('MLB')
    # Keep a readable order when possible.
    preferred = ['NBA', 'MLB', 'NHL', 'CBB']
    ordered = [x for x in preferred if x in leagues] + [x for x in leagues if x not in preferred]
    site['leagues'] = ordered
    if game_df.get('forecast_generated_date') is not None and not game_df.empty:
        latest_forecast = max((iso_date(v) for v in game_df['forecast_generated_date']), default='')
        if latest_forecast:
            site['lastUpdated'] = latest_forecast
    write_json(data_dir / 'site.json', site)

    print(f'Wrote {len(mlb_games)} MLB games into {data_dir / "games.json"}')
    print(f'Wrote {len(mlb_props)} MLB homepage props into {data_dir / "props.json"}')
    print(f'Wrote MLB detail files under {data_dir / "mlb_game_details"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
