#!/usr/bin/env python3
"""
build_mlb_player_day_profiles.py

Read-only/additive builder for MLB prop-analyzer player-day profiles.

Purpose
-------
The current prop analyzer stores one JSON detail file per player/stat, such as:

    data/mlb_props_analyzer/2026-06-14/660271_h.json
    data/mlb_props_analyzer/2026-06-14/660271_tb.json
    data/mlb_props_analyzer/2026-06-14/660271_hrr.json

That is fine for a one-stat-at-a-time view, but it makes multi-prop analysis
hard. This script groups those existing files into one profile per player/date:

    data/mlb_props_analyzer/2026-06-14/player_profiles/660271.json

The output is additive. It does not modify or delete existing prop-analyzer files.

Run from the project root:

    python build_mlb_player_day_profiles.py --data-dir data --date 2026-06-14

Or build every date folder:

    python build_mlb_player_day_profiles.py --data-dir data --all-dates
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = "mlb-player-day-profile-v1"

STAT_DISPLAY_FALLBACK = {
    "H": "Hits",
    "TB": "Total Bases",
    "HRR": "Hits+Runs+RBI",
    "HR": "Home Runs",
    "2B": "Doubles",
    "BB": "Walks",
    "K": "Strikeouts",
    "SB": "Stolen Bases",
    "ER": "Pitcher Earned Runs",
    "HA": "Pitcher Hits Allowed",
    "IP": "Pitcher Innings",
    "OUTS": "Pitcher Outs",
}

STAT_SORT_ORDER = {
    "H": 10,
    "TB": 20,
    "HRR": 30,
    "HR": 40,
    "2B": 50,
    "BB": 60,
    "K": 70,
    "SB": 80,
    "ER": 110,
    "HA": 120,
    "IP": 130,
    "OUTS": 140,
}

DETAIL_SUFFIX_TO_STAT = {
    "2b": "2B",
    "bb": "BB",
    "er": "ER",
    "h": "H",
    "ha": "HA",
    "hr": "HR",
    "hrr": "HRR",
    "ip": "IP",
    "k": "K",
    "outs": "OUTS",
    "sb": "SB",
    "tb": "TB",
}

NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        if NUMERIC_RE.match(text):
            try:
                return float(text)
            except Exception:
                return None
    return None


def safe_int(value: Any) -> Optional[int]:
    f = safe_float(value)
    if f is None:
        return None
    if abs(f - round(f)) < 1e-9:
        return int(round(f))
    return None


def clean_value(value: Any) -> Any:
    """Return JSON-friendly values with NaN/Inf removed."""
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None
    if isinstance(value, dict):
        return {str(k): clean_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_value(v) for v in value]
    return value


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(clean_value(payload), f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_detail_filename(path: Path) -> Optional[Tuple[str, str]]:
    """Return (file_profile_key, stat) from a detail filename."""
    stem = path.stem
    if stem in {"index", "manifest"}:
        return None
    for suffix, stat in sorted(DETAIL_SUFFIX_TO_STAT.items(), key=lambda kv: -len(kv[0])):
        tail = "_" + suffix
        if stem.lower().endswith(tail):
            return stem[: -len(tail)], stat
    return None


def latest_date_folder(base: Path) -> Optional[str]:
    if not base.exists():
        return None
    dates = []
    for child in base.iterdir():
        if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name):
            dates.append(child.name)
    return sorted(dates)[-1] if dates else None


def iter_date_folders(base: Path, date: Optional[str], all_dates: bool) -> List[str]:
    if all_dates:
        if not base.exists():
            return []
        return sorted(
            child.name
            for child in base.iterdir()
            if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name)
        )
    if date:
        return [date]
    latest = latest_date_folder(base)
    return [latest] if latest else []


def normalize_player_id(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            return None
        if NUMERIC_RE.match(text):
            return str(int(float(text)))
        return text
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return str(int(float(value)))
    return str(value)


def profile_key_for(detail: Dict[str, Any], file_key: str) -> str:
    player_id = normalize_player_id(detail.get("playerId"))
    if player_id:
        return player_id
    # Use filename key for TBD rows so multiple unknown players are not merged
    # just because playerId is null.
    team = str(detail.get("team") or "team").strip().lower()
    ptype = str(detail.get("playerType") or "player").strip().lower()
    safe_file_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_key)
    return f"{ptype}_{team}_{safe_file_key}"


def parse_context_text(text: str) -> Dict[str, Any]:
    """Parse the existing board/driver text into optional matchup fields."""
    text = text or ""
    out: Dict[str, Any] = {
        "raw": text,
        "lineupOrder": None,
        "batterHand": None,
        "pitcherHand": None,
        "handednessText": None,
        "temperatureF": None,
        "windMph": None,
        "parsedFrom": "driverSummary/boardContext",
    }

    m = re.search(r"\bOrder\s+(\d+)\b", text, re.I)
    if m:
        out["lineupOrder"] = int(m.group(1))

    # Handles L vs R, R vs L, B vs R, etc.
    m = re.search(r"\b([LRBS])\s+vs\s+([LRBS])\b", text, re.I)
    if m:
        out["batterHand"] = m.group(1).upper()
        out["pitcherHand"] = m.group(2).upper()
        out["handednessText"] = f"{out['batterHand']} vs {out['pitcherHand']}"

    m = re.search(r"(-?\d+(?:\.\d+)?)\s*°\s*F", text, re.I)
    if m:
        out["temperatureF"] = safe_float(m.group(1))

    m = re.search(r"\bWind\s+(-?\d+(?:\.\d+)?)", text, re.I)
    if m:
        out["windMph"] = safe_float(m.group(1))

    return out


def load_analyzer_rows(data_dir: Path) -> List[Dict[str, Any]]:
    """Load optional prop board rows from data/mlb_props_analyzer.json if available."""
    path = data_dir / "mlb_props_analyzer.json"
    if not path.exists():
        return []
    try:
        payload = load_json(path)
    except Exception:
        return []

    candidates: List[Any] = []
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in ["rows", "props", "data", "items", "players", "allProps"]:
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        # Some builders group by category/date; flatten common one-level lists.
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                # Avoid duplicating the same list twice too badly by accepting and de-duping below.
                candidates.extend(value)

    rows: List[Dict[str, Any]] = []
    seen = set()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        marker = json.dumps(row, sort_keys=True, default=str)[:1000]
        if marker in seen:
            continue
        seen.add(marker)
        rows.append(row)
    return rows


def row_date(row: Dict[str, Any]) -> Optional[str]:
    for key in ["gameDate", "date", "targetDate"]:
        value = row.get(key)
        if value:
            return str(value)[:10]
    return None


def row_stat(row: Dict[str, Any]) -> Optional[str]:
    for key in ["stat", "prop", "market", "statKey"]:
        value = row.get(key)
        if value:
            text = str(value).upper().strip()
            if text in {"HITS"}:
                return "H"
            if text in {"TOTAL_BASES", "TOTAL BASES"}:
                return "TB"
            if text in {"HITS+RUNS+RBI", "HITS_RUNS_RBI", "H+R+RBI"}:
                return "HRR"
            return text
    return None


def make_board_row_index(rows: List[Dict[str, Any]], target_date: str) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Index analyzer board rows by (playerId/playerName fallback, stat)."""
    index: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rdate = row_date(row)
        if rdate and rdate != target_date:
            continue
        stat = row_stat(row)
        if not stat:
            continue
        pid = normalize_player_id(row.get("playerId"))
        if pid:
            key = (pid, stat)
            index[key].append(row)
        player = str(row.get("player") or row.get("name") or "").strip().lower()
        team = str(row.get("team") or "").strip().lower()
        if player:
            index[(f"name:{player}|{team}", stat)].append(row)
    return index


def prop_lines_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for row in rows:
        line = safe_float(row.get("line") if "line" in row else row.get("propLine"))
        prob = None
        for key in ["prob_cons", "probability", "prob", "hitProbability", "modelProbability"]:
            if key in row:
                prob = safe_float(row.get(key))
                break
        href = row.get("href") or row.get("url")
        side = row.get("side") or row.get("pick") or row.get("direction")
        marker = (line, prob, href, side)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(
            {
                "line": line,
                "probability": prob,
                "probabilityDisplay": f"{prob * 100:.1f}%" if prob is not None and prob <= 1.000001 else None,
                "side": side,
                "href": href,
                "sourceScore": safe_float(row.get("score") or row.get("current_score") or row.get("score_v2")),
            }
        )
    return out


def compact_game_key(game: Dict[str, Any]) -> str:
    game_id = game.get("gameId")
    if game_id not in [None, ""]:
        return f"id:{game_id}"
    parts = [
        str(game.get("gameDate") or game.get("label") or ""),
        str(game.get("opp") or ""),
        str(game.get("location") or ""),
        str(game.get("seq") or ""),
    ]
    return "|".join(parts)


def merge_game_logs(details_by_stat: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    seq_fallback = 0

    for stat, detail in details_by_stat.items():
        for game in detail.get("games") or []:
            if not isinstance(game, dict):
                continue
            key = compact_game_key(game)
            seq_fallback += 1
            row = by_key.setdefault(
                key,
                {
                    "gameKey": key,
                    "gameId": game.get("gameId"),
                    "gameDate": game.get("gameDate"),
                    "label": game.get("label"),
                    "shortLabel": game.get("shortLabel"),
                    "seq": game.get("seq") if game.get("seq") is not None else seq_fallback,
                    "opp": game.get("opp"),
                    "location": game.get("location"),
                    "isHome": game.get("isHome"),
                    "contextValue": game.get("contextValue"),
                    "simBin": game.get("simBin"),
                    "simScore": game.get("simScore"),
                    "simPct": game.get("simPct"),
                    "stats": {},
                },
            )
            # Preserve the earliest/common context while adding stat values.
            row["stats"][stat] = {
                "value": safe_float(game.get("value")),
                "rawValue": game.get("value"),
                "minutes": safe_float(game.get("minutes")),
                "simBin": game.get("simBin"),
                "simScore": safe_float(game.get("simScore")),
                "simPct": safe_float(game.get("simPct")),
            }

    def sort_key(row: Dict[str, Any]) -> Tuple[str, int, str]:
        return (
            str(row.get("gameDate") or row.get("label") or ""),
            safe_int(row.get("seq")) or 0,
            str(row.get("gameKey")),
        )

    return sorted(by_key.values(), key=sort_key)


def build_chart_series(details_by_stat: Dict[str, Dict[str, Any]], merged_log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    game_keys = [row.get("gameKey") for row in merged_log]
    series = []
    for stat in sorted(details_by_stat, key=lambda s: (STAT_SORT_ORDER.get(s, 999), s)):
        detail = details_by_stat[stat]
        values_by_key: Dict[str, Optional[float]] = {}
        for game in detail.get("games") or []:
            if isinstance(game, dict):
                values_by_key[compact_game_key(game)] = safe_float(game.get("value"))
        y = [values_by_key.get(key) for key in game_keys]
        series.append(
            {
                "stat": stat,
                "label": detail.get("statDisplay") or STAT_DISPLAY_FALLBACK.get(stat, stat),
                "modelPred": safe_float(detail.get("modelPred") or detail.get("modelMu")),
                "sampleType": detail.get("sampleType"),
                "x": [row.get("shortLabel") or row.get("label") or row.get("gameDate") for row in merged_log],
                "gameKeys": game_keys,
                "y": y,
            }
        )
    return series


def summarize_similar_games(detail: Dict[str, Any]) -> Dict[str, Any]:
    games = [g for g in (detail.get("similarGames") or []) if isinstance(g, dict)]
    vals = [safe_float(g.get("value")) for g in games]
    vals = [v for v in vals if v is not None]
    bins = Counter(str(g.get("simBin") or "missing") for g in games)
    return {
        "count": len(games),
        "avgValue": round(sum(vals) / len(vals), 4) if vals else None,
        "maxSimScore": max([safe_float(g.get("simScore")) for g in games if safe_float(g.get("simScore")) is not None], default=None),
        "bins": dict(sorted(bins.items())),
        "topGames": [
            {
                "gameDate": g.get("gameDate"),
                "opp": g.get("opp"),
                "location": g.get("location"),
                "value": safe_float(g.get("value")),
                "simScore": safe_float(g.get("simScore")),
                "simPct": safe_float(g.get("simPct")),
            }
            for g in games[:5]
        ],
    }


def build_available_prop(
    stat: str,
    detail: Dict[str, Any],
    detail_filename: str,
    board_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    games = [g for g in (detail.get("games") or []) if isinstance(g, dict)]
    recent_values = [safe_float(g.get("value")) for g in games[-5:]]
    recent_values = [v for v in recent_values if v is not None]
    all_values = [safe_float(g.get("value")) for g in games]
    all_values = [v for v in all_values if v is not None]
    samples = detail.get("samples") if isinstance(detail.get("samples"), dict) else {}
    model_pred = safe_float(detail.get("modelPred") or detail.get("modelMu"))

    return {
        "stat": stat,
        "statDisplay": detail.get("statDisplay") or STAT_DISPLAY_FALLBACK.get(stat, stat),
        "detailFile": detail_filename,
        "sampleType": detail.get("sampleType"),
        "recentWindow": detail.get("recentWindow"),
        "modelPred": model_pred,
        "modelPredDisplay": f"{model_pred:.2f}" if model_pred is not None else None,
        "modelSigma": safe_float(detail.get("modelSigma")),
        "contextMetricLabel": detail.get("contextMetricLabel"),
        "contextMetricValue": safe_float(detail.get("contextMetricValue")),
        "samples": samples,
        "recent5Avg": round(sum(recent_values) / len(recent_values), 4) if recent_values else None,
        "allGamesAvg": round(sum(all_values) / len(all_values), 4) if all_values else None,
        "gameCount": len(games),
        "lineOptions": prop_lines_from_rows(board_rows),
        "similarity": summarize_similar_games(detail),
    }


def quality_flags(profile: Dict[str, Any]) -> Dict[str, Any]:
    available_stats = {p["stat"] for p in profile.get("availableProps") or []}
    player_type = profile.get("playerType")
    warnings = []

    if not profile.get("playerId"):
        warnings.append("missing playerId/TBD profile")
    if len(available_stats) <= 1:
        warnings.append("only one prop available")
    if player_type == "batter":
        for stat in ["H", "TB", "HRR"]:
            if stat not in available_stats:
                warnings.append(f"missing {stat} detail")
    ctx = profile.get("matchupContext") or {}
    if not ctx.get("handednessText"):
        warnings.append("handedness not parsed from driver text")
    if ctx.get("temperatureF") is None:
        warnings.append("temperature not parsed from driver text")
    if ctx.get("windMph") is None:
        warnings.append("wind not parsed from driver text")

    return {
        "multiPropReady": len(available_stats) >= 2,
        "coreBatterPropsReady": player_type == "batter" and {"H", "TB", "HRR"}.issubset(available_stats),
        "availableStatCount": len(available_stats),
        "warnings": warnings,
    }


def build_profile(
    profile_key: str,
    file_key: str,
    details_by_stat: Dict[str, Dict[str, Any]],
    detail_filenames_by_stat: Dict[str, str],
    board_index: Dict[Tuple[str, str], List[Dict[str, Any]]],
    target_date: str,
) -> Dict[str, Any]:
    stats_sorted = sorted(details_by_stat, key=lambda s: (STAT_SORT_ORDER.get(s, 999), s))
    primary = details_by_stat[stats_sorted[0]]
    player_id = normalize_player_id(primary.get("playerId"))
    player_name = str(primary.get("player") or "").strip()
    team = str(primary.get("team") or "").strip()
    name_key = f"name:{player_name.lower()}|{team.lower()}" if player_name else ""

    context_text = primary.get("driverSummary") or primary.get("boardContext") or ""
    if not context_text:
        for stat in stats_sorted:
            context_text = details_by_stat[stat].get("driverSummary") or details_by_stat[stat].get("boardContext") or ""
            if context_text:
                break

    available_props = []
    for stat in stats_sorted:
        detail = details_by_stat[stat]
        rows: List[Dict[str, Any]] = []
        if player_id:
            rows.extend(board_index.get((player_id, stat), []))
        if name_key:
            rows.extend(board_index.get((name_key, stat), []))
        available_props.append(build_available_prop(stat, detail, detail_filenames_by_stat[stat], rows))

    merged_log = merge_game_logs(details_by_stat)
    chart_series = build_chart_series(details_by_stat, merged_log)

    profile: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now_iso(),
        "gameDate": target_date,
        "profileKey": profile_key,
        "sourceFileKey": file_key,
        "playerId": player_id,
        "player": player_name,
        "league": primary.get("league") or "MLB",
        "playerType": primary.get("playerType"),
        "team": team,
        "opp": primary.get("opp"),
        "matchup": primary.get("matchup"),
        "location": primary.get("location"),
        "injuryStatus": primary.get("injuryStatus"),
        "injuryNote": primary.get("injuryNote"),
        "injuryUpdated": primary.get("injuryUpdated"),
        "boardContext": primary.get("boardContext") or primary.get("driverSummary"),
        "driverSummary": primary.get("driverSummary") or primary.get("boardContext"),
        "matchupContext": parse_context_text(context_text),
        "availableStats": stats_sorted,
        "availableProps": available_props,
        "combinedGameLog": merged_log,
        "chartSeries": chart_series,
        "uiHints": {
            "defaultSelectedStats": [s for s in ["H", "TB", "HRR"] if s in stats_sorted][:3] or stats_sorted[:3],
            "recommendedChartMode": "smallMultiples" if len(stats_sorted) > 1 else "singleSeries",
            "canUseNormalizedMultiLine": len(stats_sorted) > 1,
            "primaryStat": stats_sorted[0] if stats_sorted else None,
        },
    }
    profile["dataQuality"] = quality_flags(profile)
    return profile


def build_for_date(data_dir: Path, target_date: str, include_tbd: bool) -> Dict[str, Any]:
    detail_dir = data_dir / "mlb_props_analyzer" / target_date
    if not detail_dir.exists():
        return {
            "date": target_date,
            "detailDir": str(detail_dir),
            "error": "detail directory missing",
            "profilesWritten": 0,
        }

    board_rows = load_analyzer_rows(data_dir)
    board_index = make_board_row_index(board_rows, target_date)

    grouped: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    grouped_file_keys: Dict[str, str] = {}
    grouped_filenames: Dict[str, Dict[str, str]] = defaultdict(dict)
    files_scanned = 0
    files_loaded = 0
    skipped = Counter()

    for path in sorted(detail_dir.glob("*.json")):
        if path.parent.name == "player_profiles":
            continue
        parsed = parse_detail_filename(path)
        if not parsed:
            skipped["filename_not_detail"] += 1
            continue
        file_key, stat_from_name = parsed
        files_scanned += 1
        try:
            detail = load_json(path)
        except Exception:
            skipped["json_load_failed"] += 1
            continue
        if not isinstance(detail, dict):
            skipped["not_object"] += 1
            continue
        stat = str(detail.get("stat") or stat_from_name).upper()
        if stat == "2B" or stat in STAT_DISPLAY_FALLBACK:
            pass
        else:
            # Keep unknown stats, but track them.
            skipped["unknown_stat_kept"] += 1
        pkey = profile_key_for(detail, file_key)
        if not include_tbd and not normalize_player_id(detail.get("playerId")):
            skipped["tbd_or_missing_playerId"] += 1
            continue
        grouped[pkey][stat] = detail
        grouped_file_keys[pkey] = file_key
        grouped_filenames[pkey][stat] = path.name
        files_loaded += 1

    out_dir = detail_dir / "player_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)

    profiles = []
    stat_counter = Counter()
    warning_counter = Counter()
    multi_prop_ready = 0
    core_batter_ready = 0

    for pkey, details_by_stat in sorted(grouped.items()):
        profile = build_profile(
            profile_key=pkey,
            file_key=grouped_file_keys.get(pkey, pkey),
            details_by_stat=details_by_stat,
            detail_filenames_by_stat=grouped_filenames[pkey],
            board_index=board_index,
            target_date=target_date,
        )
        filename = f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', pkey)}.json"
        rel_path = f"player_profiles/{filename}"
        write_json(out_dir / filename, profile)

        for stat in profile.get("availableStats") or []:
            stat_counter[stat] += 1
        q = profile.get("dataQuality") or {}
        if q.get("multiPropReady"):
            multi_prop_ready += 1
        if q.get("coreBatterPropsReady"):
            core_batter_ready += 1
        for warning in q.get("warnings") or []:
            warning_counter[warning] += 1

        profiles.append(
            {
                "profileKey": pkey,
                "playerId": profile.get("playerId"),
                "player": profile.get("player"),
                "playerType": profile.get("playerType"),
                "team": profile.get("team"),
                "opp": profile.get("opp"),
                "matchup": profile.get("matchup"),
                "availableStats": profile.get("availableStats"),
                "availableStatCount": len(profile.get("availableStats") or []),
                "multiPropReady": q.get("multiPropReady"),
                "coreBatterPropsReady": q.get("coreBatterPropsReady"),
                "matchupContext": profile.get("matchupContext"),
                "profileFile": rel_path,
            }
        )

    index_payload = {
        "schemaVersion": SCHEMA_VERSION + "-index",
        "generatedAt": utc_now_iso(),
        "gameDate": target_date,
        "detailDir": str(detail_dir),
        "count": len(profiles),
        "profiles": profiles,
    }
    write_json(out_dir / "index.json", index_payload)

    summary = {
        "date": target_date,
        "detailDir": str(detail_dir),
        "filesScanned": files_scanned,
        "filesLoadedIntoProfiles": files_loaded,
        "profilesWritten": len(profiles),
        "multiPropReadyProfiles": multi_prop_ready,
        "coreBatterPropsReadyProfiles": core_batter_ready,
        "statCoverage": dict(sorted(stat_counter.items())),
        "warningCounts": dict(sorted(warning_counter.items())),
        "skipped": dict(sorted(skipped.items())),
        "outputDir": str(out_dir),
        "indexFile": str(out_dir / "index.json"),
    }
    return summary


def write_summary_csv(path: Path, summaries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "filesScanned",
        "filesLoadedIntoProfiles",
        "profilesWritten",
        "multiPropReadyProfiles",
        "coreBatterPropsReadyProfiles",
        "outputDir",
        "indexFile",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in summaries:
            writer.writerow({field: row.get(field) for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description="Build additive MLB prop-analyzer player-day profiles for multi-prop UI work.")
    parser.add_argument("--data-dir", default="data", help="Site data directory. Default: data")
    parser.add_argument("--date", default=None, help="Specific date folder to build, e.g. 2026-06-14. Defaults to latest.")
    parser.add_argument("--all-dates", action="store_true", help="Build every YYYY-MM-DD folder under data/mlb_props_analyzer.")
    parser.add_argument("--include-tbd", action="store_true", help="Include missing-playerId/TBD profiles. Default: skip them.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    detail_base = data_dir / "mlb_props_analyzer"
    dates = iter_date_folders(detail_base, args.date, args.all_dates)
    if not dates:
        raise SystemExit(f"No detail date folders found under {detail_base}")

    summaries = []
    for target_date in dates:
        summary = build_for_date(data_dir, target_date, include_tbd=args.include_tbd)
        summaries.append(summary)
        if summary.get("error"):
            print(f"[WARN] {target_date}: {summary['error']}")
        else:
            print(
                f"[OK] {target_date}: wrote {summary['profilesWritten']} profiles "
                f"({summary['multiPropReadyProfiles']} multi-prop-ready) -> {summary['outputDir']}"
            )

    audits_dir = data_dir / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    summary_payload = {
        "generatedAt": utc_now_iso(),
        "dataDir": str(data_dir),
        "dates": dates,
        "includeTbd": bool(args.include_tbd),
        "summaries": summaries,
    }
    write_json(audits_dir / "mlb_player_day_profiles_summary.json", summary_payload)
    write_summary_csv(audits_dir / "mlb_player_day_profiles_summary.csv", summaries)
    print(f"[OK] Wrote {audits_dir / 'mlb_player_day_profiles_summary.json'}")
    print(f"[OK] Wrote {audits_dir / 'mlb_player_day_profiles_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
