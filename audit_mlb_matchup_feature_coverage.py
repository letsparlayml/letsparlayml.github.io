#!/usr/bin/env python3
"""Audit MLB prop analyzer matchup feature coverage.

Run from the site project root after rebuilding props and profiles:

    python audit_mlb_matchup_feature_coverage.py --data-dir data --all-dates
    python audit_mlb_matchup_feature_coverage.py --data-dir data --date 2026-06-14

This is read-only. It writes coverage summaries under data/audits/.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DETAIL_RE = re.compile(r"^(?:pitcher_)?[^_]+_([a-z0-9]+)\.json$", re.I)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def has_text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def has_num(v: Any) -> bool:
    try:
        if v is None or v == "":
            return False
        float(v)
        return True
    except Exception:
        return False


def date_folders(base: Path, date: str | None, all_dates: bool) -> list[Path]:
    if date:
        return [base / date]
    folders = [p for p in base.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", p.name)] if base.exists() else []
    return sorted(folders) if all_dates else sorted(folders)[-1:]


def scan_date(folder: Path) -> dict[str, Any]:
    detail_files = [p for p in folder.glob("*.json") if DETAIL_RE.match(p.name) and p.name not in {"index.json", "manifest.json"}]
    detail_counts = Counter()
    hist_counts = Counter()
    profile_counts = Counter()
    hist_rows = 0

    for path in detail_files:
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        ctx = data.get("matchupContext") if isinstance(data.get("matchupContext"), dict) else {}
        if ctx:
            detail_counts["currentContext"] += 1
        if has_text(ctx.get("handednessText")) or (has_text(ctx.get("batterHand")) and has_text(ctx.get("pitcherHand"))):
            detail_counts["currentHandedness"] += 1
        if has_num(ctx.get("temperatureF")):
            detail_counts["currentTemperature"] += 1
        if has_num(ctx.get("windMph")):
            detail_counts["currentWind"] += 1
        if has_text(ctx.get("park")):
            detail_counts["currentPark"] += 1
        if has_text(ctx.get("opponentStarterName")) or has_text(ctx.get("opponentStarterId")):
            detail_counts["currentStarter"] += 1
        if has_text(ctx.get("pitchMixSummary")):
            detail_counts["currentPitchMix"] += 1

        for row in data.get("games") or []:
            if not isinstance(row, dict):
                continue
            hist_rows += 1
            if has_text(row.get("handednessText")) or (has_text(row.get("batterHand")) and (has_text(row.get("opposingPitcherHand")) or has_text(row.get("pitcherHand")))):
                hist_counts["historicalHandednessRows"] += 1
            if has_text(row.get("park")):
                hist_counts["historicalParkRows"] += 1
            if has_num(row.get("temperatureF")) or has_num(row.get("windMph")):
                hist_counts["historicalWeatherRows"] += 1
            if has_text(row.get("opposingStarterName")) or has_text(row.get("opposingStarterId")):
                hist_counts["historicalStarterRows"] += 1
            if has_text(row.get("pitchMixSummary")):
                hist_counts["historicalPitchMixRows"] += 1

    profile_dir = folder / "player_profiles"
    profile_files = [p for p in profile_dir.glob("*.json") if p.name != "index.json"] if profile_dir.exists() else []
    for path in profile_files:
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        cov = ((data.get("matchupFeatureSummary") or {}).get("featureCoverage") or {})
        for key, val in cov.items():
            if val:
                profile_counts[key] += 1

    return {
        "date": folder.name,
        "detailFiles": len(detail_files),
        "historicalRows": hist_rows,
        "profileFiles": len(profile_files),
        "detailCoverage": dict(detail_counts),
        "historicalRowCoverage": dict(hist_counts),
        "profileCoverage": dict(profile_counts),
    }


def pct(n: int, d: int) -> str:
    return f"{(n / d * 100):.1f}%" if d else "0.0%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--date")
    ap.add_argument("--all-dates", action="store_true")
    args = ap.parse_args()

    base = args.data_dir / "mlb_props_analyzer"
    rows = [scan_date(folder) for folder in date_folders(base, args.date, args.all_dates) if folder.exists()]
    audits = args.data_dir / "audits"
    audits.mkdir(parents=True, exist_ok=True)

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "datesScanned": len(rows),
        "rows": rows,
    }
    (audits / "mlb_matchup_feature_coverage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = audits / "mlb_matchup_feature_coverage_summary.csv"
    fields = [
        "date", "detailFiles", "historicalRows", "profileFiles",
        "currentHandedness", "currentHandednessPct", "currentWeather", "currentWeatherPct", "currentPark", "currentPitchMix",
        "historicalHandednessRows", "historicalHandednessPct", "historicalWeatherRows", "historicalWeatherPct",
        "historicalParkRows", "historicalPitchMixRows",
        "profileHistoricalHandedness", "profileHistoricalPitchMix", "profileHistoricalPark", "profileHistoricalWeather",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            d = r["detailCoverage"]
            h = r["historicalRowCoverage"]
            p = r["profileCoverage"]
            row = {
                "date": r["date"],
                "detailFiles": r["detailFiles"],
                "historicalRows": r["historicalRows"],
                "profileFiles": r["profileFiles"],
                "currentHandedness": d.get("currentHandedness", 0),
                "currentHandednessPct": pct(d.get("currentHandedness", 0), r["detailFiles"]),
                "currentWeather": d.get("currentTemperature", 0) + d.get("currentWind", 0),
                "currentWeatherPct": pct(max(d.get("currentTemperature", 0), d.get("currentWind", 0)), r["detailFiles"]),
                "currentPark": d.get("currentPark", 0),
                "currentPitchMix": d.get("currentPitchMix", 0),
                "historicalHandednessRows": h.get("historicalHandednessRows", 0),
                "historicalHandednessPct": pct(h.get("historicalHandednessRows", 0), r["historicalRows"]),
                "historicalWeatherRows": h.get("historicalWeatherRows", 0),
                "historicalWeatherPct": pct(h.get("historicalWeatherRows", 0), r["historicalRows"]),
                "historicalParkRows": h.get("historicalParkRows", 0),
                "historicalPitchMixRows": h.get("historicalPitchMixRows", 0),
                "profileHistoricalHandedness": p.get("historicalHandedness", 0),
                "profileHistoricalPitchMix": p.get("historicalPitchMix", 0),
                "profileHistoricalPark": p.get("historicalPark", 0),
                "profileHistoricalWeather": p.get("historicalWeather", 0),
            }
            w.writerow(row)
    print(f"[OK] Wrote {audits / 'mlb_matchup_feature_coverage_summary.json'}")
    print(f"[OK] Wrote {csv_path}")


if __name__ == "__main__":
    main()
