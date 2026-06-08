"""Audit MLB prop top-pick scoring and prop-analyzer similarity details.

This is intentionally read-only. It does not change the site output. It creates
CSV/JSON files that make the current scoring/similarity behavior easier to
verify before changing the frontend or pick logic.

Typical use from the project root:
    python audit_mlb_prop_scoring.py --data-dir data --detail-date 2026-06-14

Useful outputs:
    data/audits/mlb_prop_scoring_audit_summary.json
    data/audits/mlb_prop_results_bucket_audit.csv
    data/audits/mlb_current_candidate_score_audit.csv
    data/audits/mlb_similarity_detail_audit.csv
    data/audits/mlb_similarity_score_distribution.csv
    data/audits/mlb_player_profile_readiness.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(val) or math.isinf(val):
        return default
    return val


def pct(value: Any) -> float | None:
    val = safe_float(value)
    if val is None:
        return None
    if val > 1.0 and val <= 100.0:
        return val / 100.0
    return val


def safe_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def safe_date(value: Any) -> str:
    text = safe_str(value)
    return text[:10] if len(text) >= 10 else text


def bucket_number(value: float | None, buckets: list[tuple[float, float, str]], missing: str = "missing") -> str:
    if value is None:
        return missing
    for lo, hi, label in buckets:
        if value >= lo and value < hi:
            return label
    return buckets[-1][2] if buckets else str(value)


def result_counts(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(safe_str(r.get("result")) or "Unknown" for r in rows)
    wins = counts.get("Win", 0)
    losses = counts.get("Loss", 0)
    pushes = counts.get("Push", 0)
    pending = counts.get("Pending", 0)
    graded = wins + losses
    total_graded = wins + losses + pushes
    return {
        "sample": wins + losses + pushes + pending,
        "graded_no_push": graded,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "win_rate_ex_push": round(wins / graded, 4) if graded else None,
        "win_rate_with_push": round(wins / total_graded, 4) if total_graded else None,
    }


def summarize_group(rows: list[dict[str, Any]], group_key: str, min_sample: int = 1) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[safe_str(row.get(group_key)) or "missing"].append(row)
    out = []
    for key, vals in groups.items():
        counts = result_counts(vals)
        if counts["sample"] < min_sample:
            continue
        probs = [pct(v.get("probability")) for v in vals]
        probs = [p for p in probs if p is not None]
        edges = [safe_float(v.get("model_edge_abs")) for v in vals]
        edges = [e for e in edges if e is not None]
        out.append({
            "group": group_key,
            "bucket": key,
            **counts,
            "avg_probability": round(mean(probs), 4) if probs else None,
            "avg_model_edge_abs": round(mean(edges), 4) if edges else None,
        })
    out.sort(key=lambda r: (r["group"], -(r.get("sample") or 0), str(r.get("bucket"))))
    return out


def infer_side(row: dict[str, Any]) -> str:
    model = safe_float(row.get("model"))
    line = safe_float(row.get("line"))
    board = safe_str(row.get("board")).lower()
    if "lowest" in board or "low er" in board:
        return "under"
    if model is not None and line is not None:
        if model > line:
            return "over"
        if model < line:
            return "under"
    return "unknown"


def enrich_history_rows(history_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prob_buckets = [
        (0.00, 0.50, "<50%"),
        (0.50, 0.55, "50-55%"),
        (0.55, 0.60, "55-60%"),
        (0.60, 0.65, "60-65%"),
        (0.65, 0.70, "65-70%"),
        (0.70, 0.75, "70-75%"),
        (0.75, 0.80, "75-80%"),
        (0.80, 1.01, "80%+"),
    ]
    edge_buckets = [
        (0.00, 0.10, "0.00-0.10"),
        (0.10, 0.25, "0.10-0.25"),
        (0.25, 0.50, "0.25-0.50"),
        (0.50, 0.75, "0.50-0.75"),
        (0.75, 1.00, "0.75-1.00"),
        (1.00, 999.0, "1.00+"),
    ]
    model_buckets = [
        (-999.0, 1.0, "<1"),
        (1.0, 2.0, "1-2"),
        (2.0, 3.0, "2-3"),
        (3.0, 4.0, "3-4"),
        (4.0, 5.0, "4-5"),
        (5.0, 999.0, "5+"),
    ]
    out = []
    for row in history_rows:
        r = dict(row)
        model = safe_float(r.get("model"))
        line = safe_float(r.get("line"))
        prob = pct(r.get("probability"))
        side = infer_side(r)
        raw_edge = None if model is None or line is None else model - line
        side_edge = None
        if raw_edge is not None:
            side_edge = abs(raw_edge)
            if side == "under":
                side_edge = abs(raw_edge)
        r["date"] = safe_date(r.get("date"))
        r["role"] = safe_str(r.get("role") or r.get("playerType")) or "missing"
        r["stat"] = safe_str(r.get("stat")).upper() or "missing"
        r["board"] = safe_str(r.get("board")) or "missing"
        r["side"] = side
        r["probability_norm"] = prob
        r["prob_bucket"] = bucket_number(prob, prob_buckets)
        r["model_edge_raw"] = raw_edge
        r["model_edge_abs"] = side_edge
        r["edge_bucket"] = bucket_number(side_edge, edge_buckets)
        r["model_bucket"] = bucket_number(model, model_buckets)
        out.append(r)
    return out


def current_row_score(row: dict[str, Any], prefer_model_gap: bool = False) -> float:
    # Mirrors build_home_top_picks_json.py row_score as of the uploaded site.
    prob = pct(row.get("prob_cons")) or 0.0
    pred = safe_float(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"), 0.0) or 0.0
    avg = safe_float(row.get("avg_anchor"), 0.0) or 0.0
    line = safe_float(row.get("line"), 0.0) or 0.0
    hit_score = safe_float(row.get("hit_score"), 0.0) or 0.0
    gap = pred - max(line, 0.0)
    avg_gap = pred - avg
    if prefer_model_gap:
        return avg_gap * 1.25 + pred * 0.15 + prob * 0.20
    return prob * 0.60 + hit_score * 0.15 + max(gap, -2.0) * 0.10 + max(pred, 0.0) * 0.02


def current_score_component_row(row: dict[str, Any]) -> dict[str, Any]:
    prob = pct(row.get("prob_cons")) or 0.0
    pred = safe_float(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"), 0.0) or 0.0
    avg = safe_float(row.get("avg_anchor"), 0.0) or 0.0
    line = safe_float(row.get("line"), 0.0) or 0.0
    hit_score = safe_float(row.get("hit_score"), 0.0) or 0.0
    gap = pred - max(line, 0.0)
    score = current_row_score(row)
    warnings: list[str] = []
    player = safe_str(row.get("player"))
    if "probable starter tbd" in player.lower() or " tbd" in player.lower():
        warnings.append("TBD player/starter")
    if row.get("line") is None:
        warnings.append("missing line")
    if pct(row.get("prob_cons")) is None:
        warnings.append("missing probability")
    if safe_float(row.get("hit_score")) is None and safe_str(row.get("playerType")) == "batter":
        warnings.append("missing hit_score")
    if safe_str(row.get("injuryStatus")):
        warnings.append(f"injury={row.get('injuryStatus')}")
    return {
        "current_score": round(score, 6),
        "prob_component": round(prob * 0.60, 6),
        "hit_component": round(hit_score * 0.15, 6),
        "gap_component": round(max(gap, -2.0) * 0.10, 6),
        "pred_component": round(max(pred, 0.0) * 0.02, 6),
        "probability": prob,
        "pred": pred,
        "avg": avg,
        "line": row.get("line"),
        "gap": gap,
        "hit_score": hit_score,
        "warnings": "; ".join(warnings),
    }



def is_tbd_player(row: dict[str, Any]) -> bool:
    player = safe_str(row.get("player")).lower()
    return any(token in player for token in ("tbd", "to be determined", "probable starter"))


def pitcher_projected_ip(row: dict[str, Any]) -> float | None:
    for key in ("expMin", "contextMetricValue", "projectedIP", "predictedIP", "ip", "IP"):
        value = safe_float(row.get(key))
        if value is not None:
            return value
    for key in ("summary", "driver_summary", "boardDriver"):
        text = safe_str(row.get(key))
        match = re.search(r"projected\s+([0-9]+(?:\.[0-9]+)?)\s*IP", text, flags=re.IGNORECASE)
        if match:
            return safe_float(match.group(1))
    return None


def is_probable_starting_pitcher(row: dict[str, Any], min_ip: float = 3.0) -> bool:
    if safe_str(row.get("playerType") or row.get("role")).lower() != "pitcher":
        return False
    projected_ip = pitcher_projected_ip(row)
    if projected_ip is not None and projected_ip < min_ip:
        return False
    text = " ".join(safe_str(row.get(k)) for k in ("summary", "driver_summary", "boardDriver", "reason_flags")).lower()
    if any(token in text for token in ("relief", "opener", "bulk", "bullpen")) and (projected_ip is None or projected_ip < 4.0):
        return False
    return True


def line_matches(row: dict[str, Any], wanted: float | None) -> bool:
    if wanted is None:
        return True
    line = safe_float(row.get("line"))
    return line is not None and abs(line - wanted) < 1e-9


def category_replay_rows(entries: list[dict[str, Any]], target_date: str) -> list[dict[str, Any]]:
    categories = [
        {"category": "Best hits", "stat": "H", "role": "batter", "line": 0.5, "prefer_model_gap": False},
        {"category": "Best hits + runs + RBI", "stat": "HRR", "role": "batter", "line": 1.5, "prefer_model_gap": False},
        {"category": "Best two-plus total bases", "stat": "TB", "role": "batter", "line": 1.5, "prefer_model_gap": False},
        {"category": "Top pitcher strikeouts", "stat": "K", "role": "pitcher", "line": None, "prefer_model_gap": True},
        {"category": "Top pitcher hits allowed", "stat": "HA", "role": "pitcher", "line": None, "prefer_model_gap": False},
        {"category": "Starter ER candidates", "stat": "ER", "role": "pitcher", "line": None, "prefer_model_gap": False},
    ]
    replay: list[dict[str, Any]] = []
    for cat in categories:
        rows = []
        for e in entries:
            if safe_date(e.get("gameDate")) != target_date:
                continue
            if safe_str(e.get("stat")).upper() != cat["stat"]:
                continue
            if cat["role"] and safe_str(e.get("playerType") or e.get("role")).lower() != cat["role"]:
                continue
            if not line_matches(e, cat["line"]):
                continue
            if is_tbd_player(e):
                continue
            status = safe_str(e.get("injuryStatus") or e.get("status")).lower()
            if status in {"out", "doubtful", "o", "d"}:
                continue
            if cat["stat"] == "ER" and not is_probable_starting_pitcher(e):
                continue
            rows.append(e)
        rows.sort(key=lambda r: current_row_score(r, prefer_model_gap=bool(cat["prefer_model_gap"])), reverse=True)
        seen = set()
        rank = 0
        for e in rows:
            key = safe_str(e.get("playerId") or e.get("player")).lower()
            if key in seen:
                continue
            seen.add(key)
            rank += 1
            comp = current_score_component_row(e)
            replay.append({
                "category": cat["category"],
                "rank": rank,
                "gameDate": target_date,
                "player": e.get("player"),
                "playerId": e.get("playerId"),
                "team": e.get("team"),
                "opp": e.get("opp"),
                "matchup": e.get("matchup"),
                "stat": e.get("stat"),
                "line": e.get("line"),
                "prob_cons": pct(e.get("prob_cons")),
                "pred_anchor": e.get("pred_anchor"),
                "avg_anchor": e.get("avg_anchor"),
                "hit_score": e.get("hit_score"),
                "sim_avg": e.get("sim_avg"),
                "score_mode": "prefer_model_gap" if cat["prefer_model_gap"] else "normal",
                "current_score": round(current_row_score(e, prefer_model_gap=bool(cat["prefer_model_gap"])), 6),
                "normal_score": comp["current_score"],
                "warnings": comp["warnings"],
                "driver_summary": e.get("driver_summary") or e.get("summary"),
            })
            if rank >= 12:
                break
    return replay

def audit_current_candidates(analyzer: dict[str, Any], target_date: str | None, out_dir: Path) -> dict[str, Any]:
    entries = analyzer.get("entries") or []
    if not target_date:
        target_date = analyzer.get("targetDate") or ""
    rows = [r for r in entries if safe_date(r.get("gameDate")) == target_date]
    audit_rows = []
    for r in rows:
        comp = current_score_component_row(r)
        audit_rows.append({
            "gameDate": safe_date(r.get("gameDate")),
            "player": r.get("player"),
            "playerId": r.get("playerId"),
            "playerType": r.get("playerType"),
            "team": r.get("team"),
            "opp": r.get("opp"),
            "matchup": r.get("matchup"),
            "stat": r.get("stat"),
            "stat_display": r.get("stat_display"),
            "line": r.get("line"),
            "prob_cons": pct(r.get("prob_cons")),
            "pred_anchor": r.get("pred_anchor"),
            "avg_anchor": r.get("avg_anchor"),
            "hit_score": r.get("hit_score"),
            "sim_avg": r.get("sim_avg"),
            "current_score": comp["current_score"],
            "prob_component": comp["prob_component"],
            "hit_component": comp["hit_component"],
            "gap_component": comp["gap_component"],
            "pred_component": comp["pred_component"],
            "gap": comp["gap"],
            "driver_summary": r.get("driver_summary") or r.get("summary"),
            "warnings": comp["warnings"],
            "href": f"props_analyzer.html?league=MLB&date={safe_date(r.get('gameDate'))}&stat={r.get('stat')}&playerId={r.get('playerId')}&line={r.get('line')}",
        })
    audit_rows.sort(key=lambda x: x.get("current_score") or 0, reverse=True)
    write_csv(out_dir / "mlb_current_candidate_score_audit.csv", audit_rows)

    eligible_stats = {"H", "TB", "HRR", "K", "HA", "ER"}
    home_pick_rows = [
        r for r in audit_rows
        if safe_str(r.get("stat")).upper() in eligible_stats
        and "TBD player/starter" not in safe_str(r.get("warnings"))
        and "missing probability" not in safe_str(r.get("warnings"))
    ]
    write_csv(out_dir / "mlb_current_home_pick_candidate_score_audit.csv", home_pick_rows)
    category_rows = category_replay_rows(entries, target_date)
    write_csv(out_dir / "mlb_current_home_pick_category_replay.csv", category_rows)

    by_stat = Counter(r.get("stat") for r in rows)
    warning_counts = Counter()
    for r in audit_rows:
        if r.get("warnings"):
            for w in str(r["warnings"]).split("; "):
                warning_counts[w] += 1
    top_preview = audit_rows[:25]
    return {
        "target_date": target_date,
        "candidate_rows": len(rows),
        "stats_on_board": dict(sorted(by_stat.items())),
        "warning_counts": dict(warning_counts),
        "top_25_by_current_score": top_preview,
        "category_replay_count": len(category_rows),
        "category_replay_top_rows": [r for r in category_rows if r.get("rank") == 1],
    }


def audit_results_history(history_rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    enriched = enrich_history_rows(history_rows)
    graded = [r for r in enriched if safe_str(r.get("result")) not in {"", "Pending"}]
    bucket_rows: list[dict[str, Any]] = []
    for group_key in ["stat", "role", "board", "side", "prob_bucket", "edge_bucket", "model_bucket"]:
        bucket_rows.extend(summarize_group(graded, group_key))
    # Stat x probability bucket is very helpful for calibration risk.
    stat_prob: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in graded:
        stat_prob[(r.get("stat") or "missing", r.get("prob_bucket") or "missing")].append(r)
    for (stat, prob_bucket), vals in stat_prob.items():
        counts = result_counts(vals)
        if counts["sample"] < 5:
            continue
        probs = [p for p in (pct(v.get("probability")) for v in vals) if p is not None]
        bucket_rows.append({
            "group": "stat_x_prob_bucket",
            "bucket": f"{stat}|{prob_bucket}",
            **counts,
            "avg_probability": round(mean(probs), 4) if probs else None,
            "avg_model_edge_abs": round(mean([safe_float(v.get("model_edge_abs"), 0) or 0 for v in vals]), 4),
        })
    write_csv(out_dir / "mlb_prop_results_bucket_audit.csv", bucket_rows)

    # Daily trend helps detect drift without needing to expose proprietary model details.
    daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in graded:
        daily[r.get("date") or "missing"].append(r)
    daily_rows = []
    for date, vals in sorted(daily.items()):
        daily_rows.append({"date": date, **result_counts(vals)})
    write_csv(out_dir / "mlb_prop_daily_results_audit.csv", daily_rows)

    by_stat = {row["bucket"]: row for row in summarize_group(graded, "stat")}
    by_prob = [r for r in bucket_rows if r.get("group") == "prob_bucket"]
    by_prob.sort(key=lambda r: str(r.get("bucket")))
    return {
        "rows_loaded": len(history_rows),
        "graded_rows": len(graded),
        "overall": result_counts(graded),
        "by_stat": by_stat,
        "probability_bucket_calibration": by_prob,
    }


def stat_from_detail_filename(path: Path) -> str:
    stem = path.stem
    if stem.startswith("pitcher_"):
        return stem.split("_")[-1].upper()
    parts = stem.rsplit("_", 1)
    return parts[-1].upper() if len(parts) == 2 else ""


def extract_hand_weather_flags(text: str) -> dict[str, Any]:
    text = safe_str(text)
    hand_match = re.search(r"\b([LR])\s+vs\s+([LR])\b", text)
    temp_match = re.search(r"(\d+)°F", text)
    wind_match = re.search(r"Wind\s+(-?\d+)", text, flags=re.I)
    order_match = re.search(r"Order\s+(\d+)", text, flags=re.I)
    return {
        "has_handedness_text": bool(hand_match),
        "batter_hand": hand_match.group(1) if hand_match else "",
        "pitcher_hand": hand_match.group(2) if hand_match else "",
        "has_temperature_text": bool(temp_match),
        "temperature_f": int(temp_match.group(1)) if temp_match else None,
        "has_wind_text": bool(wind_match),
        "wind": int(wind_match.group(1)) if wind_match else None,
        "lineup_order": int(order_match.group(1)) if order_match else None,
    }


def audit_similarity_details(detail_dir: Path, analyzer: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    files = sorted(detail_dir.glob("*.json")) if detail_dir.exists() else []
    analyzer_entries = analyzer.get("entries") or []
    entry_lookup: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in analyzer_entries:
        pid = safe_str(e.get("playerId")) or f"pitcher_{safe_str(e.get('team')).lower()}_{safe_str(e.get('opp')).lower()}"
        entry_lookup[(safe_date(e.get("gameDate")), pid, safe_str(e.get("stat")).upper())].append(e)

    detail_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    profile_groups: dict[tuple[str, str, str], dict[str, Any]] = {}

    all_similarity_scores: list[float] = []
    features_seen = Counter()
    missing_feature_counts = Counter()

    for path in files:
        payload = load_json(path, {}) or {}
        pid = safe_str(payload.get("playerId"))
        if not pid and path.stem.startswith("pitcher_"):
            pid = "pitcher_0"
        stat = safe_str(payload.get("stat") or stat_from_detail_filename(path)).upper()
        player = safe_str(payload.get("player"))
        player_type = safe_str(payload.get("playerType"))
        date = safe_date(payload.get("gameDate"))
        games = payload.get("games") or []
        sim_games = payload.get("similarGames") or []
        values = [safe_float(g.get("value")) for g in games]
        values = [v for v in values if v is not None]
        sim_values = [safe_float(g.get("value")) for g in sim_games]
        sim_values = [v for v in sim_values if v is not None]
        scores = [safe_float(g.get("simScore")) for g in sim_games]
        scores = [s for s in scores if s is not None]
        all_similarity_scores.extend(scores)
        flags = extract_hand_weather_flags(payload.get("driverSummary") or payload.get("boardContext") or "")
        for k, v in flags.items():
            if k.startswith("has_") and v:
                features_seen[k] += 1
            elif k.startswith("has_") and not v:
                missing_feature_counts[k] += 1
        # Historical game rows currently do not carry these matchup fields.
        historical_keys = set().union(*(g.keys() for g in games)) if games else set()
        for missing_key in ["pitcherHand", "batterHand", "pitchMix", "park", "temperature", "wind"]:
            if missing_key not in historical_keys:
                missing_feature_counts[f"historical_missing_{missing_key}"] += 1

        lines = sorted({safe_float(e.get("line")) for e in entry_lookup.get((date, pid, stat), []) if safe_float(e.get("line")) is not None})
        detail_rows.append({
            "file": path.name,
            "gameDate": date,
            "player": player,
            "playerId": pid,
            "playerType": player_type,
            "team": payload.get("team"),
            "opp": payload.get("opp"),
            "matchup": payload.get("matchup"),
            "stat": stat,
            "modelPred": payload.get("modelPred"),
            "line_options_from_index": ";".join(str(x) for x in lines),
            "games_count": len(games),
            "similar_games_count": len(sim_games),
            "sim_score_count": len(scores),
            "all_avg": round(mean(values), 4) if values else None,
            "similar_avg": round(mean(sim_values), 4) if sim_values else None,
            "similar_minus_all_avg": round((mean(sim_values) - mean(values)), 4) if sim_values and values else None,
            "similar_score_avg": round(mean(scores), 4) if scores else None,
            "similar_score_min": round(min(scores), 4) if scores else None,
            "similar_score_max": round(max(scores), 4) if scores else None,
            "similar_score_std": round(pstdev(scores), 4) if len(scores) > 1 else 0 if scores else None,
            "has_handedness_text": flags["has_handedness_text"],
            "batter_hand": flags["batter_hand"],
            "pitcher_hand": flags["pitcher_hand"],
            "temperature_f": flags["temperature_f"],
            "wind": flags["wind"],
            "lineup_order": flags["lineup_order"],
            "historical_context_fields": ";".join(sorted(historical_keys)),
            "driverSummary": payload.get("driverSummary"),
        })

        for sg in sim_games:
            score_rows.append({
                "file": path.name,
                "player": player,
                "playerId": pid,
                "stat": stat,
                "similarGameDate": sg.get("gameDate"),
                "opp": sg.get("opp"),
                "location": sg.get("location"),
                "contextValue": sg.get("contextValue"),
                "value": sg.get("value"),
                "simScore": sg.get("simScore"),
                "simBin": sg.get("simBin"),
                "simPct": sg.get("simPct"),
            })

        profile_key = (date, pid, player)
        prof = profile_groups.setdefault(profile_key, {
            "gameDate": date,
            "player": player,
            "playerId": pid,
            "playerType": player_type,
            "team": payload.get("team"),
            "opp": payload.get("opp"),
            "matchup": payload.get("matchup"),
            "stats_available": set(),
            "files": 0,
            "total_games_rows": 0,
            "total_similar_rows": 0,
        })
        prof["stats_available"].add(stat)
        prof["files"] += 1
        prof["total_games_rows"] += len(games)
        prof["total_similar_rows"] += len(sim_games)

    write_csv(out_dir / "mlb_similarity_detail_audit.csv", detail_rows)
    write_csv(out_dir / "mlb_similarity_score_distribution.csv", score_rows)

    readiness_rows = []
    for _, prof in profile_groups.items():
        stats = sorted(prof.pop("stats_available"))
        readiness_rows.append({
            **prof,
            "stat_count": len(stats),
            "stats_available": ";".join(stats),
            "multi_prop_ready": len(stats) >= 2,
        })
    readiness_rows.sort(key=lambda r: (-(r.get("stat_count") or 0), str(r.get("player"))))
    write_csv(out_dir / "mlb_player_profile_readiness.csv", readiness_rows)

    score_summary = {
        "count": len(all_similarity_scores),
        "avg": round(mean(all_similarity_scores), 4) if all_similarity_scores else None,
        "min": round(min(all_similarity_scores), 4) if all_similarity_scores else None,
        "max": round(max(all_similarity_scores), 4) if all_similarity_scores else None,
        "std": round(pstdev(all_similarity_scores), 4) if len(all_similarity_scores) > 1 else None,
    }
    stat_counter = Counter(r.get("stat") for r in detail_rows)
    return {
        "detail_dir": str(detail_dir),
        "files_loaded": len(files),
        "detail_rows": len(detail_rows),
        "stats_found": dict(sorted(stat_counter.items())),
        "score_summary": score_summary,
        "feature_coverage_from_driver_text": dict(features_seen),
        "missing_feature_counts": dict(missing_feature_counts),
        "player_profiles": len(readiness_rows),
        "multi_prop_ready_profiles": sum(1 for r in readiness_rows if r.get("multi_prop_ready")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MLB prop scoring and similarity details.")
    parser.add_argument("--data-dir", default="data", help="Path to the site data directory.")
    parser.add_argument("--detail-date", default=None, help="Date folder under data/mlb_props_analyzer to audit, e.g. 2026-06-14.")
    parser.add_argument("--candidate-date", default=None, help="Date from mlb_props_analyzer.json entries to score. Defaults to analyzer targetDate.")
    parser.add_argument("--out-dir", default=None, help="Output directory. Defaults to <data-dir>/audits.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir) if args.out_dir else data_dir / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)

    history = load_json(data_dir / "mlb_prop_results_history.json", []) or []
    analyzer = load_json(data_dir / "mlb_props_analyzer.json", {}) or {}
    home_top_picks = load_json(data_dir / "home_top_picks.json", {}) or {}

    if args.detail_date:
        detail_date = args.detail_date
    else:
        dates = analyzer.get("dates") or []
        detail_date = str(dates[-1]) if dates else safe_date(analyzer.get("targetDate"))
    detail_dir = data_dir / "mlb_props_analyzer" / detail_date if detail_date else data_dir / "mlb_props_analyzer"

    results_summary = audit_results_history(history, out_dir) if history else {"rows_loaded": 0, "warning": "No mlb_prop_results_history.json found."}
    candidate_summary = audit_current_candidates(analyzer, args.candidate_date or detail_date or analyzer.get("targetDate"), out_dir) if analyzer else {"warning": "No mlb_props_analyzer.json found."}
    similarity_summary = audit_similarity_details(detail_dir, analyzer, out_dir)

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "data_dir": str(data_dir),
            "history_file_exists": (data_dir / "mlb_prop_results_history.json").exists(),
            "analyzer_file_exists": (data_dir / "mlb_props_analyzer.json").exists(),
            "home_top_picks_file_exists": (data_dir / "home_top_picks.json").exists(),
            "detail_date": detail_date,
            "detail_dir_exists": detail_dir.exists(),
            "home_top_picks_targetDate": home_top_picks.get("targetDate"),
            "home_top_cards_count": len(home_top_picks.get("topCards") or []),
        },
        "results_history_audit": results_summary,
        "current_candidate_score_audit": candidate_summary,
        "similarity_detail_audit": similarity_summary,
        "current_scoring_formula": {
            "source": "build_home_top_picks_json.py row_score",
            "normal": "prob_cons*0.60 + hit_score*0.15 + max(pred_anchor-line,-2)*0.10 + max(pred_anchor,0)*0.02",
            "prefer_model_gap": "(pred_anchor-avg_anchor)*1.25 + pred_anchor*0.15 + prob_cons*0.20",
        },
        "audit_notes": [
            "This audit is read-only and is meant to verify the current logic before changing top-pick selection.",
            "The uploaded detail files can verify similarity-score coverage and feature availability, but not future hit rate for 2026-06-14 because those games are not graded in the provided history.",
            "Similarity-game rows currently expose opponent, home/away, lineup/context value, recency-derived score, and result value. They do not expose pitch mix, batter/pitcher hand, park, or weather at the historical-game-row level.",
            "Use the bucket audit to decide whether probability, model edge, stat category, or board type should be weighted differently in the next scoring version.",
        ],
        "recommended_next_step": "Review bucket performance and similarity feature gaps, then add a versioned score_v2 beside the current score instead of replacing current behavior immediately.",
    }
    write_json(out_dir / "mlb_prop_scoring_audit_summary.json", summary)
    print(json.dumps({
        "out_dir": str(out_dir),
        "summary_file": str(out_dir / "mlb_prop_scoring_audit_summary.json"),
        "history_rows": results_summary.get("rows_loaded"),
        "detail_files": similarity_summary.get("files_loaded"),
        "candidate_rows": candidate_summary.get("candidate_rows"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
