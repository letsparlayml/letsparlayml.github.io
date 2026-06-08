#!/usr/bin/env python3
"""
build_mlb_top_picks_v2_preview.py

Read-only Step 3 helper for LetsParlayML MLB site updates.

Purpose:
  Build a homepage-style score_v2 preview from the Step 2 audit outputs without
  changing data/home_top_picks.json or any production site file.

Inputs:
  data/audits/mlb_top_pick_score_v2_category_leaders.csv
  data/audits/mlb_top_pick_score_v2_category_comparison.csv (optional)

Outputs:
  data/audits/mlb_home_top_picks_v2_preview.csv
  data/audits/mlb_home_top_picks_v2_preview.json
  data/audits/mlb_home_top_picks_v2_preview_summary.json

This is intentionally a preview layer. Use it to inspect the proposed board before
wiring score_v2 into build_home_top_picks_json.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_CATEGORY_ORDER = [
    "Best hits",
    "Best hits + runs + RBI",
    "Best two-plus total bases",
]

VOLATILE_STATS = {"TB", "HRR", "HR", "SB", "2B"}
WEAK_HISTORY_STATS = {"TB", "HRR"}
STRONG_HISTORY_STATS = {"H", "HA", "K"}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        if isinstance(value, str) and value.strip() == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    x = _safe_float(value, None)
    if x is None:
        return default
    return int(x)


def _text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if s.lower() == "nan":
        return ""
    return s.strip()


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    # Preserve a useful order while still including any unexpected columns.
    preferred = [
        "homepage_rank",
        "category",
        "category_rank",
        "tier",
        "player",
        "team",
        "opp",
        "matchup",
        "stat",
        "stat_display",
        "line",
        "prob_cons",
        "prob_display",
        "pred_anchor",
        "gap",
        "score_v2",
        "current_score",
        "score_v2_rank_all",
        "current_score_rank_all",
        "prob_bucket",
        "prob_bucket_rate",
        "stat_rate",
        "stat_prob_bucket_rate",
        "hit_score",
        "sim_avg",
        "risk_level",
        "display_warnings",
        "score_v2_drivers",
        "href",
    ]
    cols = []
    for c in preferred:
        if any(c in r for r in rows):
            cols.append(c)
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)

    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _prob_display(p: Optional[float]) -> str:
    if p is None:
        return ""
    return f"{p * 100:.1f}%"


def _warning_parts(*values: Any) -> List[str]:
    parts: List[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        # Support both pipe and semicolon style warning strings.
        for raw in text.replace(";", "|").split("|"):
            part = raw.strip()
            if part and part.lower() not in {"nan", "none"}:
                parts.append(part)
    # Unique while preserving order.
    out: List[str] = []
    seen = set()
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _candidate_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    player_id = _text(row.get("playerId"))
    if not player_id:
        player_id = _text(row.get("player")).lower()
    return (player_id, _text(row.get("stat")).upper(), _text(row.get("line")))


def _player_key(row: Dict[str, Any]) -> str:
    player_id = _text(row.get("playerId"))
    if player_id:
        return player_id
    return _text(row.get("player")).lower()


def _matchup_key(row: Dict[str, Any]) -> str:
    return _text(row.get("matchup")) or f"{_text(row.get('team'))}-{_text(row.get('opp'))}"


def _is_tbd_or_missing_player(row: Dict[str, Any]) -> bool:
    player = _text(row.get("player")).lower()
    player_id = _text(row.get("playerId")).lower()
    warnings = " ".join(_warning_parts(row.get("score_v2_warnings"), row.get("current_warnings"))).lower()
    if "tbd" in player or "probable starter tbd" in player:
        return True
    if player_id in {"none", "null", "nan"}:
        return True
    if "tbd player/starter" in warnings:
        return True
    return False


def _risk_level(row: Dict[str, Any]) -> str:
    stat = _text(row.get("stat")).upper()
    score = _safe_float(row.get("score_v2"), 0.0) or 0.0
    warnings = _warning_parts(row.get("score_v2_warnings"), row.get("current_warnings"))

    if warnings or stat in WEAK_HISTORY_STATS:
        if score >= 45:
            return "Volatile but supported"
        return "High volatility"
    if score >= 65:
        return "Strongest"
    if score >= 55:
        return "Playable"
    return "Lean"


def _tier(row: Dict[str, Any]) -> str:
    stat = _text(row.get("stat")).upper()
    score = _safe_float(row.get("score_v2"), 0.0) or 0.0
    warnings = _warning_parts(row.get("score_v2_warnings"), row.get("current_warnings"))

    if stat in WEAK_HISTORY_STATS:
        return "Volatile"
    if warnings:
        return "Caution"
    if score >= 68:
        return "A"
    if score >= 60:
        return "B"
    return "C"


def _display_warnings(row: Dict[str, Any]) -> str:
    warnings = _warning_parts(row.get("score_v2_warnings"), row.get("current_warnings"))
    stat = _text(row.get("stat")).upper()
    if stat == "TB" and not any("TB" in w or "total bases" in w.lower() for w in warnings):
        warnings.append("TB has been weaker historically; require stronger matchup support")
    if stat == "HRR" and not any("HRR" in w or "break-even" in w.lower() for w in warnings):
        warnings.append("HRR has been close to break-even historically; treat as volatile")
    return " | ".join(warnings)


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)

    for c in [
        "score_v2",
        "current_score",
        "prob_cons",
        "pred_anchor",
        "avg_anchor",
        "hit_score",
        "sim_avg",
        "gap",
        "prob_bucket_rate",
        "stat_rate",
        "stat_prob_bucket_rate",
    ]:
        x = _safe_float(out.get(c), None)
        out[c] = "" if x is None else round(x, 6)

    for c in [
        "score_v2_category_leader_rank",
        "score_v2_rank_all",
        "current_score_rank_all",
        "score_v2_rank_category",
        "stat_prob_bucket_sample",
    ]:
        x = _safe_int(out.get(c), None)
        out[c] = "" if x is None else x

    p = _safe_float(row.get("prob_cons"), None)
    out["prob_display"] = _prob_display(p)
    out["tier"] = _tier(row)
    out["risk_level"] = _risk_level(row)
    out["display_warnings"] = _display_warnings(row)
    out["category_rank"] = out.get("score_v2_category_leader_rank") or out.get("score_v2_rank_category") or ""
    return out


def _score_sort_key(row: Dict[str, Any]) -> Tuple[float, float, float]:
    score = _safe_float(row.get("score_v2"), -999.0) or -999.0
    current = _safe_float(row.get("current_score"), -999.0) or -999.0
    prob = _safe_float(row.get("prob_cons"), -999.0) or -999.0
    return (score, current, prob)


def build_preview(
    rows: List[Dict[str, Any]],
    *,
    category_order: List[str],
    max_homepage_picks: int,
    max_per_category_panel: int,
    max_per_player_homepage: int,
    max_per_matchup_homepage: int,
    allow_tbd: bool = False,
) -> Dict[str, Any]:
    filtered = []
    skipped = Counter()

    for row in rows:
        if not allow_tbd and _is_tbd_or_missing_player(row):
            skipped["tbd_or_missing_player"] += 1
            continue
        if _safe_float(row.get("score_v2"), None) is None:
            skipped["missing_score_v2"] += 1
            continue
        filtered.append(row)

    # Category panels: preserve each category's own leaders.
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        grouped[_text(row.get("category"))].append(row)

    category_panels = []
    for category in category_order:
        cat_rows = grouped.get(category, [])
        cat_rows = sorted(cat_rows, key=_score_sort_key, reverse=True)
        picks = [_normalize_row(r) for r in cat_rows[:max_per_category_panel]]
        category_panels.append({
            "category": category,
            "picks": picks,
            "top_score": picks[0].get("score_v2") if picks else None,
            "count_available": len(cat_rows),
        })

    # Homepage preview: pick across categories with player/matchup controls.
    homepage: List[Dict[str, Any]] = []
    player_counts = Counter()
    matchup_counts = Counter()
    used_candidate_keys = set()

    # First pass: try to give every category one representative in desired order.
    for category in category_order:
        if len(homepage) >= max_homepage_picks:
            break
        cat_rows = sorted(grouped.get(category, []), key=_score_sort_key, reverse=True)
        for row in cat_rows:
            player = _player_key(row)
            matchup = _matchup_key(row)
            ck = _candidate_key(row)

            if ck in used_candidate_keys:
                continue
            if player_counts[player] >= max_per_player_homepage:
                continue
            if matchup_counts[matchup] >= max_per_matchup_homepage:
                continue

            homepage.append(row)
            used_candidate_keys.add(ck)
            player_counts[player] += 1
            matchup_counts[matchup] += 1
            break

    # Second pass: fill remaining slots by score_v2, still respecting controls.
    all_rows = sorted(filtered, key=_score_sort_key, reverse=True)
    for row in all_rows:
        if len(homepage) >= max_homepage_picks:
            break
        player = _player_key(row)
        matchup = _matchup_key(row)
        ck = _candidate_key(row)

        if ck in used_candidate_keys:
            continue
        if player_counts[player] >= max_per_player_homepage:
            continue
        if matchup_counts[matchup] >= max_per_matchup_homepage:
            continue

        homepage.append(row)
        used_candidate_keys.add(ck)
        player_counts[player] += 1
        matchup_counts[matchup] += 1

    homepage_norm = []
    for i, row in enumerate(homepage, start=1):
        nr = _normalize_row(row)
        nr["homepage_rank"] = i
        homepage_norm.append(nr)

    # Comparison notes that are useful when reviewing whether score_v2 should be promoted.
    stat_counts = Counter(_text(r.get("stat")).upper() for r in homepage)
    category_counts = Counter(_text(r.get("category")) for r in homepage)
    warning_counts = Counter()
    for r in homepage:
        for w in _warning_parts(r.get("score_v2_warnings"), r.get("current_warnings")):
            warning_counts[w] += 1
        stat = _text(r.get("stat")).upper()
        if stat in WEAK_HISTORY_STATS:
            warning_counts[f"{stat} volatile category"] += 1

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "data/audits/mlb_top_pick_score_v2_category_leaders.csv",
        "settings": {
            "max_homepage_picks": max_homepage_picks,
            "max_per_category_panel": max_per_category_panel,
            "max_per_player_homepage": max_per_player_homepage,
            "max_per_matchup_homepage": max_per_matchup_homepage,
            "allow_tbd": allow_tbd,
            "category_order": category_order,
        },
        "inputRows": len(rows),
        "eligibleRows": len(filtered),
        "skipped": dict(skipped),
        "homepagePickCount": len(homepage_norm),
        "homepageStats": dict(stat_counts),
        "homepageCategories": dict(category_counts),
        "homepageWarningCounts": dict(warning_counts),
        "topHomepagePick": homepage_norm[0] if homepage_norm else None,
    }

    return {
        "summary": summary,
        "homepagePicks": homepage_norm,
        "categoryPanels": category_panels,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data", help="Site data directory. Default: data")
    ap.add_argument("--leaders-file", default=None, help="Override path to mlb_top_pick_score_v2_category_leaders.csv")
    ap.add_argument("--out-dir", default=None, help="Override output directory. Default: data/audits")
    ap.add_argument("--max-homepage-picks", type=int, default=9)
    ap.add_argument("--max-per-category-panel", type=int, default=6)
    ap.add_argument("--max-per-player-homepage", type=int, default=1)
    ap.add_argument("--max-per-matchup-homepage", type=int, default=2)
    ap.add_argument("--allow-tbd", action="store_true")
    ap.add_argument(
        "--category-order",
        default=",".join(DEFAULT_CATEGORY_ORDER),
        help="Comma-separated category order.",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    audits_dir = Path(args.out_dir) if args.out_dir else data_dir / "audits"
    leaders_path = Path(args.leaders_file) if args.leaders_file else audits_dir / "mlb_top_pick_score_v2_category_leaders.csv"

    rows = _read_csv(leaders_path)
    if not rows:
        raise SystemExit(f"No rows found in {leaders_path}. Run audit_mlb_top_pick_score_v2.py first.")

    category_order = [x.strip() for x in args.category_order.split(",") if x.strip()]
    # Include any unexpected categories after the preferred ones.
    seen = set(category_order)
    for r in rows:
        cat = _text(r.get("category"))
        if cat and cat not in seen:
            category_order.append(cat)
            seen.add(cat)

    preview = build_preview(
        rows,
        category_order=category_order,
        max_homepage_picks=args.max_homepage_picks,
        max_per_category_panel=args.max_per_category_panel,
        max_per_player_homepage=args.max_per_player_homepage,
        max_per_matchup_homepage=args.max_per_matchup_homepage,
        allow_tbd=args.allow_tbd,
    )

    audits_dir.mkdir(parents=True, exist_ok=True)
    json_path = audits_dir / "mlb_home_top_picks_v2_preview.json"
    csv_path = audits_dir / "mlb_home_top_picks_v2_preview.csv"
    summary_path = audits_dir / "mlb_home_top_picks_v2_preview_summary.json"

    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(json.dumps(preview["summary"], indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(csv_path, preview["homepagePicks"])

    print(f"[OK] Wrote {json_path}")
    print(f"[OK] Wrote {csv_path}")
    print(f"[OK] Wrote {summary_path}")
    print(f"[OK] Homepage picks: {preview['summary']['homepagePickCount']}")
    if preview["homepagePicks"]:
        top = preview["homepagePicks"][0]
        print(f"[OK] Top preview pick: {top.get('player')} {top.get('stat')} {top.get('line')} ({top.get('score_v2')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
