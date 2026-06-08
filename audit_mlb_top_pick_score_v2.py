"""Build a read-only MLB top-pick score_v2 comparison audit.

This script does NOT change the site, homepage cards, prop analyzer, or any
production JSON. It reads the Step 1 audit outputs and writes new comparison
files into data/audits so the current pick scoring can be compared against a
more conservative score_v2 before any live logic is replaced.

Expected workflow from the project root:

    # First run Step 1 if you have not already:
    python audit_mlb_prop_scoring.py --data-dir data --detail-date 2026-06-14 --candidate-date 2026-06-14

    # Then run this Step 2 audit:
    python audit_mlb_top_pick_score_v2.py --data-dir data

Outputs:
    data/audits/mlb_top_pick_score_v2_comparison.csv
    data/audits/mlb_top_pick_score_v2_deduped_top25.csv
    data/audits/mlb_top_pick_score_v2_category_leaders.csv
    data/audits/mlb_top_pick_score_v2_category_comparison.csv
    data/audits/mlb_top_pick_score_v2_summary.json

The formula is intentionally versioned and transparent. Treat this as a
candidate scoring model, not a replacement, until the comparison is reviewed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_TOP_PICK_STATS = {"H", "TB", "HRR", "K", "HA", "ER"}
DEFAULT_BASELINE = 0.5755
SHRINKAGE_N = 75

PROB_BUCKETS = [
    (0.00, 0.50, "<50%"),
    (0.50, 0.55, "50-55%"),
    (0.55, 0.60, "55-60%"),
    (0.60, 0.65, "60-65%"),
    (0.65, 0.70, "65-70%"),
    (0.70, 0.75, "70-75%"),
    (0.75, 0.80, "75-80%"),
    (0.80, 1.01, "80%+"),
]

STAT_LABELS = {
    "H": "Hits",
    "TB": "Total Bases",
    "HRR": "Hits + Runs + RBI",
    "K": "Pitcher Strikeouts",
    "HA": "Pitcher Hits Allowed",
    "ER": "Pitcher Earned Runs",
    "OUTS": "Pitcher Outs",
    "BB": "Walks",
    "HR": "Home Runs",
    "2B": "Doubles",
    "SB": "Stolen Bases",
    "IP": "Pitcher Innings",
}

CATEGORY_CONFIG = [
    {"category": "Best hits", "stat": "H", "role": "batter", "preferred_line": 0.5},
    {"category": "Best hits + runs + RBI", "stat": "HRR", "role": "batter", "preferred_line": 1.5},
    {"category": "Best two-plus total bases", "stat": "TB", "role": "batter", "preferred_line": 1.5},
    {"category": "Top pitcher strikeouts", "stat": "K", "role": "pitcher", "preferred_line": None},
    {"category": "Top pitcher hits allowed", "stat": "HA", "role": "pitcher", "preferred_line": None},
    {"category": "Starter ER candidates", "stat": "ER", "role": "pitcher", "preferred_line": None},
]


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(val) or math.isinf(val):
        return default
    return val


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def pct(value: Any) -> float | None:
    val = safe_float(value)
    if val is None:
        return None
    if 1.0 < val <= 100.0:
        return val / 100.0
    return val


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def prob_bucket(prob: float | None) -> str:
    if prob is None:
        return "missing"
    for lo, hi, label in PROB_BUCKETS:
        if lo <= prob < hi:
            return label
    return "80%+" if prob >= 0.80 else "<50%"


def shrink_rate(rate: float | None, sample: int | None, baseline: float = DEFAULT_BASELINE, shrink_n: int = SHRINKAGE_N) -> float:
    if rate is None or not sample:
        return baseline
    sample = max(int(sample), 0)
    return ((rate * sample) + (baseline * shrink_n)) / (sample + shrink_n)


def score_rate(rate: float) -> float:
    """Map historical rate to a 0-1 score around the baseline.

    50% is weak, 58% is roughly neutral-to-good, 68% is excellent.
    """
    return clamp((rate - 0.48) / 0.22)


def build_history_maps(summary: dict[str, Any], bucket_rows: list[dict[str, Any]]) -> dict[str, Any]:
    history = summary.get("results_history_audit") or {}
    overall = history.get("overall") or {}
    baseline = safe_float(overall.get("win_rate_ex_push"), DEFAULT_BASELINE) or DEFAULT_BASELINE

    stat_rates: dict[str, dict[str, Any]] = {}
    for stat, row in (history.get("by_stat") or {}).items():
        rate = safe_float(row.get("win_rate_ex_push"))
        sample = int(safe_float(row.get("graded_no_push") or row.get("sample"), 0) or 0)
        stat_rates[str(stat).upper()] = {
            "raw_rate": rate,
            "sample": sample,
            "shrunk_rate": shrink_rate(rate, sample, baseline),
        }

    prob_rates: dict[str, dict[str, Any]] = {}
    for row in history.get("probability_bucket_calibration") or []:
        bucket = safe_str(row.get("bucket"))
        rate = safe_float(row.get("win_rate_ex_push"))
        sample = int(safe_float(row.get("graded_no_push") or row.get("sample"), 0) or 0)
        prob_rates[bucket] = {
            "raw_rate": rate,
            "sample": sample,
            "shrunk_rate": shrink_rate(rate, sample, baseline),
        }

    stat_prob_rates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in bucket_rows:
        if safe_str(row.get("group")) != "stat_x_prob_bucket":
            continue
        bucket = safe_str(row.get("bucket"))
        if "|" not in bucket:
            continue
        stat, pb = bucket.split("|", 1)
        rate = safe_float(row.get("win_rate_ex_push"))
        sample = int(safe_float(row.get("graded_no_push") or row.get("sample"), 0) or 0)
        stat_prob_rates[(stat.upper(), pb)] = {
            "raw_rate": rate,
            "sample": sample,
            "shrunk_rate": shrink_rate(rate, sample, baseline),
        }

    return {
        "baseline": baseline,
        "stat_rates": stat_rates,
        "prob_rates": prob_rates,
        "stat_prob_rates": stat_prob_rates,
    }


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["stat"] = safe_str(out.get("stat")).upper()
    out["playerType"] = safe_str(out.get("playerType") or out.get("role")).lower()
    out["prob_cons"] = pct(out.get("prob_cons"))
    out["line"] = safe_float(out.get("line"))
    out["pred_anchor"] = safe_float(out.get("pred_anchor"))
    out["avg_anchor"] = safe_float(out.get("avg_anchor"))
    out["hit_score"] = safe_float(out.get("hit_score"))
    out["sim_avg"] = safe_float(out.get("sim_avg"))
    out["current_score"] = safe_float(out.get("current_score"), 0.0) or 0.0
    out["gap"] = safe_float(out.get("gap"))
    if out["gap"] is None and out["pred_anchor"] is not None and out["line"] is not None:
        out["gap"] = out["pred_anchor"] - out["line"]
    return out


def is_tbd(row: dict[str, Any]) -> bool:
    player = safe_str(row.get("player")).lower()
    warnings = safe_str(row.get("warnings")).lower()
    return any(token in player for token in ["tbd", "probable starter", "to be determined"]) or "tbd" in warnings


def is_missing_probability(row: dict[str, Any]) -> bool:
    return row.get("prob_cons") is None or "missing probability" in safe_str(row.get("warnings")).lower()


def is_supported_home_pick_role(row: dict[str, Any]) -> bool:
    stat = row.get("stat")
    role = row.get("playerType")
    if stat in {"H", "TB", "HRR"}:
        return role == "batter"
    if stat in {"K", "HA", "ER"}:
        return role == "pitcher"
    return False


def approx_line_quality(row: dict[str, Any]) -> float:
    """Heuristic line/playability score.

    This does not say a line is good or bad betting value. It only marks whether
    the candidate resembles the lines the current homepage categories are meant
    to surface.
    """
    stat = row.get("stat")
    line = row.get("line")
    if line is None:
        return 0.45
    if stat == "H":
        return 1.0 if abs(line - 0.5) < 1e-9 else 0.62
    if stat == "TB":
        if abs(line - 1.5) < 1e-9:
            return 0.72
        if abs(line - 0.5) < 1e-9:
            return 0.58
        return 0.50
    if stat == "HRR":
        if abs(line - 1.5) < 1e-9:
            return 0.74
        if abs(line - 0.5) < 1e-9:
            return 0.64
        return 0.50
    if stat == "K":
        if line >= 6.5:
            return 0.78
        if line >= 4.5:
            return 0.86
        if line >= 2.5:
            return 0.76
        return 0.55
    if stat == "HA":
        return 0.80 if line >= 3.5 else 0.65
    if stat == "ER":
        return 0.70 if line >= 1.5 else 0.50
    return 0.45


def model_edge_score(row: dict[str, Any]) -> float:
    gap = safe_float(row.get("gap"))
    pred = row.get("pred_anchor")
    line = row.get("line")
    if gap is None or pred is None or line is None:
        return 0.35
    denom = max(1.0, abs(line))
    # The current candidate rows are mostly over-style candidates, so positive
    # gap is favorable. Negative gap gets a low but nonzero score.
    return clamp((gap / denom) / 1.6 + 0.15)


def recent_support_score(row: dict[str, Any]) -> float:
    hit = row.get("hit_score")
    if hit is not None:
        return clamp(hit)
    avg = row.get("avg_anchor")
    line = row.get("line")
    if avg is not None and line is not None:
        return clamp((avg - line) / max(1.0, abs(line)) / 1.5 + 0.45)
    return 0.50


def similarity_support_score(row: dict[str, Any]) -> float:
    sim = row.get("sim_avg")
    line = row.get("line")
    if sim is None or line is None:
        return 0.50
    return clamp((sim - line) / max(1.0, abs(line)) / 1.5 + 0.45)


def data_quality_penalties(row: dict[str, Any], stat_known: bool) -> tuple[float, list[str]]:
    penalties = 0.0
    warnings: list[str] = []
    stat = row.get("stat")
    role = row.get("playerType")

    if is_tbd(row):
        penalties += 100.0
        warnings.append("EXCLUDE: TBD player/starter")
    if is_missing_probability(row):
        penalties += 22.0
        warnings.append("Missing model probability")
    if stat not in SUPPORTED_TOP_PICK_STATS or not is_supported_home_pick_role(row):
        penalties += 18.0
        warnings.append("Not currently a homepage top-pick category/role")
    if not stat_known:
        penalties += 8.0
        warnings.append("No historical stat bucket yet")
    if role == "batter" and row.get("hit_score") is None:
        penalties += 4.0
        warnings.append("Missing recent hit-score support")
    if stat == "TB":
        penalties += 8.0
        warnings.append("TB has weak historical bucket; require stronger matchup support")
    if stat == "HRR":
        penalties += 4.0
        warnings.append("HRR is near break-even historically; require stricter support")
    if row.get("line") is None:
        penalties += 6.0
        warnings.append("Missing line")
    return penalties, warnings


def build_driver_notes(row: dict[str, Any], components: dict[str, Any]) -> str:
    notes = []
    prob = row.get("prob_cons")
    pred = row.get("pred_anchor")
    line = row.get("line")
    gap = row.get("gap")
    stat = row.get("stat")
    if prob is not None:
        notes.append(f"Model prob {prob:.1%}; calibrated bucket {components['prob_bucket']}={components['prob_bucket_rate']:.1%}")
    if pred is not None and line is not None:
        notes.append(f"Model {pred:.2f} vs line {line:g} ({gap:+.2f})")
    if components.get("stat_rate") is not None:
        notes.append(f"{stat} history {components['stat_rate']:.1%}")
    if row.get("hit_score") is not None:
        notes.append(f"recent hit score {row['hit_score']:.2f}")
    if row.get("sim_avg") is not None and line is not None:
        notes.append(f"similar avg {row['sim_avg']:.2f}")
    if safe_str(row.get("driver_summary")):
        notes.append(safe_str(row.get("driver_summary")))
    return " | ".join(notes[:6])


def score_v2(row: dict[str, Any], history_maps: dict[str, Any]) -> dict[str, Any]:
    stat = row.get("stat")
    prob = row.get("prob_cons")
    pb = prob_bucket(prob)

    stat_info = history_maps["stat_rates"].get(stat, {})
    prob_info = history_maps["prob_rates"].get(pb, {})
    stat_prob_info = history_maps["stat_prob_rates"].get((stat, pb), {})

    stat_known = bool(stat_info)
    stat_rate = safe_float(stat_info.get("shrunk_rate"), history_maps["baseline"]) or history_maps["baseline"]
    prob_bucket_rate = safe_float(prob_info.get("shrunk_rate"), history_maps["baseline"]) or history_maps["baseline"]
    stat_prob_rate = safe_float(stat_prob_info.get("shrunk_rate"))

    # If the combined stat+prob bucket has enough support, use it lightly.
    stat_prob_sample = int(safe_float(stat_prob_info.get("sample"), 0) or 0)
    if stat_prob_rate is not None and stat_prob_sample >= 20:
        calibrated_rate = (prob_bucket_rate * 0.60) + (stat_prob_rate * 0.40)
    else:
        calibrated_rate = prob_bucket_rate

    model_prob_component = score_rate((prob or history_maps["baseline"]) * 0.35 + calibrated_rate * 0.65)
    stat_component = score_rate(stat_rate)
    edge_component = model_edge_score(row)
    recent_component = recent_support_score(row)
    sim_component = similarity_support_score(row)
    line_component = approx_line_quality(row)

    penalties, warnings = data_quality_penalties(row, stat_known=stat_known)

    # Conservative v2 weighting: rely less on raw probability and more on
    # historical category strength + line/model support.
    raw_0_100 = (
        model_prob_component * 24.0
        + stat_component * 22.0
        + edge_component * 18.0
        + recent_component * 14.0
        + sim_component * 8.0
        + line_component * 8.0
        + 6.0
    )
    final_score = max(0.0, raw_0_100 - penalties)

    components = {
        "prob_bucket": pb,
        "prob_bucket_rate": prob_bucket_rate,
        "stat_rate": stat_rate,
        "stat_prob_bucket_rate": stat_prob_rate,
        "stat_prob_bucket_sample": stat_prob_sample,
        "model_prob_component": model_prob_component,
        "stat_component": stat_component,
        "edge_component": edge_component,
        "recent_component": recent_component,
        "similarity_component": sim_component,
        "line_quality_component": line_component,
        "penalty_points": penalties,
    }
    return {
        **components,
        "score_v2": round(final_score, 3),
        "score_v2_raw_before_penalty": round(raw_0_100, 3),
        "score_v2_warnings": "; ".join(warnings),
        "score_v2_drivers": build_driver_notes(row, components),
    }


def player_key(row: dict[str, Any]) -> str:
    pid = safe_str(row.get("playerId"))
    if pid:
        return pid
    return safe_str(row.get("player")).lower()


def category_for_row(row: dict[str, Any]) -> str:
    stat = row.get("stat")
    line = row.get("line")
    role = row.get("playerType")
    for cfg in CATEGORY_CONFIG:
        if cfg["stat"] != stat:
            continue
        if cfg.get("role") and cfg["role"] != role:
            continue
        preferred = cfg.get("preferred_line")
        if preferred is None or line is None or abs(float(line) - float(preferred)) < 1e-9:
            return cfg["category"]
    return f"Other {STAT_LABELS.get(stat, stat)}"


def add_ranks(rows: list[dict[str, Any]]) -> None:
    rows.sort(key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["score_v2_rank_all"] = idx

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[category_for_row(row)].append(row)
    for cat_rows in by_category.values():
        cat_rows.sort(key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)
        for idx, row in enumerate(cat_rows, start=1):
            row["score_v2_rank_category"] = idx

    current_sorted = sorted(rows, key=lambda r: safe_float(r.get("current_score"), 0.0) or 0.0, reverse=True)
    for idx, row in enumerate(current_sorted, start=1):
        row["current_score_rank_all"] = idx


def build_deduped_top(
    rows: list[dict[str, Any]],
    limit: int = 25,
    max_per_player: int = 1,
    max_per_team: int = 4,
    max_per_category: int = 6,
) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)
    player_counts: Counter[str] = Counter()
    team_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    selected = []
    for row in sorted_rows:
        if safe_float(row.get("score_v2"), 0) <= 0:
            continue
        category = category_for_row(row)
        if category.startswith("Other"):
            continue
        if "EXCLUDE" in safe_str(row.get("score_v2_warnings")):
            continue
        key = player_key(row)
        team = safe_str(row.get("team"))
        if key and player_counts[key] >= max_per_player:
            continue
        if team and team_counts[team] >= max_per_team:
            continue
        if category and category_counts[category] >= max_per_category:
            continue
        out = dict(row)
        out["score_v2_deduped_rank"] = len(selected) + 1
        selected.append(out)
        if key:
            player_counts[key] += 1
        if team:
            team_counts[team] += 1
        if category:
            category_counts[category] += 1
        if len(selected) >= limit:
            break
    return selected


def build_category_leaders(rows: list[dict[str, Any]], per_category: int = 12) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cat = category_for_row(row)
        if not cat.startswith("Other"):
            groups[cat].append(row)

    leaders = []
    for cat in [cfg["category"] for cfg in CATEGORY_CONFIG]:
        cat_rows = sorted(groups.get(cat, []), key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)
        seen_players = set()
        rank = 0
        for row in cat_rows:
            if "EXCLUDE" in safe_str(row.get("score_v2_warnings")):
                continue
            key = player_key(row)
            if key in seen_players:
                continue
            seen_players.add(key)
            rank += 1
            out = dict(row)
            out["category"] = cat
            out["score_v2_category_leader_rank"] = rank
            leaders.append(out)
            if rank >= per_category:
                break
    return leaders


def compare_current_category_replay(current_replay: list[dict[str, Any]], category_leaders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_by_cat_rank = {}
    for row in current_replay:
        cat = safe_str(row.get("category"))
        rank = int(safe_float(row.get("rank"), 0) or 0)
        if rank:
            current_by_cat_rank[(cat, rank)] = row

    v2_by_cat_rank = {}
    for row in category_leaders:
        cat = safe_str(row.get("category"))
        rank = int(safe_float(row.get("score_v2_category_leader_rank"), 0) or 0)
        if rank:
            v2_by_cat_rank[(cat, rank)] = row

    rows = []
    for cat in [cfg["category"] for cfg in CATEGORY_CONFIG]:
        max_rank = max(
            [0]
            + [r for c, r in current_by_cat_rank if c == cat]
            + [r for c, r in v2_by_cat_rank if c == cat]
        )
        for rank in range(1, min(max_rank, 12) + 1):
            cur = current_by_cat_rank.get((cat, rank), {})
            v2 = v2_by_cat_rank.get((cat, rank), {})
            rows.append({
                "category": cat,
                "rank": rank,
                "current_player": cur.get("player"),
                "current_team": cur.get("team"),
                "current_opp": cur.get("opp"),
                "current_stat": cur.get("stat"),
                "current_line": cur.get("line"),
                "current_score": cur.get("current_score"),
                "current_prob": cur.get("prob_cons"),
                "current_driver_summary": cur.get("driver_summary"),
                "score_v2_player": v2.get("player"),
                "score_v2_team": v2.get("team"),
                "score_v2_opp": v2.get("opp"),
                "score_v2_stat": v2.get("stat"),
                "score_v2_line": v2.get("line"),
                "score_v2": v2.get("score_v2"),
                "score_v2_prob": v2.get("prob_cons"),
                "score_v2_drivers": v2.get("score_v2_drivers"),
                "score_v2_warnings": v2.get("score_v2_warnings"),
                "same_pick": (
                    safe_str(cur.get("playerId") or cur.get("player"))
                    == safe_str(v2.get("playerId") or v2.get("player"))
                    and safe_str(cur.get("stat")) == safe_str(v2.get("stat"))
                    and safe_str(cur.get("line")) == safe_str(v2.get("line"))
                ) if cur and v2 else False,
            })
    return rows


def summarize_outputs(rows: list[dict[str, Any]], deduped: list[dict[str, Any]], category_leaders: list[dict[str, Any]], history_maps: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    warning_counts = Counter()
    stat_counts = Counter()
    for row in rows:
        stat_counts[row.get("stat")] += 1
        for warning in safe_str(row.get("score_v2_warnings")).split("; "):
            if warning:
                warning_counts[warning] += 1

    top_by_stat = {}
    for stat in sorted({r.get("stat") for r in rows}):
        stat_rows = [r for r in rows if r.get("stat") == stat]
        stat_rows.sort(key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)
        top_by_stat[stat] = stat_rows[:5]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "formula_version": "score_v2_audit_2026_06_08",
        "formula_intent": "Conservative comparison score only. Does not replace current site scoring.",
        "baseline_history_win_rate_ex_push": round(history_maps["baseline"], 4),
        "component_weights": {
            "calibrated_probability_bucket": 24,
            "historical_stat_strength": 22,
            "model_edge_vs_line": 18,
            "recent_hit_or_average_support": 14,
            "similar_game_support": 8,
            "line_quality": 8,
            "base_points": 6,
            "risk_penalties": "TBD/missing/unsupported/TB/HRR/data-quality penalties subtracted after raw score",
        },
        "rows_scored": len(rows),
        "stats_on_board": dict(sorted(stat_counts.items())),
        "warning_counts": dict(warning_counts),
        "top_25_deduped": deduped[:25],
        "category_leader_count": len(category_leaders),
        "top_by_supported_stat": {k: v for k, v in top_by_stat.items() if k in SUPPORTED_TOP_PICK_STATS},
        "notes": [
            "TBD/probable-starter rows are effectively excluded through a 100-point penalty.",
            "TB and HRR receive conservative penalties because Step 1 history showed weaker historical hit rates than H, HA, and K.",
            "The score uses probability-bucket calibration because raw 80%+ model probabilities did not hit at 80% in the Step 1 history.",
            "This output is meant for review. The homepage/top-picks builder should not be changed until the score_v2 comparison looks reasonable over several slates.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create score_v2 audit comparison for MLB top-pick candidates.")
    parser.add_argument("--data-dir", default="data", help="Site data directory. Default: data")
    parser.add_argument("--audits-dir", default=None, help="Audit output/input directory. Default: <data-dir>/audits")
    parser.add_argument("--candidate-csv", default=None, help="Optional candidate CSV. Default: data/audits/mlb_current_home_pick_candidate_score_audit.csv")
    parser.add_argument("--all-candidates-csv", default=None, help="Optional all-candidate CSV. Used only if home-pick candidate CSV is missing.")
    parser.add_argument("--summary-json", default=None, help="Optional Step 1 summary JSON path.")
    parser.add_argument("--bucket-csv", default=None, help="Optional Step 1 bucket CSV path.")
    parser.add_argument("--limit", type=int, default=25, help="Rows in deduped top output. Default: 25")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    audits_dir = Path(args.audits_dir) if args.audits_dir else data_dir / "audits"
    candidate_path = Path(args.candidate_csv) if args.candidate_csv else audits_dir / "mlb_current_home_pick_candidate_score_audit.csv"
    all_candidate_path = Path(args.all_candidates_csv) if args.all_candidates_csv else audits_dir / "mlb_current_candidate_score_audit.csv"
    summary_path = Path(args.summary_json) if args.summary_json else audits_dir / "mlb_prop_scoring_audit_summary.json"
    bucket_path = Path(args.bucket_csv) if args.bucket_csv else audits_dir / "mlb_prop_results_bucket_audit.csv"
    current_replay_path = audits_dir / "mlb_current_home_pick_category_replay.csv"

    raw_rows = read_csv(candidate_path)
    candidate_source = str(candidate_path)
    if not raw_rows:
        raw_rows = read_csv(all_candidate_path)
        candidate_source = str(all_candidate_path)

    summary = load_json(summary_path, {})
    bucket_rows = read_csv(bucket_path)
    current_replay = read_csv(current_replay_path)
    history_maps = build_history_maps(summary, bucket_rows)

    normalized = [normalize_row(r) for r in raw_rows]
    scored: list[dict[str, Any]] = []
    for row in normalized:
        sv2 = score_v2(row, history_maps)
        category = category_for_row(row)
        scored.append({
            "gameDate": row.get("gameDate"),
            "player": row.get("player"),
            "playerId": row.get("playerId"),
            "playerType": row.get("playerType"),
            "team": row.get("team"),
            "opp": row.get("opp"),
            "matchup": row.get("matchup"),
            "category": category,
            "stat": row.get("stat"),
            "stat_display": row.get("stat_display") or STAT_LABELS.get(row.get("stat"), row.get("stat")),
            "line": row.get("line"),
            "prob_cons": row.get("prob_cons"),
            "pred_anchor": row.get("pred_anchor"),
            "avg_anchor": row.get("avg_anchor"),
            "hit_score": row.get("hit_score"),
            "sim_avg": row.get("sim_avg"),
            "gap": row.get("gap"),
            "current_score": row.get("current_score"),
            "driver_summary": row.get("driver_summary"),
            "current_warnings": row.get("warnings"),
            "href": row.get("href"),
            **sv2,
        })

    add_ranks(scored)
    scored.sort(key=lambda r: safe_float(r.get("score_v2"), 0.0) or 0.0, reverse=True)

    deduped = build_deduped_top(scored, limit=args.limit)
    category_leaders = build_category_leaders(scored)
    category_comparison = compare_current_category_replay(current_replay, category_leaders)

    common_fields = [
        "score_v2_rank_all", "current_score_rank_all", "score_v2_rank_category", "category",
        "gameDate", "player", "playerId", "playerType", "team", "opp", "matchup",
        "stat", "stat_display", "line", "prob_cons", "pred_anchor", "avg_anchor", "hit_score", "sim_avg", "gap",
        "current_score", "score_v2", "score_v2_raw_before_penalty", "penalty_points",
        "prob_bucket", "prob_bucket_rate", "stat_rate", "stat_prob_bucket_rate", "stat_prob_bucket_sample",
        "model_prob_component", "stat_component", "edge_component", "recent_component", "similarity_component", "line_quality_component",
        "score_v2_drivers", "score_v2_warnings", "current_warnings", "driver_summary", "href",
    ]

    write_csv(audits_dir / "mlb_top_pick_score_v2_comparison.csv", scored, common_fields)
    write_csv(audits_dir / "mlb_top_pick_score_v2_deduped_top25.csv", deduped, ["score_v2_deduped_rank"] + common_fields)
    write_csv(audits_dir / "mlb_top_pick_score_v2_category_leaders.csv", category_leaders, ["score_v2_category_leader_rank"] + common_fields)
    write_csv(audits_dir / "mlb_top_pick_score_v2_category_comparison.csv", category_comparison)

    inputs = {
        "data_dir": str(data_dir),
        "audits_dir": str(audits_dir),
        "candidate_source": candidate_source,
        "summary_json": str(summary_path),
        "bucket_csv": str(bucket_path),
        "current_replay_csv": str(current_replay_path),
        "candidate_rows_loaded": len(raw_rows),
    }
    write_json(audits_dir / "mlb_top_pick_score_v2_summary.json", summarize_outputs(scored, deduped, category_leaders, history_maps, inputs))

    print(f"[OK] Wrote {audits_dir / 'mlb_top_pick_score_v2_comparison.csv'}")
    print(f"[OK] Wrote {audits_dir / 'mlb_top_pick_score_v2_deduped_top25.csv'}")
    print(f"[OK] Wrote {audits_dir / 'mlb_top_pick_score_v2_category_leaders.csv'}")
    print(f"[OK] Wrote {audits_dir / 'mlb_top_pick_score_v2_category_comparison.csv'}")
    print(f"[OK] Wrote {audits_dir / 'mlb_top_pick_score_v2_summary.json'}")


if __name__ == "__main__":
    main()
