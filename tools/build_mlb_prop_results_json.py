#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

DISPLAY_TIMEZONE = 'America/Denver'
DEFAULT_MLB_DATA_DIR = Path(r'C:\python\mlb_data')

FINAL_MARKERS = ('final', 'game over', 'completed early')


def clean_str(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if text.lower() == 'nan':
        return ''
    try:
        repaired = text.encode('latin1').decode('utf-8')
        if repaired:
            text = repaired
    except Exception:
        pass
    return text


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


def board_source_rows_from_analyzer_payload(payload: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    entries = payload.get('entries') or []

    def choose_rows(stat: str, player_type: str = 'batter', limit: int = 10, unique_by_player: bool = False) -> list[dict[str, Any]]:
        pool = [
            e for e in entries
            if clean_str(e.get('gameDate')) == clean_str(target_date)
            and normalize_stat(e.get('stat')) == normalize_stat(stat)
        ]
        if player_type:
            typed = [e for e in pool if clean_str(e.get('playerType')).lower() == clean_str(player_type).lower()]
            base = typed if typed else pool
        else:
            base = pool

        if clean_str(player_type).lower() == 'pitcher':
            base = [
                e for e in base
                if not __import__('re').search(r'(^|\b)(tbd|to be determined|probable starter tbd)(\b|$)', clean_str(e.get('player')), __import__('re').I)
            ]

        def sort_key(row: dict[str, Any]):
            pred = safe_float(row.get('pred_anchor'))
            if pred is None:
                pred = safe_float(row.get('mu_cons')) or 0.0
            avg = safe_float(row.get('avg_anchor')) or 0.0
            prob = safe_float(row.get('prob_cons'))
            prob = -1.0 if prob is None else prob
            if clean_str(player_type).lower() == 'pitcher':
                return (-pred, -avg, -prob, clean_str(row.get('player')))
            return (-prob, -pred, clean_str(row.get('player')))

        seen: set[tuple[Any, ...]] = set()
        chosen: list[dict[str, Any]] = []
        for row in sorted(base, key=sort_key):
            if unique_by_player:
                key = (clean_str(row.get('playerId') or row.get('player')), normalize_stat(row.get('stat')))
            else:
                key = (clean_str(row.get('playerId') or row.get('player')), normalize_stat(row.get('stat')), safe_float(row.get('line')))
            if key in seen:
                continue
            seen.add(key)
            chosen.append(row)
            if len(chosen) >= limit:
                break
        return chosen

    board_specs = [
        ('Best hits', 'H', 'batter', 10, False),
        ('Best two-plus total bases', 'TB', 'batter', 10, False),
        ('Top pitcher strikeouts', 'K', 'pitcher', 10, True),
    ]
    rows: list[dict[str, Any]] = []
    for board_title, stat, player_type, limit, unique_by_player in board_specs:
        for entry in choose_rows(stat, player_type=player_type, limit=limit, unique_by_player=unique_by_player):
            team = clean_str(entry.get('team'))
            opp = clean_str(entry.get('opp'))
            prob = safe_float(entry.get('prob_cons'))
            pred = safe_float(entry.get('pred_anchor'))
            if pred is None:
                pred = safe_float(entry.get('mu_cons'))
            note = clean_str(entry.get('boardDriver') or entry.get('summary') or entry.get('driver_summary'))
            if not note and team and opp and prob is not None:
                note = f'{team} vs {opp} • {prob * 100:.0f}% to clear'
            rows.append({
                'date': clean_str(entry.get('gameDate')),
                'league': 'MLB',
                'player': clean_str(entry.get('player')),
                'team': team,
                'opp': opp,
                'matchup': f'{team} vs {opp}'.strip(),
                'stat': normalize_stat(entry.get('stat')),
                'line': safe_float(entry.get('line')),
                'model': pred,
                'probability': prob,
                'confidence': '',
                'note': note,
                'gameId': safe_int(entry.get('gameId')),
                'board': board_title,
            })
    return rows


def load_board_snapshot_rows(snapshot_path: Path, launch_date: str = '') -> list[dict[str, Any]]:
    payload = load_json(snapshot_path, {})
    if isinstance(payload, list):
        rows = payload
    else:
        rows = payload.get('rows') or []
    out = []
    for row in rows:
        date = clean_str(row.get('date') or row.get('gameDate'))
        if launch_date and date and date < launch_date:
            continue
        out.append({
            'date': date,
            'league': 'MLB',
            'player': clean_str(row.get('player')),
            'team': clean_str(row.get('team')),
            'opp': clean_str(row.get('opp') or row.get('opponent')),
            'matchup': clean_str(row.get('matchup')) or f"{clean_str(row.get('team'))} vs {clean_str(row.get('opp') or row.get('opponent'))}".strip(),
            'stat': normalize_stat(row.get('stat') or row.get('stat_display')),
            'line': safe_float(row.get('line')),
            'model': safe_float(row.get('modelPrediction') if 'modelPrediction' in row else row.get('model')),
            'probability': safe_float(row.get('probability')),
            'confidence': clean_str(row.get('confidence')),
            'note': clean_str(row.get('note')),
            'gameId': safe_int(row.get('gameId') or row.get('gamePk')),
            'board': clean_str(row.get('board')),
        })
    return out


def local_today_iso() -> str:
    try:
        return pd.Timestamp.now(tz=DISPLAY_TIMEZONE).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def date_range_inclusive(start_date: str, end_date: str) -> list[str]:
    if not start_date or not end_date or start_date > end_date:
        return []
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    dates: list[str] = []
    cur = start
    while cur <= end:
        dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def load_git_board_rows(repo: Path, target_date: str) -> list[dict[str, Any]]:
    if not target_date or not (repo / '.git').exists():
        return []
    try:
        rev_list = subprocess.run(
            ['git', 'rev-list', 'HEAD', '--', 'data/mlb_props_analyzer.json'],
            cwd=repo, capture_output=True, text=True, check=True
        )
    except Exception:
        return []
    revisions = [line.strip() for line in rev_list.stdout.splitlines() if line.strip()]
    for rev in revisions:
        try:
            shown = subprocess.run(
                ['git', 'show', f'{rev}:data/mlb_props_analyzer.json'],
                cwd=repo, capture_output=True, text=True, check=True
            )
            payload = json.loads(shown.stdout)
        except Exception:
            continue
        if clean_str(payload.get('targetDate')) != clean_str(target_date):
            continue
        return board_source_rows_from_analyzer_payload(payload, target_date)
    return []


def load_table_latest(base_dir: Path, table: str) -> pd.DataFrame:
    table_dir = base_dir / table
    pq = table_dir / f'{table}_latest.parquet'
    csv = table_dir / f'{table}_latest.csv'
    try:
        if pq.exists():
            return pd.read_parquet(pq)
        if csv.exists():
            return pd.read_csv(csv)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def local_date(value: Any) -> str:
    raw = clean_str(value)
    if not raw:
        return ''
    try:
        ts = pd.to_datetime(raw, utc=True)
        if pd.isna(ts):
            return ''
        return ts.tz_convert(DISPLAY_TIMEZONE).date().isoformat()
    except Exception:
        return raw[:10]


def normalize_name(name: Any) -> str:
    return ''.join(ch.lower() for ch in clean_str(name) if ch.isalnum())


def normalize_stat(stat: Any) -> str:
    text = clean_str(stat).upper().replace('.', '').replace('+', '').replace(' ', '')
    aliases = {
        'HITS': 'H', 'HIT': 'H', 'H': 'H',
        'TOTALBASES': 'TB', 'TB': 'TB',
        'DOUBLES': '2B', '2B': '2B',
        'HOMERUNS': 'HR', 'HOME RUNS': 'HR', 'HR': 'HR',
        'STRIKEOUTS': 'K', 'KS': 'K', 'K': 'K',
        'WALKS': 'BB', 'BB': 'BB',
        'STOLENBASES': 'SB', 'SB': 'SB',
        'RBI': 'RBI',
        'RUNS': 'R', 'R': 'R',
        'HRR': 'HRR', 'HRRBIRUNS': 'HRR', 'HITSRUNSRBI': 'HRR', 'HRRBI': 'HRR',
        'OUTS': 'OUTS', 'OUT': 'OUTS',
        'IP': 'IP', 'INNINGSPITCHED': 'IP',
        'HITSALLOWED': 'HA', 'HA': 'HA',
        'ER': 'ER', 'EARNEDRUNS': 'ER',
    }
    return aliases.get(text, text)


def is_final_status(value: Any) -> bool:
    text = clean_str(value).lower()
    return any(mark in text for mark in FINAL_MARKERS)


def prep_games(games_df: pd.DataFrame) -> pd.DataFrame:
    if games_df is None or games_df.empty:
        return pd.DataFrame()
    df = games_df.copy()
    if 'gamePk' in df.columns:
        df['gamePk'] = pd.to_numeric(df['gamePk'], errors='coerce')
    if 'gameDate' in df.columns:
        df['gameDateLocal'] = df['gameDate'].map(local_date)
    else:
        df['gameDateLocal'] = ''
    df['away_team_norm'] = df.get('away_team', pd.Series(index=df.index)).map(clean_str)
    df['home_team_norm'] = df.get('home_team', pd.Series(index=df.index)).map(clean_str)
    df['is_final'] = df.get('status_detailed', pd.Series(index=df.index)).map(is_final_status)
    keep = [c for c in ['gamePk', 'gameDate', 'gameDateLocal', 'status_detailed', 'is_final', 'away_team', 'home_team', 'away_total', 'home_total', 'away_1', 'home_1'] if c in df.columns]
    return df[keep].copy()


def prep_batter_logs(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if 'player_id' in out.columns:
        out['player_id'] = pd.to_numeric(out['player_id'], errors='coerce')
    out['player_norm'] = out.get('player_name', pd.Series(index=out.index)).map(normalize_name)
    out['team_norm'] = out.get('team', pd.Series(index=out.index)).map(clean_str)
    out['opp_norm'] = out.get('opponent', pd.Series(index=out.index)).map(clean_str)
    out['gameDateLocal'] = out.get('gameDate', pd.Series(index=out.index)).map(local_date)
    if 'gamePk' in out.columns:
        out['gamePk'] = pd.to_numeric(out['gamePk'], errors='coerce')
    for col in ['hits', 'totalBases', 'doubles', 'homeRuns', 'strikeOuts', 'baseOnBalls', 'stolenBases', 'runs', 'rbi']:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')
    return out


def prep_pitcher_logs(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if 'player_id' in out.columns:
        out['player_id'] = pd.to_numeric(out['player_id'], errors='coerce')
    out['player_norm'] = out.get('player_name', pd.Series(index=out.index)).map(normalize_name)
    out['team_norm'] = out.get('team', pd.Series(index=out.index)).map(clean_str)
    out['opp_norm'] = out.get('opponent', pd.Series(index=out.index)).map(clean_str)
    out['gameDateLocal'] = out.get('gameDate', pd.Series(index=out.index)).map(local_date)
    if 'gamePk' in out.columns:
        out['gamePk'] = pd.to_numeric(out['gamePk'], errors='coerce')
    if 'outs' not in out.columns and 'inningsPitched' in out.columns:
        try:
            out['outs'] = out['inningsPitched'].map(ip_to_outs)
        except Exception:
            pass
    for col in ['outs', 'strikeOuts', 'baseOnBalls', 'hits_allowed', 'earnedRuns', 'inningsPitched']:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')
    return out


def ip_to_outs(value: Any) -> float | None:
    raw = clean_str(value)
    if not raw:
        return None
    if '.' in raw:
        whole, frac = raw.split('.', 1)
        try:
            return int(whole) * 3 + int(frac)
        except Exception:
            return None
    val = safe_float(raw)
    return None if val is None else val * 3.0


def pick_game_row(prop: dict[str, Any], games_df: pd.DataFrame) -> dict[str, Any] | None:
    if games_df.empty:
        return None
    game_pk = safe_int(prop.get('gameId') or prop.get('gamePk'))
    if game_pk is not None and 'gamePk' in games_df.columns:
        hit = games_df.loc[games_df['gamePk'].eq(game_pk)]
        if not hit.empty:
            return hit.iloc[-1].to_dict()
    game_date = clean_str(prop.get('gameDate') or prop.get('date'))
    team = clean_str(prop.get('team'))
    opp = clean_str(prop.get('opp') or prop.get('opponent'))
    if not game_date or not team or not opp:
        return None
    mask = games_df['gameDateLocal'].eq(game_date) & (
        ((games_df.get('away_team', pd.Series(index=games_df.index)).astype(str) == team) & (games_df.get('home_team', pd.Series(index=games_df.index)).astype(str) == opp)) |
        ((games_df.get('home_team', pd.Series(index=games_df.index)).astype(str) == team) & (games_df.get('away_team', pd.Series(index=games_df.index)).astype(str) == opp))
    )
    hit = games_df.loc[mask]
    return None if hit.empty else hit.iloc[-1].to_dict()


def stat_value_from_row(row: pd.Series | dict[str, Any], stat: str, role: str) -> float | None:
    getter = row.get if isinstance(row, dict) else row.get
    if role == 'batter':
        mapping = {
            'H': 'hits', 'TB': 'totalBases', '2B': 'doubles', 'HR': 'homeRuns', 'K': 'strikeOuts',
            'BB': 'baseOnBalls', 'SB': 'stolenBases', 'RBI': 'rbi', 'R': 'runs'
        }
        if stat == 'HRR':
            vals = [safe_float(getter('hits')), safe_float(getter('runs')), safe_float(getter('rbi'))]
            vals = [v for v in vals if v is not None]
            return sum(vals) if vals else None
        col = mapping.get(stat)
        return safe_float(getter(col)) if col else None
    if role == 'pitcher':
        mapping = {
            'OUTS': 'outs', 'IP': 'inningsPitched', 'K': 'strikeOuts', 'BB': 'baseOnBalls', 'HA': 'hits_allowed', 'ER': 'earnedRuns'
        }
        col = mapping.get(stat)
        return safe_float(getter(col)) if col else None
    return None


def resolve_player_row(prop: dict[str, Any], batter_df: pd.DataFrame, pitcher_df: pd.DataFrame, games_df: pd.DataFrame) -> tuple[str | None, dict[str, Any] | None]:
    player_norm = normalize_name(prop.get('player'))
    team = clean_str(prop.get('team'))
    opp = clean_str(prop.get('opp') or prop.get('opponent'))
    game_date = clean_str(prop.get('gameDate') or prop.get('date'))
    game_pk = safe_int(prop.get('gameId') or prop.get('gamePk'))
    stat = normalize_stat(prop.get('stat') or prop.get('stat_display'))

    def subset(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        mask = df['player_norm'].eq(player_norm)
        if game_pk is not None and 'gamePk' in df.columns:
            mask &= df['gamePk'].eq(game_pk)
        else:
            if game_date:
                mask &= df['gameDateLocal'].eq(game_date)
            if team:
                mask &= df['team_norm'].eq(team)
            if opp:
                mask &= df['opp_norm'].eq(opp)
        return df.loc[mask]

    bat = subset(batter_df)
    pit = subset(pitcher_df)

    # final-game filter if we can match the game
    game_row = pick_game_row(prop, games_df)
    if game_row and not is_final_status(game_row.get('status_detailed')):
        return None, None

    pitcher_only = {'OUTS', 'IP', 'HA', 'ER'}
    if stat in pitcher_only:
        return ('pitcher', None if pit.empty else pit.iloc[-1].to_dict())

    # Ks and BB can exist for both, prefer whichever table has the player on that slate.
    if not bat.empty and pit.empty:
        return 'batter', bat.iloc[-1].to_dict()
    if not pit.empty and bat.empty:
        return 'pitcher', pit.iloc[-1].to_dict()
    if not bat.empty and not pit.empty:
        # Prefer batter for H/TB/2B/HR/SB/R/RBI/HRR and pitcher for pitcher-only stats.
        if stat in {'H', 'TB', '2B', 'HR', 'SB', 'RBI', 'R', 'HRR'}:
            return 'batter', bat.iloc[-1].to_dict()
        return 'pitcher', pit.iloc[-1].to_dict()
    return None, None


def outcome_label(actual: float | None, line: float | None) -> str:
    if actual is None or line is None:
        return 'Pending'
    if abs(actual - line) < 1e-9:
        return 'Push'
    return 'Win' if actual > line else 'Loss'


def merge_unique(existing: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in existing + new_rows:
        key = (
            clean_str(row.get('date')),
            clean_str(row.get('player')),
            clean_str(row.get('team')),
            normalize_stat(row.get('stat')),
            safe_float(row.get('line')),
            clean_str(row.get('matchup')),
        )
        by_key[key] = row
    rows = list(by_key.values())
    rows.sort(key=lambda r: (clean_str(r.get('date')), clean_str(r.get('player')), clean_str(r.get('stat'))), reverse=True)
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [r for r in rows if clean_str(r.get('result')) in {'Win', 'Loss', 'Push'}]
    wins = sum(clean_str(r.get('result')) == 'Win' for r in settled)
    losses = sum(clean_str(r.get('result')) == 'Loss' for r in settled)
    pushes = sum(clean_str(r.get('result')) == 'Push' for r in settled)
    by_stat: dict[str, dict[str, Any]] = {}
    for stat, group in defaultdict(list, ((normalize_stat(r.get('stat')), []) for r in settled)).items():
        pass
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in settled:
        grouped[normalize_stat(row.get('stat'))].append(row)
    for stat, group in grouped.items():
        w = sum(clean_str(r.get('result')) == 'Win' for r in group)
        l = sum(clean_str(r.get('result')) == 'Loss' for r in group)
        p = sum(clean_str(r.get('result')) == 'Push' for r in group)
        dec = w + l
        by_stat[stat] = {
            'wins': w,
            'losses': l,
            'pushes': p,
            'settled': len(group),
            'decisionCount': dec,
            'winRate': round(w / dec, 4) if dec else None,
        }
    dates = sorted({clean_str(r.get('date')) for r in settled if clean_str(r.get('date'))})
    decisions = wins + losses
    return {
        'asOf': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'latestSettledDate': dates[-1] if dates else '',
        'overall': {
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'settled': len(settled),
            'decisionCount': decisions,
            'winRate': round(wins / decisions, 4) if decisions else None,
        },
        'byStat': by_stat,
    }




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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build MLB prop results history from site props.json and scraper outputs.')
    parser.add_argument('--website-repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--mlb-data-dir', type=Path, default=DEFAULT_MLB_DATA_DIR)
    parser.add_argument('--enable', action='store_true')
    parser.add_argument('--live-start-date', default='')
    parser.add_argument('--props-path', type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.enable:
        print('[INFO] MLB prop results tracking disabled. Use --enable when ready.')
        return 0

    data_dir = args.website_repo / 'data'
    repo = args.website_repo
    props_path = args.props_path or (data_dir / 'props.json')
    snapshot_path = data_dir / 'mlb_home_board_snapshot.json'
    analyzer_path = data_dir / 'mlb_props_analyzer.json'
    pending_path = data_dir / 'mlb_prop_results_pending.json'
    history_path = data_dir / 'mlb_prop_results_history.json'
    summary_path = data_dir / 'mlb_prop_results_summary.json'

    launch_date = resolve_launch_date(data_dir, args.live_start_date)
    if not launch_date:
        write_json(history_path, [])
        write_json(pending_path, [])
        write_json(summary_path, {"latestDate": None, "overall": {"wins": 0, "losses": 0, "pushes": 0, "graded": 0, "winPct": None}, "byStat": {}})
        print('[INFO] MLB prop results tracking is paused until data/mlb_results_launch_date.txt is set.')
        return 0

    history = load_json(history_path, [])
    pending = load_json(pending_path, [])

    yesterday = (datetime.fromisoformat(local_today_iso()).date() - timedelta(days=1)).isoformat()
    pending = [
        row for row in pending
        if clean_str(row.get('date')) and clean_str(row.get('date')) >= launch_date and clean_str(row.get('date')) <= yesterday
    ]

    current = load_board_snapshot_rows(snapshot_path, launch_date)
    analyzer_payload = load_json(analyzer_path, {})
    analyzer_target_date = clean_str(analyzer_payload.get('targetDate')) if isinstance(analyzer_payload, dict) else ''
    if analyzer_target_date and (not launch_date or analyzer_target_date >= launch_date):
        current = merge_unique(current, board_source_rows_from_analyzer_payload(analyzer_payload, analyzer_target_date))
    source_label = str(snapshot_path)
    if not current:
        all_props = load_json(props_path, [])
        for p in all_props:
            if clean_str(p.get('league')).upper() != 'MLB':
                continue
            game_date = clean_str(p.get('gameDate'))
            if launch_date and game_date and game_date < launch_date:
                continue
            current.append({
                'date': game_date,
                'league': 'MLB',
                'player': clean_str(p.get('player')),
                'team': clean_str(p.get('team')),
                'opp': clean_str(p.get('opp') or p.get('opponent')),
                'matchup': f"{clean_str(p.get('team'))} vs {clean_str(p.get('opp') or p.get('opponent'))}".strip(),
                'stat': clean_str(p.get('stat') or p.get('stat_display')),
                'line': safe_float(p.get('line')),
                'model': safe_float(p.get('modelPrediction') if 'modelPrediction' in p else p.get('model')),
                'probability': safe_float(p.get('probability')),
                'confidence': clean_str(p.get('confidence')),
                'note': clean_str(p.get('note')),
                'gameId': safe_int(p.get('gameId') or p.get('gamePk')),
                'board': clean_str(p.get('board')),
            })
        source_label = str(props_path)

    existing_counts: dict[str, int] = defaultdict(int)
    for row in history + pending:
        row_date = clean_str(row.get('date'))
        if row_date:
            existing_counts[row_date] += 1

    git_backfill = []
    for missing_date in date_range_inclusive(launch_date, yesterday):
        if existing_counts.get(missing_date, 0) >= 30:
            continue
        git_backfill.extend(load_git_board_rows(repo, missing_date))

    current = merge_unique(current, git_backfill)
    pending = merge_unique(pending, current)

    batter_df = prep_batter_logs(load_table_latest(args.mlb_data_dir, 'batter_game_logs'))
    pitcher_df = prep_pitcher_logs(load_table_latest(args.mlb_data_dir, 'pitcher_game_logs'))
    games_df = prep_games(load_table_latest(args.mlb_data_dir, 'games'))

    unresolved = []
    settled_rows = []
    for prop in pending:
        game_row = pick_game_row(prop, games_df)
        if game_row is None or not is_final_status(game_row.get('status_detailed')):
            unresolved.append(prop)
            continue
        role, actual_row = resolve_player_row(prop, batter_df, pitcher_df, games_df)
        if role is None or actual_row is None:
            unresolved.append(prop)
            continue
        stat_key = normalize_stat(prop.get('stat'))
        actual_value = stat_value_from_row(actual_row, stat_key, role)
        line = safe_float(prop.get('line'))
        settled_rows.append({
            **prop,
            'role': role,
            'actual': actual_value,
            'result': outcome_label(actual_value, line),
            'gamePk': safe_int(actual_row.get('gamePk') or prop.get('gameId')),
        })

    history = merge_unique(history, settled_rows)
    write_json(history_path, history)
    write_json(pending_path, unresolved)
    write_json(summary_path, summarize(history))

    print(f'Loaded {len(current)} tracked MLB board props from {source_label}')
    if git_backfill:
        print(f'Backfilled {len(git_backfill)} MLB board props from git history for prior dates.')
    print(f'Settled {len(settled_rows)} MLB props; {len(unresolved)} still pending')
    print(f'Wrote MLB prop history -> {history_path}')
    print(f'Wrote MLB prop pending queue -> {pending_path}')
    print(f'Wrote MLB prop summary -> {summary_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
