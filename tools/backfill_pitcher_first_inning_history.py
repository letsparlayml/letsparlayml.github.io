#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo


def load_core(repo: Path):
    path = repo / "tools" / "first_inning_backfill_core.py"
    if not path.exists():
        raise SystemExit(f"Private first-inning backfill core not found: {path}")
    spec = importlib.util.spec_from_file_location("first_inning_core", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def parse_ymd(value: str, label: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise SystemExit(f"Invalid {label}: {value!r}; expected YYYY-MM-DD") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def positive_number(value: Any) -> bool:
    try:
        x = float(value)
        return math.isfinite(x) and x > 0
    except Exception:
        return False


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def make_backup(repo: Path, files: Iterable[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = repo / "validation" / f"first_inning_history_backup_{stamp}"
    for src in files:
        if not src.exists():
            continue
        try:
            rel = src.relative_to(repo)
        except ValueError:
            rel = Path(src.name)
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return backup


def discover_historical_outings(core, mlb_data_dir: Path, start_date: date, end_date: date) -> Tuple[List[Dict[str, Any]], str]:
    raw, source = core.read_latest_pitcher_game_logs(mlb_data_dir)
    if raw is None or raw.empty:
        raise SystemExit("No rows found in pitcher_game_logs_latest.parquet/csv.")

    cols = list(raw.columns)
    pid_col = core.find_col(cols, ["player_id", "pitcher_id", "playerId", "pitcherId", "mlbam_id"])
    name_col = core.find_col(cols, ["player_name", "pitcher_name", "fullName", "player", "pitcher", "name"])
    game_col = core.find_col(cols, ["gamePk", "game_pk", "gameId", "game_id"])
    local_date_col = core.find_col(cols, ["gameDate_mlb_local", "gameDateLocal", "game_date_local", "date_local"])
    date_col = core.find_col(cols, ["gameDate", "game_date", "date", "game_datetime"])
    team_col = core.find_col(cols, ["team", "team_abbr", "pitching_team"])
    opp_col = core.find_col(cols, ["opponent", "opp", "opponent_team", "opp_team"])
    side_col = core.find_col(cols, ["team_side", "side"])
    home_col = core.find_col(cols, ["isHome", "is_home"])
    loc_col = core.find_col(cols, ["location", "home_away", "homeAway"])
    outs_col = core.find_col(cols, ["outs", "outs_recorded", "pitching_outs"])
    ip_col = core.find_col(cols, ["inningsPitched", "innings_pitched", "IP", "ip"])
    pitches_col = core.find_col(cols, ["pitchesThrown", "pitches_thrown", "pitch_count", "pitches"])

    if not game_col or not date_col or (not pid_col and not name_col):
        raise SystemExit(
            "Pitcher game-log schema is missing required columns. "
            f"game={game_col}, date={date_col}, player_id={pid_col}, player_name={name_col}"
        )

    rows: List[Dict[str, Any]] = []
    for _, r in raw.iterrows():
        gid = core.clean_id(r.get(game_col))
        pid = core.clean_id(r.get(pid_col)) if pid_col else ""
        player = str(r.get(name_col) or "").strip() if name_col else ""
        if not gid or (not pid and not core.norm_name(player)):
            continue

        if local_date_col:
            d_text = core.safe_date(r.get(local_date_col))
        else:
            parsed = core.pd.to_datetime(r.get(date_col), errors="coerce", utc=True)
            if core.pd.isna(parsed):
                continue
            d_text = parsed.tz_convert("America/Denver").date().isoformat()
        if not d_text:
            continue
        d = parse_ymd(d_text, "pitcher-log date")
        if d < start_date or d > end_date:
            continue

        # Ignore non-appearance placeholders, but retain legitimate zero-out
        # appearances when pitches were thrown.
        has_work = True
        if outs_col or ip_col or pitches_col:
            has_work = any(
                positive_number(r.get(col))
                for col in (outs_col, ip_col, pitches_col)
                if col
            )
        if not has_work:
            continue

        is_home: Optional[bool] = None
        if home_col:
            raw_home = str(r.get(home_col) or "").strip().lower()
            if raw_home in {"1", "true", "yes", "home", "h"}:
                is_home = True
            elif raw_home in {"0", "false", "no", "away", "a", "road"}:
                is_home = False
        if is_home is None and side_col:
            side = str(r.get(side_col) or "").strip().upper()
            if side == "HOME":
                is_home = True
            elif side == "AWAY":
                is_home = False
        if is_home is None and loc_col:
            location = str(r.get(loc_col) or "").strip().lower()
            if location in {"home", "h"}:
                is_home = True
            elif location in {"away", "a", "road"}:
                is_home = False

        rows.append({
            "playerId": pid,
            "player": player,
            "gameId": gid,
            "date": d_text,
            "team": core.team_norm(r.get(team_col)) if team_col else "",
            "opponent": core.team_norm(r.get(opp_col)) if opp_col else "",
            "isHome": is_home,
            "source": source or str(mlb_data_dir / "pitcher_game_logs"),
            "starterMethod": "historical_pitcher_game_logs_backfill",
            "starterConfidence": "pending_statsapi_first_pitcher_verification",
        })

    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        who = core.clean_id(row.get("playerId")) or core.norm_name(row.get("player"))
        dedup[(who, core.clean_id(row.get("gameId")))] = row
    out = sorted(dedup.values(), key=lambda x: (x.get("date") or "", int(core.clean_id(x.get("gameId")) or 0), x.get("player") or ""))
    return out, source


def row_side(core, feed: Dict[str, Any], row: Dict[str, Any]) -> str:
    pid = core.clean_id(row.get("playerId"))
    pname = core.norm_name(row.get("player"))
    for side in ("away", "home"):
        info = feed.get(side) or {}
        ids = {core.clean_id(v) for v in (info.get("pitcherIds") or []) if core.clean_id(v)}
        names = {core.norm_name(v) for v in (info.get("pitcherNames") or []) if core.norm_name(v)}
        if (pid and pid in ids) or (pname and pname in names):
            return side
    if row.get("isHome") is True:
        return "home"
    if row.get("isHome") is False:
        return "away"
    team = core.team_norm(row.get("team"))
    for side in ("away", "home"):
        if team and team == core.team_norm((feed.get(side) or {}).get("abbr")):
            return side
    return ""


def exact_first_pitcher_match(core, info: Dict[str, Any], row: Dict[str, Any]) -> bool:
    pid = core.clean_id(row.get("playerId"))
    pname = core.norm_name(row.get("player"))
    first_id = core.clean_id(info.get("firstPitcherId"))
    first_name = core.norm_name(info.get("firstPitcherName"))
    if pid and first_id:
        return pid == first_id
    return bool(pname and first_name and pname == first_name)


def build_payloads_for_game(core, feed: Dict[str, Any], rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    payloads: List[Dict[str, Any]] = []
    gid = core.clean_id(feed.get("gamePk") or (rows[0].get("gameId") if rows else ""))

    for side in ("away", "home"):
        info = feed.get(side) or {}
        if core.num(info.get("runs1")) is None:
            errors.append(f"game {gid}: {side} first-inning runs missing")
        if not (core.clean_id(info.get("firstPitcherId")) or core.norm_name(info.get("firstPitcherName"))):
            errors.append(f"game {gid}: {side} first pitcher missing")

    verified_sides = set()
    for row in rows:
        side = row_side(core, feed, row)
        info = feed.get(side) or {} if side else {}
        verified = bool(side and exact_first_pitcher_match(core, info, row))
        appeared = bool(side)
        base = {
            "source": feed.get("source") or f"statsapi game {gid}",
            "confidence": "high_statsapi_boxscore",
            "starterMethod": "statsapi_boxscore_first_pitcher",
            "actualStarterVerified": verified,
            "playerId": core.clean_id(row.get("playerId")),
            "player": str(row.get("player") or ""),
            "team": core.team_norm(row.get("team")),
            "opponent": core.team_norm(row.get("opponent")),
            "isHome": True if side == "home" else False if side == "away" else row.get("isHome"),
            "location": "Home" if side == "home" else "Away" if side == "away" else "",
            "gameId": gid,
            "date": core.safe_date(row.get("date")),
            "firstPitcherId": core.clean_id(info.get("firstPitcherId")),
            "firstPitcher": str(info.get("firstPitcherName") or "").strip(),
        }
        if verified:
            runs = core.num((feed.get("away") or {}).get("runs1")) if side == "home" else core.num((feed.get("home") or {}).get("runs1"))
            if runs is None:
                errors.append(f"game {gid}: verified {side} starter has no opponent first-inning runs")
                continue
            verified_sides.add(side)
            payloads.append({
                **base,
                "runs": float(runs),
                "method": "statsapi_first_pitcher_in_half_inning",
                "status": "confirmed_first_inning_start",
                "display": str(int(float(runs))) if float(runs).is_integer() else str(float(runs)),
                "note": "Actual first pitcher verified from the MLB StatsAPI box score.",
            })
        else:
            payloads.append({
                **base,
                "runs": None,
                "method": "statsapi_boxscore_non_start_classification",
                "status": "relief_or_bulk_after_opener" if appeared else "did_not_start",
                "display": "Relief" if appeared else "Did not start",
                "note": (
                    f"MLB box score first pitcher was {str(info.get('firstPitcherName') or info.get('firstPitcherId') or 'another pitcher')}; "
                    "no pitcher-specific first-inning runs were assigned."
                ),
            })

    if verified_sides != {"away", "home"}:
        errors.append(
            f"game {gid}: expected verified first pitchers for away and home, got {sorted(verified_sides)}"
        )
    return payloads, errors


def public_lookup(lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in lookup.items():
        row = dict(value)
        row.pop("priority", None)
        out[key] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill verified historical pitcher first-inning results from completed game logs.")
    ap.add_argument("--website-repo", required=True)
    ap.add_argument("--mlb-data-dir", required=True)
    ap.add_argument("--start-date", default="")
    ap.add_argument("--end-date", default="")
    ap.add_argument("--lookback-days", type=int, default=21)
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    repo = Path(args.website_repo).resolve()
    mlb_data_dir = Path(args.mlb_data_dir).resolve()
    core = load_core(repo)

    today_local = datetime.now(ZoneInfo("America/Denver")).date()
    end_date = parse_ymd(args.end_date, "end date") if args.end_date else today_local - timedelta(days=1)
    start_date = parse_ymd(args.start_date, "start date") if args.start_date else end_date - timedelta(days=max(1, args.lookback_days) - 1)
    if start_date > end_date:
        raise SystemExit(f"start date {start_date} is after end date {end_date}")
    if end_date >= today_local:
        raise SystemExit(f"end date must be before today ({today_local}); unplayed/current games are never backfilled")

    json_path = repo / "data" / "derived" / "pitcher_first_inning_runs.json"
    audit_path = repo / "data" / "derived" / "pitcher_first_inning_runs_audit.csv"
    report_path = repo / "validation" / "pitcher_first_inning_history_backfill.json"

    lookup = core.load_existing_lookup(json_path)
    audit = core.load_existing_audit(audit_path)
    before_public = public_lookup(lookup)
    protected_before = {
        key: value for key, value in before_public.items()
        if str(value.get("date") or "") and str(value.get("date")) < start_date.isoformat()
    }
    protected_hash_before = stable_hash(protected_before)

    outings, source = discover_historical_outings(core, mlb_data_dir, start_date, end_date)
    by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in outings:
        by_game[core.clean_id(row.get("gameId"))].append(row)
    if not by_game:
        raise SystemExit(f"No completed pitcher-game rows found from {start_date} through {end_date}.")

    print("Historical first-inning backfill")
    print(f"  Date range          : {start_date} through {end_date}")
    print(f"  Pitcher log source  : {source}")
    print(f"  Pitcher appearances : {len(outings)}")
    print(f"  Unique games        : {len(by_game)}")

    added_payloads: List[Dict[str, Any]] = []
    unresolved_games: List[Dict[str, Any]] = []
    consecutive_failures = 0

    for index, gid in enumerate(sorted(by_game, key=lambda x: int(x)), start=1):
        rows = by_game[gid]
        game_date = min(str(row.get("date") or "") for row in rows)
        print(f"[{index}/{len(by_game)}] {game_date} game {gid}")
        feed = core.fetch_statsapi_first_inning(repo, gid)
        if not feed or not feed.get("ok"):
            consecutive_failures += 1
            unresolved_games.append({"gameId": gid, "date": game_date, "reason": "StatsAPI feed unavailable or invalid"})
            if consecutive_failures >= max(1, args.max_consecutive_failures):
                print("ERROR: repeated StatsAPI failures; stopping before lookup files are changed.")
                break
            continue
        consecutive_failures = 0
        payloads, errors = build_payloads_for_game(core, feed, rows)
        if errors:
            unresolved_games.append({"gameId": gid, "date": game_date, "reason": "; ".join(errors)})
            continue
        added_payloads.extend(payloads)

    selected_games = len(by_game)
    resolved_games = selected_games - len(unresolved_games)
    verified_starters = [p for p in added_payloads if p.get("actualStarterVerified") is True and core.num(p.get("runs")) is not None]
    expected_verified = resolved_games * 2

    validation = {
        "dateRange": {"start": start_date.isoformat(), "end": end_date.isoformat(), "todayLocal": today_local.isoformat()},
        "source": source,
        "pitcherAppearances": len(outings),
        "selectedGames": selected_games,
        "resolvedGames": resolved_games,
        "unresolvedGames": unresolved_games,
        "verifiedStarterRows": len(verified_starters),
        "expectedVerifiedStarterRows": expected_verified,
        "currentOrFutureRowsSelected": sum(1 for row in outings if str(row.get("date") or "") >= today_local.isoformat()),
        "protectedHistoryHashBefore": protected_hash_before,
    }
    validation["passed"] = (
        not unresolved_games
        and len(verified_starters) == selected_games * 2
        and validation["currentOrFutureRowsSelected"] == 0
    )

    if not validation["passed"]:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(report_path, validation)
        print(json.dumps(validation, indent=2))
        print("ERROR: coverage validation failed. Lookup and audit files were not changed.")
        return 3

    # Apply only after complete game-level validation succeeds.
    for payload in added_payloads:
        keys = core.build_keys(payload.get("playerId"), payload.get("player"), payload.get("gameId"), payload.get("date"))
        core.add_lookup(lookup, keys, payload, priority=97)
        audit.append(payload)

    after_public = public_lookup(lookup)
    protected_after = {
        key: value for key, value in after_public.items()
        if str(value.get("date") or "") and str(value.get("date")) < start_date.isoformat()
    }
    protected_hash_after = stable_hash(protected_after)
    validation["protectedHistoryHashAfter"] = protected_hash_after
    validation["olderHistoryUnchanged"] = protected_hash_before == protected_hash_after

    new_numeric_by_date: Dict[str, int] = Counter()
    new_nonstart_by_date: Dict[str, int] = Counter()
    for payload in added_payloads:
        d = str(payload.get("date") or "")
        if core.num(payload.get("runs")) is not None:
            new_numeric_by_date[d] += 1
        elif str(payload.get("status") or "") in core.NON_START_STATUSES:
            new_nonstart_by_date[d] += 1
    validation["numericStarterRowsByDate"] = dict(sorted(new_numeric_by_date.items()))
    validation["nonStartRowsByDate"] = dict(sorted(new_nonstart_by_date.items()))
    validation["olderHistoryUnchanged"] = protected_hash_before == protected_hash_after
    validation["passed"] = bool(validation["passed"] and validation["olderHistoryUnchanged"])

    if not validation["passed"]:
        atomic_write_json(report_path, validation)
        print(json.dumps(validation, indent=2))
        print("ERROR: protected pre-range history changed in memory. Nothing was written.")
        return 4

    if args.validate_only:
        atomic_write_json(report_path, validation)
        print(json.dumps(validation, indent=2))
        print("Validation-only mode: lookup and audit files were not changed.")
        return 0

    backup = make_backup(repo, [json_path, audit_path])
    diagnostics = {
        "mode": "verified_historical_backfill",
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "pitcherAppearances": len(outings),
        "uniqueGames": selected_games,
        "verifiedStarters": len(verified_starters),
        "classifiedNonStarts": len(added_payloads) - len(verified_starters),
        "existingLookupKeys": len(before_public),
        "finalLookupKeys": len(after_public),
    }
    payload = {
        "schemaVersion": "1.6-verified-historical-backfill",
        "generatedAt": core.now_utc(),
        "mlbDataDir": str(mlb_data_dir),
        "diagnostics": diagnostics,
        "lookup": after_public,
    }
    fieldnames = [
        "date", "gameId", "playerId", "player", "team", "opponent", "runs",
        "status", "display", "confidence", "method", "starterMethod",
        "firstPitcher", "firstPitcherId", "note", "source",
    ]
    clean_audit = core.dedupe_audit(audit)
    atomic_write_json(json_path, payload)
    atomic_write_csv(audit_path, clean_audit, fieldnames)

    validation["backup"] = str(backup)
    validation["lookupPath"] = str(json_path)
    validation["auditPath"] = str(audit_path)
    validation["finalLookupKeys"] = len(after_public)
    atomic_write_json(report_path, validation)

    print(json.dumps(validation, indent=2))
    print("SUCCESS: verified historical first-inning lookup was updated atomically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
