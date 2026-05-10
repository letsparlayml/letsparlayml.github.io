#!/usr/bin/env python
"""
Build robust static MLB Game Intelligence reports for Let's Parlay ML.

This builder uses the site JSON files first, especially the MLB props analyzer
split files, because those already contain actual recent player game logs.
It also supports optional local mlb_data folders for first-inning starter logs
and richer batter splits if those raw logs are present.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAT_LABELS = {
    "H": "Hits",
    "TB": "Total Bases",
    "HRR": "Hits + Runs + RBI",
    "K": "Strikeouts",
    "HR": "Home Runs",
    "BB": "Walks",
    "2B": "Doubles",
    "SB": "Stolen Bases",
    "IP": "IP",
    "OUTS": "Outs",
    "HA": "Hits Allowed",
    "ER": "Earned Runs",
}

BATTER_FEATURE_STATS = ["H", "TB", "HRR", "K", "HR", "BB"]
PITCHER_STATS = ["IP", "K", "HA", "ER", "BB", "OUTS"]


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except Exception:
        return None
    if not math.isfinite(n):
        return None
    return n


def avg(values: Iterable[Any]) -> Optional[float]:
    xs = [num(v) for v in values]
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def pct(count: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return count / total


def round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    n = num(value)
    return round(n, digits) if n is not None else None


def slug_part(value: Any) -> str:
    s = str(value or "").upper().strip()
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    return s or "NA"


def norm_name(value: Any) -> str:
    s = str(value or "").lower()
    s = re.sub(r"[áàäâãå]", "a", s)
    s = re.sub(r"[éèëê]", "e", s)
    s = re.sub(r"[íìïî]", "i", s)
    s = re.sub(r"[óòöôõ]", "o", s)
    s = re.sub(r"[úùüû]", "u", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()




def clean_id(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    if re.match(r"^\d+\.0$", s):
        return s[:-2]
    return s

def team_norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def safe_date(value: Any) -> str:
    s = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    if "T" in s:
        return s.split("T", 1)[0]
    return s


def fmt_num(value: Any, digits: int = 1, fallback: str = "—") -> str:
    n = num(value)
    if n is None:
        return fallback
    return f"{n:.{digits}f}"


def fmt_pct(value: Any, digits: int = 0, fallback: str = "—") -> str:
    n = num(value)
    if n is None:
        return fallback
    return f"{n * 100:.{digits}f}%"


def local_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_props_analyzer(repo: Path) -> Dict[str, Any]:
    return read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}


def series_path_for(props: Dict[str, Any], entry: Dict[str, Any], stat: str) -> Optional[Path]:
    idx = props.get("seriesIndex") or {}
    date = entry.get("gameDate") or props.get("targetDate")
    player_id = entry.get("playerId") or entry.get("player_id")
    ptype = entry.get("playerType") or "batter"
    keys = [
        f"{date}|MLB|{ptype}|{player_id}|{stat}",
        f"{date}|MLB|{player_id}|{stat}",
    ]
    for key in keys:
        p = idx.get(key)
        if p:
            return Path(str(p).replace("\\", "/"))
    return None


def load_series(repo: Path, props: Dict[str, Any], entry: Dict[str, Any], stat: str) -> Optional[Dict[str, Any]]:
    rel = series_path_for(props, entry, stat)
    if not rel:
        return None
    return read_json(repo / rel, None)


def entries_by_game(props: Dict[str, Any], target_date: str) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in props.get("entries") or []:
        if str(e.get("gameDate") or "") != target_date:
            continue
        gid = str(e.get("gameId") or e.get("gamePk") or "")
        if gid:
            out[gid].append(e)
    return out


def primary_entry(entries: List[Dict[str, Any]], player_id: Any, player_type: str, stat: Optional[str] = None) -> Optional[Dict[str, Any]]:
    for e in entries:
        if str(e.get("playerId") or "") != str(player_id or ""):
            continue
        if str(e.get("playerType") or "").lower() != player_type.lower():
            continue
        if stat and str(e.get("stat") or "").upper() != stat.upper():
            continue
        return e
    return None


def collect_players(entries: List[Dict[str, Any]], player_type: str) -> List[Dict[str, Any]]:
    seen = {}
    for e in entries:
        if str(e.get("playerType") or "").lower() != player_type.lower():
            continue
        pid = str(e.get("playerId") or norm_name(e.get("player")))
        if not pid:
            continue
        if pid not in seen:
            seen[pid] = {
                "playerId": e.get("playerId"),
                "player": e.get("player"),
                "team": e.get("team"),
                "opp": e.get("opp"),
                "location": e.get("location"),
                "boardContext": e.get("boardContext") or e.get("boardDriver") or e.get("driver_summary") or "",
            }
    return list(seen.values())


def get_games(series: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not series:
        return []
    games = series.get("games") or []
    games = [g for g in games if isinstance(g, dict)]
    games.sort(key=lambda g: (str(g.get("gameDate") or ""), int(num(g.get("seq")) or 0)))
    return games


def is_real_game_date(value: Any) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value or "").strip()))


def analyzer_aggregate_windows(stat_games: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    labels = ["L3", "L5", "L10", "Prior"]
    out = []
    maps = {}
    for stat, rows in stat_games.items():
        maps[stat] = {str(r.get("gameDate") or r.get("label") or ""): r for r in rows}
    for lab in labels:
        row = {"label": lab}
        found = False
        for stat in PITCHER_STATS:
            r = maps.get(stat, {}).get(lab)
            if r:
                found = True
                row[stat] = round_or_none(r.get("value"), 2)
                if stat == "IP" and row.get("IP") is None:
                    row[stat] = round_or_none(r.get("minutes"), 1)
        if found:
            out.append(row)
    return out




def first_inning_history_for_pitcher(player_id: Any, player_name: Any, first_inning_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return deduped first-inning RA records for a pitcher from the derived lookup.

    The lookup stores multiple keys per start so the game rows can join by ID,
    name, game, or date. This helper collapses those duplicate values into one
    history list that can be summarized for overall and home/away splits.
    """
    pid = clean_id(player_id)
    nm = norm_name(player_name)
    rows: List[Dict[str, Any]] = []
    seen = set()
    for value in (first_inning_map or {}).values():
        if not isinstance(value, dict):
            continue
        value_pid = clean_id(value.get("playerId"))
        value_name = norm_name(value.get("player"))
        if pid and value_pid and pid != value_pid:
            continue
        if not pid and nm and value_name and nm != value_name:
            continue
        if pid and not value_pid and nm and value_name and nm != value_name:
            continue
        runs = num(value.get("runs"))
        if runs is None:
            continue
        game_id = clean_id(value.get("gameId"))
        date = safe_date(value.get("date"))
        dedupe_key = (game_id or date, date, runs, team_norm(value.get("team")), team_norm(value.get("opponent")))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        row = dict(value)
        row["runs"] = runs
        row["gameId"] = game_id
        row["date"] = date
        # Older cached records may not include isHome. Infer it from the method
        # when possible, but keep None if unknown.
        if row.get("isHome") not in [True, False]:
            loc = str(row.get("location") or "").strip().lower()
            if loc == "home":
                row["isHome"] = True
            elif loc in {"away", "road"}:
                row["isHome"] = False
            else:
                row["isHome"] = None
        rows.append(row)
    rows.sort(key=lambda r: (safe_date(r.get("date")), clean_id(r.get("gameId"))))
    return rows


def summarize_first_inning_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [num(r.get("runs")) for r in records]
    vals = [v for v in vals if v is not None]
    return {
        "samples": len(vals),
        "runAllowedRate": pct(sum(1 for v in vals if v > 0), len(vals)) if vals else None,
        "avgRunsAllowed": round_or_none(avg(vals), 2) if vals else None,
        "zeroRunCount": sum(1 for v in vals if v == 0),
        "multiRunCount": sum(1 for v in vals if v >= 2),
    }


def is_true_start_row(row: Dict[str, Any]) -> bool:
    """Keep only rows that represent a real start/appearance for the last-5-start table.

    The analyzer can include postponed/no-game rows or relief/bulk appearances in
    recent windows. Those should not appear in a section labeled last 5 starts.
    """
    status = str(row.get("firstInningStatus") or "").strip().lower()
    display = str(row.get("firstInningDisplay") or "").strip().lower()
    non_start_statuses = {
        "relief_or_bulk_after_opener",
        "not_first_inning_pitcher",
        "appeared_after_first_inning",
        "did_not_start",
    }
    if status in non_start_statuses:
        return False
    if "did not start" in display or "postpon" in display or "no game" in display:
        return False
    # If there is no pitch data and the box row is all zeros, this is almost
    # always a postponed/no-game placeholder rather than a completed start.
    if status == "no_pitch_data":
        box_vals = [num(row.get(k)) for k in ("ip", "k", "hitsAllowed", "er", "bb")]
        if all(v in (None, 0) for v in box_vals):
            return False
    return True


def first_inning_scope_flags(summary: Dict[str, Any]) -> Dict[str, bool]:
    last_samples = int(summary.get("firstInningSamples") or 0)
    overall_samples = int(summary.get("firstInningOverallSamples") or 0)
    location_samples = int(summary.get("firstInningLocationSamples") or 0)
    return {
        # Only show the overall box when it is actually wider than the recent
        # sample. Otherwise it looks like a duplicate of Last 5 and implies a
        # larger history that the data does not support.
        "showOverallFirstInning": overall_samples > last_samples,
        "showLocationFirstInning": location_samples > 0,
    }

def combine_pitcher_last_starts(repo: Path, props: Dict[str, Any], entries: List[Dict[str, Any]], pitcher: Dict[str, Any], first_inning_map: Dict[str, Any]) -> Dict[str, Any]:
    pid = clean_id(pitcher.get("playerId"))
    stat_series: Dict[str, Optional[Dict[str, Any]]] = {}
    stat_games: Dict[str, List[Dict[str, Any]]] = {}
    for stat in PITCHER_STATS:
        e = primary_entry(entries, pid, "pitcher", stat) or primary_entry(entries, pid, "pitcher")
        series = load_series(repo, props, e, stat) if e else None
        stat_series[stat] = series
        stat_games[stat] = get_games(series)

    # Use only actual dated games as starts. Some analyzer files contain aggregate
    # windows like Prior/L10/L5/L3; those are useful, but they are not starts.
    candidate_games = stat_games.get("IP") or stat_games.get("K") or stat_games.get("HA") or []
    # Pull more than five candidates first. We filter postponed/no-start/relief
    # rows after first-inning lookup, then keep the latest five true starts.
    base_games = [g for g in candidate_games if is_real_game_date(g.get("gameDate") or g.get("label"))][-25:]
    aggregate_windows = analyzer_aggregate_windows(stat_games)

    # Build maps by gameId/date for each stat.
    maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for stat, rows in stat_games.items():
        m = {}
        for row in rows:
            key = clean_id(row.get("gameId") or row.get("gamePk") or row.get("gameDate") or row.get("label") or "")
            if key:
                m[key] = row
        maps[stat] = m

    last5 = []
    for row in base_games:
        key = clean_id(row.get("gameId") or row.get("gamePk") or row.get("gameDate") or row.get("label") or "")
        def stat_value(stat: str) -> Optional[float]:
            r = maps.get(stat, {}).get(key)
            return round_or_none(r.get("value") if r else None, 2)
        game_id = clean_id(row.get("gameId") or row.get("gamePk") or "")
        start_date = safe_date(row.get("gameDate") or row.get("label"))
        pnorm = norm_name(pitcher.get('player'))
        lookup_keys = [
            f"id:{pid}|game:{game_id}" if pid and game_id else "",
            f"name:{pnorm}|game:{game_id}" if pnorm and game_id else "",
            f"id:{pid}|date:{start_date}" if pid and start_date else "",
            f"name:{pnorm}|date:{start_date}" if pnorm and start_date else "",
            f"id:{pid}|game:{key}" if pid and key else "",
            f"name:{pnorm}|game:{key}" if pnorm and key else "",
        ]
        first = None
        for lk in lookup_keys:
            if lk in first_inning_map:
                first = first_inning_map[lk]
                break
        first_status = first.get("status") if isinstance(first, dict) else ""
        first_display = first.get("display") if isinstance(first, dict) else ""
        first_note = first.get("note") if isinstance(first, dict) else ""
        last5.append({
            "date": safe_date(row.get("gameDate") or row.get("label")),
            "gameId": clean_id(row.get("gameId") or row.get("gamePk") or ""),
            "opponent": row.get("opp") or "",
            "location": row.get("location") or ("Home" if str(row.get("isHome")) == "1" else "Away" if str(row.get("isHome")) == "0" else ""),
            "ip": stat_value("IP") if stat_value("IP") is not None else round_or_none(row.get("minutes"), 1),
            "k": stat_value("K"),
            "hitsAllowed": stat_value("HA"),
            "er": stat_value("ER"),
            "bb": stat_value("BB"),
            "outs": stat_value("OUTS"),
            "firstInningRunsAllowed": first.get("runs") if isinstance(first, dict) else first,
            "firstInningStatus": first_status,
            "firstInningDisplay": first_display,
            "firstInningNote": first_note,
            "firstInningSource": first.get("source") if isinstance(first, dict) else "",
        })

    # Remove postponed/no-game rows and pitchers who appeared after an opener so
    # the table is truly last five starts. Backfill from the extra candidates
    # pulled above, then cap to five.
    filtered_last5 = [r for r in last5 if is_true_start_row(r)]
    dropped_non_start_rows = len(last5) - len(filtered_last5)
    last5 = filtered_last5[-5:]

    summary = {
        "avgIP": round_or_none(avg([r.get("ip") for r in last5]), 1),
        "avgK": round_or_none(avg([r.get("k") for r in last5]), 1),
        "avgHitsAllowed": round_or_none(avg([r.get("hitsAllowed") for r in last5]), 1),
        "avgER": round_or_none(avg([r.get("er") for r in last5]), 1),
        "avgBB": round_or_none(avg([r.get("bb") for r in last5]), 1),
        "startsCount": len(last5),
        "hasStartByStartLogs": bool(last5),
        "droppedNonStartRows": dropped_non_start_rows,
    }
    # If start-by-start logs are unavailable, expose the analyzer windows without
    # pretending they are actual game rows.
    if not last5 and aggregate_windows:
        l5 = next((w for w in aggregate_windows if w.get("label") == "L5"), aggregate_windows[0])
        summary.update({
            "avgIP": round_or_none(l5.get("IP"), 1),
            "avgK": round_or_none(l5.get("K"), 1),
            "avgHitsAllowed": round_or_none(l5.get("HA"), 1),
            "avgER": round_or_none(l5.get("ER"), 1),
            "avgBB": round_or_none(l5.get("BB"), 1),
            "startsCount": 0,
        })
    first_values = [num(r.get("firstInningRunsAllowed")) for r in last5 if r.get("firstInningRunsAllowed") is not None]
    non_start_rows = [r for r in last5 if r.get("firstInningStatus") in {"relief_or_bulk_after_opener", "not_first_inning_pitcher", "appeared_after_first_inning", "did_not_start"}]
    unresolved_first_rows = [r for r in last5 if r.get("firstInningStatus") and r.get("firstInningStatus") not in {"relief_or_bulk_after_opener", "not_first_inning_pitcher", "appeared_after_first_inning", "did_not_start"}]
    summary["firstInningRunAllowedRate"] = pct(sum(1 for v in first_values if v and v > 0), len(first_values)) if first_values else None
    summary["firstInningSamples"] = len(first_values)
    summary["firstInningNonStartRows"] = len(non_start_rows)
    summary["firstInningUnresolvedRows"] = len(unresolved_first_rows)

    # Full available first-inning history and home/away split summaries.
    first_history = first_inning_history_for_pitcher(pid, pitcher.get("player"), first_inning_map)
    overall_fi = summarize_first_inning_records(first_history)
    home_fi = summarize_first_inning_records([r for r in first_history if r.get("isHome") is True])
    away_fi = summarize_first_inning_records([r for r in first_history if r.get("isHome") is False])
    loc = str(pitcher.get("location") or "").strip().lower()
    loc_records = [r for r in first_history if (r.get("isHome") is True and loc == "home") or (r.get("isHome") is False and loc in {"away", "road"})]
    loc_fi = summarize_first_inning_records(loc_records)
    summary.update({
        "firstInningOverallSamples": overall_fi.get("samples"),
        "firstInningOverallRunAllowedRate": overall_fi.get("runAllowedRate"),
        "firstInningOverallAvgRunsAllowed": overall_fi.get("avgRunsAllowed"),
        "firstInningHomeSamples": home_fi.get("samples"),
        "firstInningHomeRunAllowedRate": home_fi.get("runAllowedRate"),
        "firstInningAwaySamples": away_fi.get("samples"),
        "firstInningAwayRunAllowedRate": away_fi.get("runAllowedRate"),
        "firstInningLocation": "Home" if loc == "home" else "Away" if loc in {"away", "road"} else "",
        "firstInningLocationSamples": loc_fi.get("samples"),
        "firstInningLocationRunAllowedRate": loc_fi.get("runAllowedRate"),
        "firstInningHistoryRows": len(first_history),
    })
    summary.update(first_inning_scope_flags(summary))

    # Same opponent starts when available.
    opp = team_norm(pitcher.get("opp"))
    same_opp = []
    for row in (stat_games.get("IP") or stat_games.get("K") or []):
        if not is_real_game_date(row.get("gameDate") or row.get("label")):
            continue
        if team_norm(row.get("opp")) == opp:
            key = clean_id(row.get("gameId") or row.get("gamePk") or row.get("gameDate") or row.get("label") or "")
            def sv(stat: str):
                r = maps.get(stat, {}).get(key)
                return round_or_none(r.get("value") if r else None, 2)
            same_opp.append({
                "date": safe_date(row.get("gameDate") or row.get("label")),
                "ip": sv("IP") if sv("IP") is not None else round_or_none(row.get("minutes"), 1),
                "k": sv("K"), "hitsAllowed": sv("HA"), "er": sv("ER"), "bb": sv("BB"),
            })
    same_opp = same_opp[-5:]

    flags = []
    if last5:
        er2 = sum(1 for r in last5 if (num(r.get("er")) is not None and num(r.get("er")) <= 2))
        ip6 = sum(1 for r in last5 if (num(r.get("ip")) is not None and num(r.get("ip")) >= 6))
        ha6 = sum(1 for r in last5 if (num(r.get("hitsAllowed")) is not None and num(r.get("hitsAllowed")) >= 6))
        k5 = sum(1 for r in last5 if (num(r.get("k")) is not None and num(r.get("k")) >= 5))
        if er2 >= 4:
            flags.append(f"Held opponents to 2 ER or fewer in {er2}/{len(last5)} recent starts.")
        elif er2 <= 1 and len(last5) >= 4:
            flags.append(f"Allowed 3+ ER in {len(last5)-er2}/{len(last5)} recent starts.")
        if ip6 >= 3:
            flags.append(f"Worked 6+ IP in {ip6}/{len(last5)} recent starts.")
        if ha6 >= 3:
            flags.append(f"Allowed 6+ hits in {ha6}/{len(last5)} recent starts.")
        if k5 >= 3:
            flags.append(f"Reached 5+ strikeouts in {k5}/{len(last5)} recent starts.")
    if not last5 and aggregate_windows:
        flags.append("Detailed start-by-start pitcher logs were not found for this starter in the site files; showing analyzer L3/L5/L10 windows instead.")
    if same_opp:
        flags.append(f"Has {len(same_opp)} recent start(s) in the logs against {pitcher.get('opp')}.")
    if summary.get("firstInningSamples"):
        rate_txt = fmt_pct(summary.get("firstInningRunAllowedRate"), 0)
        flags.append(f"First-inning run allowed in {rate_txt} of the last-{summary.get('firstInningSamples')} matched recent-start sample.")
    if summary.get("droppedNonStartRows"):
        flags.append(f"Removed {summary.get('droppedNonStartRows')} postponed/non-start/bulk row(s) so the table shows true recent starts.")
    if summary.get("firstInningNonStartRows"):
        flags.append(f"{summary.get('firstInningNonStartRows')} recent row(s) were relief/bulk appearances, so pitcher-specific 1st-inning RA does not apply to those games.")
    if summary.get("showOverallFirstInning"):
        flags.append(f"Available overall first-inning RA: {fmt_pct(summary.get('firstInningOverallRunAllowedRate'), 0)} over {summary.get('firstInningOverallSamples')} matched starts.")
    if summary.get("showLocationFirstInning") and summary.get("firstInningLocation"):
        flags.append(f"Available {summary.get('firstInningLocation').lower()} first-inning RA: {fmt_pct(summary.get('firstInningLocationRunAllowedRate'), 0)} over {summary.get('firstInningLocationSamples')} matched starts.")
    if not summary.get("firstInningSamples") and not summary.get("showOverallFirstInning"):
        flags.append("First-inning starter run history was not found in the site files; this will populate if raw inning logs are available locally.")

    projections = {}
    for stat, series in stat_series.items():
        if series:
            projections[stat] = round_or_none(series.get("modelPred") or series.get("modelMu"), 2)
    return {
        "playerId": pid,
        "player": pitcher.get("player"),
        "team": pitcher.get("team"),
        "opponent": pitcher.get("opp"),
        "location": pitcher.get("location"),
        "context": pitcher.get("boardContext") or "",
        "last5Starts": last5,
        "aggregateWindows": aggregate_windows,
        "last5Summary": summary,
        "sameOpponentStarts": same_opp,
        "projections": projections,
        "flags": flags[:5],
    }


def stat_history(series: Optional[Dict[str, Any]], threshold: float = 1.0, last_n: int = 10) -> Dict[str, Any]:
    games = get_games(series)
    last = games[-last_n:]
    vals = [num(g.get("value")) for g in last]
    vals_clean = [v for v in vals if v is not None]
    hits = sum(1 for v in vals_clean if v >= threshold)
    out = {
        "sample": len(vals_clean),
        "hitRate": pct(hits, len(vals_clean)) if vals_clean else None,
        "avg": round_or_none(avg(vals_clean), 2),
        "lastValues": vals_clean[-5:],
    }
    return out


def location_history(series: Optional[Dict[str, Any]], target_location: str, threshold: float = 1.0) -> Dict[str, Any]:
    games = get_games(series)
    loc = str(target_location or "").lower()
    matched = [g for g in games if str(g.get("location") or ("Home" if str(g.get("isHome")) == "1" else "Away" if str(g.get("isHome")) == "0" else "")).lower() == loc]
    vals = [num(g.get("value")) for g in matched if num(g.get("value")) is not None]
    return {
        "sample": len(vals),
        "hitRate": pct(sum(1 for v in vals if v >= threshold), len(vals)) if vals else None,
        "avg": round_or_none(avg(vals), 2),
    }


def opponent_history(series: Optional[Dict[str, Any]], opponent: str, threshold: float = 1.0) -> Dict[str, Any]:
    games = get_games(series)
    opp = team_norm(opponent)
    matched = [g for g in games if team_norm(g.get("opp")) == opp]
    vals = [num(g.get("value")) for g in matched if num(g.get("value")) is not None]
    return {
        "sample": len(vals),
        "hitRate": pct(sum(1 for v in vals if v >= threshold), len(vals)) if vals else None,
        "avg": round_or_none(avg(vals), 2),
    }


def similar_history(series: Optional[Dict[str, Any]], threshold: float = 1.0) -> Dict[str, Any]:
    sims = series.get("similarGames") if series else None
    if not isinstance(sims, list):
        return {"sample": 0, "hitRate": None, "avg": None}
    vals = [num(g.get("value")) for g in sims if num(g.get("value")) is not None]
    return {
        "sample": len(vals),
        "hitRate": pct(sum(1 for v in vals if v >= threshold), len(vals)) if vals else None,
        "avg": round_or_none(avg(vals), 2),
    }


def parse_hand_context(text: str) -> Dict[str, str]:
    # Examples: "Order 1 • R vs R • 57°F • Wind 12", "OAK vs BAL • R"
    out = {"batSide": "", "pitchHand": ""}
    m = re.search(r"\b([LRBS])\s+vs\s+([LR])\b", text or "", flags=re.I)
    if m:
        out["batSide"] = m.group(1).upper()
        out["pitchHand"] = m.group(2).upper()
    else:
        m = re.search(r"•\s*([LR])\s*(?:$|•)", text or "", flags=re.I)
        if m:
            out["pitchHand"] = m.group(1).upper()
    return out


def collect_batter_research(repo: Path, props: Dict[str, Any], entries: List[Dict[str, Any]], raw_splits: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    players = collect_players(entries, "batter")
    positives = []
    risks = []
    all_research = []

    for p in players:
        pid = p.get("playerId")
        stat_data: Dict[str, Optional[Dict[str, Any]]] = {}
        for stat in BATTER_FEATURE_STATS:
            e = primary_entry(entries, pid, "batter", stat)
            stat_data[stat] = load_series(repo, props, e, stat) if e else None

        h = stat_data.get("H")
        tb = stat_data.get("TB")
        hrr = stat_data.get("HRR")
        k = stat_data.get("K")
        hr = stat_data.get("HR")
        location = p.get("location") or ""
        opponent = p.get("opp") or ""
        hand = parse_hand_context(p.get("boardContext") or "")

        h10 = stat_history(h, 1, 10)
        h5 = stat_history(h, 1, 5)
        tb10 = stat_history(tb, 2, 10)
        hrr10 = stat_history(hrr, 2, 10)
        k10 = stat_history(k, 1, 10)
        k2_10 = stat_history(k, 2, 10)
        hr20 = stat_history(hr, 1, 20)
        loc_h = location_history(h, location, 1)
        opp_h = opponent_history(h, opponent, 1)
        sim_h = similar_history(h, 1)
        sim_tb = similar_history(tb, 2)
        sim_hrr = similar_history(hrr, 2)

        raw = raw_splits.get(norm_name(p.get("player")), {})
        split_notes = []
        if raw:
            ph = hand.get("pitchHand")
            if ph and raw.get("pitchHand", {}).get(ph):
                d = raw["pitchHand"][ph]
                split_notes.append(f"vs {ph}HP raw split: {fmt_num(d.get('avg_hits'), 2)} hits/game over {d.get('sample')} games")
            if location and raw.get("location", {}).get(location.lower()):
                d = raw["location"][location.lower()]
                split_notes.append(f"{location} raw split: {fmt_num(d.get('avg_hits'), 2)} hits/game over {d.get('sample')} games")
            if raw.get("dayNight"):
                # Add only if a game day/night flag was detectable from data.
                for dn, d in raw.get("dayNight", {}).items():
                    split_notes.append(f"{dn.title()} raw split: {fmt_num(d.get('avg_hits'), 2)} hits/game over {d.get('sample')} games")
                    break

        notes = []
        if h10["sample"]:
            notes.append(f"Hit in {round((h10['hitRate'] or 0) * h10['sample'])}/{h10['sample']} recent games; {fmt_num(h10['avg'], 2)} H/game in that span.")
        if h5["sample"] and h10["sample"] and h5.get("avg") is not None and h10.get("avg") is not None:
            diff = h5["avg"] - h10["avg"]
            if abs(diff) >= 0.25:
                notes.append(f"Recent hit pace {'up' if diff > 0 else 'down'}: last 5 at {fmt_num(h5['avg'],2)} H/game vs last 10 at {fmt_num(h10['avg'],2)}.")
        if loc_h["sample"] >= 5:
            notes.append(f"{location} split in logs: hit in {round((loc_h['hitRate'] or 0) * loc_h['sample'])}/{loc_h['sample']}, {fmt_num(loc_h['avg'], 2)} H/game.")
        if opp_h["sample"] >= 2:
            notes.append(f"Recent games vs {opponent}: hit in {round((opp_h['hitRate'] or 0) * opp_h['sample'])}/{opp_h['sample']}, {fmt_num(opp_h['avg'], 2)} H/game.")
        if sim_h["sample"] >= 4:
            notes.append(f"Similar-game sample: hit in {round((sim_h['hitRate'] or 0) * sim_h['sample'])}/{sim_h['sample']}, {fmt_num(sim_h['avg'], 2)} H/game.")
        if tb10["sample"]:
            notes.append(f"2+ total bases in {round((tb10['hitRate'] or 0) * tb10['sample'])}/{tb10['sample']} recent games.")
        if hrr10["sample"]:
            notes.append(f"2+ HRR in {round((hrr10['hitRate'] or 0) * hrr10['sample'])}/{hrr10['sample']} recent games.")
        if k10["sample"]:
            notes.append(f"Strikeout context: {fmt_num(k10['avg'], 2)} K/game last {k10['sample']}; 2+ K in {round((k2_10['hitRate'] or 0) * (k2_10['sample'] or 0))}/{k2_10['sample'] or 0}.")
        if hr20["sample"] and (hr20.get("hitRate") or 0) >= 0.15:
            notes.append(f"HR signal: homered in {round((hr20['hitRate'] or 0) * hr20['sample'])}/{hr20['sample']} recent games.")
        notes.extend(split_notes[:2])

        # Scores intentionally prioritize actual results over model projection.
        hot_score = 0.0
        if h10.get("hitRate") is not None:
            hot_score += (h10["hitRate"] or 0) * 2.0
        if h10.get("avg") is not None:
            hot_score += min(h10["avg"] or 0, 2.0) * 0.6
        if loc_h.get("hitRate") is not None and loc_h.get("sample", 0) >= 5:
            hot_score += (loc_h["hitRate"] or 0) * 0.8
        if sim_h.get("hitRate") is not None and sim_h.get("sample", 0) >= 4:
            hot_score += (sim_h["hitRate"] or 0) * 0.8
        if tb10.get("hitRate") is not None:
            hot_score += (tb10["hitRate"] or 0) * 0.5
        if hrr10.get("hitRate") is not None:
            hot_score += (hrr10["hitRate"] or 0) * 0.5

        cold_score = 0.0
        if h10.get("hitRate") is not None:
            cold_score += max(0, 0.55 - (h10["hitRate"] or 0)) * 2.5
        if h10.get("avg") is not None:
            cold_score += max(0, 0.85 - (h10["avg"] or 0)) * 1.2
        if k10.get("avg") is not None:
            cold_score += max(0, (k10["avg"] or 0) - 1.0) * 0.7
        if k2_10.get("hitRate") is not None:
            cold_score += (k2_10["hitRate"] or 0) * 0.5
        if h5.get("avg") is not None and h10.get("avg") is not None and h5["avg"] < h10["avg"] - 0.25:
            cold_score += 0.6

        projections = {}
        for stat, series in stat_data.items():
            if series:
                projections[stat] = round_or_none(series.get("modelPred") or series.get("modelMu"), 2)

        research = {
            "playerId": pid,
            "player": p.get("player"),
            "team": p.get("team"),
            "opponent": opponent,
            "location": location,
            "context": p.get("boardContext") or "",
            "batSide": hand.get("batSide"),
            "pitchHand": hand.get("pitchHand"),
            "metrics": {
                "hitsLast10": h10,
                "hitsLast5": h5,
                "tb2Last10": tb10,
                "hrr2Last10": hrr10,
                "kLast10": k10,
                "k2Last10": k2_10,
                "hrLast20": hr20,
                "locationHits": loc_h,
                "opponentHits": opp_h,
                "similarHits": sim_h,
                "similarTB2": sim_tb,
                "similarHRR2": sim_hrr,
            },
            "projections": projections,
            "notes": notes[:6],
            "hotScore": round(hot_score, 3),
            "coldScore": round(cold_score, 3),
        }
        all_research.append(research)
        if hot_score >= 2.6 and notes:
            positives.append(research)
        if cold_score >= 1.3 and notes:
            risks.append(research)

    positives.sort(key=lambda x: (x.get("hotScore") or 0), reverse=True)
    risks.sort(key=lambda x: (x.get("coldScore") or 0), reverse=True)
    return positives[:8], risks[:6], all_research


def parse_scores(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None
    nums = re.findall(r"(-?\d+(?:\.\d+)?)", str(text))
    if len(nums) < 2:
        return None
    return float(nums[0]), float(nums[1])


def team_model_form(team: str, results_history: List[Dict[str, Any]], display_limit: int = 5) -> Dict[str, Any]:
    """Build a team model-form card where the stats and visible rows use the same sample.

    The row scores stay in matchup order (away at home) so users do not have to
    mentally flip the numbers between the two team cards. Team-specific stats
    are based on that team's own predicted vs actual runs within the displayed
    sample.
    """
    team = team_norm(team)
    rows = []
    for r in results_history:
        if str(r.get("league") or "").upper() != "MLB":
            continue
        matchup = str(r.get("matchup") or "")
        teams = [team_norm(x) for x in re.split(r"\s+@\s+|\s+vs\s+", matchup)]
        if team not in teams:
            continue
        pred = parse_scores(r.get("predicted") or "")
        actual = parse_scores(r.get("actual") or "")
        if not pred or not actual or len(teams) < 2:
            continue
        away, home = teams[0], teams[1]
        pred_away, pred_home = pred
        act_away, act_home = actual
        if team == away:
            pred_for, pred_against = pred_away, pred_home
            act_for, act_against = act_away, act_home
        else:
            pred_for, pred_against = pred_home, pred_away
            act_for, act_against = act_home, act_away
        pred_margin = pred_for - pred_against
        act_margin = act_for - act_against
        team_error = abs(pred_for - act_for)
        opponent_error = abs(pred_against - act_against)
        scoreboard_error = team_error + opponent_error
        projected_total = pred_away + pred_home
        actual_total = act_away + act_home
        total_error = abs(projected_total - actual_total)
        team_diff = act_for - pred_for
        opponent_diff = act_against - pred_against

        def run_word(value: float) -> str:
            return "run" if abs(value - 1.0) < 0.05 else "runs"

        def scored_text(label: str, diff: float) -> str:
            if abs(diff) < 0.05:
                return f"{label} scored almost exactly as projected."
            if diff > 0:
                return f"{label} scored {abs(diff):.1f} more {run_word(abs(diff))} than projected."
            return f"{label} scored {abs(diff):.1f} fewer {run_word(abs(diff))} than projected."

        def allowed_text(label: str, diff: float) -> str:
            if abs(diff) < 0.05:
                return f"{label} allowed almost exactly the projected runs."
            if diff > 0:
                return f"{label} allowed {abs(diff):.1f} more {run_word(abs(diff))} than projected."
            return f"{label} allowed {abs(diff):.1f} fewer {run_word(abs(diff))} than projected."

        team_diff_text = scored_text(team, team_diff)
        opponent_diff_text = allowed_text(team, opponent_diff)
        scoreboard_text = f"Full scoreboard miss: {scoreboard_error:.1f} total {run_word(scoreboard_error)} across both teams."
        total_text = f"Projected total missed by {total_error:.1f} {run_word(total_error)}."
        rows.append({
            "date": r.get("date") or "",
            "matchup": matchup,
            "awayTeam": away,
            "homeTeam": home,
            "predAway": pred_away,
            "predHome": pred_home,
            "actualAway": act_away,
            "actualHome": act_home,
            "predFor": pred_for,
            "predAgainst": pred_against,
            "actualFor": act_for,
            "actualAgainst": act_against,
            "teamError": team_error,
            "opponentError": opponent_error,
            "scoreboardError": round(scoreboard_error, 2),
            "projectedTotal": round(projected_total, 2),
            "actualTotal": round(actual_total, 2),
            "totalError": round(total_error, 2),
            "teamDiff": round(team_diff, 2),
            "opponentDiff": round(opponent_diff, 2),
            "teamDiffText": team_diff_text,
            "opponentDiffText": opponent_diff_text,
            "scoreboardText": scoreboard_text,
            "totalText": total_text,
            "withinOneFive": team_error <= 1.5,
            "bigMiss": team_error > 1.5,
            "correctSide": (pred_margin >= 0 and act_margin >= 0) or (pred_margin < 0 and act_margin < 0),
            "scoreError": abs(pred_for - act_for) + abs(pred_against - act_against),
            "overUnderTeam": "over" if act_for > pred_for + 0.25 else "under" if act_for < pred_for - 0.25 else "near",
        })
    rows.sort(key=lambda x: x.get("date") or "")
    sample_rows = rows[-display_limit:]
    correct = sum(1 for r in sample_rows if r.get("correctSide"))
    avg_team_err = avg([r.get("teamError") for r in sample_rows])
    within_15 = sum(1 for r in sample_rows if r.get("withinOneFive"))
    big_miss = sum(1 for r in sample_rows if r.get("bigMiss"))
    # Do not assign a vague "Hot/Solid/Cold" badge here. The metrics below
    # are clearer and avoid over-selling a small five-game sample.
    label = ""
    return {
        "team": team,
        "sample": len(sample_rows),
        "availableSettledGames": len(rows),
        "displayLimit": display_limit,
        "sideCorrect": correct,
        "sideAccuracy": pct(correct, len(sample_rows)) if sample_rows else None,
        "avgTeamRunError": round_or_none(avg_team_err, 1),
        "withinOneFiveCount": within_15,
        "withinOneFiveRate": pct(within_15, len(sample_rows)) if sample_rows else None,
        "bigMissCount": big_miss,
        "teamOverCount": sum(1 for r in sample_rows if r.get("overUnderTeam") == "over"),
        "teamUnderCount": sum(1 for r in sample_rows if r.get("overUnderTeam") == "under"),
        "label": label,
        "games": sample_rows,
        "coverageNote": f"Stats use the same {len(sample_rows)} settled games shown below. Model and final scores stay in away/home order; the explanation is specific to {team}.",
    }


def snapshot_game(repo: Path, game: Dict[str, Any], target_date: str) -> None:
    # Archive current projection for future movement reads. Keep it small.
    if not target_date:
        return
    snap_dir = repo / "data" / "prediction_snapshots" / "mlb" / target_date
    snap_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    key = f"{game.get('gamePk') or game.get('id')}_{stamp}.json"
    payload = {
        "capturedAt": local_now(),
        "gameId": game.get("id"),
        "gamePk": game.get("gamePk"),
        "awayTeam": game.get("awayTeam"),
        "homeTeam": game.get("homeTeam"),
        "gameDate": game.get("gameDate") or target_date,
        "modelAwayScore": game.get("modelAwayScore"),
        "modelHomeScore": game.get("modelHomeScore"),
        "modelTotal": game.get("modelTotal"),
        "homeWinProb": game.get("homeWinProb"),
        "awayWinProb": game.get("awayWinProb"),
        "nrfiProb": game.get("nrfiProb"),
        "yrfiProb": game.get("yrfiProb"),
    }
    write_json(snap_dir / key, payload)


def movement_from_game_records(game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Use the existing week-to-game movement already shown in the game page.

    The previous Game Intelligence section only looked at newly saved intraday
    snapshots, so it could miss the meaningful movement that already exists on
    the page in game["movement"]. This function links the research section to
    that same movement source.
    """
    rows = [r for r in (game.get("movement") or []) if isinstance(r, dict)]
    if len(rows) < 2:
        return None

    def has_scores(row: Dict[str, Any]) -> bool:
        return num(row.get("predictedAway")) is not None and num(row.get("predictedHome")) is not None

    rows = [r for r in rows if has_scores(r)]
    if len(rows) < 2:
        return None

    rows.sort(key=lambda x: str(x.get("date") or x.get("capturedAt") or ""))
    first, last = rows[0], rows[-1]

    away = game.get("awayTeam") or "Away"
    home = game.get("homeTeam") or "Home"

    def value(row: Dict[str, Any], *keys: str) -> Optional[float]:
        for k in keys:
            v = num(row.get(k))
            if v is not None:
                return v
        return None

    def delta(*keys: str) -> Optional[float]:
        a = value(first, *keys)
        b = value(last, *keys)
        return round_or_none(b - a, 3) if a is not None and b is not None else None

    first_away = value(first, "predictedAway", "modelAwayScore")
    last_away = value(last, "predictedAway", "modelAwayScore")
    first_home = value(first, "predictedHome", "modelHomeScore")
    last_home = value(last, "predictedHome", "modelHomeScore")
    first_total = value(first, "modelTotal")
    last_total = value(last, "modelTotal")
    first_spread = value(first, "modelHomeSpread")
    last_spread = value(last, "modelHomeSpread")

    # The page's main movement table stores modelHomeSpread, where negative means
    # the away team is favored by that many runs. Convert it into a readable team
    # spread label for bullets.
    def spread_label(home_spread: Optional[float]) -> str:
        if home_spread is None:
            return "—"
        # modelHomeSpread = home - away. Negative means away projected ahead.
        if home_spread < 0:
            return f"{away} {home_spread:+.2f}"
        if home_spread > 0:
            return f"{home} {-home_spread:+.2f}"
        return "Pick'em"

    movements = {
        "awayScoreDelta": delta("predictedAway", "modelAwayScore"),
        "homeScoreDelta": delta("predictedHome", "modelHomeScore"),
        "totalDelta": delta("modelTotal"),
        "modelSpreadDelta": delta("modelHomeSpread"),
        "homeWinProbDelta": delta("homeWinProb"),
        "awayWinProbDelta": delta("awayWinProb"),
        "favoriteWinProbDelta": delta("favoriteWinProb"),
        "favoriteCoverProbDelta": delta("favoriteCoverProb", "marketCoverProb"),
        "nrfiProbDelta": delta("nrfiProb"),
        "yrfiProbDelta": delta("yrfiProb"),
        "marketOverProbDelta": delta("marketOverProb", "fallbackOverProb"),
    }

    bullets: List[str] = []
    away_d = movements.get("awayScoreDelta")
    home_d = movements.get("homeScoreDelta")
    total_d = movements.get("totalDelta")
    nrfi_d = movements.get("nrfiProbDelta")
    fav_d = movements.get("favoriteWinProbDelta")
    cover_d = movements.get("favoriteCoverProbDelta")

    if away_d is not None and abs(away_d) >= 0.10:
        bullets.append(f"{away} run projection moved {away_d:+.2f}, from {first_away:.2f} to {last_away:.2f}.")
    if home_d is not None and abs(home_d) >= 0.10:
        bullets.append(f"{home} run projection moved {home_d:+.2f}, from {first_home:.2f} to {last_home:.2f}.")
    if first_spread is not None and last_spread is not None and abs(last_spread - first_spread) >= 0.10:
        bullets.append(f"Model spread moved from {spread_label(first_spread)} to {spread_label(last_spread)}.")
    if total_d is not None and abs(total_d) >= 0.10:
        bullets.append(f"Projected total moved {total_d:+.2f}, from {first_total:.2f} to {last_total:.2f}.")
    if fav_d is not None and abs(fav_d) >= 0.02:
        bullets.append(f"Win probability for the listed model favorite moved {fav_d:+.1%}.")
    if cover_d is not None and abs(cover_d) >= 0.02:
        bullets.append(f"Cover probability moved {cover_d:+.1%} across the saved movement records.")
    if nrfi_d is not None and abs(nrfi_d) >= 0.02:
        bullets.append(f"NRFI probability moved {nrfi_d:+.1%}.")

    analysis_parts: List[str] = []
    side_delta = None
    if first_away is not None and last_away is not None and first_home is not None and last_home is not None:
        first_away_margin = first_away - first_home
        last_away_margin = last_away - last_home
        side_delta = round_or_none(last_away_margin - first_away_margin, 3)
        if side_delta is not None and abs(side_delta) >= 0.15:
            toward = away if side_delta > 0 else home
            analysis_parts.append(
                f"The side movement strengthened toward {toward}: {away} moved {away_d:+.2f} runs while {home} moved {home_d:+.2f}, changing the projected margin by {side_delta:+.2f} runs."
            )
        elif away_d is not None and home_d is not None and abs(away_d) >= 0.10 and abs(home_d) >= 0.10:
            if away_d > 0 and home_d > 0:
                analysis_parts.append(
                    f"Both offenses moved up ({away} {away_d:+.2f}, {home} {home_d:+.2f}), so the movement is more about a higher-scoring game environment than a stronger side."
                )
            elif away_d < 0 and home_d < 0:
                analysis_parts.append(
                    f"Both offenses moved down ({away} {away_d:+.2f}, {home} {home_d:+.2f}), so the movement points more toward run suppression than a clearer side."
                )
    if total_d is not None and abs(total_d) >= 0.30:
        if total_d > 0:
            analysis_parts.append(f"The projected total climbed {total_d:+.2f}, which points to more offensive expectation than the earliest saved read.")
        else:
            analysis_parts.append(f"The projected total fell {total_d:+.2f}, which points to a lower-run game script than the earliest saved read.")
    if nrfi_d is not None and abs(nrfi_d) >= 0.05:
        if nrfi_d < 0:
            analysis_parts.append(f"NRFI probability dropped {nrfi_d:+.1%}, so the first-inning read became more YRFI/early-scoring friendly.")
        else:
            analysis_parts.append(f"NRFI probability rose {nrfi_d:+.1%}, so the first-inning read became more pitcher-friendly early.")
    if not analysis_parts and bullets:
        analysis_parts.append("Movement exists, but it is not large enough in one direction to materially change the read from the earliest saved projection.")

    return {
        "available": True,
        "source": "game_movement",
        "title": "Week-to-game movement read",
        "description": "Interprets the same saved movement records shown in the main prediction movement chart.",
        "firstDate": first.get("date") or first.get("capturedAt"),
        "latestDate": last.get("date") or last.get("capturedAt"),
        "movements": movements,
        "movementToward": (away if side_delta is not None and side_delta > 0.15 else home if side_delta is not None and side_delta < -0.15 else None),
        "awayMarginDelta": side_delta,
        "analysis": " ".join(analysis_parts),
        "bullets": bullets,
        "snapshots": rows,
    }


def read_snapshots(repo: Path, game: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    # Prefer the existing game.movement array because it is the source already
    # powering the movement chart/table on the detail page.
    linked = movement_from_game_records(game)
    if linked:
        return linked

    # Fallback to same-day snapshots created by this builder. This is useful if
    # game.movement is absent in a future build but the builder runs multiple
    # times before game start.
    snap_dir = repo / "data" / "prediction_snapshots" / "mlb" / target_date
    rows = []
    if snap_dir.exists():
        for p in snap_dir.glob("*.json"):
            s = read_json(p, {}) or {}
            if str(s.get("gamePk") or "") == str(game.get("gamePk") or "") or str(s.get("gameId") or "") == str(game.get("id") or ""):
                rows.append(s)
    rows.sort(key=lambda x: x.get("capturedAt") or "")
    if len(rows) < 2:
        return {
            "available": False,
            "source": "builder_snapshots",
            "title": "Intraday snapshot movement",
            "description": "Needs at least two builder snapshots from the same game day.",
            "summary": "Prediction movement needs game.movement records or at least two builder snapshots from the same game day. This run captured the current snapshot.",
            "snapshots": rows,
        }
    first, last = rows[0], rows[-1]
    def delta(k: str) -> Optional[float]:
        a, b = num(first.get(k)), num(last.get(k))
        return round_or_none(b - a, 3) if a is not None and b is not None else None
    movements = {
        "awayScoreDelta": delta("modelAwayScore"),
        "homeScoreDelta": delta("modelHomeScore"),
        "totalDelta": delta("modelTotal"),
        "homeWinProbDelta": delta("homeWinProb"),
        "nrfiProbDelta": delta("nrfiProb"),
    }
    bullets = []
    away_d = movements.get("awayScoreDelta")
    home_d = movements.get("homeScoreDelta")
    if away_d is not None and abs(away_d) >= 0.1:
        bullets.append(f"{game.get('awayTeam')} run projection moved {away_d:+.2f} from first to latest builder snapshot.")
    if home_d is not None and abs(home_d) >= 0.1:
        bullets.append(f"{game.get('homeTeam')} run projection moved {home_d:+.2f} from first to latest builder snapshot.")
    if movements.get("totalDelta") is not None and abs(movements["totalDelta"]) >= 0.1:
        bullets.append(f"Game total projection moved {movements['totalDelta']:+.2f}.")
    if movements.get("nrfiProbDelta") is not None and abs(movements["nrfiProbDelta"]) >= 0.02:
        bullets.append(f"NRFI probability moved {movements['nrfiProbDelta']:+.1%}.")
    return {
        "available": True,
        "source": "builder_snapshots",
        "title": "Intraday snapshot movement",
        "description": "First builder snapshot vs latest builder snapshot from this game day.",
        "movements": movements,
        "bullets": bullets,
        "snapshots": rows,
    }


def build_first_inning_map(mlb_data_dir: Optional[Path], repo: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort optional enrichment.

    Preferred source is data/derived/pitcher_first_inning_runs.json, produced by
    tools/build_pitcher_first_inning_lookup.py. That lookup supports parquet and
    CSV inference from pitcher_game_logs + game_team_box/linescore files.

    The legacy fallback below still scans CSV files directly if the derived
    lookup was not created yet.
    """
    if repo is not None:
        cache_path = repo / "data" / "derived" / "pitcher_first_inning_runs.json"
        cached = read_json(cache_path, {}) or {}
        lookup = cached.get("lookup") if isinstance(cached, dict) else None
        if isinstance(lookup, dict) and lookup:
            return lookup
    if not mlb_data_dir or not mlb_data_dir.exists():
        return {}
    roots = [mlb_data_dir / "pitcher_game_logs", mlb_data_dir]
    files = []
    for root in roots:
        if root.exists():
            files.extend(list(root.rglob("*.csv")))
    files = files[:300]
    out: Dict[str, Any] = {}
    name_cols = ["player", "pitcher", "player_name", "pitcher_name", "name"]
    id_cols = ["playerId", "player_id", "pitcherId", "pitcher_id", "mlbam_id", "id"]
    date_cols = ["gameDate", "game_date", "date"]
    game_cols = ["gameId", "game_id", "gamePk", "game_pk"]
    direct_cols = ["first_inning_runs_allowed", "firstInningRunsAllowed", "first_inning_ra", "inning1_runs_allowed", "ra_1st", "r_1st", "runs_allowed_1st"]
    inning_cols = ["inning", "inning_number", "inn"]
    run_cols = ["runs", "r", "runs_allowed", "ra", "earnedRuns", "earned_runs", "er"]

    for fp in files:
        try:
            with fp.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                fields = set(reader.fieldnames)
                dcol = next((c for c in direct_cols if c in fields), None)
                icol = next((c for c in inning_cols if c in fields), None)
                rcol = next((c for c in run_cols if c in fields), None)
                if not dcol and not (icol and rcol):
                    continue
                ncol = next((c for c in name_cols if c in fields), None)
                pidcol = next((c for c in id_cols if c in fields), None)
                datecol = next((c for c in date_cols if c in fields), None)
                gamecol = next((c for c in game_cols if c in fields), None)
                for row in reader:
                    if icol:
                        inn = str(row.get(icol) or "").strip().lower()
                        if inn not in {"1", "1.0", "top 1", "bottom 1", "first"}:
                            continue
                    runs = num(row.get(dcol) if dcol else row.get(rcol))
                    if runs is None:
                        continue
                    src = str(fp)
                    if pidcol:
                        pid = str(row.get(pidcol) or "").strip()
                        if pid:
                            if gamecol and row.get(gamecol):
                                out[f"id:{pid}|game:{row.get(gamecol)}"] = {"runs": runs, "source": src}
                            if datecol and row.get(datecol):
                                out[f"id:{pid}|date:{safe_date(row.get(datecol))}"] = {"runs": runs, "source": src}
                    if ncol:
                        nm = norm_name(row.get(ncol))
                        if nm:
                            if gamecol and row.get(gamecol):
                                out[f"name:{nm}|game:{row.get(gamecol)}"] = {"runs": runs, "source": src}
                            if datecol and row.get(datecol):
                                out[f"name:{nm}|date:{safe_date(row.get(datecol))}"] = {"runs": runs, "source": src}
        except Exception:
            continue
    return out


def build_raw_batter_splits(mlb_data_dir: Optional[Path]) -> Dict[str, Any]:
    if not mlb_data_dir or not mlb_data_dir.exists():
        return {}
    root = mlb_data_dir / "batter_game_logs"
    if not root.exists():
        return {}
    files = list(root.rglob("*.csv"))[:300]
    rows_by_player: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fields = set(reader.fieldnames or [])
                name_col = next((c for c in ["player", "batter", "player_name", "name"] if c in fields), None)
                hit_col = next((c for c in ["H", "h", "hits", "hit"] if c in fields), None)
                if not name_col or not hit_col:
                    continue
                loc_col = next((c for c in ["location", "home_away", "isHome", "homeAway"] if c in fields), None)
                hand_col = next((c for c in ["oppPitchHand", "startingPitcherHand", "pitcher_hand", "throws", "p_throws"] if c in fields), None)
                dn_col = next((c for c in ["dayNight", "day_night", "game_type_time", "timeOfDay"] if c in fields), None)
                for row in reader:
                    nm = norm_name(row.get(name_col))
                    h = num(row.get(hit_col))
                    if not nm or h is None:
                        continue
                    loc = str(row.get(loc_col) or "").strip().lower() if loc_col else ""
                    if loc in {"1", "true", "h", "home"}: loc = "home"
                    if loc in {"0", "false", "a", "away", "road"}: loc = "away"
                    hand = str(row.get(hand_col) or "").strip().upper()[:1] if hand_col else ""
                    dn = str(row.get(dn_col) or "").strip().lower() if dn_col else ""
                    rows_by_player[nm].append({"hits": h, "location": loc, "pitchHand": hand, "dayNight": dn})
        except Exception:
            continue
    out = {}
    for nm, rows in rows_by_player.items():
        data = {"location": {}, "pitchHand": {}, "dayNight": {}}
        for field, values in [("location", ["home", "away"]), ("pitchHand", ["L", "R"]), ("dayNight", ["day", "night"] )]:
            for val in values:
                subset = [r for r in rows if r.get(field) == val]
                if len(subset) >= 3:
                    data[field][val] = {
                        "sample": len(subset),
                        "avg_hits": round_or_none(avg([r["hits"] for r in subset]), 2),
                        "hit_rate": pct(sum(1 for r in subset if r["hits"] >= 1), len(subset)),
                    }
        if any(data[k] for k in data):
            out[nm] = data
    return out


def quick_writeup(game: Dict[str, Any], pitcher_reports: List[Dict[str, Any]], positives: List[Dict[str, Any]], risks: List[Dict[str, Any]], movement: Dict[str, Any], forms: Dict[str, Any]) -> str:
    away, home = game.get("awayTeam"), game.get("homeTeam")
    pieces = []
    if num(game.get("modelAwayScore")) is not None and num(game.get("modelHomeScore")) is not None:
        pieces.append(f"The current model score is {away} {fmt_num(game.get('modelAwayScore'),2)} at {home} {fmt_num(game.get('modelHomeScore'),2)}, with a projected total of {fmt_num(game.get('modelTotal'),2)}.")
    if movement.get("available") and movement.get("analysis"):
        pieces.append("Movement read: " + movement["analysis"])
    elif movement.get("available") and movement.get("bullets"):
        pieces.append("Movement read: " + " ".join(movement.get("bullets", [])[:2]))
    else:
        pieces.append("Movement read: this page needs saved movement records or another builder run before it can explain how the model changed.")
    if pitcher_reports:
        best = sorted(pitcher_reports, key=lambda p: (num(p.get("last5Summary", {}).get("avgER")) if num(p.get("last5Summary", {}).get("avgER")) is not None else 999))[0]
        bs = best.get('last5Summary', {})
        if bs.get('hasStartByStartLogs'):
            pieces.append(f"Pitching context: {best.get('player')} has the better recent run-prevention profile in the available start logs at {fmt_num(bs.get('avgER'),1)} ER over the last {bs.get('startsCount')} starts.")
        else:
            pieces.append(f"Pitching context: detailed start-by-start logs were not available for every starter, so the page separates actual starts from analyzer L3/L5/L10 windows instead of treating those windows as box scores.")
    if positives:
        names = ", ".join([p.get("player") or "" for p in positives[:3]])
        pieces.append(f"Batter research is strongest for {names}, based on recent hit rates, matching location/opponent samples, or similar-game production.")
    if risks:
        names = ", ".join([p.get("player") or "" for p in risks[:2]])
        pieces.append(f"The cold/risk list flags {names} because the recent hit profile or strikeout trend is weaker than the projection alone would show.")
    return " ".join([p for p in pieces if p])


def build_report_for_game(repo: Path, props: Dict[str, Any], entries: List[Dict[str, Any]], game: Dict[str, Any], target_date: str, results_history: List[Dict[str, Any]], first_inning_map: Dict[str, Any], raw_splits: Dict[str, Any]) -> Dict[str, Any]:
    snapshot_game(repo, game, target_date)
    movement = read_snapshots(repo, game, target_date)
    pitcher_players = collect_players(entries, "pitcher")
    pitcher_reports = [combine_pitcher_last_starts(repo, props, entries, p, first_inning_map) for p in pitcher_players]
    positives, risks, all_batter_research = collect_batter_research(repo, props, entries, raw_splits)
    forms = {
        str(game.get("awayTeam")): team_model_form(game.get("awayTeam"), results_history),
        str(game.get("homeTeam")): team_model_form(game.get("homeTeam"), results_history),
    }
    first_inning = {
        "nrfiProb": game.get("nrfiProb"),
        "yrfiProb": game.get("yrfiProb"),
        "pitcherSamples": [
            {
                "player": p.get("player"),
                "team": p.get("team"),
                "location": p.get("location"),
                "sample": p.get("last5Summary", {}).get("firstInningSamples"),
                "runAllowedRate": p.get("last5Summary", {}).get("firstInningRunAllowedRate"),
                "overallSamples": p.get("last5Summary", {}).get("firstInningOverallSamples"),
                "overallRunAllowedRate": p.get("last5Summary", {}).get("firstInningOverallRunAllowedRate"),
                "showOverallFirstInning": p.get("last5Summary", {}).get("showOverallFirstInning"),
                "locationSamples": p.get("last5Summary", {}).get("firstInningLocationSamples"),
                "locationRunAllowedRate": p.get("last5Summary", {}).get("firstInningLocationRunAllowedRate"),
                "showLocationFirstInning": p.get("last5Summary", {}).get("showLocationFirstInning"),
                "nonStartRows": p.get("last5Summary", {}).get("firstInningNonStartRows"),
                "unresolvedRows": p.get("last5Summary", {}).get("firstInningUnresolvedRows"),
            }
            for p in pitcher_reports
        ],
        "note": "Starter first-inning run history requires raw inning-level/pitcher-log data. It is shown when those columns are found locally.",
    }
    return {
        "schemaVersion": "2.9",
        "generatedAt": local_now(),
        "gameId": game.get("id"),
        "gamePk": game.get("gamePk"),
        "league": "MLB",
        "date": game.get("gameDate") or target_date,
        "awayTeam": game.get("awayTeam"),
        "homeTeam": game.get("homeTeam"),
        "headline": f"{game.get('awayTeam')} @ {game.get('homeTeam')} matchup research",
        "quickWriteup": quick_writeup(game, pitcher_reports, positives, risks, movement, forms),
        "modelForm": forms,
        "predictionMovement": movement,
        "pitchingMatchup": pitcher_reports,
        "firstInningOutlook": first_inning,
        "batterResearch": {
            "positiveSignals": positives,
            "riskFlags": risks,
            "allPlayers": all_batter_research,
        },
        "dataCoverage": {
            "propsAnalyzerEntries": len(entries),
            "firstInningHistoryFound": bool(first_inning_map),
            "rawBatterSplitsFound": bool(raw_splits),
        },
    }


def copy_into_detail_files(repo: Path, report: Dict[str, Any], game: Dict[str, Any]) -> None:
    # Also tuck a lightweight copy into the existing game detail json if it exists.
    detail_path = str(game.get("detailPath") or "").replace("\\", "/")
    if not detail_path:
        return
    p = repo / detail_path
    if not p.exists():
        return
    d = read_json(p, {}) or {}
    d["gameIntelligence"] = {
        "reportPath": report.get("reportPath"),
        "quickWriteup": report.get("quickWriteup"),
        "dataCoverage": report.get("dataCoverage"),
    }
    write_json(p, d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--website-repo", default=".", help="Path to letsparlayml.github.io repo")
    ap.add_argument("--mlb-data-dir", default="", help="Optional C:\\python\\mlb_data for first-inning/split enrichment")
    ap.add_argument("--target-date", default="", help="Override target date")
    args = ap.parse_args()

    repo = Path(args.website_repo).resolve()
    data_dir = repo / "data"
    games = read_json(data_dir / "games.json", []) or []
    site = read_json(data_dir / "site.json", {}) or {}
    props = load_props_analyzer(repo)
    results_history = read_json(data_dir / "results_history.json", []) or []
    target_date = args.target_date or props.get("targetDate") or site.get("targetDate") or ""
    if not target_date:
        raise SystemExit("No target date found. Provide --target-date or ensure site.json/mlb_props_analyzer.json has one.")

    mlb_data = Path(args.mlb_data_dir).resolve() if args.mlb_data_dir else None
    first_inning_map = build_first_inning_map(mlb_data, repo)
    raw_splits = build_raw_batter_splits(mlb_data)

    by_gid = entries_by_game(props, target_date)
    out_dir = data_dir / "game_intelligence"
    if out_dir.exists():
        # keep snapshots separate; replace reports cleanly
        for p in out_dir.glob("*.json"):
            try: p.unlink()
            except Exception: pass
    out_dir.mkdir(parents=True, exist_ok=True)

    index = {"generatedAt": local_now(), "targetDate": target_date, "reports": []}
    built = 0
    for game in games:
        if str(game.get("league") or "").upper() != "MLB":
            continue
        game_date = str(game.get("gameDate") or target_date)
        if game_date != target_date:
            continue
        gid = str(game.get("gamePk") or "")
        entries = by_gid.get(gid, [])
        if not entries:
            # Don't build empty fluff reports.
            continue
        report = build_report_for_game(repo, props, entries, game, target_date, results_history, first_inning_map, raw_splits)
        filename = f"mlb_{target_date}_{slug_part(game.get('awayTeam'))}_{slug_part(game.get('homeTeam'))}_{game.get('gamePk') or game.get('id')}.json"
        rel = f"data/game_intelligence/{filename}"
        report["reportPath"] = rel
        write_json(repo / rel, report)
        copy_into_detail_files(repo, report, game)
        index["reports"].append({
            "gameId": game.get("id"),
            "gamePk": game.get("gamePk"),
            "league": "MLB",
            "date": target_date,
            "awayTeam": game.get("awayTeam"),
            "homeTeam": game.get("homeTeam"),
            "path": rel,
        })
        built += 1
    write_json(out_dir / "index.json", index)
    print(f"Built {built} MLB Game Intelligence report(s) for {target_date}.")
    print(f"First-inning raw history found: {bool(first_inning_map)}")
    print(f"Raw batter split enrichment found: {bool(raw_splits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
