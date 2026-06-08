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

SCHEMA_VERSION = "mlb-player-day-profile-v4"

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


def lineup_band(order: Optional[int]) -> Optional[str]:
    if order is None:
        return None
    if order <= 3:
        return "top-third lineup"
    if order <= 6:
        return "middle-third lineup"
    return "bottom-third lineup"


def handedness_bucket(batter_hand: Optional[str], pitcher_hand: Optional[str]) -> Optional[str]:
    if not batter_hand or not pitcher_hand:
        return None
    b = str(batter_hand).upper()
    p = str(pitcher_hand).upper()
    if b == "B":
        return f"switch hitter vs {p}HP"
    if b in {"L", "R"} and p in {"L", "R"}:
        return "opposite-side matchup" if b != p else "same-side matchup"
    return f"{b} vs {p}"


def temperature_bucket(temp_f: Optional[float]) -> Optional[str]:
    if temp_f is None:
        return None
    if temp_f < 55:
        return "cold environment"
    if temp_f < 70:
        return "mild/cool environment"
    if temp_f < 85:
        return "warm environment"
    return "hot environment"


def wind_bucket(wind_mph: Optional[float]) -> Optional[str]:
    if wind_mph is None:
        return None
    if wind_mph < 7:
        return "low wind"
    if wind_mph < 14:
        return "moderate wind"
    return "high wind"


def parse_context_text(text: str) -> Dict[str, Any]:
    """Parse the existing board/driver text into structured current matchup fields.

    This intentionally parses only the *current* matchup text that already exists in
    the daily analyzer files. It does not invent historical handedness or pitch-mix
    data. Those still need to be added upstream before similarity can score them.
    """
    text = text or ""
    out: Dict[str, Any] = {
        "raw": text,
        "lineupOrder": None,
        "lineupBand": None,
        "batterHand": None,
        "pitcherHand": None,
        "handednessText": None,
        "handednessBucket": None,
        "temperatureF": None,
        "temperatureBucket": None,
        "windMph": None,
        "windBucket": None,
        "currentFeatures": [],
        "summaryPieces": [],
        "parsedFrom": "driverSummary/boardContext",
    }

    m = re.search(r"\bOrder\s+(\d+)\b", text, re.I)
    if m:
        order = int(m.group(1))
        out["lineupOrder"] = order
        out["lineupBand"] = lineup_band(order)

    # Handles L vs R, R vs L, B vs R, etc.
    m = re.search(r"\b([LRBS])\s+vs\s+([LRBS])\b", text, re.I)
    if m:
        out["batterHand"] = m.group(1).upper()
        out["pitcherHand"] = m.group(2).upper()
        out["handednessText"] = f"{out['batterHand']} vs {out['pitcherHand']}"
        out["handednessBucket"] = handedness_bucket(out["batterHand"], out["pitcherHand"])

    m = re.search(r"(-?\d+(?:\.\d+)?)\s*°\s*F", text, re.I)
    if m:
        temp = safe_float(m.group(1))
        out["temperatureF"] = temp
        out["temperatureBucket"] = temperature_bucket(temp)

    m = re.search(r"\bWind\s+(-?\d+(?:\.\d+)?)", text, re.I)
    if m:
        wind = safe_float(m.group(1))
        out["windMph"] = wind
        out["windBucket"] = wind_bucket(wind)

    features: List[Dict[str, Any]] = []
    summary: List[str] = []
    if out.get("lineupOrder") is not None:
        features.append({
            "key": "lineupOrder",
            "label": "Lineup",
            "value": f"Order {out['lineupOrder']}",
            "note": out.get("lineupBand"),
            "available": True,
        })
        summary.append(f"Order {out['lineupOrder']}")
    if out.get("handednessText"):
        features.append({
            "key": "handedness",
            "label": "Handedness",
            "value": out["handednessText"],
            "note": out.get("handednessBucket"),
            "available": True,
        })
        summary.append(out["handednessText"])
    if out.get("temperatureF") is not None:
        features.append({
            "key": "temperature",
            "label": "Temperature",
            "value": f"{out['temperatureF']:.0f}°F",
            "note": out.get("temperatureBucket"),
            "available": True,
        })
        summary.append(f"{out['temperatureF']:.0f}°F")
    if out.get("windMph") is not None:
        features.append({
            "key": "wind",
            "label": "Wind",
            "value": f"{out['windMph']:.0f} mph",
            "note": out.get("windBucket"),
            "available": True,
        })
        summary.append(f"Wind {out['windMph']:.0f}")

    out["currentFeatures"] = features
    out["summaryPieces"] = summary
    out["featureCoverage"] = {
        "lineupOrder": out.get("lineupOrder") is not None,
        "currentHandedness": bool(out.get("handednessText")),
        "currentTemperature": out.get("temperatureF") is not None,
        "currentWind": out.get("windMph") is not None,
        "historicalHandedness": False,
        "historicalPitchMix": False,
        "historicalPark": False,
        "historicalWeather": False,
    }
    out["similarityReadiness"] = {
        "currentContextReady": bool(summary),
        "canScoreCurrentHandedness": bool(out.get("handednessText")),
        "canScoreHistoricalHandedness": False,
        "canScorePitchMix": False,
        "nextRequiredInputs": [
            "historical batter hand and pitcher hand per game-log row",
            "current and historical opposing starter identity",
            "pitch mix / pitch-type profile by opposing starter",
            "park/weather values per historical row",
        ],
    }
    return out


def native_detail_context(detail: Dict[str, Any]) -> Dict[str, Any]:
    ctx = detail.get("matchupContext") if isinstance(detail.get("matchupContext"), dict) else None
    if not ctx:
        ctx = detail.get("currentMatchupContext") if isinstance(detail.get("currentMatchupContext"), dict) else None
    return dict(ctx or {})


def merge_native_context(parsed: Dict[str, Any], native: Dict[str, Any]) -> Dict[str, Any]:
    """Merge structured context emitted by the upstream analyzer with parsed text.

    Parsed text is still the fallback, but native fields are preferred because they
    are less fragile and can include park/starter/pitch-mix fields that are not
    always shown in the short display summary.
    """
    out = dict(parsed or {})
    native = native or {}
    field_map = {
        "lineupOrder": ["lineupOrder", "projectedLineupOrder", "projected_batting_order"],
        "batterHand": ["batterHand", "batSide", "bat_side"],
        "pitcherHand": ["pitcherHand", "opposingPitcherHand", "oppPitchHand", "opp_pitch_hand"],
        "handednessText": ["handednessText"],
        "temperatureF": ["temperatureF", "tempF", "temperature_f"],
        "windMph": ["windMph", "wind_mph"],
        "park": ["park", "venue", "venueName", "ballpark"],
        "opponentStarterName": ["opponentStarterName", "opposingStarterName", "oppStarterName"],
        "opponentStarterId": ["opponentStarterId", "opposingStarterId", "oppStarterId"],
        "pitchMixSummary": ["pitchMixSummary", "pitchMix", "pitch_mix"],
    }
    for target, candidates in field_map.items():
        for key in candidates:
            value = native.get(key)
            if value not in [None, ""]:
                if target == "lineupOrder":
                    value = safe_int(value)
                elif target in {"temperatureF", "windMph"}:
                    value = safe_float(value)
                elif target in {"batterHand", "pitcherHand"}:
                    value = str(value).strip().upper()[:1]
                out[target] = value
                break

    if not out.get("handednessText") and out.get("batterHand") and out.get("pitcherHand"):
        out["handednessText"] = f"{out['batterHand']} vs {out['pitcherHand']}"
    if out.get("lineupOrder") is not None:
        out["lineupBand"] = lineup_band(int(out["lineupOrder"]))
    if out.get("batterHand") and out.get("pitcherHand"):
        out["handednessBucket"] = handedness_bucket(out.get("batterHand"), out.get("pitcherHand"))
    if out.get("temperatureF") is not None:
        out["temperatureBucket"] = temperature_bucket(safe_float(out.get("temperatureF")))
    if out.get("windMph") is not None:
        out["windBucket"] = wind_bucket(safe_float(out.get("windMph")))

    features: List[Dict[str, Any]] = []
    summary: List[str] = []
    if out.get("lineupOrder") is not None:
        features.append({"key": "lineupOrder", "label": "Lineup", "value": f"Order {out['lineupOrder']}", "note": out.get("lineupBand"), "available": True})
        summary.append(f"Order {out['lineupOrder']}")
    if out.get("handednessText"):
        features.append({"key": "handedness", "label": "Handedness", "value": out["handednessText"], "note": out.get("handednessBucket"), "available": True})
        summary.append(out["handednessText"])
    if out.get("temperatureF") is not None:
        features.append({"key": "temperature", "label": "Temperature", "value": f"{safe_float(out['temperatureF']):.0f}°F", "note": out.get("temperatureBucket"), "available": True})
        summary.append(f"{safe_float(out['temperatureF']):.0f}°F")
    if out.get("windMph") is not None:
        features.append({"key": "wind", "label": "Wind", "value": f"{safe_float(out['windMph']):.0f} mph", "note": out.get("windBucket"), "available": True})
        summary.append(f"Wind {safe_float(out['windMph']):.0f}")
    if out.get("park"):
        features.append({"key": "park", "label": "Park", "value": str(out["park"]), "note": "current venue", "available": True})
    if out.get("opponentStarterName"):
        features.append({"key": "opponentStarter", "label": "Opp starter", "value": str(out["opponentStarterName"]), "note": out.get("pitcherHand") and f"{out.get('pitcherHand')}HP", "available": True})
    if out.get("pitchMixSummary"):
        features.append({"key": "pitchMix", "label": "Pitch mix", "value": str(out["pitchMixSummary"]), "note": "current starter profile", "available": True})

    out["currentFeatures"] = features
    out["summaryPieces"] = summary
    out["featureCoverage"] = {
        "lineupOrder": out.get("lineupOrder") is not None,
        "currentHandedness": bool(out.get("handednessText")),
        "currentTemperature": out.get("temperatureF") is not None,
        "currentWind": out.get("windMph") is not None,
        "currentPark": bool(out.get("park")),
        "currentStarter": bool(out.get("opponentStarterName") or out.get("opponentStarterId")),
        "currentPitchMix": bool(out.get("pitchMixSummary")),
        "historicalHandedness": False,
        "historicalPitchMix": False,
        "historicalPark": False,
        "historicalWeather": False,
    }
    out["similarityReadiness"] = {
        "currentContextReady": bool(summary),
        "canScoreCurrentHandedness": bool(out.get("handednessText")),
        "canScoreHistoricalHandedness": False,
        "canScorePitchMix": False,
        "nextRequiredInputs": [
            "historical batter hand and pitcher hand per game-log row",
            "current and historical opposing starter identity",
            "pitch mix / pitch-type profile by opposing starter",
            "park/weather values per historical row",
        ],
    }
    return out


def parse_date(value: Any) -> Optional[datetime]:
    if value in [None, ""]:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except Exception:
        return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def current_context_order(detail: Dict[str, Any], matchup_context: Dict[str, Any]) -> Optional[float]:
    order = safe_float((matchup_context or {}).get("lineupOrder"))
    if order is not None:
        return order
    return safe_float(detail.get("contextMetricValue"))


def similarity_tier(score: float) -> str:
    if score >= 80:
        return "Strong match"
    if score >= 65:
        return "Good match"
    if score >= 50:
        return "Partial match"
    return "Loose match"


def similarity_bin(score: float) -> str:
    if score >= 80:
        return "Strong v2"
    if score >= 65:
        return "Good v2"
    if score >= 50:
        return "Partial v2"
    return "Loose v2"


def score_similarity_v2_game(
    game: Dict[str, Any],
    detail: Dict[str, Any],
    target_date: str,
    matchup_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Explainable similarity score using only features available on historical rows.

    Important: the current detail files do not carry historical handedness, pitch mix,
    park, temperature, or wind for each historical game row. Those are intentionally
    listed as missing, not silently guessed.
    """
    score = 0.0
    components: Dict[str, float] = {}
    reasons: List[str] = []
    missing: List[str] = []

    current_opp = str(detail.get("opp") or "").strip().upper()
    hist_opp = str(game.get("opp") or "").strip().upper()
    if current_opp and hist_opp:
        if current_opp == hist_opp:
            components["sameOpponent"] = 22.0
            reasons.append(f"same opponent {hist_opp}")
        else:
            components["sameOpponent"] = 0.0
    else:
        missing.append("opponent")

    current_loc = str(detail.get("location") or "").strip().lower()
    hist_loc = str(game.get("location") or "").strip().lower()
    if current_loc and hist_loc:
        if current_loc == hist_loc:
            components["sameLocation"] = 18.0
            reasons.append(f"same location {game.get('location')}")
        else:
            components["sameLocation"] = 0.0
    else:
        missing.append("home/away")

    current_hand = str((matchup_context or {}).get("handednessText") or "").strip().upper()
    hist_hand = str(game.get("handednessText") or "").strip().upper()
    if not hist_hand:
        hb = str(game.get("batterHand") or "").strip().upper()[:1]
        hp = str(game.get("opposingPitcherHand") or game.get("pitcherHand") or "").strip().upper()[:1]
        if hb and hp:
            hist_hand = f"{hb} VS {hp}"
    if current_hand and hist_hand:
        components["sameHandedness"] = 18.0 if current_hand == hist_hand else 6.0
        reasons.append(f"historical hand match {hist_hand.replace(' VS ', ' vs ')}" if current_hand == hist_hand else f"historical hand differs {hist_hand.replace(' VS ', ' vs ')}")
    elif current_hand:
        missing.append("historical handedness")

    current_park = str((matchup_context or {}).get("park") or "").strip().upper()
    hist_park = str(game.get("park") or "").strip().upper()
    if current_park and hist_park:
        if current_park == hist_park:
            components["samePark"] = 8.0
            reasons.append("same park")
        else:
            components["samePark"] = 0.0
    elif current_park:
        missing.append("historical park")

    current_temp = safe_float((matchup_context or {}).get("temperatureF"))
    hist_temp = safe_float(game.get("temperatureF"))
    if current_temp is not None and hist_temp is not None:
        temp_score = clamp(6.0 - (abs(current_temp - hist_temp) / 5.0), 0.0, 6.0)
        components["temperatureSimilarity"] = round(temp_score, 2)
        if temp_score >= 4:
            reasons.append(f"similar temperature ({hist_temp:.0f}°F)")
    elif current_temp is not None:
        missing.append("historical temperature")

    current_wind = safe_float((matchup_context or {}).get("windMph"))
    hist_wind = safe_float(game.get("windMph"))
    if current_wind is not None and hist_wind is not None:
        wind_score = clamp(4.0 - (abs(current_wind - hist_wind) / 3.0), 0.0, 4.0)
        components["windSimilarity"] = round(wind_score, 2)
        if wind_score >= 2.5:
            reasons.append(f"similar wind ({hist_wind:.0f} mph)")
    elif current_wind is not None:
        missing.append("historical wind")

    current_pitch_mix = str((matchup_context or {}).get("pitchMixSummary") or "").strip()
    hist_pitch_mix = str(game.get("pitchMixSummary") or "").strip()
    if current_pitch_mix and hist_pitch_mix:
        # Seed only: true pitch-type similarity should use pitch usage/quality vectors later.
        components["pitchMixAvailable"] = 2.0
        reasons.append("pitch-mix field available")
    elif current_pitch_mix:
        missing.append("historical pitch mix")

    projected_order = current_context_order(detail, matchup_context)
    hist_order = safe_float(game.get("contextValue"))
    if projected_order is not None and hist_order is not None:
        diff = abs(projected_order - hist_order)
        ctx_score = clamp(18.0 - (diff * 4.0), 0.0, 18.0)
        components["lineupOrContext"] = round(ctx_score, 2)
        if ctx_score > 0:
            reasons.append(f"similar lineup/context ({hist_order:g} vs {projected_order:g})")
    else:
        missing.append("historical lineup/context")

    # Use AB/IP quality as a light sample-confidence piece, not as a direct matchup edge.
    minutes = safe_float(game.get("minutes"))
    player_type = str(detail.get("playerType") or "").lower()
    if minutes is not None:
        if player_type == "batter":
            sample_score = 8.0 if minutes >= 4 else 5.0 if minutes >= 3 else 2.0 if minutes > 0 else 0.0
            if minutes >= 3:
                reasons.append(f"usable AB sample ({minutes:g})")
        elif player_type == "pitcher":
            sample_score = 8.0 if minutes >= 5 else 5.0 if minutes >= 3 else 2.0 if minutes > 0 else 0.0
            if minutes >= 3:
                reasons.append(f"usable IP/outs sample ({minutes:g})")
        else:
            sample_score = 5.0 if minutes > 0 else 0.0
        components["sampleContext"] = sample_score
    else:
        missing.append("AB/IP sample")

    gdate = parse_date(game.get("gameDate") or game.get("label"))
    tdate = parse_date(target_date)
    if gdate and tdate:
        days = max(0, (tdate - gdate).days)
        # Full recency credit for the last week, fades to zero at about 60 days.
        recency_score = 22.0 if days <= 7 else clamp(22.0 * (1.0 - ((days - 7) / 53.0)), 0.0, 22.0)
        components["recency"] = round(recency_score, 2)
        if recency_score >= 14:
            reasons.append(f"recent sample ({days}d)")
    else:
        missing.append("game date")

    # Stability/base score for rows with a valid actual value.
    if safe_float(game.get("value")) is not None:
        components["hasResult"] = 12.0
    else:
        missing.append("actual result")

    score = round(clamp(sum(components.values()), 0.0, 100.0), 2)
    out = dict(game)
    out["simScoreV2"] = score
    out["simPctV2"] = score
    out["simBinV2"] = similarity_bin(score)
    out["simTierV2"] = similarity_tier(score)
    out["simComponentsV2"] = components
    out["simReasonsV2"] = reasons[:5]
    out["simMissingV2"] = missing
    out["simMethodV2"] = "available-feature-similarity-v2"
    # Make these rows compatible with the existing table renderer when used directly.
    out["simScore"] = score
    out["simPct"] = score
    out["simBin"] = out["simBinV2"]
    return out


def summarize_similarity_v2(detail: Dict[str, Any], target_date: str, matchup_context: Dict[str, Any]) -> Dict[str, Any]:
    games = [g for g in (detail.get("games") or []) if isinstance(g, dict)]
    scored = [score_similarity_v2_game(g, detail, target_date, matchup_context or {}) for g in games]
    scored_by_score = sorted(
        scored,
        key=lambda g: (safe_float(g.get("simScoreV2")) or 0.0, str(g.get("gameDate") or "")),
        reverse=True,
    )
    top = scored_by_score[:12]
    vals = [safe_float(g.get("value")) for g in top]
    vals = [v for v in vals if v is not None]
    all_scores = [safe_float(g.get("simScoreV2")) for g in scored]
    all_scores = [v for v in all_scores if v is not None]
    bins = Counter(str(g.get("simBinV2") or "missing") for g in top)

    coverage = {
        "sameOpponent": True,
        "homeAway": True,
        "lineupOrContext": any(safe_float(g.get("contextValue")) is not None for g in games),
        "abOrIpSample": any(safe_float(g.get("minutes")) is not None for g in games),
        "recency": True,
        "currentHandednessParsed": bool((matchup_context or {}).get("handednessText")),
        "currentPark": bool((matchup_context or {}).get("park")),
        "currentWeather": (matchup_context or {}).get("temperatureF") is not None or (matchup_context or {}).get("windMph") is not None,
        "currentPitchMix": bool((matchup_context or {}).get("pitchMixSummary")),
        "historicalHandedness": any(g.get("handednessText") or (g.get("batterHand") and (g.get("opposingPitcherHand") or g.get("pitcherHand"))) for g in games),
        "historicalPitchMix": any(g.get("pitchMixSummary") for g in games),
        "historicalWeather": any(safe_float(g.get("temperatureF")) is not None or safe_float(g.get("windMph")) is not None for g in games),
        "historicalPark": any(g.get("park") for g in games),
        "historicalStarter": any(g.get("opposingStarterName") or g.get("opposingStarterId") for g in games),
    }
    warnings = []
    if coverage["currentHandednessParsed"] and not coverage["historicalHandedness"]:
        warnings.append("Current handedness is structured, but historical game rows still do not include batter/pitcher hand.")
    if coverage["currentPitchMix"] and not coverage["historicalPitchMix"]:
        warnings.append("Current pitch mix is structured, but historical pitch-mix rows are not available yet.")
    if (coverage["currentPark"] and not coverage["historicalPark"]) or (coverage["currentWeather"] and not coverage["historicalWeather"]):
        warnings.append("Park/weather similarity is only scored when those fields exist on historical rows.")

    def compact_similarity_row(g: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "gameKey": compact_game_key(g),
            "gameId": g.get("gameId"),
            "gameDate": g.get("gameDate"),
            "label": g.get("label"),
            "shortLabel": g.get("shortLabel"),
            "seq": g.get("seq"),
            "opp": g.get("opp"),
            "location": g.get("location"),
            "isHome": g.get("isHome"),
            "value": safe_float(g.get("value")),
            "minutes": safe_float(g.get("minutes")),
            "contextValue": safe_float(g.get("contextValue")),
            "batterHand": g.get("batterHand"),
            "pitcherHand": g.get("opposingPitcherHand") or g.get("pitcherHand"),
            "handednessText": g.get("handednessText"),
            "park": g.get("park"),
            "temperatureF": safe_float(g.get("temperatureF")),
            "windMph": safe_float(g.get("windMph")),
            "pitchMixSummary": g.get("pitchMixSummary"),
            "simScoreV2": safe_float(g.get("simScoreV2")),
            "simPctV2": safe_float(g.get("simPctV2")),
            "simBinV2": g.get("simBinV2"),
            "simTierV2": g.get("simTierV2"),
            "simComponentsV2": g.get("simComponentsV2"),
            "simReasonsV2": g.get("simReasonsV2"),
            "simMissingV2": g.get("simMissingV2"),
            "simScore": safe_float(g.get("simScoreV2")),
            "simPct": safe_float(g.get("simPctV2")),
            "simBin": g.get("simBinV2"),
        }

    # Keep the top rows for the similarity-detail cards, but also preserve every
    # scored historical row so chart points and recent-game logs can be colored
    # consistently instead of only coloring rows that happened to land in topGames.
    scored_by_time = sorted(
        scored,
        key=lambda g: (
            str(g.get("gameDate") or g.get("label") or ""),
            safe_int(g.get("seq")) or 0,
            compact_game_key(g),
        ),
    )

    return {
        "method": "available-feature-similarity-v2",
        "description": "Ranks historical rows using available fields: opponent, home/away, lineup/context, AB/IP sample, recency, and optional historical handedness/park/weather/pitch-mix fields when present. Score is capped at 100.",
        "count": len(top),
        "totalHistoricalRows": len(scored),
        "avgValue": round(sum(vals) / len(vals), 4) if vals else None,
        "avgScore": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
        "maxScore": max(all_scores) if all_scores else None,
        "bins": dict(sorted(bins.items())),
        "featureCoverage": coverage,
        "warnings": warnings,
        "topGames": [compact_similarity_row(g) for g in top],
        "allGames": [compact_similarity_row(g) for g in scored_by_time],
    }

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
                    # For MLB batter rows, the original detail files store AB in `minutes`
                    # because the analyzer was adapted from NBA minutes. `contextValue`
                    # can be lineup/context metadata instead, so prefer minutes here.
                    "minutes": safe_float(game.get("minutes")),
                    "contextValue": safe_float(game.get("minutes")) if safe_float(game.get("minutes")) is not None else safe_float(game.get("contextValue")),
                    "rawContextValue": game.get("contextValue"),
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
                "contextValue": safe_float(game.get("contextValue")),
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

PITCHER_AVERAGE_LINE_STATS = {"K", "ER", "HA", "IP", "OUTS", "BB"}


def normal_over_probability(mean: Optional[float], sigma: Optional[float], line: Optional[float]) -> Optional[float]:
    if mean is None or line is None:
        return None
    if sigma is None or not math.isfinite(sigma) or sigma <= 0:
        return None
    z = (line - mean) / sigma
    return round(1.0 - (0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))), 6)


def comparison_line_for_prop(stat: str, player_type: Any, all_games_avg: Optional[float], recent5_avg: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """Use a pitcher average as the comparison line for pitcher prop pages.

    The user grades pitcher props against the pitcher's average, not against the
    lowest static prop line. Batter props keep the board/book line behavior.
    """
    if str(player_type or "").lower() == "pitcher":
        if all_games_avg is not None:
            return round(float(all_games_avg), 4), "full sample average"
        if recent5_avg is not None:
            return round(float(recent5_avg), 4), "recent average"
    return None, None


def normalize_stat(stat: Any) -> str:
    return str(stat or "").upper().strip()


def build_available_prop(
    stat: str,
    detail: Dict[str, Any],
    detail_filename: str,
    board_rows: List[Dict[str, Any]],
    target_date: str,
    matchup_context: Dict[str, Any],
) -> Dict[str, Any]:
    games = [g for g in (detail.get("games") or []) if isinstance(g, dict)]
    recent_values = [safe_float(g.get("value")) for g in games[-5:]]
    recent_values = [v for v in recent_values if v is not None]
    all_values = [safe_float(g.get("value")) for g in games]
    all_values = [v for v in all_values if v is not None]
    samples = detail.get("samples") if isinstance(detail.get("samples"), dict) else {}
    model_pred = safe_float(detail.get("modelPred") or detail.get("modelMu"))
    model_sigma = safe_float(detail.get("modelSigma"))
    recent5_avg = round(sum(recent_values) / len(recent_values), 4) if recent_values else None
    all_games_avg = round(sum(all_values) / len(all_values), 4) if all_values else None
    player_type = detail.get("playerType")
    if not player_type and (str(detail_filename or "").lower().startswith("pitcher_") or normalize_stat(stat) in {"HA", "IP", "OUTS"}):
        player_type = "pitcher"
    comparison_line, comparison_source = comparison_line_for_prop(stat, player_type, all_games_avg, recent5_avg)
    comparison_probability = normal_over_probability(model_pred, model_sigma, comparison_line)

    return {
        "stat": stat,
        "statDisplay": detail.get("statDisplay") or STAT_DISPLAY_FALLBACK.get(stat, stat),
        "detailFile": detail_filename,
        "sampleType": detail.get("sampleType"),
        "recentWindow": detail.get("recentWindow"),
        "playerType": player_type,
        "modelPred": model_pred,
        "modelPredDisplay": f"{model_pred:.2f}" if model_pred is not None else None,
        "modelSigma": model_sigma,
        "contextMetricLabel": detail.get("contextMetricLabel"),
        "contextMetricValue": safe_float(detail.get("contextMetricValue")),
        "samples": samples,
        "recent5Avg": recent5_avg,
        "allGamesAvg": all_games_avg,
        "comparisonLine": comparison_line,
        "comparisonLineSource": comparison_source,
        "comparisonProbability": comparison_probability,
        "comparisonMode": "pitcher_average" if comparison_line is not None else "listed_line",
        "gameCount": len(games),
        "lineOptions": prop_lines_from_rows(board_rows),
        "similarity": summarize_similar_games(detail),
        "similarityV2": summarize_similarity_v2(detail, target_date, matchup_context),
    }



def aggregate_similarity_coverage(available_props: List[Dict[str, Any]], matchup_context: Dict[str, Any]) -> Dict[str, Any]:
    cover = dict((matchup_context or {}).get("featureCoverage") or {})
    sim_coverages = [p.get("similarityV2", {}).get("featureCoverage", {}) for p in available_props if isinstance(p.get("similarityV2"), dict)]
    for key in [
        "sameOpponent", "homeAway", "lineupOrContext", "abOrIpSample", "recency",
        "currentHandednessParsed", "currentPark", "currentWeather", "currentPitchMix",
        "historicalHandedness", "historicalPitchMix", "historicalWeather", "historicalPark", "historicalStarter",
    ]:
        if key not in cover:
            cover[key] = any(bool(c.get(key)) for c in sim_coverages)
        elif key.startswith("historical"):
            cover[key] = any(bool(c.get(key)) for c in sim_coverages)
    return cover


def similarity_readiness_from_coverage(coverage: Dict[str, Any]) -> Dict[str, Any]:
    next_inputs = []
    if not coverage.get("historicalHandedness"):
        next_inputs.append("historical batter hand and pitcher hand per game-log row")
    if not coverage.get("historicalStarter"):
        next_inputs.append("current and historical opposing starter identity")
    if not coverage.get("historicalPitchMix"):
        next_inputs.append("pitch mix / pitch-type profile by opposing starter")
    if not coverage.get("historicalPark") or not coverage.get("historicalWeather"):
        next_inputs.append("park/weather values per historical row")
    return {
        "currentContextReady": any(bool(coverage.get(k)) for k in ["lineupOrder", "currentHandedness", "currentTemperature", "currentWind", "currentPark"]),
        "canScoreCurrentHandedness": bool(coverage.get("currentHandedness") or coverage.get("currentHandednessParsed")),
        "canScoreHistoricalHandedness": bool(coverage.get("historicalHandedness")),
        "canScorePitchMix": bool(coverage.get("currentPitchMix") and coverage.get("historicalPitchMix")),
        "nextRequiredInputs": next_inputs,
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
    pitcher_lineup_ctx = profile.get("pitcherLineupContext") or {}
    if player_type == "pitcher":
        if not pitcher_lineup_ctx:
            warnings.append("current opposing lineup handedness not matched yet")
        if ctx.get("temperatureF") is None:
            warnings.append("current temperature not parsed")
        if ctx.get("windMph") is None:
            warnings.append("current wind not parsed")
        coverage = profile.get("matchupFeatureSummary", {}).get("featureCoverage", {}) or {}
        if not coverage.get("historicalHandedness"):
            warnings.append("historical opposing-lineup handedness not available in pitcher start rows yet")
        if not coverage.get("historicalPitchMix"):
            warnings.append("historical pitcher pitch mix not available in start rows yet")
    else:
        if not ctx.get("handednessText"):
            warnings.append("current handedness not parsed")
        if ctx.get("temperatureF") is None:
            warnings.append("current temperature not parsed")
        if ctx.get("windMph") is None:
            warnings.append("current wind not parsed")
        coverage = profile.get("matchupFeatureSummary", {}).get("featureCoverage", {}) or {}
        if not coverage.get("historicalHandedness"):
            warnings.append("historical handedness not available yet")
        if not coverage.get("historicalPitchMix"):
            warnings.append("historical pitch mix not available yet")

    return {
        "multiPropReady": len(available_stats) >= 2,
        "coreBatterPropsReady": player_type == "batter" and {"H", "TB", "HRR"}.issubset(available_stats),
        "availableStatCount": len(available_stats),
        "warnings": warnings,
    }




def first_present(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if isinstance(row, dict) and key in row and row.get(key) not in [None, ""]:
            return row.get(key)
    return None


def normalize_hand(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if text.startswith("SW") or text in {"B", "S"}:
        return "S"
    if text.startswith("R"):
        return "R"
    if text.startswith("L"):
        return "L"
    return text[:1]


def resolve_site_json_path(data_dir: Path, value: Any) -> Optional[Path]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    p = Path(raw)
    candidates: List[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.extend([
            data_dir.parent / p,
            data_dir / p,
            data_dir / raw.replace("data/", "", 1),
        ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def bucket_label(value: Optional[float], low: float, high: float) -> str:
    if value is None or not math.isfinite(value):
        return "unknown"
    if value >= high:
        return "high"
    if value >= low:
        return "medium"
    return "low"


def mean_numeric(rows: List[Dict[str, Any]], keys: Iterable[str]) -> Optional[float]:
    vals: List[float] = []
    for row in rows:
        val = safe_float(first_present(row, keys))
        if val is not None:
            vals.append(val)
    return round(sum(vals) / len(vals), 4) if vals else None


def batter_metric(row: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    return safe_float(first_present(row, keys))


def compact_lineup_player(row: Dict[str, Any], metric_keys: Iterable[str], metric_label: str) -> Dict[str, Any]:
    metric = batter_metric(row, metric_keys)
    order = safe_int(first_present(row, ["order", "lineupOrder", "battingOrder", "projectedLineupOrder"]))
    return {
        "playerId": normalize_player_id(first_present(row, ["playerId", "PLAYER_ID", "batterId", "mlbamId"])),
        "player": str(first_present(row, ["player", "name", "PLAYER_NAME", "batter"]) or "").strip(),
        "team": str(first_present(row, ["team", "TEAM_ABBR", "teamAbbr"]) or "").strip(),
        "order": order,
        "hand": normalize_hand(first_present(row, ["batSide", "batterHand", "hand", "stand", "bats"])),
        "metric": metric,
        "metricLabel": metric_label,
    }


def top_lineup_players(rows: List[Dict[str, Any]], metric_keys: Iterable[str], metric_label: str, limit: int = 4, reverse: bool = True) -> List[Dict[str, Any]]:
    enriched = []
    for row in rows:
        metric = batter_metric(row, metric_keys)
        if metric is None:
            continue
        enriched.append((metric, row))
    enriched.sort(key=lambda x: x[0], reverse=reverse)
    return [compact_lineup_player(row, metric_keys, metric_label) for _, row in enriched[:limit]]


def lineup_count_by_hand(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"R": 0, "L": 0, "S": 0, "Unknown": 0}
    for row in rows:
        hand = normalize_hand(first_present(row, ["batSide", "batterHand", "hand", "stand", "bats"]))
        if hand in {"R", "L", "S"}:
            counts[hand] += 1
        else:
            counts["Unknown"] += 1
    return counts


def lineup_band_rows(rows: List[Dict[str, Any]], lo: int, hi: int) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        order = safe_int(first_present(row, ["order", "lineupOrder", "battingOrder", "projectedLineupOrder"]))
        if order is not None and lo <= order <= hi:
            out.append(row)
    return out


def side_advantage_counts(rows: List[Dict[str, Any]], pitcher_hand: str) -> Dict[str, int]:
    pitcher_hand = normalize_hand(pitcher_hand)
    counts = {"opposite": 0, "same": 0, "switch": 0, "unknown": 0}
    for row in rows:
        hand = normalize_hand(first_present(row, ["batSide", "batterHand", "hand", "stand", "bats"]))
        if hand == "S":
            counts["switch"] += 1
        elif hand in {"R", "L"} and pitcher_hand in {"R", "L"}:
            if hand == pitcher_hand:
                counts["same"] += 1
            else:
                counts["opposite"] += 1
        else:
            counts["unknown"] += 1
    return counts


def build_pitcher_lineup_context_for_game(game: Dict[str, Any], detail: Dict[str, Any]) -> List[Tuple[Tuple[str, str], Dict[str, Any]]]:
    batters = [b for b in (detail.get("batters") or detail.get("projectedBatters") or []) if isinstance(b, dict)]
    pitchers = [p for p in (detail.get("pitchers") or detail.get("projectedPitchers") or []) if isinstance(p, dict)]
    if not batters or not pitchers:
        return []

    away_team = str(first_present(game, ["awayTeam", "away"]) or first_present(detail, ["awayTeam", "away"]) or "").strip()
    home_team = str(first_present(game, ["homeTeam", "home"]) or first_present(detail, ["homeTeam", "home"]) or "").strip()
    game_id = str(first_present(game, ["id", "gameId", "gamePk"]) or first_present(detail, ["id", "gameId", "gamePk"]) or "").strip()
    matchup = f"{away_team} @ {home_team}".strip(" @")

    out: List[Tuple[Tuple[str, str], Dict[str, Any]]] = []
    for pitcher in pitchers:
        pitcher_id = normalize_player_id(first_present(pitcher, ["playerId", "PLAYER_ID", "pitcherId", "mlbamId"]))
        pitcher_name = str(first_present(pitcher, ["player", "name", "PLAYER_NAME", "pitcher"]) or "").strip()
        pitcher_team = str(first_present(pitcher, ["team", "TEAM_ABBR", "teamAbbr"]) or "").strip()
        pitcher_hand = normalize_hand(first_present(pitcher, ["hand", "pitcherHand", "throws", "throwHand"]))
        if not pitcher_team and pitcher.get("isHome") is not None:
            pitcher_team = home_team if int(pitcher.get("isHome")) == 1 else away_team
        opp_team = ""
        if pitcher_team and away_team and home_team:
            opp_team = home_team if pitcher_team == away_team else away_team if pitcher_team == home_team else ""
        if not opp_team:
            opp_team = str(first_present(pitcher, ["opp", "opponent", "opponentTeam"]) or "").strip()

        opp_rows = []
        for batter in batters:
            bteam = str(first_present(batter, ["team", "TEAM_ABBR", "teamAbbr"]) or "").strip()
            if opp_team and bteam == opp_team:
                opp_rows.append(batter)
            elif pitcher_team and bteam and bteam != pitcher_team and not opp_team:
                opp_rows.append(batter)
        if not opp_rows:
            continue

        ordered_rows = sorted(
            opp_rows,
            key=lambda r: safe_int(first_present(r, ["order", "lineupOrder", "battingOrder", "projectedLineupOrder"])) or 99,
        )
        top_third = lineup_band_rows(ordered_rows, 1, 3)
        middle_third = lineup_band_rows(ordered_rows, 4, 6)
        bottom_third = lineup_band_rows(ordered_rows, 7, 9)
        hand_counts = lineup_count_by_hand(ordered_rows)
        top_counts = lineup_count_by_hand(top_third)
        side_counts = side_advantage_counts(ordered_rows, pitcher_hand)
        top_side_counts = side_advantage_counts(top_third, pitcher_hand)

        avg_hit_prob = mean_numeric(ordered_rows, ["probHit", "hitProb", "probH", "probabilityHit"])
        avg_hits = mean_numeric(ordered_rows, ["predHits", "hitsPred", "modelHits"])
        avg_tb_prob = mean_numeric(ordered_rows, ["probTB2Plus", "probTB", "tbProb", "probTotalBases"])
        avg_tb = mean_numeric(ordered_rows, ["predTB", "predTotalBases", "totalBasesPred"])
        avg_hr_prob = mean_numeric(ordered_rows, ["probHR", "hrProb"])
        avg_hrr_prob = mean_numeric(ordered_rows, ["probHRR2Plus", "probHRR", "hrrProb"])
        avg_k = mean_numeric(ordered_rows, ["predK", "predStrikeouts", "strikeoutPred"])
        avg_bb = mean_numeric(ordered_rows, ["predBB", "predWalks", "walkPred", "probBB", "bbProb"])

        contact_pressure_value = avg_hit_prob if avg_hit_prob is not None else (avg_hits / 1.2 if avg_hits is not None else None)
        power_pressure_value = avg_tb_prob if avg_tb_prob is not None else (avg_tb / 2.0 if avg_tb is not None else None)
        if avg_hrr_prob is not None and power_pressure_value is not None:
            power_pressure_value = max(power_pressure_value, avg_hrr_prob)
        if avg_hr_prob is not None and power_pressure_value is not None:
            power_pressure_value = max(power_pressure_value, avg_hr_prob * 2.0)
        k_pressure_value = avg_k if avg_k is not None else None
        walk_pressure_value = avg_bb if avg_bb is not None else None

        contact_threats = top_lineup_players(ordered_rows, ["probHit", "predHits", "hitProb"], "contact", 4)
        power_threats = top_lineup_players(ordered_rows, ["probTB2Plus", "predTB", "probHRR2Plus", "probHR", "predHR"], "power", 4)
        strikeout_targets = top_lineup_players(ordered_rows, ["predK", "probK", "strikeoutPred"], "K risk", 4)
        walk_risk_bats = top_lineup_players(ordered_rows, ["predBB", "probBB", "walkPred"], "walk risk", 4)

        context = {
            "available": True,
            "gameId": game_id,
            "matchup": matchup,
            "pitcherId": pitcher_id,
            "pitcher": pitcher_name,
            "pitcherTeam": pitcher_team,
            "pitcherHand": pitcher_hand,
            "opponentTeam": opp_team,
            "lineupSize": len(ordered_rows),
            "lineupHandCounts": hand_counts,
            "topThirdHandCounts": top_counts,
            "middleThirdHandCounts": lineup_count_by_hand(middle_third),
            "bottomThirdHandCounts": lineup_count_by_hand(bottom_third),
            "sideAdvantageCounts": side_counts,
            "topThirdSideAdvantageCounts": top_side_counts,
            "lineupPressure": {
                "contact": bucket_label(contact_pressure_value, 0.55, 0.64),
                "power": bucket_label(power_pressure_value, 0.35, 0.52),
                "strikeoutOpportunity": bucket_label(k_pressure_value, 0.75, 1.05),
                "walkRisk": bucket_label(walk_pressure_value, 0.28, 0.45),
                "contactValue": contact_pressure_value,
                "powerValue": power_pressure_value,
                "strikeoutValue": k_pressure_value,
                "walkValue": walk_pressure_value,
            },
            "contactThreats": contact_threats,
            "powerThreats": power_threats,
            "strikeoutTargets": strikeout_targets,
            "walkRiskBats": walk_risk_bats,
            "summaryPieces": [
                f"{opp_team} projected lineup" if opp_team else "Opposing projected lineup",
                f"{hand_counts.get('R',0)} RHB",
                f"{hand_counts.get('L',0)} LHB",
                f"{hand_counts.get('S',0)} switch",
                f"{side_counts.get('opposite',0)} opposite-side bats" if pitcher_hand else "",
            ],
        }
        keys = []
        if pitcher_id:
            keys.append((pitcher_id, pitcher_team))
        if pitcher_name:
            keys.append((f"name:{pitcher_name.lower()}|{pitcher_team.lower()}", pitcher_team))
        for key in keys:
            out.append((key, context))
    return out


def load_pitcher_lineup_contexts(data_dir: Path, target_date: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Build a pitcher -> opposing projected lineup context from game detail files.

    Uses data/games.json detailPath entries when available. This is additive and safe:
    if detail files or batter handedness fields are missing, pitcher profiles simply
    omit pitcherLineupContext.
    """
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    games_path = data_dir / "games.json"
    game_rows: List[Dict[str, Any]] = []
    if games_path.exists():
        try:
            payload = load_json(games_path)
            if isinstance(payload, list):
                game_rows = [g for g in payload if isinstance(g, dict)]
            elif isinstance(payload, dict):
                for key in ["games", "rows", "data"]:
                    if isinstance(payload.get(key), list):
                        game_rows.extend([g for g in payload[key] if isinstance(g, dict)])
        except Exception:
            game_rows = []

    for game in game_rows:
        gdate = str(first_present(game, ["gameDate", "date", "targetDate"]) or "")[:10]
        if gdate and gdate != target_date:
            continue
        detail_path = resolve_site_json_path(data_dir, first_present(game, ["detailPath", "mlbDetailPath", "path"]))
        if not detail_path:
            continue
        try:
            detail = load_json(detail_path)
        except Exception:
            continue
        if not isinstance(detail, dict):
            continue
        for key, context in build_pitcher_lineup_context_for_game(game, detail):
            index[key] = context

    # Fallback: scan common detail folders if games.json did not expose a detailPath.
    if not index:
        candidates = []
        for pattern in [
            f"mlb_game_details/{target_date}*.json",
            f"mlb_game_details/{target_date}/*.json",
            f"derived/mlb_game_details/{target_date}*.json",
            f"derived/mlb_game_details/{target_date}/*.json",
        ]:
            candidates.extend(data_dir.glob(pattern))
        for detail_path in candidates:
            try:
                detail = load_json(detail_path)
            except Exception:
                continue
            if not isinstance(detail, dict):
                continue
            game = {
                "gameDate": target_date,
                "awayTeam": detail.get("awayTeam"),
                "homeTeam": detail.get("homeTeam"),
                "id": detail.get("id") or detail.get("gameId") or detail.get("gamePk"),
            }
            for key, context in build_pitcher_lineup_context_for_game(game, detail):
                index[key] = context

    return index


def build_profile(
    profile_key: str,
    file_key: str,
    details_by_stat: Dict[str, Dict[str, Any]],
    detail_filenames_by_stat: Dict[str, str],
    board_index: Dict[Tuple[str, str], List[Dict[str, Any]]],
    target_date: str,
    pitcher_lineup_index: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    stats_sorted = sorted(details_by_stat, key=lambda s: (STAT_SORT_ORDER.get(s, 999), s))
    primary = details_by_stat[stats_sorted[0]]
    player_id = normalize_player_id(primary.get("playerId"))
    player_name = str(primary.get("player") or "").strip()
    team = str(primary.get("team") or "").strip()
    name_key = f"name:{player_name.lower()}|{team.lower()}" if player_name else ""
    pitcher_lineup_context = None
    if str(primary.get("playerType") or "").lower() == "pitcher" and pitcher_lineup_index:
        if player_id:
            pitcher_lineup_context = pitcher_lineup_index.get((player_id, team))
        if not pitcher_lineup_context and name_key:
            pitcher_lineup_context = pitcher_lineup_index.get((name_key, team))

    context_text = primary.get("driverSummary") or primary.get("boardContext") or ""
    if not context_text:
        for stat in stats_sorted:
            context_text = details_by_stat[stat].get("driverSummary") or details_by_stat[stat].get("boardContext") or ""
            if context_text:
                break

    native_context = {}
    for stat in stats_sorted:
        native_context = native_detail_context(details_by_stat[stat])
        if native_context:
            break
    matchup_context = merge_native_context(parse_context_text(context_text), native_context)

    available_props = []
    for stat in stats_sorted:
        detail = details_by_stat[stat]
        rows: List[Dict[str, Any]] = []
        if player_id:
            rows.extend(board_index.get((player_id, stat), []))
        if name_key:
            rows.extend(board_index.get((name_key, stat), []))
        available_props.append(build_available_prop(stat, detail, detail_filenames_by_stat[stat], rows, target_date, matchup_context))

    merged_log = merge_game_logs(details_by_stat)
    chart_series = build_chart_series(details_by_stat, merged_log)
    aggregate_coverage = aggregate_similarity_coverage(available_props, matchup_context)
    aggregate_readiness = similarity_readiness_from_coverage(aggregate_coverage)
    missing_for_true_similarity = []
    if not aggregate_coverage.get("historicalHandedness"):
        missing_for_true_similarity.append("historical handedness")
    if not aggregate_coverage.get("historicalPitchMix"):
        missing_for_true_similarity.append("pitch mix")
    if not aggregate_coverage.get("historicalPark"):
        missing_for_true_similarity.append("historical park")
    if not aggregate_coverage.get("historicalWeather"):
        missing_for_true_similarity.append("historical weather")

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
        "matchupContext": matchup_context,
        "pitcherLineupContext": pitcher_lineup_context,
        "matchupFeatureSummary": {
            "currentFeatures": matchup_context.get("currentFeatures") or [],
            "summaryPieces": matchup_context.get("summaryPieces") or [],
            "featureCoverage": aggregate_coverage,
            "similarityReadiness": aggregate_readiness,
            "missingForTrueSimilarity": missing_for_true_similarity,
        },
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
    pitcher_lineup_index = load_pitcher_lineup_contexts(data_dir, target_date)

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
    current_handedness_ready = 0
    current_weather_ready = 0
    current_lineup_ready = 0
    pitcher_lineup_ready = 0

    for pkey, details_by_stat in sorted(grouped.items()):
        profile = build_profile(
            profile_key=pkey,
            file_key=grouped_file_keys.get(pkey, pkey),
            details_by_stat=details_by_stat,
            detail_filenames_by_stat=grouped_filenames[pkey],
            board_index=board_index,
            target_date=target_date,
            pitcher_lineup_index=pitcher_lineup_index,
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
        ctx_cov = ((profile.get("matchupFeatureSummary") or {}).get("featureCoverage") or {})
        if ctx_cov.get("currentHandedness"):
            current_handedness_ready += 1
        if ctx_cov.get("currentTemperature") or ctx_cov.get("currentWind"):
            current_weather_ready += 1
        if ctx_cov.get("lineupOrder"):
            current_lineup_ready += 1
        if profile.get("pitcherLineupContext"):
            pitcher_lineup_ready += 1
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
        "currentHandednessReadyProfiles": current_handedness_ready,
        "currentWeatherReadyProfiles": current_weather_ready,
        "currentLineupReadyProfiles": current_lineup_ready,
        "pitcherLineupReadyProfiles": pitcher_lineup_ready,
        "pitcherLineupContextsAvailable": len(pitcher_lineup_index),
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
        "currentHandednessReadyProfiles",
        "currentWeatherReadyProfiles",
        "currentLineupReadyProfiles",
        "pitcherLineupReadyProfiles",
        "pitcherLineupContextsAvailable",
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
