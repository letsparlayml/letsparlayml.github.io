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
DISPLAY_TIMEZONE = "America/Denver"




def normalize_team_token(value: Any) -> str:
    return ''.join(ch for ch in clean_str(value).upper() if ch.isalnum())


def parse_matchup(matchup: Any) -> tuple[str, str]:
    raw = clean_str(matchup)
    if not raw or '@' not in raw:
        return '', ''
    away, home = raw.split('@', 1)
    return clean_str(away), clean_str(home)


def market_matchup_key(game_date: str, away_team: Any, home_team: Any) -> str:
    return f"{clean_str(game_date)}|{normalize_team_token(away_team)}|{normalize_team_token(home_team)}"


def iso_timestamp(value: Any) -> str:
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return ''
    return ts.isoformat().replace('+00:00', 'Z')


def choose_total_prob_fields(total_line: Any, row: pd.Series) -> tuple[str, float | None, float | None]:
    total = safe_float(total_line)
    if total is not None:
        if abs(total - 7.5) < 0.11:
            over = safe_float(row.get('over_7p5_prob'))
            return f"Over {total:.1f}", over, (1 - over) if over is not None else None
        if abs(total - 8.5) < 0.11:
            over = safe_float(row.get('over_8p5_prob'))
            return f"Over {total:.1f}", over, (1 - over) if over is not None else None
    over85 = safe_float(row.get('over_8p5_prob'))
    if over85 is not None:
        return 'Over 8.5', over85, 1 - over85
    over75 = safe_float(row.get('over_7p5_prob'))
    if over75 is not None:
        return 'Over 7.5', over75, 1 - over75
    return '', None, None


def choose_win_team_and_prob(row: pd.Series) -> tuple[str, float | None]:
    home_team = clean_str(row.get('home_team'))
    away_team = clean_str(row.get('away_team'))
    home_win = safe_float(row.get('home_win_prob'))
    away_win = safe_float(row.get('away_win_prob'))
    favorite_team = clean_str(row.get('favorite_team'))
    if favorite_team:
        if favorite_team == home_team:
            return favorite_team, home_win
        if favorite_team == away_team:
            return favorite_team, away_win
    if (home_win or 0) >= (away_win or 0):
        return home_team, home_win
    return away_team, away_win


def derive_market_context(row: pd.Series, market_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    home_team = clean_str(row.get('home_team'))
    away_team = clean_str(row.get('away_team'))
    favorite_team, favorite_win_prob = choose_win_team_and_prob(row)

    default_cover_prob = safe_float(row.get('favorite_minus1p5_prob'))
    default_cover_label = f"{favorite_team} -1.5" if favorite_team else 'Favorite -1.5'

    market_spread = safe_float((market_entry or {}).get('marketSpread'))
    market_total = safe_float((market_entry or {}).get('marketTotal'))
    line_source = clean_str((market_entry or {}).get('source'))
    line_updated = clean_str((market_entry or {}).get('updatedAt')) or clean_str((market_entry or {}).get('__file_updated'))
    market_away_ml = safe_float((market_entry or {}).get('marketAwayML') if (market_entry or {}).get('marketAwayML') is not None else ((market_entry or {}).get('awayML') if (market_entry or {}).get('awayML') is not None else (market_entry or {}).get('awayMoneyline')))
    market_home_ml = safe_float((market_entry or {}).get('marketHomeML') if (market_entry or {}).get('marketHomeML') is not None else ((market_entry or {}).get('homeML') if (market_entry or {}).get('homeML') is not None else (market_entry or {}).get('homeMoneyline')))

    market_cover_prob = None
    market_cover_label = ''
    market_cover_team = ''
    if market_spread is not None and abs(abs(market_spread) - 1.5) < 0.11:
        if market_spread > 0:
            market_cover_team = home_team
            market_cover_label = f"{home_team} -1.5"
            market_cover_prob = safe_float(row.get('home_minus1p5_prob'))
        elif market_spread < 0:
            market_cover_team = away_team
            market_cover_label = f"{away_team} -1.5"
            market_cover_prob = safe_float(row.get('away_minus1p5_prob'))

    total_label, market_over_prob, market_under_prob = choose_total_prob_fields(market_total, row)
    fallback_total_label, fallback_over_prob, fallback_under_prob = choose_total_prob_fields(None, row)

    return {
        'favoriteTeam': favorite_team,
        'favoriteWinLabel': f"{favorite_team} win" if favorite_team else 'Favorite win',
        'favoriteWinProb': favorite_win_prob,
        'favoriteCoverLabel': default_cover_label,
        'favoriteCoverProb': default_cover_prob,
        'marketSpread': market_spread,
        'marketTotal': market_total,
        'marketCoverTeam': market_cover_team,
        'marketCoverLabel': market_cover_label,
        'marketCoverProb': market_cover_prob,
        'marketTotalLabel': total_label,
        'marketOverProb': market_over_prob,
        'marketUnderProb': market_under_prob,
        'fallbackTotalLabel': fallback_total_label,
        'fallbackOverProb': fallback_over_prob,
        'fallbackUnderProb': fallback_under_prob,
        'marketAwayML': market_away_ml,
        'marketHomeML': market_home_ml,
        'marketLineSource': line_source,
        'marketLineUpdated': line_updated,
    }


def load_market_entries_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.suffix.lower() == '.json':
            raw = load_json(path, [])
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            if isinstance(raw, dict):
                for key in ('items', 'rows', 'entries', 'data'):
                    val = raw.get(key)
                    if isinstance(val, list):
                        return [x for x in val if isinstance(x, dict)]
                return []
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(path)
            return df.to_dict(orient='records')
    except Exception:
        return []
    return []


def load_mlb_market_lines(repo: Path, mlb_output_dir: Path) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], int]:
    candidates = [
        repo / 'data' / 'market_lines_archive.json',
        repo / 'data' / 'mlb_market_lines.json',
        repo / 'data' / 'mlb_market_lines.csv',
        mlb_output_dir / 'market_lines_archive.json',
        mlb_output_dir / 'mlb_market_lines.json',
        mlb_output_dir / 'mlb_market_lines.csv',
    ]

    by_pk: dict[int, dict[str, Any]] = {}
    by_matchup: dict[str, dict[str, Any]] = {}
    parsed = 0

    for path in candidates:
        if not path.exists():
            continue
        file_updated = iso_timestamp(path.stat().st_mtime)
        for entry in load_market_entries_from_path(path):
            league = clean_str(entry.get('league'))
            if league and league.upper() != 'MLB':
                continue
            away_team = clean_str(entry.get('awayTeam'))
            home_team = clean_str(entry.get('homeTeam'))
            if (not away_team or not home_team) and clean_str(entry.get('matchup')):
                away_team, home_team = parse_matchup(entry.get('matchup'))
            game_date = clean_str(entry.get('date')) or local_date(entry.get('gameDate')) or iso_date(entry.get('gameDate'))
            game_pk = safe_int(entry.get('gamePk'))
            market_spread = safe_float(entry.get('marketSpread') if entry.get('marketSpread') is not None else entry.get('spread'))
            market_total = safe_float(entry.get('marketTotal') if entry.get('marketTotal') is not None else entry.get('total'))
            market_away_ml = safe_float(entry.get('marketAwayML') if entry.get('marketAwayML') is not None else (entry.get('awayML') if entry.get('awayML') is not None else entry.get('awayMoneyline')))
            market_home_ml = safe_float(entry.get('marketHomeML') if entry.get('marketHomeML') is not None else (entry.get('homeML') if entry.get('homeML') is not None else entry.get('homeMoneyline')))
            if not away_team or not home_team or not game_date:
                continue
            if market_spread is None and market_total is None and market_away_ml is None and market_home_ml is None:
                continue
            parsed += 1
            normalized = {
                'gamePk': game_pk,
                'date': game_date,
                'awayTeam': away_team,
                'homeTeam': home_team,
                'marketSpread': market_spread,
                'marketTotal': market_total,
                'marketAwayML': market_away_ml,
                'marketHomeML': market_home_ml,
                'source': clean_str(entry.get('source')) or path.name,
                'updatedAt': clean_str(entry.get('updatedAt')) or file_updated,
                '__rank': (clean_str(entry.get('updatedAt')) or file_updated, str(path)),
                '__file_updated': file_updated,
            }
            if game_pk is not None:
                existing = by_pk.get(game_pk)
                if not existing or normalized['__rank'] >= existing.get('__rank', ('', '')):
                    by_pk[game_pk] = normalized
            matchup_key = market_matchup_key(game_date, away_team, home_team)
            existing = by_matchup.get(matchup_key)
            if not existing or normalized['__rank'] >= existing.get('__rank', ('', '')):
                by_matchup[matchup_key] = normalized

    for mapping in (by_pk, by_matchup):
        for item in mapping.values():
            item.pop('__rank', None)
    return by_pk, by_matchup, parsed

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


def local_date(value: Any, tz_name: str = DISPLAY_TIMEZONE) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return ""
    if getattr(ts, "tzinfo", None) is None:
        return ts.date().isoformat()
    return ts.tz_convert(tz_name).date().isoformat()


def game_display_date(row: pd.Series, tz_name: str = DISPLAY_TIMEZONE) -> str:
    game_dt = local_date(row.get('gameDate'), tz_name)
    if game_dt:
        return game_dt
    return local_date(row.get('target_game_date') or row.get('gameDate'), tz_name) or iso_date(row.get('target_game_date') or row.get('gameDate'))


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



def game_identity_key(row: pd.Series) -> str:
    game_pk = safe_int(row.get('gamePk'))
    if game_pk is not None:
        return f"gamepk|{game_pk}"
    target_date = game_display_date(row)
    away = clean_str(row.get('away_team')).upper()
    home = clean_str(row.get('home_team')).upper()
    game_time = iso_datetime_utc(row.get('gameDate'))
    return f"{target_date}|{away}|{home}|{game_time}"


def movement_point_from_row(row: pd.Series, market_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    home_runs = safe_float(row.get('pred_home_runs'))
    away_runs = safe_float(row.get('pred_away_runs'))
    context = derive_market_context(row, market_entry)
    return {
        'date': local_date(row.get('forecast_generated_date')) or game_display_date(row),
        'predictedAway': away_runs,
        'predictedHome': home_runs,
        'modelHomeSpread': home_runs - away_runs if home_runs is not None and away_runs is not None else None,
        'marketSpread': context.get('marketSpread'),
        'modelTotal': safe_float(row.get('pred_total')),
        'marketTotal': context.get('marketTotal'),
        'nrfiProb': safe_float(row.get('nrfi_prob')),
        'homeWinProb': safe_float(row.get('home_win_prob')),
        'awayWinProb': safe_float(row.get('away_win_prob')),
        'favoriteWinLabel': context.get('favoriteWinLabel'),
        'favoriteWinProb': context.get('favoriteWinProb'),
        'favoriteCoverLabel': context.get('favoriteCoverLabel'),
        'favoriteCoverProb': context.get('favoriteCoverProb'),
        'marketCoverLabel': context.get('marketCoverLabel'),
        'marketCoverProb': context.get('marketCoverProb'),
        'marketTotalLabel': context.get('marketTotalLabel'),
        'marketOverProb': context.get('marketOverProb'),
        'marketUnderProb': context.get('marketUnderProb'),
        'fallbackTotalLabel': context.get('fallbackTotalLabel'),
        'fallbackOverProb': context.get('fallbackOverProb'),
        'fallbackUnderProb': context.get('fallbackUnderProb'),
        'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
        'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
        'over7p5Prob': safe_float(row.get('over_7p5_prob')),
        'over8p5Prob': safe_float(row.get('over_8p5_prob')),
        'note': 'Snapshot'
    }


def build_movement(movement_rows: pd.DataFrame, market_entry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if movement_rows is None or movement_rows.empty:
        return []
    work = movement_rows.copy()
    work['__forecast_date'] = work['forecast_generated_date'].map(iso_date)
    work = work.sort_values(['__forecast_date', 'gameDate', 'home_team', 'away_team'])
    points: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for _, row in work.iterrows():
        point = movement_point_from_row(row, market_entry=market_entry)
        point_date = clean_str(point.get('date'))
        if not point_date:
            continue
        if point_date in seen_dates:
            points[-1] = point
        else:
            seen_dates.add(point_date)
            points.append(point)
    return points


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
        pred_hits = safe_float(row.get('pred_hits'))
        pred_runs = safe_float(row.get('pred_runs'))
        pred_rbi = safe_float(row.get('pred_rbi'))
        pred_hrr = None
        if pred_hits is not None or pred_runs is not None or pred_rbi is not None:
            pred_hrr = (pred_hits or 0) + (pred_runs or 0) + (pred_rbi or 0)
        else:
            pred_hrr = safe_float(row.get('pred_hrr'))
        item = {
            'playerId': safe_int(row.get('player_id')),
            'player': clean_str(row.get('player_name')),
            'team': clean_str(row.get('team')),
            'opponent': clean_str(row.get('opponent')),
            'order': safe_int(row.get('projected_batting_order') if clean_str(row.get('projected_batting_order')) != '' else row.get('batting_order')),
            'batSide': clean_str(row.get('batSide')),
            'oppPitchHand': clean_str(row.get('opp_pitch_hand') or row.get('oppPitchHand') or row.get('pitchHand')),
            'predHits': pred_hits,
            'predTB': safe_float(row.get('pred_total_bases')),
            'predDoubles': safe_float(row.get('pred_doubles')),
            'predHR': safe_float(row.get('pred_hr')),
            'predK': safe_float(row.get('pred_k')),
            'predBB': safe_float(row.get('pred_bb')),
            'predRBI': pred_rbi,
            'predRuns': pred_runs,
            'predSB': safe_float(row.get('pred_sb')),
            'predHRR': pred_hrr,
            'probHit': safe_float(row.get('prob_hit')),
            'probTB2Plus': safe_float(row.get('prob_tb2plus')),
            'probDouble': safe_float(row.get('prob_double')),
            'probHR': safe_float(row.get('prob_hr')),
            'probK': safe_float(row.get('prob_k')),
            'probBB': safe_float(row.get('prob_bb')),
            'probSB': safe_float(row.get('prob_sb')),
            'probHRR2Plus': safe_float(row.get('prob_hrr2plus')),
        }
        out.append(item)
    return out


def build_game_lookup(game_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    lookup = {}
    for _, row in game_df.iterrows():
        game_date = game_display_date(row)
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
        game_date = local_date(row.get('gameDate')) or iso_date(row.get('gameDate'))
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



def build_game_objects(
    game_df: pd.DataFrame,
    movement_lookup: dict[str, pd.DataFrame] | None = None,
    market_lines_by_pk: dict[int, dict[str, Any]] | None = None,
    market_lines_by_matchup: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[str]]:
    movement_lookup = movement_lookup or {}
    market_lines_by_pk = market_lines_by_pk or {}
    market_lines_by_matchup = market_lines_by_matchup or {}
    games = []
    by_pk: dict[int, dict[str, Any]] = {}
    dates = sorted({game_display_date(row) for _, row in game_df.iterrows() if game_display_date(row)})
    for _, row in game_df.sort_values(['target_game_date', 'gameDate', 'home_team', 'away_team']).iterrows():
        game_pk = safe_int(row.get('gamePk'))
        target_date = game_display_date(row)
        game_time = iso_datetime_utc(row.get('gameDate'))
        home_runs = safe_float(row.get('pred_home_runs'))
        away_runs = safe_float(row.get('pred_away_runs'))
        model_spread = (home_runs - away_runs) if home_runs is not None and away_runs is not None else None
        identity = game_identity_key(row)
        movement_rows = movement_lookup.get(identity)
        market_entry = market_lines_by_pk.get(game_pk) if game_pk is not None else None
        if market_entry is None:
            market_entry = market_lines_by_matchup.get(market_matchup_key(target_date, row.get('away_team'), row.get('home_team')))
        context = derive_market_context(row, market_entry)
        obj = {
            'id': f"mlb-{game_pk}",
            'gamePk': game_pk,
            'league': 'MLB',
            'gameDate': target_date,
            'gameDateTimeUtc': game_time,
            'awayTeam': clean_str(row.get('away_team')),
            'homeTeam': clean_str(row.get('home_team')),
            'marketSpread': context.get('marketSpread'),
            'marketTotal': context.get('marketTotal'),
            'marketAwayML': context.get('marketAwayML'),
            'marketHomeML': context.get('marketHomeML'),
            'modelAwayScore': away_runs,
            'modelHomeScore': home_runs,
            'modelHomeSpread': model_spread,
            'modelTotal': safe_float(row.get('pred_total')),
            'homeWinProb': safe_float(row.get('home_win_prob')),
            'awayWinProb': safe_float(row.get('away_win_prob')),
            'favoriteWinLabel': context.get('favoriteWinLabel'),
            'favoriteWinProb': context.get('favoriteWinProb'),
            'nrfiProb': safe_float(row.get('nrfi_prob')),
            'yrfiProb': safe_float(row.get('yrfi_prob')),
            'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
            'awayPlus1p5Prob': safe_float(row.get('away_plus1p5_prob')),
            'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
            'homePlus1p5Prob': safe_float(row.get('home_plus1p5_prob')),
            'favoriteMinus1p5Prob': safe_float(row.get('favorite_minus1p5_prob')),
            'underdogPlus1p5Prob': safe_float(row.get('underdog_plus1p5_prob')),
            'favoriteCoverLabel': context.get('favoriteCoverLabel'),
            'favoriteCoverProb': context.get('favoriteCoverProb'),
            'marketCoverLabel': context.get('marketCoverLabel'),
            'marketCoverProb': context.get('marketCoverProb'),
            'over7p5Prob': safe_float(row.get('over_7p5_prob')),
            'over8p5Prob': safe_float(row.get('over_8p5_prob')),
            'marketTotalLabel': context.get('marketTotalLabel'),
            'marketOverProb': context.get('marketOverProb'),
            'marketUnderProb': context.get('marketUnderProb'),
            'fallbackTotalLabel': context.get('fallbackTotalLabel'),
            'fallbackOverProb': context.get('fallbackOverProb'),
            'fallbackUnderProb': context.get('fallbackUnderProb'),
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
            'movement': build_movement(movement_rows if movement_rows is not None else pd.DataFrame([row]), market_entry=market_entry),
            'marketSpreadText': 'Pending' if context.get('marketSpread') is None else context.get('marketCoverLabel') or 'Available',
            'marketTotalText': 'Pending' if context.get('marketTotal') is None else context.get('marketTotalLabel') or f"{context.get('marketTotal')}",
            'marketLineSource': context.get('marketLineSource'),
            'marketLineUpdated': context.get('marketLineUpdated'),
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
                'favoriteWinLabel': game.get('favoriteWinLabel'),
                'favoriteWinProb': game.get('favoriteWinProb'),
                'nrfiProb': game.get('nrfiProb'),
                'yrfiProb': game.get('yrfiProb'),
                'homeMinus1p5Prob': game.get('homeMinus1p5Prob'),
                'awayPlus1p5Prob': game.get('awayPlus1p5Prob'),
                'awayMinus1p5Prob': game.get('awayMinus1p5Prob'),
                'homePlus1p5Prob': game.get('homePlus1p5Prob'),
                'favoriteCoverLabel': game.get('favoriteCoverLabel'),
                'favoriteCoverProb': game.get('favoriteCoverProb'),
                'marketCoverLabel': game.get('marketCoverLabel'),
                'marketCoverProb': game.get('marketCoverProb'),
                'over7p5Prob': game.get('over7p5Prob'),
                'over8p5Prob': game.get('over8p5Prob'),
                'marketTotal': game.get('marketTotal'),
                'marketTotalLabel': game.get('marketTotalLabel'),
                'marketOverProb': game.get('marketOverProb'),
                'marketUnderProb': game.get('marketUnderProb'),
                'fallbackTotalLabel': game.get('fallbackTotalLabel'),
                'fallbackOverProb': game.get('fallbackOverProb'),
                'fallbackUnderProb': game.get('fallbackUnderProb'),
                'oneRunGameProb': game.get('oneRunGameProb'),
                'tieAfter9Prob': game.get('tieAfter9Prob'),
                'medianTotal': game.get('medianTotal'),
                'medianMargin': game.get('medianMargin'),
                'marketLineSource': game.get('marketLineSource'),
                'marketAwayML': game.get('marketAwayML'),
                'marketHomeML': game.get('marketHomeML'),
                'marketLineUpdated': game.get('marketLineUpdated'),
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


def load_all_game_forecasts(root: Path) -> pd.DataFrame:
    if not root.exists():
        return pd.DataFrame()
    candidates = sorted(root.rglob('game_predictions_*.csv'))
    frames: list[pd.DataFrame] = []
    for path in candidates:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.copy()
        df['__source_file'] = str(path)
        df['__source_mtime'] = path.stat().st_mtime
        df['__forecast_date'] = df.get('forecast_generated_date', pd.Series([None] * len(df))).map(iso_date)
        df['__identity_key'] = df.apply(game_identity_key, axis=1)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_games = pd.concat(frames, ignore_index=True)
    all_games = all_games.sort_values(['__forecast_date', '__source_mtime', '__source_file', 'gameDate', 'home_team', 'away_team'])
    # De-duplicate the same game within the same forecast date, keeping the newest file.
    all_games = all_games.drop_duplicates(subset=['__identity_key', '__forecast_date'], keep='last')
    return all_games


def split_latest_and_movement(all_game_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    if all_game_df is None or all_game_df.empty:
        return pd.DataFrame(), {}
    latest_rows = (
        all_game_df
        .sort_values(['__identity_key', '__forecast_date', '__source_mtime', '__source_file'])
        .drop_duplicates(subset=['__identity_key'], keep='last')
        .copy()
    )
    movement_lookup = {key: grp.copy() for key, grp in all_game_df.groupby('__identity_key', sort=False)}
    return latest_rows, movement_lookup


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

    pitcher_csv = args.pitcher_csv or find_latest('pitcher_predictions_*.csv', args.mlb_output_dir)
    batter_csv = args.batter_csv or find_latest('batter_predictions_*.csv', args.mlb_output_dir)
    workbook = args.picks_workbook or find_latest('top_batter_picks*.xlsx', args.mlb_output_dir)

    if args.game_csv:
        latest_game_df = pd.read_csv(args.game_csv)
        latest_game_df['__identity_key'] = latest_game_df.apply(game_identity_key, axis=1)
        latest_game_df['__forecast_date'] = latest_game_df.get('forecast_generated_date', pd.Series([None] * len(latest_game_df))).map(iso_date)
        all_game_df = latest_game_df.copy()
    else:
        all_game_df = load_all_game_forecasts(args.mlb_output_dir)
        latest_game_df, movement_lookup = split_latest_and_movement(all_game_df)

    if args.game_csv:
        movement_lookup = {key: grp.copy() for key, grp in latest_game_df.groupby('__identity_key', sort=False)}

    if latest_game_df is None or latest_game_df.empty:
        raise SystemExit('Could not find any MLB game_predictions CSVs.')
    if not pitcher_csv or not pitcher_csv.exists():
        raise SystemExit('Could not find an MLB pitcher_predictions CSV.')
    if not batter_csv or not batter_csv.exists():
        raise SystemExit('Could not find an MLB batter_predictions CSV.')

    pitcher_df = pd.read_csv(pitcher_csv)
    batter_df = pd.read_csv(batter_csv)
    market_lines_by_pk, market_lines_by_matchup, market_line_rows = load_mlb_market_lines(repo, args.mlb_output_dir)

    mlb_games, by_pk, mlb_dates = build_game_objects(
        latest_game_df,
        movement_lookup,
        market_lines_by_pk=market_lines_by_pk,
        market_lines_by_matchup=market_lines_by_matchup,
    )
    build_game_details(latest_game_df, pitcher_df, batter_df, by_pk, data_dir / 'mlb_game_details')

    existing_games = load_json(data_dir / 'games.json', [])
    keep_games = [g for g in existing_games if clean_str(g.get('league')).upper() != 'MLB']
    combined_games = keep_games + mlb_games
    combined_games.sort(key=lambda g: (clean_str(g.get('gameDate')), clean_str(g.get('league')), clean_str(g.get('awayTeam')), clean_str(g.get('homeTeam'))))
    write_json(data_dir / 'games.json', combined_games)

    existing_props = load_json(data_dir / 'props.json', [])
    keep_props = [p for p in existing_props if clean_str(p.get('league')).upper() != 'MLB']
    game_lookup = build_game_lookup(latest_game_df)
    mlb_props = build_props_from_workbook(workbook, game_lookup, args.top_props_limit)
    combined_props = keep_props + mlb_props
    write_json(data_dir / 'props.json', combined_props)

    site = load_json(data_dir / 'site.json', {})
    leagues = [clean_str(x).upper() for x in site.get('leagues', []) if clean_str(x)]
    if 'MLB' not in leagues:
        leagues.append('MLB')
    preferred = ['NBA', 'MLB', 'NHL', 'CBB']
    ordered = [x for x in preferred if x in leagues] + [x for x in leagues if x not in preferred]
    site['leagues'] = ordered
    if latest_game_df.get('forecast_generated_date') is not None and not latest_game_df.empty:
        latest_forecast = max((iso_date(v) for v in latest_game_df['forecast_generated_date']), default='')
        if latest_forecast:
            site['lastUpdated'] = latest_forecast
    write_json(data_dir / 'site.json', site)

    movement_sizes = [len(g.get('movement') or []) for g in mlb_games]
    max_points = max(movement_sizes) if movement_sizes else 0
    matched_market_lines = sum(1 for g in mlb_games if g.get('marketSpread') is not None or g.get('marketTotal') is not None)
    print(f'Loaded {len(all_game_df)} total MLB forecast rows across all game prediction files.')
    print(f'Loaded {market_line_rows} MLB market-line archive rows; matched {matched_market_lines} current MLB games.')
    print(f'Wrote {len(mlb_games)} MLB games into {data_dir / "games.json"}')
    print(f'MLB movement points per game: min={min(movement_sizes) if movement_sizes else 0}, max={max_points}')
    print(f'Wrote {len(mlb_props)} MLB homepage props into {data_dir / "props.json"}')
    print(f'Wrote MLB detail files under {data_dir / "mlb_game_details"}')
    return 0


if __name__ == '__main__':

    raise SystemExit(main())
