#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f'pandas is required: {exc}')

try:
    import pyarrow.parquet as pq  # type: ignore
except Exception:  # pragma: no cover
    pq = None

DEFAULT_MLB_DATA_DIR = Path(r'C:\python\mlb_data')
DEFAULT_MLB_OUTPUT_DIR = Path(r'C:\python\mlb_model_outputs')

FIELD_GROUPS: dict[str, list[str]] = {
    'join_game_id': [
        'gamePk', 'game_pk', 'gameId', 'game_id', 'game_id_mlb', 'mlb_game_id', 'pk'
    ],
    'date': [
        'gameDate', 'game_date', 'date', 'officialDate', 'target_game_date', 'forecast_generated_date'
    ],
    'team_context': [
        'team', 'team_abbr', 'teamName', 'team_name', 'opponent', 'opp', 'away_team', 'home_team',
        'awayTeam', 'homeTeam', 'team_side', 'isHome', 'location'
    ],
    'batter_hand': [
        'batSide', 'bat_side', 'stand', 'batterHand', 'batter_hand', 'bats', 'bat_hand', 'hitter_hand'
    ],
    'pitcher_hand': [
        'opp_pitch_hand', 'opposing_pitcher_hand', 'opposingPitcherHand', 'pitcherHand',
        'pitcher_hand', 'starterHand', 'starter_hand', 'oppStarterHand', 'opponentStarterHand',
        'pitchHand', 'pitch_hand', 'throws', 'throwingHand', 'hand'
    ],
    'starter_identity': [
        'opp_starter_name', 'opposing_starter_name', 'opposingStarterName', 'opponentStarter',
        'starter_name', 'starterName', 'pitcher_name', 'opp_pitcher_name', 'probablePitcherName',
        'away_probable_pitcher', 'home_probable_pitcher', 'awayStarter', 'homeStarter',
        'opp_starter_id', 'opposing_starter_id', 'opposingStarterId', 'opponentStarterId',
        'starter_id', 'starterId', 'pitcher_id', 'opp_pitcher_id', 'probablePitcherId',
        'away_probable_pitcher_id', 'home_probable_pitcher_id'
    ],
    'park': [
        'park', 'venue', 'venueName', 'venue_name', 'ballpark', 'stadium', 'field', 'parkName'
    ],
    'weather_temp': [
        'temperature_f', 'temperatureF', 'temp_f', 'game_temp_f', 'temperature_2m',
        'temperature', 'temp', 'weather_temp', 'weatherTemp'
    ],
    'weather_wind': [
        'wind_speed_10m', 'windMph', 'wind_mph', 'wind', 'wind_speed', 'windSpeed',
        'wind_direction', 'windDirection', 'wind_dir'
    ],
    'pitch_mix': [
        'pitch_mix', 'pitchMix', 'starter_pitch_mix', 'opp_pitch_mix', 'opposing_pitch_mix',
        'fastball_pct', 'slider_pct', 'changeup_pct', 'curve_pct', 'cutter_pct', 'sinker_pct',
        'ff_pct', 'sl_pct', 'ch_pct', 'cu_pct', 'fc_pct', 'si_pct', 'pitch_type', 'pitchType'
    ],
    'lineup_context': [
        'batting_order', 'battingOrder', 'projected_batting_order', 'lineupSpot', 'lineup_spot'
    ],
}

PREFERRED_SOURCE_HINTS = [
    'batter_game_logs', 'pitcher_game_logs', 'game', 'games', 'schedule', 'probable', 'pitcher',
    'weather', 'venue', 'lineup', 'statcast', 'pitch_mix', 'pitchmix'
]


def clean_str(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if text.lower() in {'nan', 'none', 'null'}:
        return ''
    return text


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def newest_file_for_table(table_dir: Path) -> Path | None:
    if not table_dir.exists() or not table_dir.is_dir():
        return None
    preferred = [
        table_dir / f'{table_dir.name}_latest.parquet',
        table_dir / f'{table_dir.name}_latest.csv',
        table_dir / f'{table_dir.name}.parquet',
        table_dir / f'{table_dir.name}.csv',
    ]
    for p in preferred:
        if p.exists() and p.is_file():
            return p
    files = [p for p in table_dir.glob('*') if p.is_file() and p.suffix.lower() in {'.csv', '.parquet', '.json'}]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def find_source_files(mlb_data_dir: Path, mlb_output_dir: Path, max_output_files: int) -> list[Path]:
    files: list[Path] = []
    if mlb_data_dir.exists():
        for child in sorted(mlb_data_dir.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                p = newest_file_for_table(child)
                if p:
                    files.append(p)
            elif child.is_file() and child.suffix.lower() in {'.csv', '.parquet', '.json'}:
                files.append(child)
    if mlb_output_dir.exists():
        output_files = [p for p in mlb_output_dir.rglob('*.csv') if p.is_file()]
        output_files = sorted(output_files, key=lambda p: p.stat().st_mtime, reverse=True)[:max_output_files]
        files.extend(output_files)
    # De-dupe while preserving order.
    seen = set()
    out = []
    for p in files:
        key = str(p.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def parquet_schema(path: Path) -> tuple[list[str], int | None]:
    if pq is not None:
        try:
            pf = pq.ParquetFile(path)
            return list(pf.schema.names), int(pf.metadata.num_rows) if pf.metadata is not None else None
        except Exception:
            pass
    try:
        df = pd.read_parquet(path)
        return list(df.columns), int(len(df))
    except Exception:
        return [], None


def csv_schema(path: Path) -> tuple[list[str], int | None]:
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            header = next(reader, [])
        return [h.strip() for h in header if h is not None], None
    except UnicodeDecodeError:
        try:
            with path.open('r', encoding='latin-1', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, [])
            return [h.strip() for h in header if h is not None], None
        except Exception:
            return [], None
    except Exception:
        return [], None


def json_schema(path: Path) -> tuple[list[str], int | None]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return [], None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ['rows', 'data', 'items', 'games', 'entries']:
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            return list(data.keys()), 1
    else:
        return [], None
    cols = set()
    for row in rows[:25]:
        if isinstance(row, dict):
            cols.update(row.keys())
    return sorted(cols), len(rows)


def get_schema(path: Path) -> tuple[list[str], int | None]:
    suffix = path.suffix.lower()
    if suffix == '.parquet':
        return parquet_schema(path)
    if suffix == '.csv':
        return csv_schema(path)
    if suffix == '.json':
        return json_schema(path)
    return [], None


def read_sample(path: Path, columns: list[str], sample_rows: int) -> pd.DataFrame:
    if not columns or sample_rows <= 0:
        return pd.DataFrame()
    suffix = path.suffix.lower()
    try:
        if suffix == '.csv':
            return pd.read_csv(path, usecols=lambda c: c in set(columns), nrows=sample_rows, low_memory=False)
        if suffix == '.parquet':
            return pd.read_parquet(path, columns=columns).head(sample_rows)
        if suffix == '.json':
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                for key in ['rows', 'data', 'items', 'games', 'entries']:
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
            if isinstance(data, list):
                return pd.DataFrame(data).loc[:, lambda d: [c for c in columns if c in d.columns]].head(sample_rows)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def group_hits(columns: list[str]) -> dict[str, list[str]]:
    col_lookup = {c.lower(): c for c in columns}
    hits: dict[str, list[str]] = {}
    for group, candidates in FIELD_GROUPS.items():
        matched = []
        candidate_lowers = {c.lower() for c in candidates}
        for col in columns:
            low = col.lower()
            if low in candidate_lowers:
                matched.append(col)
                continue
            # Looser pitch-mix/weather matches because those outputs often have vendor-specific column names.
            if group == 'pitch_mix' and any(token in low for token in ['pitch_mix', 'pitchmix', 'fastball', 'slider', 'changeup', 'curve', 'cutter', 'sinker', 'sweeper']):
                matched.append(col)
            elif group == 'weather_temp' and any(token in low for token in ['temp', 'temperature']):
                matched.append(col)
            elif group == 'weather_wind' and 'wind' in low:
                matched.append(col)
            elif group == 'starter_identity' and any(token in low for token in ['starter', 'probable', 'pitcher_name', 'pitcher_id']):
                matched.append(col)
        hits[group] = sorted(set(matched))
    return hits


def non_empty_counts(path: Path, hits: dict[str, list[str]], sample_rows: int) -> dict[str, dict[str, Any]]:
    sample_cols = sorted({c for cols in hits.values() for c in cols})
    df = read_sample(path, sample_cols, sample_rows)
    out: dict[str, dict[str, Any]] = {}
    if df.empty:
        return out
    for group, cols in hits.items():
        group_out: dict[str, Any] = {}
        for col in cols:
            if col not in df.columns:
                continue
            series = df[col]
            if series.dtype == object:
                non_empty = series.map(clean_str).astype(bool)
            else:
                non_empty = series.notna()
            group_out[col] = {
                'sampleNonEmpty': int(non_empty.sum()),
                'sampleRows': int(len(series)),
                'examples': [clean_str(v) for v in series[non_empty].head(3).tolist()],
            }
        if group_out:
            out[group] = group_out
    return out


def score_source(path: Path, hits: dict[str, list[str]]) -> int:
    name = str(path).lower()
    score = 0
    for hint in PREFERRED_SOURCE_HINTS:
        if hint in name:
            score += 2
    important = ['join_game_id', 'date', 'team_context', 'batter_hand', 'pitcher_hand', 'starter_identity', 'park', 'weather_temp', 'weather_wind', 'pitch_mix']
    score += sum(1 for g in important if hits.get(g))
    if hits.get('join_game_id') and (hits.get('pitcher_hand') or hits.get('starter_identity') or hits.get('park') or hits.get('weather_temp') or hits.get('weather_wind')):
        score += 10
    return score


def summarize_join_options(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    joinable = []
    for row in rows:
        hits = row.get('candidateColumns', {})
        if not hits.get('join_game_id'):
            continue
        groups = []
        for g in ['pitcher_hand', 'starter_identity', 'park', 'weather_temp', 'weather_wind', 'pitch_mix', 'batter_hand', 'lineup_context']:
            if hits.get(g):
                groups.append(g)
        if groups:
            joinable.append({
                'source': row['source'],
                'rows': row.get('rows'),
                'joinColumns': hits.get('join_game_id'),
                'usableGroups': groups,
                'bestFields': {g: hits.get(g) for g in groups},
            })
    return sorted(joinable, key=lambda r: (len(r['usableGroups']), r.get('rows') or 0), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Audit upstream MLB sources for historical matchup context fields.')
    parser.add_argument('--data-dir', type=Path, default=Path('data'), help='Website data directory for audit outputs.')
    parser.add_argument('--mlb-data-dir', type=Path, default=DEFAULT_MLB_DATA_DIR)
    parser.add_argument('--mlb-output-dir', type=Path, default=DEFAULT_MLB_OUTPUT_DIR)
    parser.add_argument('--max-output-files', type=int, default=30)
    parser.add_argument('--sample-rows', type=int, default=500)
    args = parser.parse_args()

    sources = find_source_files(args.mlb_data_dir, args.mlb_output_dir, args.max_output_files)
    rows = []
    for path in sources:
        columns, n_rows = get_schema(path)
        hits = group_hits(columns)
        useful_hits = {g: cols for g, cols in hits.items() if cols}
        counts = non_empty_counts(path, useful_hits, args.sample_rows) if useful_hits else {}
        rows.append({
            'source': str(path),
            'fileName': path.name,
            'parent': path.parent.name,
            'suffix': path.suffix.lower(),
            'rows': n_rows,
            'columnCount': len(columns),
            'candidateColumns': useful_hits,
            'sampleCoverage': counts,
            'sourceScore': score_source(path, hits),
            'modifiedTime': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None,
        })

    rows_sorted = sorted(rows, key=lambda r: r['sourceScore'], reverse=True)
    join_options = summarize_join_options(rows_sorted)
    batter_logs = [r for r in rows_sorted if 'batter_game_logs' in r['source'].lower()]
    pitcher_logs = [r for r in rows_sorted if 'pitcher_game_logs' in r['source'].lower()]

    summary = {
        'generatedAt': utc_now(),
        'inputs': {
            'mlbDataDir': str(args.mlb_data_dir),
            'mlbOutputDir': str(args.mlb_output_dir),
            'sampleRows': args.sample_rows,
            'sourcesScanned': len(rows_sorted),
        },
        'shortRead': {
            'batterGameLogsFound': bool(batter_logs),
            'pitcherGameLogsFound': bool(pitcher_logs),
            'joinableContextSources': len(join_options),
            'topJoinableSource': join_options[0] if join_options else None,
        },
        'batterGameLogs': batter_logs[:3],
        'pitcherGameLogs': pitcher_logs[:3],
        'joinableContextSources': join_options[:25],
        'topSources': rows_sorted[:30],
        'recommendedNextStep': (
            'If joinableContextSources has a source with gamePk plus starter/weather/park fields, patch build_mlb_props_analyzer_json.py to enrich historical logs by gamePk. '
            'If not, patch the upstream scraper/model output to add those fields to batter_game_logs and pitcher_game_logs before the props analyzer builder runs.'
        ),
    }

    out_dir = args.data_dir / 'audits'
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'mlb_source_matchup_context_audit.json'
    csv_path = out_dir / 'mlb_source_matchup_context_audit.csv'
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    with csv_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['sourceScore', 'source', 'rows', 'columnCount', 'candidateGroups', 'joinColumns', 'starterFields', 'handFields', 'parkFields', 'weatherFields', 'pitchMixFields'])
        writer.writeheader()
        for r in rows_sorted:
            hits = r.get('candidateColumns', {})
            writer.writerow({
                'sourceScore': r['sourceScore'],
                'source': r['source'],
                'rows': r.get('rows'),
                'columnCount': r['columnCount'],
                'candidateGroups': ', '.join(hits.keys()),
                'joinColumns': ', '.join(hits.get('join_game_id', [])),
                'starterFields': ', '.join(hits.get('starter_identity', [])),
                'handFields': ', '.join(hits.get('batter_hand', []) + hits.get('pitcher_hand', [])),
                'parkFields': ', '.join(hits.get('park', [])),
                'weatherFields': ', '.join(hits.get('weather_temp', []) + hits.get('weather_wind', [])),
                'pitchMixFields': ', '.join(hits.get('pitch_mix', [])),
            })

    print(f'[OK] Wrote {json_path}')
    print(f'[OK] Wrote {csv_path}')
    if join_options:
        print(f'[INFO] Found {len(join_options)} joinable context source(s). Top: {join_options[0]["source"]}')
    else:
        print('[INFO] No joinable historical context source found yet. Upstream logs likely need new fields added.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
