#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import timezone
from pathlib import Path
from typing import Any

import pandas as pd

DISPLAY_TIMEZONE = 'America/Denver'
DEFAULT_MLB_DATA_DIR = Path(r'C:\python\mlb_data')

BATTER_MARKETS = [
    {
        'stat': 'H',
        'display': 'Hits',
        'pred_col': 'pred_hits',
        'prob_cols': {0.5: 'prob_hit'},
        'value_col': 'hits',
        'avg_cols': ['hits_r20_x', 'hits_r10_x', 'hits_r5_x'],
        'prior_col': 'prior_bat_hits_prior',
        'default_lines': [0.5, 1.5, 2.5],
        'min_prob': 0.02,
    },
    {
        'stat': 'TB',
        'display': 'Total Bases',
        'pred_col': 'pred_total_bases',
        'prob_cols': {1.5: 'prob_tb2plus'},
        'value_col': 'totalBases',
        'avg_cols': ['totalBases_r20', 'totalBases_r10', 'totalBases_r5'],
        'prior_col': 'prior_bat_totalBases_prior',
        'default_lines': [1.5, 2.5, 3.5],
        'min_prob': 0.02,
    },
    {
        'stat': '2B',
        'display': 'Doubles',
        'pred_col': 'pred_doubles',
        'prob_cols': {0.5: 'prob_double'},
        'value_col': 'doubles',
        'avg_cols': ['doubles_r20', 'doubles_r10', 'doubles_r5'],
        'prior_col': 'prior_bat_doubles_prior',
        'default_lines': [0.5, 1.5],
        'min_prob': 0.01,
    },
    {
        'stat': 'HR',
        'display': 'Home Runs',
        'pred_col': 'pred_hr',
        'prob_cols': {0.5: 'prob_hr'},
        'value_col': 'homeRuns',
        'avg_cols': ['homeRuns_r20', 'homeRuns_r10', 'homeRuns_r5'],
        'prior_col': 'prior_bat_homeRuns_prior',
        'default_lines': [0.5, 1.5],
        'min_prob': 0.01,
    },
    {
        'stat': 'K',
        'display': 'Strikeouts',
        'pred_col': 'pred_k',
        'prob_cols': {0.5: 'prob_k'},
        'value_col': 'strikeOuts',
        'avg_cols': ['strikeOuts_r20', 'strikeOuts_r10', 'strikeOuts_r5'],
        'prior_col': 'prior_bat_strikeOuts_prior',
        'default_lines': [0.5, 1.5, 2.5],
        'min_prob': 0.02,
    },
    {
        'stat': 'BB',
        'display': 'Walks',
        'pred_col': 'pred_bb',
        'prob_cols': {0.5: 'prob_bb'},
        'value_col': 'baseOnBalls',
        'avg_cols': ['baseOnBalls_r20', 'baseOnBalls_r10', 'baseOnBalls_r5'],
        'prior_col': 'prior_bat_baseOnBalls_prior',
        'default_lines': [0.5, 1.5, 2.5],
        'min_prob': 0.02,
    },
    {
        'stat': 'HRR',
        'display': 'Hits+Runs+RBI',
        'pred_col': 'pred_hrr',
        'prob_cols': {1.5: 'prob_hrr2plus'},
        'value_col': 'hrr',
        'avg_cols': ['hrr_r20', 'hrr_r10', 'hrr_r5'],
        'prior_col': 'prior_bat_hrr_prior',
        'default_lines': [0.5, 1.5, 2.5],
        'min_prob': 0.02,
    },
    {
        'stat': 'SB',
        'display': 'Stolen Bases',
        'pred_col': 'pred_sb',
        'prob_cols': {0.5: 'prob_sb'},
        'value_col': 'stolenBases',
        'avg_cols': ['stolenBases_r20', 'stolenBases_r10', 'stolenBases_r5'],
        'prior_col': 'prior_bat_stolenBases_prior',
        'default_lines': [0.5, 1.5],
        'min_prob': 0.01,
    },
]

PITCHER_MARKETS = [
    {
        'stat': 'K',
        'display': 'Pitcher Strikeouts',
        'pred_col': 'pred_k',
        'value_col': 'strikeOuts',
        'avg_cols': ['strikeOuts_r10', 'strikeOuts_r5', 'strikeOuts_r3'],
        'prior_col': 'prior_sp_strikeOuts_prior',
        'default_lines': [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5],
        'context_label': 'IP',
        'workload_col': 'pred_ip',
    },
    {
        'stat': 'OUTS',
        'display': 'Pitcher Outs',
        'pred_col': 'pred_outs',
        'value_col': 'outsRecorded',
        'avg_cols': ['outsRecorded_r10', 'outsRecorded_r5', 'outsRecorded_r3'],
        'prior_col': 'prior_sp_outsRecorded_prior',
        'default_lines': [11.5, 14.5, 17.5, 20.5],
        'context_label': 'Outs',
        'workload_col': 'pred_outs',
    },
    {
        'stat': 'IP',
        'display': 'Pitcher Innings Pitched',
        'pred_col': 'pred_ip',
        'value_col': 'inningsPitched',
        'avg_cols': ['inningsPitched_r10', 'inningsPitched_r5', 'inningsPitched_r3'],
        'prior_col': 'prior_sp_inningsPitched_prior',
        'default_lines': [4.0, 5.0, 6.0, 7.0],
        'context_label': 'IP',
        'workload_col': 'pred_ip',
    },
    {
        'stat': 'BB',
        'display': 'Pitcher Walks Allowed',
        'pred_col': 'pred_bb',
        'value_col': 'baseOnBalls',
        'avg_cols': ['baseOnBalls_r10', 'baseOnBalls_r5', 'baseOnBalls_r3'],
        'prior_col': 'prior_sp_baseOnBalls_prior',
        'default_lines': [0.5, 1.5, 2.5, 3.5],
        'context_label': 'IP',
        'workload_col': 'pred_ip',
    },
    {
        'stat': 'HA',
        'display': 'Pitcher Hits Allowed',
        'pred_col': 'pred_hits_allowed',
        'value_col': 'hitsAllowed',
        'avg_cols': ['hitsAllowed_r10', 'hitsAllowed_r5', 'hitsAllowed_r3'],
        'prior_col': 'prior_sp_hitsAllowed_prior',
        'default_lines': [3.5, 4.5, 5.5, 6.5],
        'context_label': 'IP',
        'workload_col': 'pred_ip',
    },
    {
        'stat': 'ER',
        'display': 'Pitcher Earned Runs',
        'pred_col': 'pred_er',
        'value_col': 'earnedRuns',
        'avg_cols': ['earnedRuns_r10', 'earnedRuns_r5', 'earnedRuns_r3'],
        'prior_col': 'prior_sp_earnedRuns_prior',
        'default_lines': [0.5, 1.5, 2.5, 3.5],
        'context_label': 'IP',
        'workload_col': 'pred_ip',
    },
]

def clean_str(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if text.lower() == 'nan':
        return ''
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
    try:
        if value is None or value == '':
            return None
        return int(float(value))
    except Exception:
        return None


def first_text_from(row: Any, candidates: list[str]) -> str:
    """Return the first non-empty text value from a pandas row or Series-like object."""
    for col in candidates:
        try:
            value = row.get(col)
        except Exception:
            value = None
        text = clean_str(value)
        if text:
            return text
    return ''


def first_number_from(row: Any, candidates: list[str]) -> float | None:
    """Return the first usable numeric value from a pandas row or Series-like object."""
    for col in candidates:
        try:
            value = row.get(col)
        except Exception:
            value = None
        num = safe_float(value)
        if num is not None:
            return num
    return None


def normalize_hand(value: Any) -> str:
    text = clean_str(value).upper()
    if not text:
        return ''
    if text in {'L', 'LEFT', 'LHP', 'LH', 'LEFTY'}:
        return 'L'
    if text in {'R', 'RIGHT', 'RHP', 'RH', 'RIGHTY'}:
        return 'R'
    if text in {'B', 'S', 'SWITCH', 'BOTH'}:
        return 'B'
    return text[:1] if text[:1] in {'L', 'R', 'B'} else ''


def f_from_c_or_f(value: Any, source_col: str = '') -> float | None:
    num = safe_float(value)
    if num is None:
        return None
    # Existing weather fields in the model are usually Celsius. If the column name
    # or value already appears Fahrenheit, keep it; otherwise convert plausible C.
    col = (source_col or '').lower()
    if 'fahrenheit' in col or col.endswith('_f') or col.endswith('f') or num > 60:
        return num
    return (num * 9 / 5) + 32


def handedness_text(batter_hand: Any, pitcher_hand: Any) -> str:
    b = normalize_hand(batter_hand)
    p = normalize_hand(pitcher_hand)
    return f'{b} vs {p}' if b and p else ''


def matchup_context_from_batter_row(row: pd.Series, game: dict[str, Any] | None = None, location: str = '') -> dict[str, Any]:
    """Structured current matchup context for batter rows.

    This mirrors the text in driverSummary but stores it as real JSON fields so
    the UI and Similarity v2 do not have to parse display text forever.
    """
    order = safe_int(row.get('projected_batting_order'))
    batter_hand = normalize_hand(first_text_from(row, ['batSide','bat_side','stand','batterHand','batter_hand','bats']))
    pitcher_hand = normalize_hand(first_text_from(row, ['opp_pitch_hand','opposing_pitcher_hand','pitcherHand','starterHand','oppStarterHand','opponentStarterHand','pitchHand']))
    temp = None
    for col in ['temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','temperature','temp']:
        raw = row.get(col) if col in row.index else None
        temp = f_from_c_or_f(raw, col)
        if temp is not None:
            break
    wind = first_number_from(row, ['wind_speed_10m','windMph','wind_mph','wind','wind_speed'])
    starter = first_text_from(row, ['opp_starter_name','opposing_starter_name','opponentStarter','starter_name','pitcher_name','opp_pitcher_name'])
    starter_id = first_text_from(row, ['opp_starter_id','opposing_starter_id','opponentStarterId','pitcher_id','opp_pitcher_id'])
    park = first_text_from(row, ['park','venue','venueName','venue_name','ballpark','stadium'])
    pitch_mix = first_text_from(row, ['pitch_mix','pitchMix','starter_pitch_mix','opp_pitch_mix','opposing_pitch_mix']) or pitch_mix_summary_from_row(row)
    out = {
        'lineupOrder': order,
        'batterHand': batter_hand or None,
        'pitcherHand': pitcher_hand or None,
        'handednessText': handedness_text(batter_hand, pitcher_hand) or None,
        'temperatureF': round(temp, 1) if temp is not None else None,
        'windMph': round(wind, 1) if wind is not None else None,
        'park': park or None,
        'location': location or None,
        'opponentStarterName': starter or None,
        'opponentStarterId': starter_id or None,
        'pitchMixSummary': pitch_mix or None,
        'source': 'build_mlb_props_analyzer_json current row',
    }
    return {k: v for k, v in out.items() if v not in [None, '']}


def matchup_context_from_pitcher_row(row: pd.Series, game: dict[str, Any] | None = None, location: str = '') -> dict[str, Any]:
    pitcher_hand = normalize_hand(first_text_from(row, ['pitchHand','pitch_hand','throws','throwingHand','hand']))
    temp = None
    for col in ['temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','temperature','temp']:
        raw = row.get(col) if col in row.index else None
        temp = f_from_c_or_f(raw, col)
        if temp is not None:
            break
    wind = first_number_from(row, ['wind_speed_10m','windMph','wind_mph','wind','wind_speed'])
    park = first_text_from(row, ['park','venue','venueName','venue_name','ballpark','stadium'])
    pitch_mix = first_text_from(row, ['pitch_mix','pitchMix','starter_pitch_mix']) or pitch_mix_summary_from_row(row, pitcher=True)
    out = {
        'pitcherHand': pitcher_hand or None,
        'temperatureF': round(temp, 1) if temp is not None else None,
        'windMph': round(wind, 1) if wind is not None else None,
        'park': park or None,
        'location': location or None,
        'pitchMixSummary': pitch_mix or None,
        'source': 'build_mlb_props_analyzer_json current row',
    }
    return {k: v for k, v in out.items() if v not in [None, '']}


def row_text_source(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    out = pd.Series('', index=df.index, dtype='object')
    for col in candidates:
        if col not in df.columns:
            continue
        vals = df[col].map(clean_str)
        out = out.where(out.astype(str).str.len() > 0, vals)
    return out


def row_number_source(df: pd.DataFrame, candidates: list[str], fahrenheit: bool = False) -> pd.Series:
    out = pd.Series(math.nan, index=df.index, dtype='float64')
    for col in candidates:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors='coerce')
        if fahrenheit:
            vals = vals.map(lambda v: f_from_c_or_f(v, col) if pd.notna(v) else math.nan)
        out = out.where(out.notna(), vals)
    return out


def historical_matchup_fields_from_log_row(g: pd.Series) -> dict[str, Any]:
    """Fields to copy onto each historical game row when source logs provide them.

    This is intentionally permissive: it preserves any known field names if present,
    but leaves them blank if the current scraper/model output does not have them yet.
    """
    batter_hand = normalize_hand(g.get('batterHand'))
    pitcher_hand = normalize_hand(g.get('opposingPitcherHand') or g.get('pitcherHand'))
    temp = safe_float(g.get('temperatureF'))
    wind = safe_float(g.get('windMph'))
    out = {
        'batterHand': batter_hand or None,
        'pitcherHand': pitcher_hand or None,
        'opposingPitcherHand': pitcher_hand or None,
        'handednessText': handedness_text(batter_hand, pitcher_hand) or None,
        'opposingStarterName': clean_str(g.get('opposingStarterName')) or None,
        'opposingStarterId': clean_str(g.get('opposingStarterId')) or None,
        'park': clean_str(g.get('park')) or None,
        'temperatureF': round(temp, 1) if temp is not None else None,
        'windMph': round(wind, 1) if wind is not None else None,
        'pitchMixSummary': clean_str(g.get('pitchMixSummary')) or None,
    }
    return {k: v for k, v in out.items() if v not in [None, '']}

def compact_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

def find_latest(pattern: str, root: Path) -> Path | None:
    files = [p for p in root.rglob(pattern) if p.is_file()] if root.exists() else []
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)

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


def parse_wind_mph(value: Any) -> float | None:
    """Extract wind speed from either a numeric value or text like '19 mph, Out To CF'."""
    num = safe_float(value)
    if num is not None:
        return num
    text = clean_str(value)
    if not text:
        return None
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*mph', text, re.IGNORECASE)
    if not m:
        m = re.search(r'(-?\d+(?:\.\d+)?)', text)
    return safe_float(m.group(1)) if m else None


def first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def fill_missing_text(base: pd.Series, fallback: pd.Series) -> pd.Series:
    base_text = base.map(clean_str) if base is not None else pd.Series('', index=fallback.index, dtype='object')
    fallback_text = fallback.map(clean_str)
    return base_text.where(base_text.astype(str).str.len() > 0, fallback_text)


def fill_missing_number(base: pd.Series, fallback: pd.Series) -> pd.Series:
    base_num = pd.to_numeric(base, errors='coerce') if base is not None else pd.Series(math.nan, index=fallback.index, dtype='float64')
    fallback_num = pd.to_numeric(fallback, errors='coerce')
    return base_num.where(base_num.notna(), fallback_num)


def pitch_mix_summary_from_row(row: Any, pitcher: bool = False) -> str:
    """Create a compact text summary from the model's numeric pitch-mix fields.

    Similarity v2 only needs a transparent availability marker for now; the next
    upgrade can use a true vector distance. This summary prevents the UI from
    claiming pitch-mix is missing when the model output already has pitch-mix
    factors available on the historical prediction rows.
    """
    parts: list[str] = []
    if not pitcher:
        mapping = [
            ('power', 'pitch_mix_matchup_power_score'),
            ('TB', 'pitch_mix_tb_factor'),
            ('HR', 'hr_pitch_mix_factor'),
            ('whiff', 'batter_pitch_mix_whiff_risk'),
            ('coverage', 'pitch_mix_usage_coverage'),
            ('types', 'pitch_mix_pitch_types_matched'),
        ]
    else:
        mapping = [
            ('damage', 'pitcher_pitch_mix_damage_allowed_score'),
            ('whiff', 'pitcher_pitch_mix_whiff_score'),
            ('velo', 'pitcher_pitch_mix_velocity_score'),
            ('movement', 'pitcher_pitch_mix_movement_score'),
            ('spin', 'pitcher_pitch_mix_spin_score'),
        ]
    for label, col in mapping:
        try:
            value = row.get(col)
        except Exception:
            value = None
        num = safe_float(value)
        if num is None:
            continue
        if label == 'types':
            parts.append(f'{int(round(num))} pitch types')
        elif label == 'coverage':
            parts.append(f'coverage {num:.0%}' if 0 <= num <= 1.5 else f'coverage {num:.2f}')
        else:
            parts.append(f'{label} {num:.2f}')
    return ' • '.join(parts[:5])


def read_csv_context(path: Path, wanted: list[str]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()
    try:
        header = pd.read_csv(path, nrows=0).columns.tolist()
    except Exception:
        return pd.DataFrame()
    usecols = [c for c in wanted if c in header]
    if not usecols:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, usecols=usecols, low_memory=False)
    except Exception:
        try:
            return pd.read_csv(path, usecols=usecols)
        except Exception:
            return pd.DataFrame()


def unique_paths(paths: list[Path | None]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if not path:
            continue
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        out.append(path)
    return out


def standardize_batter_prediction_context(df: pd.DataFrame, source_name: str = '') -> pd.DataFrame:
    if df is None or df.empty or 'gamePk' not in df.columns:
        return pd.DataFrame()
    id_col = first_existing_col(df, ['player_id', 'batter_id', 'batterId', 'playerId', 'personId', 'mlb_id', 'mlbam_id'])
    if id_col is None:
        return pd.DataFrame()
    out = pd.DataFrame(index=df.index)
    out['gamePk'] = pd.to_numeric(df['gamePk'], errors='coerce')
    out['player_id'] = pd.to_numeric(df[id_col], errors='coerce')
    out = out.dropna(subset=['gamePk', 'player_id']).copy()
    if out.empty:
        return pd.DataFrame()
    src = df.loc[out.index].copy()
    out['gamePk'] = out['gamePk'].astype(int)
    out['player_id'] = out['player_id'].astype(int)
    out['batterHand'] = row_text_source(src, ['batSide','bat_side','stand','batterHand','batter_hand','bats']).map(normalize_hand)
    out['opposingPitcherHand'] = row_text_source(src, ['opp_pitch_hand','opposing_pitcher_hand','opposing_starter_hand','starterHand','oppStarterHand','opponentStarterHand','pitchHand']).map(normalize_hand)
    out['opposingStarterName'] = row_text_source(src, ['opposing_starter','opp_starter_name','opposing_starter_name','opponentStarter','starter_name','pitcher_name','opp_pitcher_name'])
    out['opposingStarterId'] = row_text_source(src, ['opp_starter_id','opposing_starter_id','opponentStarterId','pitcher_id','opp_pitcher_id'])
    out['park'] = row_text_source(src, ['park','venue','venueName','venue_name','ballpark','stadium'])
    out['temperatureF'] = row_number_source(src, ['weather_temp_f','temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','apparent_temperature','temperature','temp'], fahrenheit=True)
    out['windMph'] = row_number_source(src, ['wind_effective_speed','wind_speed_10m','windMph','wind_mph','wind_speed'])
    text_pitch_mix = row_text_source(src, ['pitch_mix','pitchMix','starter_pitch_mix','opp_pitch_mix','opposing_pitch_mix'])
    numeric_pitch_mix = src.apply(lambda r: pitch_mix_summary_from_row(r), axis=1)
    out['pitchMixSummary'] = fill_missing_text(text_pitch_mix, numeric_pitch_mix)
    out['__source'] = source_name
    sort_cols = []
    for c in ['target_game_date', 'forecast_generated_date', 'gameDate']:
        if c in src.columns:
            out[f'__sort_{c}'] = pd.to_datetime(src[c], errors='coerce')
            sort_cols.append(f'__sort_{c}')
    if sort_cols:
        out = out.sort_values(['gamePk', 'player_id'] + sort_cols)
    out = out.groupby(['gamePk', 'player_id'], as_index=False).tail(1)
    keep = ['gamePk','player_id','batterHand','opposingPitcherHand','opposingStarterName','opposingStarterId','park','temperatureF','windMph','pitchMixSummary','__source']
    return out[keep].reset_index(drop=True)


def standardize_pitcher_prediction_context(df: pd.DataFrame, source_name: str = '') -> pd.DataFrame:
    if df is None or df.empty or 'gamePk' not in df.columns:
        return pd.DataFrame()
    id_col = first_existing_col(df, ['player_id', 'pitcher_id', 'pitcherId', 'playerId', 'personId', 'mlb_id', 'mlbam_id'])
    if id_col is None:
        return pd.DataFrame()
    out = pd.DataFrame(index=df.index)
    out['gamePk'] = pd.to_numeric(df['gamePk'], errors='coerce')
    out['player_id'] = pd.to_numeric(df[id_col], errors='coerce')
    out = out.dropna(subset=['gamePk', 'player_id']).copy()
    if out.empty:
        return pd.DataFrame()
    src = df.loc[out.index].copy()
    out['gamePk'] = out['gamePk'].astype(int)
    out['player_id'] = out['player_id'].astype(int)
    out['pitcherHand'] = row_text_source(src, ['pitchHand','pitch_hand','throws','throwingHand','hand']).map(normalize_hand)
    out['park'] = row_text_source(src, ['park','venue','venueName','venue_name','ballpark','stadium'])
    out['temperatureF'] = row_number_source(src, ['weather_temp_f','temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','apparent_temperature','temperature','temp'], fahrenheit=True)
    out['windMph'] = row_number_source(src, ['wind_effective_speed','wind_speed_10m','windMph','wind_mph','wind_speed'])
    text_pitch_mix = row_text_source(src, ['pitch_mix','pitchMix','starter_pitch_mix'])
    numeric_pitch_mix = src.apply(lambda r: pitch_mix_summary_from_row(r, pitcher=True), axis=1)
    out['pitchMixSummary'] = fill_missing_text(text_pitch_mix, numeric_pitch_mix)
    out['__source'] = source_name
    sort_cols = []
    for c in ['target_game_date', 'forecast_generated_date', 'gameDate']:
        if c in src.columns:
            out[f'__sort_{c}'] = pd.to_datetime(src[c], errors='coerce')
            sort_cols.append(f'__sort_{c}')
    if sort_cols:
        out = out.sort_values(['gamePk', 'player_id'] + sort_cols)
    out = out.groupby(['gamePk', 'player_id'], as_index=False).tail(1)
    keep = ['gamePk','player_id','pitcherHand','park','temperatureF','windMph','pitchMixSummary','__source']
    return out[keep].reset_index(drop=True)


def build_prediction_context(args: argparse.Namespace, current_csv: Path | None, kind: str) -> pd.DataFrame:
    if kind == 'batter':
        history = args.mlb_output_dir / 'history' / 'batter_prediction_history.csv'
        latest = find_latest('batter_predictions_*.csv', args.mlb_output_dir)
        sources = unique_paths([history, current_csv, latest])
        wanted = [
            'gamePk','player_id','batter_id','batterId','playerId','personId','mlb_id','mlbam_id',
            'target_game_date','forecast_generated_date','gameDate','team','opponent',
            'batSide','bat_side','stand','batterHand','batter_hand','bats',
            'opp_pitch_hand','opposing_pitcher_hand','opposing_starter_hand','starterHand','oppStarterHand','opponentStarterHand','pitchHand',
            'opposing_starter','opp_starter_name','opposing_starter_name','opponentStarter','starter_name','pitcher_name','opp_pitcher_name',
            'opp_starter_id','opposing_starter_id','opponentStarterId','pitcher_id','opp_pitcher_id',
            'park','venue','venueName','venue_name','ballpark','stadium',
            'weather_temp_f','temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','apparent_temperature','temperature','temp',
            'wind_effective_speed','wind_speed_10m','windMph','wind_mph','wind_speed',
            'pitch_mix','pitchMix','starter_pitch_mix','opp_pitch_mix','opposing_pitch_mix',
            'pitch_mix_matchup_power_score','pitch_mix_tb_factor','hr_pitch_mix_factor','batter_pitch_mix_whiff_risk','pitch_mix_usage_coverage','pitch_mix_pitch_types_matched',
        ]
        frames = [standardize_batter_prediction_context(read_csv_context(path, wanted), path.name) for path in sources]
    else:
        history = args.mlb_output_dir / 'history' / 'pitcher_prediction_history.csv'
        latest = find_latest('pitcher_predictions_*.csv', args.mlb_output_dir)
        sources = unique_paths([history, current_csv, latest])
        wanted = [
            'gamePk','player_id','pitcher_id','pitcherId','playerId','personId','mlb_id','mlbam_id',
            'target_game_date','forecast_generated_date','gameDate','team','opponent',
            'pitchHand','pitch_hand','throws','throwingHand','hand',
            'park','venue','venueName','venue_name','ballpark','stadium',
            'weather_temp_f','temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','apparent_temperature','temperature','temp',
            'wind_effective_speed','wind_speed_10m','windMph','wind_mph','wind_speed',
            'pitch_mix','pitchMix','starter_pitch_mix',
            'pitcher_pitch_mix_damage_allowed_score','pitcher_pitch_mix_whiff_score','pitcher_pitch_mix_velocity_score','pitcher_pitch_mix_movement_score','pitcher_pitch_mix_spin_score',
        ]
        frames = [standardize_pitcher_prediction_context(read_csv_context(path, wanted), path.name) for path in sources]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(['gamePk', 'player_id', '__source'])
    combined = combined.groupby(['gamePk', 'player_id'], as_index=False).tail(1)
    return combined.reset_index(drop=True)


def build_game_context(args: argparse.Namespace) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    games = load_table_latest(args.mlb_data_dir, 'games')
    if games is not None and not games.empty and 'gamePk' in games.columns:
        g = pd.DataFrame()
        g['gamePk'] = pd.to_numeric(games['gamePk'], errors='coerce')
        g['park'] = row_text_source(games, ['venue_name','venueName','park','ballpark','stadium'])
        g['temperatureF'] = row_number_source(games, ['weather_temp_f','temperature_f','temperatureF','temp_f','temperature_2m','apparent_temperature'], fahrenheit=True)
        wind_text = row_text_source(games, ['wind'])
        wind_num = row_number_source(games, ['wind_mph','windMph','wind_speed_10m','wind_speed'])
        g['windMph'] = fill_missing_number(wind_num, wind_text.map(parse_wind_mph))
        frames.append(g)
    weather = load_table_latest(args.mlb_data_dir, 'game_weather')
    if weather is not None and not weather.empty and 'gamePk' in weather.columns:
        w = pd.DataFrame()
        w['gamePk'] = pd.to_numeric(weather['gamePk'], errors='coerce')
        w['temperatureF'] = row_number_source(weather, ['weather_temp_f','temperature_f','temperatureF','temperature_2m','apparent_temperature'], fahrenheit=True)
        w['windMph'] = row_number_source(weather, ['wind_speed_10m','windMph','wind_mph','wind_speed'])
        frames.append(w)
    schedule = load_table_latest(args.mlb_data_dir, 'schedule')
    if schedule is not None and not schedule.empty and 'gamePk' in schedule.columns:
        sc = pd.DataFrame()
        sc['gamePk'] = pd.to_numeric(schedule['gamePk'], errors='coerce')
        sc['park'] = row_text_source(schedule, ['venue_name','venueName','park','ballpark','stadium'])
        for col in ['away_probable_pitcher','away_probable_pitcher_id','home_probable_pitcher','home_probable_pitcher_id','away_team','home_team']:
            if col in schedule.columns:
                sc[col] = schedule[col]
        frames.append(sc)
    frames = [f.dropna(subset=['gamePk']).copy() for f in frames if f is not None and not f.empty and 'gamePk' in f.columns]
    if not frames:
        return pd.DataFrame()
    # Outer merge, filling missing values from later sources.
    base = frames[0]
    base['gamePk'] = base['gamePk'].astype(int)
    for extra in frames[1:]:
        extra['gamePk'] = extra['gamePk'].astype(int)
        base = base.merge(extra, on='gamePk', how='outer', suffixes=('', '__extra'))
        for col in list(base.columns):
            if not col.endswith('__extra'):
                continue
            orig = col[:-7]
            if orig in base.columns:
                if pd.api.types.is_numeric_dtype(base[orig]) or pd.api.types.is_numeric_dtype(base[col]):
                    base[orig] = fill_missing_number(base[orig], base[col])
                else:
                    base[orig] = fill_missing_text(base[orig], base[col])
                base = base.drop(columns=[col])
            else:
                base = base.rename(columns={col: orig})
    return base.drop_duplicates(subset=['gamePk']).reset_index(drop=True)


def enrich_logs_with_game_context(logs_df: pd.DataFrame, game_context: pd.DataFrame, player_type: str) -> pd.DataFrame:
    if logs_df is None or logs_df.empty:
        return logs_df
    out = logs_df.copy()
    if 'gamePk' not in out.columns:
        return out
    out['gamePk'] = pd.to_numeric(out['gamePk'], errors='coerce')
    if game_context is None or game_context.empty:
        return out
    ctx = game_context.copy()
    ctx['gamePk'] = pd.to_numeric(ctx['gamePk'], errors='coerce')
    merged = out.merge(ctx, on='gamePk', how='left', suffixes=('', '__game'))
    for col in ['park', 'temperatureF', 'windMph']:
        gcol = f'{col}__game'
        if gcol in merged.columns:
            if col in ['temperatureF', 'windMph']:
                merged[col] = fill_missing_number(merged.get(col), merged[gcol])
            else:
                merged[col] = fill_missing_text(merged.get(col), merged[gcol])
    if player_type == 'batter':
        is_home = pd.to_numeric(merged.get('isHome'), errors='coerce') if 'isHome' in merged.columns else pd.Series(math.nan, index=merged.index)
        away_name = merged.get('away_probable_pitcher') if 'away_probable_pitcher' in merged.columns else pd.Series('', index=merged.index)
        home_name = merged.get('home_probable_pitcher') if 'home_probable_pitcher' in merged.columns else pd.Series('', index=merged.index)
        away_id = merged.get('away_probable_pitcher_id') if 'away_probable_pitcher_id' in merged.columns else pd.Series('', index=merged.index)
        home_id = merged.get('home_probable_pitcher_id') if 'home_probable_pitcher_id' in merged.columns else pd.Series('', index=merged.index)
        opp_name = pd.Series('', index=merged.index, dtype='object')
        opp_id = pd.Series('', index=merged.index, dtype='object')
        opp_name = opp_name.where(is_home != 1, away_name).where(is_home == 1, home_name)
        opp_id = opp_id.where(is_home != 1, away_id).where(is_home == 1, home_id)
        if 'opposingStarterName' in merged.columns:
            merged['opposingStarterName'] = fill_missing_text(merged['opposingStarterName'], opp_name)
        else:
            merged['opposingStarterName'] = opp_name.map(clean_str)
        if 'opposingStarterId' in merged.columns:
            merged['opposingStarterId'] = fill_missing_text(merged['opposingStarterId'], opp_id)
        else:
            merged['opposingStarterId'] = opp_id.map(clean_str)
    drop_cols = [c for c in merged.columns if c.endswith('__game') or c in {'away_probable_pitcher','away_probable_pitcher_id','home_probable_pitcher','home_probable_pitcher_id','away_team','home_team'}]
    return merged.drop(columns=drop_cols, errors='ignore')


def enrich_logs_with_prediction_context(logs_df: pd.DataFrame, pred_context: pd.DataFrame, player_type: str) -> pd.DataFrame:
    if logs_df is None or logs_df.empty or pred_context is None or pred_context.empty:
        return logs_df
    if 'gamePk' not in logs_df.columns or 'player_id' not in logs_df.columns:
        return logs_df
    out = logs_df.copy()
    out['gamePk'] = pd.to_numeric(out['gamePk'], errors='coerce')
    out['player_id'] = pd.to_numeric(out['player_id'], errors='coerce')
    ctx = pred_context.copy()
    ctx['gamePk'] = pd.to_numeric(ctx['gamePk'], errors='coerce')
    ctx['player_id'] = pd.to_numeric(ctx['player_id'], errors='coerce')
    merged = out.merge(ctx, on=['gamePk','player_id'], how='left', suffixes=('', '__pred'))
    if player_type == 'batter':
        text_cols = ['batterHand','opposingPitcherHand','opposingStarterName','opposingStarterId','park','pitchMixSummary']
    else:
        text_cols = ['pitcherHand','park','pitchMixSummary']
    for col in text_cols:
        pcol = f'{col}__pred'
        if pcol in merged.columns:
            merged[col] = fill_missing_text(merged.get(col), merged[pcol])
    for col in ['temperatureF', 'windMph']:
        pcol = f'{col}__pred'
        if pcol in merged.columns:
            merged[col] = fill_missing_number(merged.get(col), merged[pcol])
    drop_cols = [c for c in merged.columns if c.endswith('__pred') or c == '__source']
    return merged.drop(columns=drop_cols, errors='ignore')


def enrich_batter_logs_with_matchup_context(logs_df: pd.DataFrame, pred_context: pd.DataFrame, game_context: pd.DataFrame) -> pd.DataFrame:
    out = enrich_logs_with_prediction_context(logs_df, pred_context, 'batter')
    out = enrich_logs_with_game_context(out, game_context, 'batter')
    return out


def enrich_pitcher_logs_with_matchup_context(logs_df: pd.DataFrame, pred_context: pd.DataFrame, game_context: pd.DataFrame) -> pd.DataFrame:
    out = enrich_logs_with_prediction_context(logs_df, pred_context, 'pitcher')
    out = enrich_logs_with_game_context(out, game_context, 'pitcher')
    return out

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build MLB props analyzer JSON using split detail files.')
    parser.add_argument('--website-repo', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--mlb-output-dir', type=Path, default=Path(r'C:\python\mlb_model_outputs'))
    parser.add_argument('--mlb-data-dir', type=Path, default=DEFAULT_MLB_DATA_DIR)
    parser.add_argument('--batter-csv', type=Path)
    parser.add_argument('--pitcher-csv', type=Path)
    parser.add_argument('--game-csv', type=Path)
    parser.add_argument('--recent-window', type=int, default=15)
    parser.add_argument('--max-games', type=int, default=40)
    parser.add_argument('--keep-old-details', action='store_true')
    return parser.parse_args()

def display_date_from_game_ts(value: Any) -> str:
    try:
        ts = pd.to_datetime(value, utc=True)
    except Exception:
        return clean_str(value)[:10]
    if pd.isna(ts):
        return ''
    try:
        return ts.tz_convert(DISPLAY_TIMEZONE).date().isoformat()
    except Exception:
        return ts.date().isoformat()

def display_ts(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, utc=True)
    except Exception:
        return None
    return None if pd.isna(ts) else ts

def fair_american(prob: float | None) -> int | None:
    if prob is None or prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return int(round(-(prob / (1 - prob)) * 100))
    return int(round(((1 - prob) / prob) * 100))

def build_game_lookup(game_df: pd.DataFrame) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    if game_df is None or game_df.empty:
        return lookup
    game_df = game_df.copy()
    game_df['gamePk'] = pd.to_numeric(game_df.get('gamePk'), errors='coerce')
    game_df = game_df.dropna(subset=['gamePk']).copy()
    game_df['gamePk'] = game_df['gamePk'].astype(int)
    if 'forecast_generated_date' in game_df.columns:
        game_df['__forecast_date'] = pd.to_datetime(game_df['forecast_generated_date'], errors='coerce')
        game_df = game_df.sort_values(['gamePk', '__forecast_date'])
        game_df = game_df.groupby('gamePk', as_index=False).tail(1)
    for _, row in game_df.iterrows():
        game_pk = int(row['gamePk'])
        away = clean_str(row.get('away_team'))
        home = clean_str(row.get('home_team'))
        game_ts = display_ts(row.get('gameDate'))
        display_date = display_date_from_game_ts(row.get('gameDate')) or clean_str(row.get('target_game_date'))
        lookup[game_pk] = {
            'gameDate': display_date,
            'gameTs': game_ts.isoformat() if game_ts is not None else '',
            'awayTeam': away,
            'homeTeam': home,
        }
    return lookup

def parse_batting_order(value: Any) -> int | None:
    raw = clean_str(value)
    if not raw:
        return None
    try:
        num = int(float(raw))
    except Exception:
        return None
    if num >= 100:
        return max(1, min(9, num // 100))
    return max(1, min(9, num))

def prep_batter_logs(logs_df: pd.DataFrame) -> pd.DataFrame:
    if logs_df is None or logs_df.empty or 'player_id' not in logs_df.columns:
        return pd.DataFrame()
    df = logs_df.copy()
    df['player_id'] = pd.to_numeric(df['player_id'], errors='coerce')
    df = df.dropna(subset=['player_id']).copy()
    df['player_id'] = df['player_id'].astype(int)
    df['game_ts'] = pd.to_datetime(df.get('gameDate'), errors='coerce', utc=True)
    df = df.dropna(subset=['game_ts']).copy()
    df['gameDateLocal'] = df['game_ts'].dt.tz_convert(DISPLAY_TIMEZONE).dt.date.astype(str)
    team_side = df.get('team_side')
    if team_side is not None:
        df['isHome'] = team_side.astype(str).str.upper().eq('HOME').astype(int)
        df['location'] = df['isHome'].map({1: 'Home', 0: 'Away'})
    else:
        df['isHome'] = None
        df['location'] = ''
    df['batting_order_clean'] = df.get('batting_order', pd.Series(index=df.index)).map(parse_batting_order)
    df['atBats'] = pd.to_numeric(df.get('atBats'), errors='coerce')
    df['plate_appearances'] = df['atBats'].fillna(0) + pd.to_numeric(df.get('baseOnBalls'), errors='coerce').fillna(0)
    for col in ['hits','totalBases','doubles','homeRuns','strikeOuts','baseOnBalls','stolenBases','runs','R','rbi','RBI','runsBattedIn']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'runs' not in df.columns and 'R' in df.columns:
        df['runs'] = pd.to_numeric(df.get('R'), errors='coerce')
    if 'rbi' not in df.columns:
        source_rbi = 'runsBattedIn' if 'runsBattedIn' in df.columns else 'RBI' if 'RBI' in df.columns else None
        if source_rbi:
            df['rbi'] = pd.to_numeric(df.get(source_rbi), errors='coerce')
    if 'hrr' not in df.columns:
        df['hrr'] = pd.to_numeric(df.get('hits'), errors='coerce').fillna(0) + pd.to_numeric(df.get('runs'), errors='coerce').fillna(0) + pd.to_numeric(df.get('rbi'), errors='coerce').fillna(0)

    # Optional historical matchup context. These columns are not guaranteed in every
    # local scraper output, but when they are present we preserve them so
    # Similarity v2 can start scoring handedness/park/weather without another
    # frontend change. Blank fields are ignored downstream.
    df['batterHand'] = row_text_source(df, ['batSide','bat_side','stand','batterHand','batter_hand','bats']).map(normalize_hand)
    df['opposingPitcherHand'] = row_text_source(df, ['opp_pitch_hand','opposing_pitcher_hand','pitcherHand','starterHand','oppStarterHand','opponentStarterHand','pitchHand']).map(normalize_hand)
    df['opposingStarterName'] = row_text_source(df, ['opp_starter_name','opposing_starter_name','opponentStarter','starter_name','pitcher_name','opp_pitcher_name'])
    df['opposingStarterId'] = row_text_source(df, ['opp_starter_id','opposing_starter_id','opponentStarterId','pitcher_id','opp_pitcher_id'])
    df['park'] = row_text_source(df, ['park','venue','venueName','ballpark','stadium'])
    df['temperatureF'] = row_number_source(df, ['temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','temperature','temp'], fahrenheit=True)
    df['windMph'] = row_number_source(df, ['wind_speed_10m','windMph','wind_mph','wind','wind_speed'])
    df['pitchMixSummary'] = row_text_source(df, ['pitch_mix','pitchMix','starter_pitch_mix','opp_pitch_mix','opposing_pitch_mix'])

    keep = ['gamePk','player_id','player_name','team','opponent','game_ts','gameDateLocal','isHome','location',
            'batting_order_clean','atBats','plate_appearances','hits','totalBases','doubles','homeRuns','strikeOuts',
            'baseOnBalls','stolenBases','runs','rbi','hrr','batterHand','opposingPitcherHand','opposingStarterName',
            'opposingStarterId','park','temperatureF','windMph','pitchMixSummary']
    keep = [c for c in keep if c in df.columns]
    return df[keep].sort_values(['player_id', 'game_ts']).reset_index(drop=True)

def choose_best_numeric_source(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    best_series: pd.Series | None = None
    best_count = -1
    for c in candidates:
        if c not in df.columns:
            continue
        series = pd.to_numeric(df[c], errors='coerce')
        count = int(series.notna().sum())
        if count > best_count:
            best_series = series
            best_count = count
    if best_series is None:
        return pd.Series(math.nan, index=df.index, dtype='float64')
    return best_series


def prep_pitcher_logs(logs_df: pd.DataFrame) -> pd.DataFrame:
    if logs_df is None or logs_df.empty:
        return pd.DataFrame()
    df = logs_df.copy()
    pid_col = 'player_id' if 'player_id' in df.columns else 'pitcher_id' if 'pitcher_id' in df.columns else None
    if pid_col is None:
        return pd.DataFrame()
    df['player_id'] = pd.to_numeric(df[pid_col], errors='coerce')
    df = df.dropna(subset=['player_id']).copy()
    df['player_id'] = df['player_id'].astype(int)
    df['game_ts'] = pd.to_datetime(df.get('gameDate'), errors='coerce', utc=True)
    df = df.dropna(subset=['game_ts']).copy()
    df['gameDateLocal'] = df['game_ts'].dt.tz_convert(DISPLAY_TIMEZONE).dt.date.astype(str)

    side_col = 'team_side' if 'team_side' in df.columns else 'isHome' if 'isHome' in df.columns else None
    if side_col == 'team_side':
        df['isHome'] = df['team_side'].astype(str).str.upper().eq('HOME').astype(int)
    elif side_col == 'isHome':
        df['isHome'] = pd.to_numeric(df.get('isHome'), errors='coerce')
    else:
        df['isHome'] = None
    df['location'] = df['isHome'].map({1: 'Home', 0: 'Away'}).fillna('')

    numeric_candidates = {
        'strikeOuts': ['strikeOuts', 'SO', 'so', 'Ks', 'k'],
        'baseOnBalls': ['baseOnBalls', 'BB', 'bb', 'walks', 'walksAllowed'],
        'hitsAllowed': ['hitsAllowed', 'hits_allowed', 'hitsAgainst', 'hits_against', 'HA', 'ha', 'hits', 'H', 'h'],
        'earnedRuns': ['earnedRuns', 'earned_runs', 'ER', 'er'],
        'outsRecorded': ['outsRecorded', 'outs_recorded', 'outs'],
        'inningsPitched': ['inningsPitched', 'innings_pitched', 'IP', 'ip'],
    }
    for out_col, candidates in numeric_candidates.items():
        df[out_col] = choose_best_numeric_source(df, candidates)

    # Optional historical context for pitcher prop logs.
    df['pitcherHand'] = row_text_source(df, ['pitchHand','pitch_hand','throws','throwingHand','hand']).map(normalize_hand)
    df['park'] = row_text_source(df, ['park','venue','venueName','ballpark','stadium'])
    df['temperatureF'] = row_number_source(df, ['temperature_f','temperatureF','temp_f','game_temp_f','temperature_2m','temperature','temp'], fahrenheit=True)
    df['windMph'] = row_number_source(df, ['wind_speed_10m','windMph','wind_mph','wind','wind_speed'])
    df['pitchMixSummary'] = row_text_source(df, ['pitch_mix','pitchMix','starter_pitch_mix'])

    keep = ['gamePk','player_id','player_name','fullName','team','opponent','game_ts','gameDateLocal',
            'isHome','location','strikeOuts','baseOnBalls','hitsAllowed','earnedRuns','outsRecorded','inningsPitched',
            'pitcherHand','park','temperatureF','windMph','pitchMixSummary']
    keep = [c for c in keep if c in df.columns]
    return df[keep].sort_values(['player_id', 'game_ts']).reset_index(drop=True)

def build_historical_games(player_logs: pd.DataFrame, target_ts: pd.Timestamp | None, value_col: str, opp: str,
                           location: str, max_games: int, minutes_col: str | None = None, extra_context_col: str | None = None,
                           projected_order: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if player_logs.empty or value_col not in player_logs.columns:
        return [], []
    hist = player_logs.copy()
    if target_ts is not None:
        hist = hist.loc[hist['game_ts'] < target_ts]
    hist = hist.dropna(subset=[value_col]).copy()
    if hist.empty:
        return [], []
    hist = hist.sort_values('game_ts').tail(max_games).reset_index(drop=True)

    games: list[dict[str, Any]] = []
    for _, g in hist.iterrows():
        value = safe_float(g.get(value_col))
        if value is None:
            continue
        minutes = safe_float(g.get(minutes_col)) if minutes_col else None
        row = {
            'gameId': safe_int(g.get('gamePk')),
            'gameDate': clean_str(g.get('gameDateLocal')),
            'label': clean_str(g.get('gameDateLocal')),
            'shortLabel': clean_str(g.get('gameDateLocal'))[5:] if clean_str(g.get('gameDateLocal')) else '',
            'seq': len(games) + 1,
            'value': value,
            'minutes': minutes,
            'opp': clean_str(g.get('opponent')),
            'isHome': safe_int(g.get('isHome')),
            'location': clean_str(g.get('location')),
            'simBin': 'all',
            'simScore': None,
            'simPct': None,
        }
        if extra_context_col:
            row['contextValue'] = safe_int(g.get(extra_context_col))
        # Preserve optional historical matchup fields when the source logs have them.
        # These fields are used by the player-day profile builder for Similarity v2.
        row.update(historical_matchup_fields_from_log_row(g))
        games.append(row)

    scored: list[dict[str, Any]] = []
    for row in games:
        score = 0.0
        if opp and clean_str(row.get('opp')) == opp:
            score += 55.0
        if location and clean_str(row.get('location')) == location:
            score += 20.0
        if projected_order is not None and extra_context_col:
            bo = safe_int(row.get('contextValue'))
            if bo is not None:
                score += max(0.0, 18.0 - (abs(projected_order - bo) * 4.0))
        try:
            dt = pd.to_datetime(row.get('gameDate'))
            days_old = (pd.Timestamp.now().normalize() - dt.normalize()).days
            score += max(0.0, 12.0 - min(days_old, 12))
        except Exception:
            pass
        tmp = dict(row)
        tmp['simScore'] = round(score, 2)
        scored.append(tmp)

    scored.sort(key=lambda x: (x.get('simScore') or 0, x.get('gameDate') or ''), reverse=True)
    top_sim = scored[:12]
    total = len(top_sim)
    for idx, row in enumerate(top_sim):
        pct = (idx + 1) / total if total else 1
        row['simBin'] = 'Closest 25%' if pct <= 0.25 else 'Close 25%' if pct <= 0.5 else 'Mid 25%' if pct <= 0.75 else 'Far 25%'
        row['simPct'] = round(((total - idx) / total) * 100.0, 1) if total else None
    return games, top_sim

def poisson_tail_prob(lam: float | None, threshold_int: int) -> float | None:
    if lam is None or lam <= 0 or threshold_int <= 0:
        return None
    try:
        cdf = 0.0
        term = math.exp(-lam)
        for k in range(threshold_int):
            if k == 0:
                cdf += term
            else:
                term *= lam / k
                cdf += term
        return max(0.0, min(1.0, 1.0 - cdf))
    except Exception:
        return None

def approx_prob(row: pd.Series, market: dict[str, Any], line: float, pred: float | None) -> float | None:
    if pred is None:
        return None
    direct = market.get('prob_cols', {}).get(line)
    if direct:
        p = safe_float(row.get(direct))
        if p is not None:
            return p
    needed = int(math.floor(line) + 1)
    return poisson_tail_prob(pred, needed)

def valid_lines_for_pred(lines: list[float], pred: float | None) -> list[float]:
    if pred is None:
        return lines[:]
    picks = []
    for line in lines:
        if pred >= (line - 1.75) and pred <= (line + 3.5):
            picks.append(line)
    if not picks:
        closest = min(lines, key=lambda x: abs((pred or 0) - x))
        picks = [closest]
    return sorted(set(picks))

def batter_context_summary(row: pd.Series) -> str:
    parts = []
    order = safe_int(row.get('projected_batting_order'))
    if order is not None:
        parts.append(f'Order {order}')
    bat_side = clean_str(row.get('batSide'))
    opp_hand = clean_str(row.get('opp_pitch_hand'))
    if bat_side and opp_hand:
        parts.append(f'{bat_side} vs {opp_hand}')
    temp_c = safe_float(row.get('temperature_2m'))
    if temp_c is not None:
        parts.append(f'{(temp_c * 9 / 5) + 32:.0f}°F')
    wind = safe_float(row.get('wind_speed_10m'))
    if wind is not None:
        parts.append(f'Wind {wind:.0f}')
    return ' • '.join(parts)

def build_batter_series_and_entries(row: pd.Series, market: dict[str, Any], game_lookup: dict[int, dict[str, Any]],
                                    batter_logs_lookup: dict[int, pd.DataFrame], recent_window: int, max_games: int) -> tuple[list[dict], dict | None]:
    pred = safe_float(row.get(market['pred_col']))
    if pred is None:
        return [], None
    game_pk = safe_int(row.get('gamePk'))
    game = game_lookup.get(game_pk or -1, {})
    team = clean_str(row.get('team'))
    opp = clean_str(row.get('opponent'))
    away = clean_str(game.get('awayTeam'))
    home = clean_str(game.get('homeTeam'))
    location = 'Home' if team and home and team == home else 'Away' if team and away and team == away else ''
    matchup = f'{away} @ {home}'.strip(' @') if away and home else f'{team} vs {opp}'.strip()
    game_date = clean_str(game.get('gameDate'))
    target_ts = display_ts(game.get('gameTs'))
    player_id = safe_int(row.get('player_id'))
    projected_order = safe_int(row.get('projected_batting_order'))
    matchup_context = matchup_context_from_batter_row(row, game, location)

    player_logs = batter_logs_lookup.get(player_id or -1, pd.DataFrame())
    games, similar_games = build_historical_games(
        player_logs, target_ts, market['value_col'], opp, location, max_games=max_games,
        minutes_col='atBats', extra_context_col='batting_order_clean', projected_order=projected_order
    )
    history_mode = bool(games)
    avg_anchor = None
    hit_r5 = hit_r10 = hit_r20 = sim_avg = None

    if history_mode:
        vals = [safe_float(g.get('value')) for g in games[-20:] if safe_float(g.get('value')) is not None]
        avg_anchor = (sum(vals) / len(vals)) if vals else None
        def hit_rate(n):
            sample = [safe_float(g.get('value')) for g in games[-n:] if safe_float(g.get('value')) is not None]
            return (sum(v >= 0.5 for v in sample) / len(sample)) if sample else None
        hit_r5, hit_r10, hit_r20 = hit_rate(5), hit_rate(10), hit_rate(20)
        sim_vals = [safe_float(g.get('value')) for g in similar_games if safe_float(g.get('value')) is not None]
        sim_avg = (sum(sim_vals) / len(sim_vals)) if sim_vals else None
        sample_type = 'historical_games'
        sample_note = 'MLB historical mode uses actual recent batter game logs from scraper output.'
        x_axis = 'date'
    else:
        avg_anchor = safe_float(row.get(market['avg_cols'][0]))
        sim_avg = safe_float(row.get(market['avg_cols'][1]))
        games = []
        for seq, (label, col, sim_bin) in enumerate([
            ('Prior', market['prior_col'], 'Far 25%'),
            ('L20', market['avg_cols'][0], 'Mid 25%'),
            ('L10', market['avg_cols'][1], 'Close 25%'),
            ('L5', market['avg_cols'][2], 'Closest 25%'),
        ], start=1):
            value = safe_float(row.get(col))
            if value is None:
                continue
            games.append({
                'gameId': f'snapshot-{label.lower()}',
                'gameDate': label,
                'label': label,
                'shortLabel': label,
                'seq': seq,
                'value': value,
                'minutes': None,
                'opp': opp,
                'isHome': None,
                'location': '',
                'simBin': sim_bin,
                'simScore': None,
                'simPct': None,
            })
        similar_games = []
        sample_type = 'window_snapshot'
        sample_note = 'MLB preview mode uses rolling-window snapshots and priors when batter game logs are unavailable.'
        x_axis = 'snapshot'

    series = {
        'playerId': player_id,
        'player': clean_str(row.get('player_name')),
        'league': 'MLB',
        'playerType': 'batter',
        'stat': market['stat'],
        'statDisplay': market['display'],
        'gameDate': game_date,
        'recentWindow': recent_window if history_mode else 4,
        'sampleType': sample_type,
        'sampleNote': sample_note,
        'xAxis': x_axis,
        'modelPred': pred,
        'modelMu': pred,
        'modelSigma': None,
        'contextMetricLabel': 'Projected lineup spot',
        'contextMetricValue': projected_order,
        'samples': {
            'prior': safe_float(row.get(market['prior_col'])),
            'r20': safe_float(row.get(market['avg_cols'][0])),
            'r10': safe_float(row.get(market['avg_cols'][1])),
            'r5': safe_float(row.get(market['avg_cols'][2])),
        },
        'games': games,
        'similarGames': similar_games,
        'team': team,
        'opp': opp,
        'location': location,
        'matchup': matchup,
        'injuryStatus': '',
        'injuryNote': '',
        'injuryUpdated': '',
        'driverSummary': batter_context_summary(row),
        'boardContext': batter_context_summary(row),
        'matchupContext': matchup_context,
        'currentMatchupContext': matchup_context,
    }

    entries = []
    for line in valid_lines_for_pred(market['default_lines'], pred):
        prob = approx_prob(row, market, line, pred)
        if prob is None or prob < market['min_prob']:
            continue
        entry = {
            'id': f'{game_date}|MLB|{player_id}|{market["stat"]}|{line}',
            'seriesKey': f'{game_date}|MLB|{player_id}|{market["stat"]}',
            'gameDate': game_date,
            'gameId': game_pk,
            'league': 'MLB',
            'playerType': 'batter',
            'player': clean_str(row.get('player_name')),
            'playerId': player_id,
            'team': team,
            'opp': opp,
            'location': location,
            'matchup': matchup,
            'stat': market['stat'],
            'stat_display': market['display'],
            'line': line,
            'board': '',
            'board_score': None,
            'prob_cons': prob,
            'fair_american': fair_american(prob),
            'avg_anchor': avg_anchor,
            'pred_anchor': pred,
            'mu_cons': pred,
            'pred_minus_line': (pred - line),
            'avg_minus_line': ((avg_anchor - line) if avg_anchor is not None else None),
            'line_to_avg': (line / avg_anchor) if avg_anchor not in (None, 0) else None,
            'line_to_pred': (line / pred) if pred not in (None, 0) else None,
            'matchup_score': None,
            'minutes_score': None,
            'stability_score': None,
            'agreement_score': None,
            'hit_score': hit_r5,
            'sim_avg': sim_avg,
            'expMin': None,
            'contextMetricLabel': 'Projected lineup spot',
            'contextMetricValue': projected_order,
            'reason_flags': 'mlb-historical-games' if history_mode else 'mlb-preview-windows',
            'driver_1_for': batter_context_summary(row),
            'driver_2_for': '',
            'driver_3_for': '',
            'driver_1_against': '',
            'driver_2_against': '',
            'driver_summary': batter_context_summary(row),
            'boardDriver': batter_context_summary(row),
            'summary': batter_context_summary(row),
            'matchupContext': matchup_context,
            'currentMatchupContext': matchup_context,
            'batterHand': matchup_context.get('batterHand'),
            'opposingPitcherHand': matchup_context.get('pitcherHand'),
            'handednessText': matchup_context.get('handednessText'),
            'temperatureF': matchup_context.get('temperatureF'),
            'windMph': matchup_context.get('windMph'),
            'park': matchup_context.get('park'),
            'opponentStarterName': matchup_context.get('opponentStarterName'),
            'opponentStarterId': matchup_context.get('opponentStarterId'),
            'hit_r5': hit_r5,
            'hit_r10': hit_r10,
            'hit_r25': hit_r20,
            'injuryStatus': '',
            'injuryNote': '',
        }
        entries.append(entry)
    return entries, series

def build_pitcher_series_and_entries(row: pd.Series, market: dict[str, Any], game_lookup: dict[int, dict[str, Any]],
                                     pitcher_logs_lookup: dict[int, pd.DataFrame], max_games: int) -> tuple[list[dict], dict | None]:
    pred = safe_float(row.get(market['pred_col']))
    if pred is None:
        return [], None

    game_pk = safe_int(row.get('gamePk'))
    game = game_lookup.get(game_pk or -1, {})
    team = clean_str(row.get('team'))
    opp = clean_str(row.get('opponent'))
    away = clean_str(game.get('awayTeam'))
    home = clean_str(game.get('homeTeam'))
    location = 'Home' if team and home and team == home else 'Away' if team and away and team == away else ''
    matchup = f'{away} @ {home}'.strip(' @') if away and home else f'{team} vs {opp}'.strip()
    game_date = clean_str(game.get('gameDate'))
    target_ts = display_ts(game.get('gameTs'))
    player_id = safe_int(row.get('player_id'))
    matchup_context = matchup_context_from_pitcher_row(row, game, location)

    player_logs = pitcher_logs_lookup.get(player_id or -1, pd.DataFrame())
    minutes_col = 'outsRecorded' if market['stat'] == 'OUTS' else 'inningsPitched'
    games, similar_games = build_historical_games(
        player_logs, target_ts, market['value_col'], opp, location, max_games=max_games,
        minutes_col=minutes_col, extra_context_col=None, projected_order=None
    )
    history_mode = bool(games)

    if history_mode:
        vals = [safe_float(g.get('value')) for g in games[-20:] if safe_float(g.get('value')) is not None]
        avg_anchor = (sum(vals) / len(vals)) if vals else None
        sim_vals = [safe_float(g.get('value')) for g in similar_games if safe_float(g.get('value')) is not None]
        sim_avg = (sum(sim_vals) / len(sim_vals)) if sim_vals else None
        sample_type = 'historical_games'
        sample_note = 'Pitcher mode now uses actual recent starts when pitcher logs are available.'
        x_axis = 'date'
    else:
        avg_anchor = safe_float(row.get(market['avg_cols'][0]))
        sim_avg = safe_float(row.get(market['avg_cols'][1]))
        games = []
        for seq, (label, col, sim_bin) in enumerate([
            ('Prior', market['prior_col'], 'Far 25%'),
            ('L10', market['avg_cols'][0], 'Mid 25%'),
            ('L5', market['avg_cols'][1], 'Close 25%'),
            ('L3', market['avg_cols'][2], 'Closest 25%'),
        ], start=1):
            value = safe_float(row.get(col))
            if value is None:
                continue
            games.append({
                'gameId': f'pitcher-{label.lower()}',
                'gameDate': label,
                'label': label,
                'shortLabel': label,
                'seq': seq,
                'value': value,
                'minutes': safe_float(row.get(market['workload_col'])),
                'opp': opp,
                'isHome': safe_int(row.get('is_home')),
                'location': 'Home' if safe_int(row.get('is_home')) == 1 else 'Away' if safe_int(row.get('is_home')) == 0 else '',
                'simBin': sim_bin,
                'simScore': None,
                'simPct': None,
            })
        similar_games = []
        sample_type = 'window_snapshot'
        sample_note = 'Pitcher preview mode uses rolling-form snapshots and priors when pitcher logs are unavailable.'
        x_axis = 'snapshot'

    workload_value = safe_float(row.get(market['workload_col']))
    series = {
        'playerId': player_id,
        'player': clean_str(row.get('player_name') or row.get('fullName')),
        'league': 'MLB',
        'playerType': 'pitcher',
        'stat': market['stat'],
        'statDisplay': market['display'],
        'gameDate': game_date,
        'recentWindow': 4 if not history_mode else min(10, len(games)),
        'sampleType': sample_type,
        'sampleNote': sample_note,
        'xAxis': x_axis,
        'modelPred': pred,
        'modelMu': pred,
        'modelSigma': None,
        'contextMetricLabel': market['context_label'],
        'contextMetricValue': workload_value,
        'samples': {
            'prior': safe_float(row.get(market['prior_col'])),
            'r10': safe_float(row.get(market['avg_cols'][0])),
            'r5': safe_float(row.get(market['avg_cols'][1])),
            'r3': safe_float(row.get(market['avg_cols'][2])),
        },
        'games': games,
        'similarGames': similar_games,
        'team': team,
        'opp': opp,
        'location': location,
        'matchup': matchup,
        'injuryStatus': '',
        'injuryNote': '',
        'injuryUpdated': '',
        'driverSummary': f'Projected {pred:.1f} {market["display"].lower()} • projected {workload_value or 0:.1f} {market["context_label"]}',
        'boardContext': f'{team} vs {opp} • {clean_str(row.get("pitchHand"))}',
        'matchupContext': matchup_context,
        'currentMatchupContext': matchup_context,
    }

    entries = []
    for line in valid_lines_for_pred(market['default_lines'], pred):
        threshold = int(math.floor(line) + 1) if market['stat'] != 'IP' else int(math.floor(line + 0.0001))
        prob = poisson_tail_prob(pred, threshold) if market['stat'] != 'IP' else None
        entry = {
            'id': f'{game_date}|MLB|pitcher|{player_id}|{market["stat"]}|{line}',
            'seriesKey': f'{game_date}|MLB|pitcher|{player_id}|{market["stat"]}',
            'gameDate': game_date,
            'gameId': game_pk,
            'league': 'MLB',
            'playerType': 'pitcher',
            'player': clean_str(row.get('player_name') or row.get('fullName')),
            'playerId': player_id,
            'team': team,
            'opp': opp,
            'location': location,
            'matchup': matchup,
            'stat': market['stat'],
            'stat_display': market['display'],
            'line': line,
            'board': '',
            'board_score': None,
            'prob_cons': prob,
            'fair_american': fair_american(prob),
            'avg_anchor': avg_anchor,
            'pred_anchor': pred,
            'mu_cons': pred,
            'pred_minus_line': pred - line,
            'avg_minus_line': ((avg_anchor - line) if avg_anchor is not None else None),
            'line_to_avg': (line / avg_anchor) if avg_anchor not in (None, 0) else None,
            'line_to_pred': (line / pred) if pred not in (None, 0) else None,
            'matchup_score': None,
            'minutes_score': None,
            'stability_score': None,
            'agreement_score': None,
            'hit_score': None,
            'sim_avg': sim_avg,
            'expMin': workload_value,
            'contextMetricLabel': market['context_label'],
            'contextMetricValue': workload_value,
            'reason_flags': 'mlb-pitcher-historical' if history_mode else 'mlb-pitcher-preview-windows',
            'driver_1_for': f'Projected {market["context_label"]} {workload_value or 0:.1f}',
            'driver_2_for': f'{market["avg_cols"][1]} {safe_float(row.get(market["avg_cols"][1])) or 0:.1f}',
            'driver_3_for': '',
            'driver_1_against': '',
            'driver_2_against': '',
            'driver_summary': series['driverSummary'],
            'boardDriver': series['boardContext'],
            'summary': series['driverSummary'],
            'matchupContext': matchup_context,
            'currentMatchupContext': matchup_context,
            'pitcherHand': matchup_context.get('pitcherHand'),
            'temperatureF': matchup_context.get('temperatureF'),
            'windMph': matchup_context.get('windMph'),
            'park': matchup_context.get('park'),
            'hit_r5': None,
            'hit_r10': None,
            'hit_r25': None,
            'injuryStatus': '',
            'injuryNote': '',
        }
        entries.append(entry)
    return entries, series

def series_detail_relpath(game_date: str, player_id: int | None, stat: str, player_type: str) -> str:
    safe_pid = str(player_id or 0)
    suffix = f'{safe_pid}_{stat.lower()}'
    if player_type == 'pitcher':
        suffix = f'pitcher_{suffix}'
    return f'data/mlb_props_analyzer/{game_date}/{suffix}.json'

def main() -> int:
    args = parse_args()
    repo = args.website_repo
    data_dir = repo / 'data'
    detail_root = data_dir / 'mlb_props_analyzer'

    batter_csv = args.batter_csv or find_latest('batter_predictions_*.csv', args.mlb_output_dir)
    pitcher_csv = args.pitcher_csv or find_latest('pitcher_predictions_*.csv', args.mlb_output_dir)
    game_csv = args.game_csv or find_latest('game_predictions_*.csv', args.mlb_output_dir)
    if not batter_csv or not batter_csv.exists():
        raise SystemExit('Could not find batter_predictions CSV.')
    if not game_csv or not game_csv.exists():
        raise SystemExit('Could not find game_predictions CSV.')

    batter_df = pd.read_csv(batter_csv)
    pitcher_df = pd.read_csv(pitcher_csv) if pitcher_csv and pitcher_csv.exists() else pd.DataFrame()
    game_df = pd.read_csv(game_csv)
    game_lookup = build_game_lookup(game_df)

    batter_logs_df = prep_batter_logs(load_table_latest(args.mlb_data_dir, 'batter_game_logs'))
    pitcher_logs_df = prep_pitcher_logs(load_table_latest(args.mlb_data_dir, 'pitcher_game_logs'))

    # Step 10: enrich historical game-log rows with matchup context that already
    # exists in model-output history/current files and game/schedule/weather tables.
    # This fills the historical fields that Similarity v2 is designed to score.
    game_context_df = build_game_context(args)
    batter_prediction_context = build_prediction_context(args, batter_csv, 'batter')
    pitcher_prediction_context = build_prediction_context(args, pitcher_csv, 'pitcher')
    batter_logs_df = enrich_batter_logs_with_matchup_context(batter_logs_df, batter_prediction_context, game_context_df)
    pitcher_logs_df = enrich_pitcher_logs_with_matchup_context(pitcher_logs_df, pitcher_prediction_context, game_context_df)

    batter_logs_lookup: dict[int, pd.DataFrame] = {}
    if not batter_logs_df.empty:
        for player_id, grp in batter_logs_df.groupby('player_id'):
            batter_logs_lookup[int(player_id)] = grp.copy()

    pitcher_logs_lookup: dict[int, pd.DataFrame] = {}
    if not pitcher_logs_df.empty:
        for player_id, grp in pitcher_logs_df.groupby('player_id'):
            pitcher_logs_lookup[int(player_id)] = grp.copy()

    entries: list[dict[str, Any]] = []
    series_store: dict[str, dict[str, Any]] = {}

    for _, row in batter_df.iterrows():
        for market in BATTER_MARKETS:
            new_entries, series = build_batter_series_and_entries(row, market, game_lookup, batter_logs_lookup, args.recent_window, args.max_games)
            if series:
                series_store[new_entries[0]['seriesKey'] if new_entries else f'{series["gameDate"]}|MLB|{series["playerId"]}|{series["stat"]}'] = series
            entries.extend(new_entries)

    if not pitcher_df.empty:
        for _, row in pitcher_df.iterrows():
            for market in PITCHER_MARKETS:
                new_entries, series = build_pitcher_series_and_entries(row, market, game_lookup, pitcher_logs_lookup, args.max_games)
                if series:
                    series_store[new_entries[0]['seriesKey'] if new_entries else f'{series["gameDate"]}|MLB|pitcher|{series["playerId"]}|{series["stat"]}'] = series
                entries.extend(new_entries)

    entries.sort(key=lambda e: (
        clean_str(e.get('gameDate')),
        clean_str(e.get('player')),
        clean_str(e.get('playerType')),
        clean_str(e.get('stat')),
        float(e.get('line') or 0),
    ))

    if detail_root.exists() and not args.keep_old_details:
        shutil.rmtree(detail_root)

    series_index: dict[str, str] = {}
    historical_count = 0
    preview_count = 0

    for series_key, series in series_store.items():
        player_type = clean_str(series.get('playerType') or 'batter')
        rel = series_detail_relpath(clean_str(series.get('gameDate')), safe_int(series.get('playerId')), clean_str(series.get('stat')), player_type)
        series_index[series_key] = rel
        compact_write_json(repo / rel, series)
        if clean_str(series.get('sampleType')) == 'historical_games':
            historical_count += 1
        else:
            preview_count += 1

    slim_entries = []
    for e in entries:
        slim = dict(e)
        slim.pop('inlineSeries', None)
        slim_entries.append(slim)

    dates = sorted({clean_str(e.get('gameDate')) for e in slim_entries if clean_str(e.get('gameDate'))})
    payload = {
        'targetDate': dates[0] if dates else '',
        'league': 'MLB',
        'dates': dates,
        'generatedAt': pd.Timestamp.now(tz=timezone.utc).isoformat(),
        'sourceBatterCsv': str(batter_csv),
        'sourceGameCsv': str(game_csv),
        'sourcePitcherCsv': str(pitcher_csv) if pitcher_csv else '',
        'sourceBatterLogs': str(args.mlb_data_dir / 'batter_game_logs'),
        'sourcePitcherLogs': str(args.mlb_data_dir / 'pitcher_game_logs'),
        'entryCount': len(slim_entries),
        'seriesCount': len(series_index),
        'historicalSeriesCount': historical_count,
        'previewFallbackCount': preview_count,
        'entries': slim_entries,
        'seriesIndex': series_index,
    }
    compact_write_json(data_dir / 'mlb_props_analyzer.json', payload)
    print(f'Wrote {len(slim_entries)} MLB props analyzer entries to {data_dir / "mlb_props_analyzer.json"}')
    print(f'Wrote {len(series_index)} split detail files under {detail_root}')
    print(f'Historical series: {historical_count} | Snapshot fallback: {preview_count}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
