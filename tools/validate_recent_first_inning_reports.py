#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def norm_name(value: Any) -> str:
    import re
    s = str(value or "").lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_id(value: Any) -> str:
    s = str(value or "").strip()
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--website-repo", required=True)
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", required=True)
    args = ap.parse_args()

    repo = Path(args.website_repo).resolve()
    lookup_payload = json.loads((repo / "data/derived/pitcher_first_inning_runs.json").read_text(encoding="utf-8-sig"))
    lookup = lookup_payload.get("lookup") or {}
    index = json.loads((repo / "data/game_intelligence/index.json").read_text(encoding="utf-8-sig"))

    linked = 0
    expected = 0
    mismatches: List[Dict[str, Any]] = []
    recent_numeric_lookup = 0
    for value in lookup.values():
        if not isinstance(value, dict):
            continue
        d = str(value.get("date") or "")
        if args.start_date <= d <= args.end_date and isinstance(value.get("runs"), (int, float)) and value.get("actualStarterVerified") is True:
            recent_numeric_lookup += 1

    for meta in index.get("reports") or []:
        path = repo / str(meta.get("path") or "")
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        for pitcher in report.get("pitchingMatchup") or []:
            pid = clean_id(pitcher.get("playerId"))
            pname = norm_name(pitcher.get("player"))
            for row in pitcher.get("last5Starts") or []:
                d = str(row.get("date") or "")
                if not (args.start_date <= d <= args.end_date):
                    continue
                gid = clean_id(row.get("gameId"))
                keys = [
                    f"id:{pid}|game:{gid}" if pid and gid else "",
                    f"name:{pname}|game:{gid}" if pname and gid else "",
                    f"id:{pid}|date:{d}" if pid and d else "",
                    f"name:{pname}|date:{d}" if pname and d else "",
                ]
                source = next((lookup[k] for k in keys if k and k in lookup), None)
                if not isinstance(source, dict) or not isinstance(source.get("runs"), (int, float)) or source.get("actualStarterVerified") is not True:
                    continue
                expected += 1
                if row.get("firstInningRunsAllowed") == source.get("runs"):
                    linked += 1
                else:
                    mismatches.append({
                        "report": str(meta.get("path")),
                        "player": pitcher.get("player"),
                        "date": d,
                        "gameId": gid,
                        "lookupRuns": source.get("runs"),
                        "reportRuns": row.get("firstInningRunsAllowed"),
                    })

    result = {
        "passed": recent_numeric_lookup > 0 and expected > 0 and linked == expected and not mismatches,
        "dateRange": {"start": args.start_date, "end": args.end_date},
        "recentVerifiedNumericLookupRows": recent_numeric_lookup,
        "reportRowsExpectedToLink": expected,
        "reportRowsLinked": linked,
        "mismatches": mismatches,
    }
    out = repo / "validation/recent_first_inning_report_linkage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Report: {out}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
