#!/usr/bin/env python
r"""
Build a starter first-inning runs allowed lookup for Game Intelligence.

Default mode is incremental: it loads the existing lookup, finds the current slate
pitchers from the MLB props analyzer, checks the last-start gameIds already stored,
and only appends missing pitcher-game rows. This avoids rescanning the full local
MLB data folder every time the after-predictions batch runs.

Use --full-rebuild only when you intentionally want to recreate the lookup from
all discoverable local parquet/CSV sources.

Primary output:
  <website-repo>/data/derived/pitcher_first_inning_runs.json

Audit output:
  <website-repo>/data/derived/pitcher_first_inning_runs_audit.csv

It supports two data shapes:
  1) Direct pitcher logs with a first-inning runs column.
  2) Inferred from pitcher_game_logs starters + game_team_box/linescore first-inning runs.

Run example:
  python tools/build_pitcher_first_inning_lookup.py ^
    --website-repo C:\Docs\letsparlayml.github.io ^
    --mlb-data-dir C:\python\mlb_data
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit("pandas is required for reading parquet/csv MLB data files") from exc


# ----------------------------- basic helpers -----------------------------

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def norm_name(value: Any) -> str:
    s = str(value or "").lower()
    trans = str.maketrans({
        "á":"a","à":"a","ä":"a","â":"a","ã":"a","å":"a",
        "é":"e","è":"e","ë":"e","ê":"e",
        "í":"i","ì":"i","ï":"i","î":"i",
        "ó":"o","ò":"o","ö":"o","ô":"o","õ":"o",
        "ú":"u","ù":"u","ü":"u","û":"u",
    })
    s = s.translate(trans)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()




def clean_id(value: Any) -> str:
    """Return stable MLBAM/game ids without .0 suffixes."""
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


def statcast_pitcher_display_name(value: Any) -> str:
    """Statcast player_name is usually 'Last, First'. Convert for display/name keys."""
    s = str(value or "").strip()
    if "," in s:
        last, first = [x.strip() for x in s.split(",", 1)]
        if first and last:
            return f"{first} {last}".strip()
    return s

def team_norm(value: Any) -> str:
    s = str(value or "").upper().strip()
    aliases = {
        "AZ": "ARI", "ARZ": "ARI", "WSH": "WAS", "WSN": "WAS",
        "CWS": "CHW", "CHA": "CHW", "CHICAGO WHITE SOX": "CHW",
        "CHC": "CHC", "CHN": "CHC", "LA": "LAD", "LAN": "LAD",
        "LAA": "LAA", "ANA": "LAA", "NYM": "NYM", "NYN": "NYM",
        "NYY": "NYY", "NYA": "NYY", "SF": "SF", "SFG": "SF", "SFN": "SF",
        "SD": "SD", "SDP": "SD", "TB": "TB", "TBR": "TB", "TBA": "TB",
        "KC": "KC", "KCR": "KC", "MIA": "MIA", "FLA": "MIA",
    }
    s = re.sub(r"[^A-Z0-9]", "", s)
    return aliases.get(s, s)


def safe_date(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    if "T" in s:
        return s.split("T", 1)[0]
    # pandas Timestamp string, MM/DD/YYYY, YYYYMMDD fallback
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.notna(dt):
            return str(dt.date())
    except Exception:
        pass
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s[:10]


def num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    s = str(value).strip()
    if s == "":
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def parse_boolish(value: Any) -> Optional[bool]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"1", "true", "t", "yes", "y", "starter", "start", "sp", "gs"}:
        return True
    if s in {"0", "false", "f", "no", "n", "relief", "reliever", "rp"}:
        return False
    return None


def parse_ip(value: Any) -> Optional[float]:
    """Baseball IP parser: 5.2 means 5 + 2 outs, not 5.2 innings."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    s = str(value).strip()
    if not s:
        return None
    if "." in s:
        left, right = s.split(".", 1)
        if left.lstrip("-").isdigit() and right[:1].isdigit():
            whole = int(left)
            outs = int(right[:1])
            if outs in {0, 1, 2}:
                return whole + outs / 3.0
    return num(s)


def col_lookup(columns: Iterable[str]) -> Dict[str, str]:
    return {norm_key(c): c for c in columns}


def find_col(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lookup = col_lookup(columns)
    for c in candidates:
        actual = lookup.get(norm_key(c))
        if actual:
            return actual
    return None


def find_cols_regex(columns: Iterable[str], patterns: Iterable[str]) -> List[str]:
    out = []
    for c in columns:
        ck = norm_key(c)
        for pat in patterns:
            if re.search(pat, ck, flags=re.I):
                out.append(c)
                break
    return out


def clean_scalar(value: Any) -> Any:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


# ----------------------------- file loading -----------------------------

RELEVANT_NAME_PATTERNS = [
    "pitcher", "statcast_pitch_level", "statcast", "pitch_level", "game_team_box", "team_box", "box", "line", "inning", "pbp", "play",
    "gamecenter", "score", "game_log", "gamelog",
]


def relevant_file(path: Path, scan_all: bool = False) -> bool:
    if scan_all:
        return path.suffix.lower() in {".parquet", ".csv"}
    low = str(path).lower()
    return path.suffix.lower() in {".parquet", ".csv"} and any(p in low for p in RELEVANT_NAME_PATTERNS)


def discover_files(mlb_data_dir: Path, scan_all: bool = False, max_files: int = 2000) -> List[Path]:
    files: List[Path] = []
    priority_roots = [
        mlb_data_dir / "pitcher_game_logs",
        mlb_data_dir / "game_team_box",
        mlb_data_dir / "game_team_boxes",
        mlb_data_dir / "team_box",
        mlb_data_dir / "team_boxes",
        mlb_data_dir / "linescore",
        mlb_data_dir / "linescores",
        mlb_data_dir / "pbp",
        mlb_data_dir / "play_by_play",
    ]
    seen = set()
    for root in priority_roots + [mlb_data_dir]:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and relevant_file(p, scan_all=scan_all):
                key = str(p.resolve()).lower()
                if key not in seen:
                    files.append(p)
                    seen.add(key)
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break
    return files


def read_table(path: Path) -> Optional[pd.DataFrame]:
    try:
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, low_memory=False)
    except Exception as exc:
        print(f"WARN: could not read {path}: {exc}")
        return None
    return None



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


def load_existing_lookup(json_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load the existing public lookup and add a low internal priority.

    Existing rows should normally be kept. New rows with a higher source priority
    can still replace them if a better source is found.
    """
    payload = read_json(json_path, {}) or {}
    raw = payload.get("lookup") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = {**v, "priority": int(v.get("priority", 10) or 10)}
    return out


def load_existing_audit(audit_path: Path) -> List[Dict[str, Any]]:
    if not audit_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with audit_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(dict(r))
    except Exception:
        return []
    return rows


def dedupe_audit(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        key = (
            str(r.get("date") or ""),
            clean_id(r.get("gameId") or ""),
            clean_id(r.get("playerId") or ""),
            norm_name(r.get("player") or ""),
            str(r.get("method") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


NON_START_STATUSES = {
    "relief_or_bulk_after_opener",
    "not_first_inning_pitcher",
    "appeared_after_first_inning",
    "did_not_start",
    "not_in_statcast_for_game",
    "no_statcast_pitch_data",
}


def lookup_row_resolved(value: Any) -> bool:
    """A lookup row is resolved if it has a numeric 1st-inning RA value
    or a deliberate non-start / unavailable classification.

    Without this, bullpen/bulk appearances get retried every daily run and keep
    printing as scary missing rows even though there is no first-inning RA to
    assign to that pitcher.
    """
    if not isinstance(value, dict):
        return False
    if num(value.get("runs")) is not None:
        method = str(value.get("method") or "").strip().lower()
        starter_method = str(value.get("starterMethod") or value.get("starter_method") or "").strip().lower()
        verified = value.get("actualStarterVerified") is True
        legacy_unsafe = (
            method == "statsapi_first_inning_from_current_pitcher_series"
            or (
                "current_slate_pitcher_series" in starter_method
                and "first_pitcher_in_half_inning" not in method
                and not verified
            )
        )
        if legacy_unsafe:
            return False
        return True
    status = str(value.get("status") or "").strip().lower()
    return status in NON_START_STATUSES


def start_has_lookup(lookup: Dict[str, Dict[str, Any]], start: Dict[str, Any]) -> bool:
    for k in build_keys(start.get("playerId"), start.get("player"), start.get("gameId"), start.get("date")):
        if lookup_row_resolved(lookup.get(k)):
            return True
    return False


def missing_current_starts(
    repo: Path,
    mlb_data_dir: Path,
    target_date: str,
    lookup: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    starts, source_diag = combined_current_pitcher_starts(repo, mlb_data_dir, target_date)
    missing = [s for s in starts if not start_has_lookup(lookup, s)]
    return starts, missing, source_diag


def parse_first_from_cell(value: Any) -> Optional[float]:
    """Parse first-inning runs from list/json/string line-score cells.

    This catches shapes like [0,1,0,...], "0,1,0", {"1": 0},
    {"innings": [{"runs": 0}, ...]}, or MLB-ish lineScore cells.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    obj = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
            try:
                obj = json.loads(text)
            except Exception:
                obj = text
        else:
            # Common saved line-score shape: "0,2,0,1,0" or "0|2|0|1".
            if re.search(r"\d", text) and re.search(r"[,|;/ ]", text):
                nums = re.findall(r"-?\d+(?:\.\d+)?", text)
                if nums:
                    return num(nums[0])
            return None
    if isinstance(obj, (list, tuple)):
        if not obj:
            return None
        first = obj[0]
        if isinstance(first, dict):
            for k in ["runs", "R", "r", "score"]:
                v = num(first.get(k))
                if v is not None:
                    return v
            return None
        return num(first)
    if isinstance(obj, dict):
        # Direct keyed dict.
        for k in ["1", "01", "1st", "first", "firstInning", "first_inning", "r1", "R1"]:
            if k in obj:
                v = obj[k]
                if isinstance(v, dict):
                    for kk in ["runs", "R", "r", "score"]:
                        n = num(v.get(kk))
                        if n is not None:
                            return n
                n = num(v)
                if n is not None:
                    return n
        # MLB-ish nested inning array.
        for k in ["innings", "line", "linescore", "lineScore", "runsByInning", "runs_by_inning"]:
            if k in obj:
                n = parse_first_from_cell(obj[k])
                if n is not None:
                    return n
        # MLB side shape: {"home": {"runs": ...}, "away": ...} is handled elsewhere.
    return None


def find_side_line_array_col(columns: Iterable[str], side: str) -> Optional[str]:
    """Find a home/away line-score array column, not a single first-inning column."""
    side_key = norm_key(side)
    candidates = []
    for c in columns:
        ck = norm_key(c)
        if not ck.startswith(side_key):
            continue
        if any(token in ck for token in ["linescore", "line", "runsbyinning", "runsinning", "innings", "scorebyinning"]):
            # Avoid exact first-inning scalar columns; those are handled separately.
            if not re.search(r"(r1|runs1|inning1|first|1st)$", ck):
                candidates.append(c)
    return candidates[0] if candidates else None


def load_target_date(repo: Path) -> str:
    """Resolve the active MLB slate date from current pitcher entries.

    A copied development workspace can keep a stale top-level targetDate even
    after its games and analyzer entries are refreshed. Prefer a date that
    actually has pitcher entries; otherwise use the latest pitcher-entry date.
    """
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    site = read_json(repo / "data" / "site.json", {}) or {}
    candidates = [str(props.get("targetDate") or ""), str(site.get("targetDate") or "")]
    pitcher_dates = sorted({
        str(e.get("gameDate") or "")
        for e in (props.get("entries") or [])
        if str(e.get("playerType") or "").lower() == "pitcher" and str(e.get("gameDate") or "")
    })
    for candidate in candidates:
        if candidate and candidate in pitcher_dates:
            return candidate
    if pitcher_dates:
        return pitcher_dates[-1]
    return next((c for c in candidates if c), "")

def props_series_path(props: Dict[str, Any], entry: Dict[str, Any], stat: str) -> Optional[Path]:
    idx = props.get("seriesIndex") or {}
    date = entry.get("gameDate") or props.get("targetDate")
    player_id = entry.get("playerId") or entry.get("player_id")
    ptype = entry.get("playerType") or "pitcher"
    keys = [
        f"{date}|MLB|{ptype}|{player_id}|{stat}",
        f"{date}|MLB|{player_id}|{stat}",
    ]
    for key in keys:
        rel = idx.get(key)
        if rel:
            return Path(str(rel).replace("\\", "/"))
    return None




def active_slate_dates(repo: Path, target_date: str) -> List[str]:
    """Return the site dates whose game-detail pages are currently active."""
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    site = read_json(repo / "data" / "site.json", {}) or {}
    available = {
        str(e.get("gameDate") or "")
        for e in (props.get("entries") or [])
        if str(e.get("playerType") or "").lower() == "pitcher"
        and str(e.get("gameDate") or "")
    }
    requested = str(target_date or "").strip()
    site_target = str(site.get("targetDate") or props.get("targetDate") or "").strip()
    site_next = str(site.get("nextDate") or "").strip()
    dates: List[str] = []
    for candidate in (requested, site_target):
        if candidate and candidate in available and candidate not in dates:
            dates.append(candidate)
    if site_next and site_next in available and site_next not in dates:
        if not requested or requested == site_target:
            dates.append(site_next)
    if not dates and available:
        dates.append(sorted(available)[-1])
    return dates


def detail_pitchers_for_dates(repo: Path, dates: List[str]) -> List[Dict[str, Any]]:
    """Read the pitchers actually rendered by current game-detail JSON files."""
    out: List[Dict[str, Any]] = []
    for game_date in dates:
        root = repo / "data" / "mlb_game_details" / game_date
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            detail = read_json(path, {}) or {}
            away = team_norm(detail.get("awayTeam") or (detail.get("game") or {}).get("awayTeam"))
            home = team_norm(detail.get("homeTeam") or (detail.get("game") or {}).get("homeTeam"))
            for p in (detail.get("pitchers") or []):
                if not isinstance(p, dict):
                    continue
                name = str(p.get("player") or p.get("playerName") or p.get("name") or "").strip()
                pid = clean_id(p.get("playerId") or p.get("pitcherId"))
                if not pid and not norm_name(name):
                    continue
                team = team_norm(p.get("team"))
                opponent = home if team and team == away else away if team and team == home else team_norm(p.get("opp") or p.get("opponent"))
                out.append({
                    "playerId": pid,
                    "player": name,
                    "team": team,
                    "opponent": opponent,
                    "gameDate": game_date,
                    "source": str(path),
                })
    return out


def player_match_aliases(row: Dict[str, Any]) -> List[str]:
    aliases: List[str] = []
    pid = clean_id(row.get("playerId"))
    name = norm_name(row.get("player"))
    if pid:
        aliases.append(f"id:{pid}")
    if name:
        aliases.append(f"name:{name}")
    return aliases

def current_slate_pitchers(repo: Path, target_date: str) -> List[Dict[str, Any]]:
    """Return all pitchers shown on target and next-date game pages.

    The analyzer can omit a starter or carry playerId=None, so game-detail JSON
    is merged as an authoritative display source.
    """
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    dates = active_slate_dates(repo, target_date)
    date_set = set(dates)
    candidates: List[Dict[str, Any]] = []

    for e in (props.get("entries") or []):
        if str(e.get("playerType") or "").lower() != "pitcher":
            continue
        if str(e.get("gameDate") or "") not in date_set:
            continue
        candidates.append({
            "playerId": clean_id(e.get("playerId")),
            "player": str(e.get("player") or "").strip(),
            "team": team_norm(e.get("team")),
            "opponent": team_norm(e.get("opp")),
            "gameDate": str(e.get("gameDate") or ""),
            "source": "mlb_props_analyzer",
        })

    candidates.extend(detail_pitchers_for_dates(repo, dates))

    out: List[Dict[str, Any]] = []
    seen = set()
    source_counts = Counter()
    for row in candidates:
        pid = clean_id(row.get("playerId"))
        name = str(row.get("player") or "").strip()
        key = pid or norm_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        source_counts[str(row.get("source") or "unknown")] += 1
        out.append({
            "playerId": pid,
            "player": name,
            "team": team_norm(row.get("team")),
            "opponent": team_norm(row.get("opponent")),
            "gameDate": str(row.get("gameDate") or ""),
            "activeSlateDates": dates,
            "source": row.get("source") or "",
        })

    print(
        "Active first-inning pitcher dates: "
        + (", ".join(dates) if dates else "<none>")
        + f" | unique pitchers={len(out)} | detail/analyzer candidates={len(candidates)}"
    )
    return out

def read_latest_pitcher_game_logs(mlb_data_dir: Path) -> Tuple[pd.DataFrame, str]:
    """Load the same current pitcher-game log source used by Game Intelligence."""
    root = mlb_data_dir / "pitcher_game_logs"
    if not root.exists():
        return pd.DataFrame(), ""

    preferred = [
        root / "pitcher_game_logs_latest.parquet",
        root / "pitcher_game_logs_latest.csv",
    ]
    for path in preferred:
        if not path.exists():
            continue
        frame = read_table(path)
        if frame is not None and not frame.empty:
            return frame, str(path)

    files = sorted(
        [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".parquet", ".csv"}],
        key=lambda p: p.stat().st_mtime,
    )
    frames: List[pd.DataFrame] = []
    used: List[str] = []
    for path in files:
        frame = read_table(path)
        if frame is None or frame.empty:
            continue
        frames.append(frame)
        used.append(str(path))
    if not frames:
        return pd.DataFrame(), ""
    return pd.concat(frames, ignore_index=True, sort=False), ";".join(used[-10:])


def direct_pitcher_game_log_starts(
    repo: Path,
    mlb_data_dir: Path,
    target_date: str,
) -> List[Dict[str, Any]]:
    """Get the current slate pitchers' latest actual outings from pitcher_game_logs.

    Game Intelligence already uses this table when analyzer series are stale.
    The first-inning lookup must use the same rows; otherwise the page can show a
    June 13 outing while the first-inning builder still thinks June 7 is latest.
    Starter status is verified later from the MLB StatsAPI box score.
    """
    pitchers = current_slate_pitchers(repo, target_date)
    if not pitchers:
        return []

    raw, source = read_latest_pitcher_game_logs(mlb_data_dir)
    if raw.empty:
        return []

    pid_col = find_col(raw.columns, ["player_id", "pitcher_id", "playerId", "pitcherId", "mlbam_id"])
    name_col = find_col(raw.columns, ["player_name", "pitcher_name", "fullName", "player", "pitcher", "name"])
    game_col = find_col(raw.columns, ["gamePk", "game_pk", "gameId", "game_id"])
    local_date_col = find_col(raw.columns, ["gameDate_mlb_local", "gameDateLocal", "game_date_local", "date_local"])
    date_col = find_col(raw.columns, ["gameDate", "game_date", "date", "game_datetime"])
    team_col = find_col(raw.columns, ["team", "team_abbr", "pitching_team"])
    opp_col = find_col(raw.columns, ["opponent", "opp", "opponent_team", "opp_team"])
    side_col = find_col(raw.columns, ["team_side", "side"])
    home_col = find_col(raw.columns, ["isHome", "is_home"])
    loc_col = find_col(raw.columns, ["location", "home_away", "homeAway"])

    if not game_col or (not pid_col and not name_col) or (not local_date_col and not date_col):
        return []

    pitcher_ids = {clean_id(p.get("playerId")) for p in pitchers if clean_id(p.get("playerId"))}
    pitcher_names = {norm_name(p.get("player")) for p in pitchers if norm_name(p.get("player"))}

    rows: List[Dict[str, Any]] = []
    for _, r in raw.iterrows():
        pid = clean_id(r.get(pid_col)) if pid_col else ""
        pname = str(r.get(name_col) or "").strip() if name_col else ""
        matched = bool(
            (pid and pid in pitcher_ids)
            or (norm_name(pname) and norm_name(pname) in pitcher_names)
        )
        if not matched:
            continue

        gid = clean_id(r.get(game_col))
        if not gid:
            continue

        if local_date_col:
            d = safe_date(r.get(local_date_col))
        else:
            parsed = pd.to_datetime(r.get(date_col), errors="coerce", utc=True)
            if pd.isna(parsed):
                d = ""
            else:
                d = parsed.tz_convert("America/Denver").date().isoformat()
        if not d or (target_date and d >= target_date):
            continue

        is_home: Optional[bool] = None
        location = ""
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
            "player": pname,
            "gameId": gid,
            "date": d,
            "team": team_norm(r.get(team_col)) if team_col else "",
            "opponent": team_norm(r.get(opp_col)) if opp_col else "",
            "isHome": is_home,
            "source": source or "pitcher_game_logs",
            "starterMethod": "direct_pitcher_game_logs_recent_outing",
            "starterConfidence": "pending_statsapi_first_pitcher_verification",
        })

    # Deduplicate and retain the latest five actual outings for each current pitcher.
    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        who = clean_id(row.get("playerId")) or norm_name(row.get("player"))
        dedup[(who, clean_id(row.get("gameId")))] = row

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in dedup.values():
        who = clean_id(row.get("playerId")) or norm_name(row.get("player"))
        grouped[who].append(row)

    out: List[Dict[str, Any]] = []
    for who, group in grouped.items():
        group.sort(key=lambda x: (safe_date(x.get("date")), clean_id(x.get("gameId"))))
        out.extend(group[-5:])
    return out


def combined_current_pitcher_starts(
    repo: Path,
    mlb_data_dir: Path,
    target_date: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Prefer direct logs, matching by either MLB ID or normalized player name."""
    direct = direct_pitcher_game_log_starts(repo, mlb_data_dir, target_date)
    series = current_pitcher_series_starts(repo, target_date)

    direct_by_alias: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    series_by_alias: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in direct:
        for alias in player_match_aliases(row):
            direct_by_alias[alias].append(row)
    for row in series:
        for alias in player_match_aliases(row):
            series_by_alias[alias].append(row)

    current = current_slate_pitchers(repo, target_date)
    out: List[Dict[str, Any]] = []
    used_direct = 0
    used_series = 0
    unmatched: List[str] = []

    for pitcher in current:
        aliases = player_match_aliases(pitcher)
        direct_rows: Dict[str, Dict[str, Any]] = {}
        series_rows: Dict[str, Dict[str, Any]] = {}
        for alias in aliases:
            for row in direct_by_alias.get(alias, []):
                direct_rows[clean_id(row.get("gameId"))] = row
            for row in series_by_alias.get(alias, []):
                series_rows[clean_id(row.get("gameId"))] = row

        rows = list(direct_rows.values()) if direct_rows else list(series_rows.values())
        if direct_rows:
            used_direct += len(rows)
        elif series_rows:
            used_series += len(rows)
        else:
            unmatched.append(str(pitcher.get("player") or pitcher.get("playerId") or ""))

        rows.sort(key=lambda x: (safe_date(x.get("date")), clean_id(x.get("gameId"))))
        out.extend(rows[-5:])

    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in out:
        who = clean_id(row.get("playerId")) or norm_name(row.get("player"))
        dedup[(who, clean_id(row.get("gameId")))] = row
    merged = list(dedup.values())
    merged.sort(key=lambda x: (safe_date(x.get("date")), clean_id(x.get("gameId"))))

    if unmatched:
        print(
            f"WARN: {len(unmatched)} active pitchers had no direct/series history: "
            + ", ".join(unmatched[:12])
            + (" ..." if len(unmatched) > 12 else "")
        )

    return merged, {
        "direct_rows": used_direct,
        "series_rows": used_series,
        "direct_players": len({clean_id(r.get("playerId")) or norm_name(r.get("player")) for r in direct}),
        "series_players": len({clean_id(r.get("playerId")) or norm_name(r.get("player")) for r in series}),
        "current_players": len(current),
        "unmatched_current_players": len(unmatched),
    }

def current_pitcher_series_starts(repo: Path, target_date: str) -> List[Dict[str, Any]]:
    """Get only the current slate's projected pitchers and their last actual games.

    This is much smaller and more reliable than trying to infer every historical
    starter from local parquet columns. It uses the same analyzer series that is
    already feeding the pitching matchup table.
    """
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    dates = set(active_slate_dates(repo, target_date))
    entries = [e for e in (props.get("entries") or [])
               if str(e.get("gameDate") or "") in dates
               and str(e.get("playerType") or "").lower() == "pitcher"]
    by_pid: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        pid = str(e.get("playerId") or norm_name(e.get("player")))
        if pid and pid not in by_pid:
            by_pid[pid] = e

    starts: List[Dict[str, Any]] = []
    for pid, e in by_pid.items():
        series = None
        for stat in ["IP", "OUTS", "K", "HA", "ER"]:
            rel = props_series_path(props, e, stat)
            if rel:
                series = read_json(repo / rel, {}) or {}
                if series.get("games"):
                    break
        if not series:
            continue
        games = [g for g in (series.get("games") or []) if isinstance(g, dict) and safe_date(g.get("gameDate") or g.get("label"))]
        games.sort(key=lambda g: (safe_date(g.get("gameDate") or g.get("label")), int(num(g.get("seq")) or 0)))
        for g in games[-5:]:
            gid = str(clean_scalar(g.get("gameId") or g.get("gamePk") or ""))
            if not gid:
                continue
            is_home = row_is_home(g, "location" if "location" in g else None, "isHome" if "isHome" in g else None)
            starts.append({
                "playerId": str(e.get("playerId") or series.get("playerId") or ""),
                "player": str(e.get("player") or series.get("player") or ""),
                "gameId": gid,
                "date": safe_date(g.get("gameDate") or g.get("label")),
                "team": team_norm(e.get("team") or series.get("team")),
                "opponent": team_norm(g.get("opp") or e.get("opp") or series.get("opp")),
                "isHome": is_home,
                "source": str(props_series_path(props, e, "IP") or props_series_path(props, e, "K") or "mlb_props_analyzer"),
                "starterMethod": "current_slate_pitcher_series_last5",
                "starterConfidence": "high",
            })
    # de-dupe by player+game
    seen = set()
    out = []
    for s in starts:
        key = (s.get("playerId") or norm_name(s.get("player")), s.get("gameId"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out



STATSAPI_CACHE_SCHEMA = "2.0-first-pitcher-verified"


def statsapi_player_name(players: Dict[str, Any], player_id: Any) -> str:
    pid = clean_id(player_id)
    if not pid:
        return ""
    row = players.get(f"ID{pid}") or players.get(pid) or {}
    person = row.get("person") if isinstance(row, dict) else {}
    if isinstance(person, dict) and person.get("fullName"):
        return str(person.get("fullName") or "").strip()
    if isinstance(row, dict) and row.get("fullName"):
        return str(row.get("fullName") or "").strip()
    return ""


def statsapi_team_pitcher_metadata(team_box: Any, players: Dict[str, Any]) -> Dict[str, Any]:
    row = team_box if isinstance(team_box, dict) else {}
    pitcher_ids = [clean_id(v) for v in (row.get("pitchers") or []) if clean_id(v)]
    names = [statsapi_player_name(players, pid) for pid in pitcher_ids]
    names = [name for name in names if name]
    first_id = pitcher_ids[0] if pitcher_ids else ""
    return {
        "firstPitcherId": first_id,
        "firstPitcherName": statsapi_player_name(players, first_id),
        "pitcherIds": pitcher_ids,
        "pitcherNames": names,
    }


def parse_statsapi_first_inning_feed(data: Dict[str, Any], game_pk: str, source: str) -> Optional[Dict[str, Any]]:
    game_data = data.get("gameData") or {}
    teams = game_data.get("teams") or {}
    away_team = teams.get("away") or {}
    home_team = teams.get("home") or {}
    players = game_data.get("players") or {}

    live_data = data.get("liveData") or {}
    innings = ((live_data.get("linescore") or {}).get("innings") or [])
    if not innings:
        return None

    first = innings[0]
    away_runs = num(((first.get("away") or {}).get("runs")))
    home_runs = num(((first.get("home") or {}).get("runs")))

    box_teams = ((live_data.get("boxscore") or {}).get("teams") or {})
    away_pitching = statsapi_team_pitcher_metadata(box_teams.get("away"), players)
    home_pitching = statsapi_team_pitcher_metadata(box_teams.get("home"), players)

    return {
        "ok": True,
        "schemaVersion": STATSAPI_CACHE_SCHEMA,
        "gamePk": clean_id(game_pk),
        "generatedAt": now_utc(),
        "away": {
            "abbr": team_norm(
                away_team.get("abbreviation")
                or away_team.get("teamCode")
                or away_team.get("fileCode")
                or away_team.get("name")
            ),
            "id": clean_id(away_team.get("id")),
            "runs1": away_runs,
            **away_pitching,
        },
        "home": {
            "abbr": team_norm(
                home_team.get("abbreviation")
                or home_team.get("teamCode")
                or home_team.get("fileCode")
                or home_team.get("name")
            ),
            "id": clean_id(home_team.get("id")),
            "runs1": home_runs,
            **home_pitching,
        },
        "source": source,
    }


def statsapi_pitcher_side(feed: Dict[str, Any], start: Dict[str, Any]) -> str:
    """Return the team side whose first pitcher matches this historical row."""
    pid = clean_id(start.get("playerId"))
    pname = norm_name(start.get("player"))
    is_home = start.get("isHome")

    if is_home is True:
        preferred = "home"
    elif is_home is False:
        preferred = "away"
    else:
        preferred = ""

    sides = [preferred] if preferred else []
    sides.extend(side for side in ("home", "away") if side not in sides)

    for side in sides:
        info = feed.get(side) or {}
        first_id = clean_id(info.get("firstPitcherId"))
        first_name = norm_name(info.get("firstPitcherName"))
        if pid and first_id and pid == first_id:
            return side
        if pname and first_name and pname == first_name:
            return side

    # Team/location is allowed to identify which side the pitcher belonged to,
    # but it does not verify that the pitcher was the first pitcher.
    team = team_norm(start.get("team"))
    if team:
        for side in ("home", "away"):
            if team == team_norm((feed.get(side) or {}).get("abbr")):
                return side
    return preferred


def statsapi_first_pitcher_matches(feed: Dict[str, Any], side: str, start: Dict[str, Any]) -> bool:
    if side not in {"home", "away"}:
        return False
    info = feed.get(side) or {}
    pid = clean_id(start.get("playerId"))
    pname = norm_name(start.get("player"))
    first_id = clean_id(info.get("firstPitcherId"))
    first_name = norm_name(info.get("firstPitcherName"))
    if pid and first_id:
        return pid == first_id
    if pname and first_name:
        return pname == first_name
    return False


def statsapi_pitcher_appeared(feed: Dict[str, Any], side: str, start: Dict[str, Any]) -> bool:
    if side not in {"home", "away"}:
        return False
    info = feed.get(side) or {}
    pid = clean_id(start.get("playerId"))
    pname = norm_name(start.get("player"))
    ids = {clean_id(v) for v in (info.get("pitcherIds") or []) if clean_id(v)}
    names = {norm_name(v) for v in (info.get("pitcherNames") or []) if norm_name(v)}
    return bool((pid and pid in ids) or (pname and pname in names))

def fetch_json_url(url: str, timeout: int = 12) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LetsParlayML-GameIntelligence/2.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_boxscore_linescore(boxscore: Dict[str, Any], linescore: Dict[str, Any], game_pk: str, source: str) -> Optional[Dict[str, Any]]:
    teams = (boxscore.get("teams") or {}) if isinstance(boxscore, dict) else {}
    innings = (linescore.get("innings") or []) if isinstance(linescore, dict) else []
    if not innings:
        return None
    first = innings[0] or {}

    def side_payload(side: str) -> Dict[str, Any]:
        team_box = teams.get(side) or {}
        pitcher_ids = [clean_id(v) for v in (team_box.get("pitchers") or []) if clean_id(v)]
        players = team_box.get("players") or {}
        first_id = pitcher_ids[0] if pitcher_ids else ""
        player_row = players.get(f"ID{first_id}") or players.get(first_id) or {}
        person = player_row.get("person") if isinstance(player_row, dict) else {}
        first_name = str((person or {}).get("fullName") or "").strip() if isinstance(person, dict) else ""
        names = []
        for pid in pitcher_ids:
            row = players.get(f"ID{pid}") or players.get(pid) or {}
            p = row.get("person") if isinstance(row, dict) else {}
            name = str((p or {}).get("fullName") or "").strip() if isinstance(p, dict) else ""
            if name:
                names.append(name)
        team_obj = team_box.get("team") or {}
        runs = num((((first.get(side) or {}).get("runs"))))
        return {
            "abbr": team_norm(team_obj.get("abbreviation") or team_obj.get("teamCode") or team_obj.get("name")),
            "id": clean_id(team_obj.get("id")),
            "runs1": runs,
            "firstPitcherId": first_id,
            "firstPitcherName": first_name,
            "pitcherIds": pitcher_ids,
            "pitcherNames": names,
        }

    return {
        "ok": True,
        "schemaVersion": STATSAPI_CACHE_SCHEMA,
        "gamePk": clean_id(game_pk),
        "generatedAt": now_utc(),
        "away": side_payload("away"),
        "home": side_payload("home"),
        "source": source,
    }


def fetch_statsapi_first_inning(repo: Path, game_pk: str, sleep_seconds: float = 0.0) -> Optional[Dict[str, Any]]:
    cache_dir = repo / "data" / "derived" / "statsapi_first_inning_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{game_pk}.json"
    cached = read_json(cache_path, None)
    if (
        isinstance(cached, dict)
        and cached.get("ok")
        and cached.get("schemaVersion") == STATSAPI_CACHE_SCHEMA
        and ((cached.get("home") or {}).get("firstPitcherId") or (cached.get("home") or {}).get("firstPitcherName"))
        and ((cached.get("away") or {}).get("firstPitcherId") or (cached.get("away") or {}).get("firstPitcherName"))
    ):
        return cached

    errors: List[str] = []
    feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    feed, err = fetch_json_url(feed_url)
    if feed:
        payload = parse_statsapi_first_inning_feed(feed, game_pk, feed_url)
        if payload:
            write_json(cache_path, payload)
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return payload
        errors.append("feed/live returned no usable first-inning/boxscore payload")
    elif err:
        errors.append(f"feed/live: {err}")

    box_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    line_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/linescore"
    boxscore, box_err = fetch_json_url(box_url)
    linescore, line_err = fetch_json_url(line_url)
    if boxscore and linescore:
        payload = parse_boxscore_linescore(boxscore, linescore, game_pk, f"{box_url} + {line_url}")
        if payload:
            write_json(cache_path, payload)
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return payload
        errors.append("boxscore/linescore returned no usable first-inning payload")
    else:
        if box_err:
            errors.append(f"boxscore: {box_err}")
        if line_err:
            errors.append(f"linescore: {line_err}")

    failure = {
        "ok": False,
        "schemaVersion": STATSAPI_CACHE_SCHEMA,
        "gamePk": clean_id(game_pk),
        "generatedAt": now_utc(),
        "errors": errors or ["unknown StatsAPI failure"],
        "attemptedUrls": [feed_url, box_url, line_url],
    }
    write_json(cache_path, failure)
    print(f"WARN: StatsAPI first-inning fetch failed for game {game_pk}: {' | '.join(failure['errors'])}")
    return None


def add_statsapi_current_pitcher_rows(
    repo: Path,
    target_date: str,
    lookup: Dict[str, Dict[str, Any]],
    audit: List[Dict[str, Any]],
    starts_override: Optional[List[Dict[str, Any]]] = None,
) -> int:
    starts = starts_override if starts_override is not None else current_pitcher_series_starts(repo, target_date)
    if not starts:
        return 0

    feed_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    count = 0
    api_failures = 0

    for st in starts:
        gid = clean_id(st.get("gameId"))
        if not gid:
            continue

        if gid not in feed_cache:
            print(f"StatsAPI first-inning attempt: {st.get('player') or st.get('playerId')} | {st.get('date')} | game {gid}")
            feed_cache[gid] = fetch_statsapi_first_inning(repo, gid)
            if not feed_cache[gid] or not feed_cache[gid].get("ok"):
                api_failures += 1

        feed = feed_cache.get(gid)
        if not feed or not feed.get("ok"):
            continue

        side = statsapi_pitcher_side(feed, st)
        verified = statsapi_first_pitcher_matches(feed, side, st)
        info = feed.get(side) or {} if side else {}
        first_pitcher_id = clean_id(info.get("firstPitcherId"))
        first_pitcher_name = str(info.get("firstPitcherName") or "").strip()
        appeared = statsapi_pitcher_appeared(feed, side, st)

        base_payload = {
            "source": feed.get("source") or f"statsapi game {gid}",
            "confidence": "high_statsapi_boxscore",
            "starterMethod": "statsapi_boxscore_first_pitcher",
            "actualStarterVerified": verified,
            "playerId": clean_id(st.get("playerId")),
            "player": str(st.get("player") or ""),
            "team": team_norm(st.get("team")),
            "opponent": team_norm(st.get("opponent")),
            "isHome": True if side == "home" else False if side == "away" else st.get("isHome"),
            "location": "Home" if side == "home" else "Away" if side == "away" else "",
            "gameId": gid,
            "date": safe_date(st.get("date")),
            "firstPitcherId": first_pitcher_id,
            "firstPitcher": first_pitcher_name,
        }
        keys = build_keys(st.get("playerId"), st.get("player"), gid, st.get("date"))

        if verified:
            # Home first pitcher allows the away team's Top-1 runs.
            # Away first pitcher allows the home team's Bottom-1 runs.
            runs = (feed.get("away") or {}).get("runs1") if side == "home" else (feed.get("home") or {}).get("runs1")
            if runs is None:
                continue
            payload = {
                **base_payload,
                "runs": float(runs),
                "method": "statsapi_first_pitcher_in_half_inning",
                "status": "confirmed_first_inning_start",
                "display": str(int(float(runs))) if float(runs).is_integer() else str(float(runs)),
                "note": "Actual first pitcher verified from the MLB StatsAPI box score.",
            }
            add_lookup(lookup, keys, payload, priority=96)
            audit.append(payload)
            count += 1
            continue

        # A recent-game analyzer row can be a relief/bulk appearance. Store an
        # explicit non-start classification instead of assigning the team's
        # first-inning runs to the wrong pitcher.
        status = "relief_or_bulk_after_opener" if appeared else "did_not_start"
        payload = {
            **base_payload,
            "runs": None,
            "method": "statsapi_boxscore_non_start_classification",
            "status": status,
            "display": "Relief" if appeared else "Did not start",
            "note": (
                f"MLB box score first pitcher was {first_pitcher_name or first_pitcher_id or 'another pitcher'}; "
                "no pitcher-specific first-inning runs were assigned."
            ),
        }
        add_lookup(lookup, keys, payload, priority=96)
        audit.append(payload)
        count += 1

    return count



# -------------------------- statcast first-inning extraction --------------------------

def parse_ymd(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def filename_date_range(path: Path) -> Tuple[Optional[str], Optional[str]]:
    nums = re.findall(r"(20\d{6})", path.name)
    if not nums:
        return None, None
    def fmt(x: str) -> str:
        return f"{x[:4]}-{x[4:6]}-{x[6:8]}"
    if len(nums) == 1:
        return fmt(nums[0]), fmt(nums[0])
    return fmt(nums[0]), fmt(nums[-1])


def date_in_range(date_s: str, start: Optional[str], end: Optional[str]) -> bool:
    if not date_s or not start or not end:
        return True
    d, a, b = parse_ymd(date_s), parse_ymd(start), parse_ymd(end)
    if not d or not a or not b:
        return True
    return a <= d <= b


def discover_statcast_files(mlb_data_dir: Path, needed_dates: Iterable[str], max_files: int = 500) -> List[Path]:
    roots = [mlb_data_dir / "statcast_pitch_level", mlb_data_dir]
    needed = {d for d in needed_dates if d}
    out: List[Path] = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for fp in root.rglob("*"):
            if not fp.is_file() or fp.suffix.lower() not in {".parquet", ".csv"}:
                continue
            low = str(fp).lower()
            if "statcast_pitch_level" not in low and "statcast" not in low:
                continue
            start, end = filename_date_range(fp)
            if needed and start and end and not any(date_in_range(d, start, end) for d in needed):
                continue
            key = str(fp.resolve()).lower()
            if key not in seen:
                out.append(fp)
                seen.add(key)
            if len(out) >= max_files:
                return out
    return out


def read_statcast_table(path: Path) -> Optional[pd.DataFrame]:
    wanted = [
        "game_pk", "gamePk", "game_date", "gameDate", "home_team", "away_team",
        "inning", "inning_topbot", "pitcher", "player_name", "post_home_score",
        "post_away_score", "home_score", "away_score", "at_bat_number", "pitch_number",
    ]
    try:
        if path.suffix.lower() == ".parquet":
            try:
                import pyarrow.parquet as pq  # type: ignore
                schema_cols = set(pq.read_schema(path).names)
                cols = [c for c in wanted if c in schema_cols]
                if not {"game_pk", "gamePk"}.intersection(cols) or not {"inning"}.intersection(cols):
                    return None
                return pd.read_parquet(path, columns=cols)
            except Exception:
                df = pd.read_parquet(path)
                return df[[c for c in wanted if c in df.columns]]
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, usecols=lambda c: c in wanted, low_memory=False)
    except Exception as exc:
        print(f"WARN: could not read statcast file {path}: {exc}")
        return None
    return None


def extract_statcast_first_inning_lookup(
    repo: Path,
    mlb_data_dir: Path,
    target_date: str,
    lookup: Dict[str, Dict[str, Any]],
    audit: List[Dict[str, Any]],
    starts_override: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Use statcast pitch-level parquets to identify the actual first-inning pitcher.

    This is the reliable local source in this project. The team box parquets have
    full-game totals, not inning splits. Statcast has pitch rows with game_pk,
    inning, inning_topbot, pitcher id, player_name, and post_home/post_away score.
    For Top 1, the home pitcher allowed the away team's first-inning runs. For
    Bottom 1, the away pitcher allowed the home team's first-inning runs.
    """
    starts = starts_override if starts_override is not None else current_pitcher_series_starts(repo, target_date)
    needed_game_ids = {clean_id(s.get("gameId")) for s in starts if clean_id(s.get("gameId"))}
    needed_dates = {safe_date(s.get("date")) for s in starts if safe_date(s.get("date"))}
    if not needed_game_ids and not needed_dates:
        return 0

    files = discover_statcast_files(mlb_data_dir, needed_dates)
    if not files:
        return 0

    seen_pitcher_game_side = set()
    count = 0
    for fp in files:
        df = read_statcast_table(fp)
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        game_col = find_col(cols, ["game_pk", "gamePk", "game_id", "gameId"])
        date_col = find_col(cols, ["game_date", "gameDate", "date"])
        inn_col = find_col(cols, ["inning"])
        topbot_col = find_col(cols, ["inning_topbot"])
        pitcher_col = find_col(cols, ["pitcher", "pitcherId", "pitcher_id"])
        pname_col = find_col(cols, ["player_name", "playerName", "pitcherName", "pitcher_name"])
        home_team_col = find_col(cols, ["home_team", "homeTeam"])
        away_team_col = find_col(cols, ["away_team", "awayTeam"])
        post_home_col = find_col(cols, ["post_home_score", "postHomeScore", "home_post_score"])
        post_away_col = find_col(cols, ["post_away_score", "postAwayScore", "away_post_score"])
        home_score_col = find_col(cols, ["home_score", "homeScore"])
        away_score_col = find_col(cols, ["away_score", "awayScore"])
        ab_col = find_col(cols, ["at_bat_number", "atBatNumber"])
        pitch_no_col = find_col(cols, ["pitch_number", "pitchNumber"])
        if not (game_col and inn_col and topbot_col and pitcher_col and home_team_col and away_team_col):
            continue
        if not (post_home_col or home_score_col) or not (post_away_col or away_score_col):
            continue

        work = df.copy()
        work["__game"] = work[game_col].map(clean_id)
        if needed_game_ids:
            work = work[work["__game"].isin(needed_game_ids)]
        work = work[pd.to_numeric(work[inn_col], errors="coerce") == 1]
        if work.empty:
            continue
        if date_col:
            work["__date"] = work[date_col].map(safe_date)
        else:
            work["__date"] = ""
        # keep only target last-start dates if game ids were absent/incomplete
        if not needed_game_ids and needed_dates:
            work = work[work["__date"].isin(needed_dates)]
        if work.empty:
            continue
        sort_cols = [c for c in ["__game", topbot_col, ab_col, pitch_no_col] if c]
        try:
            work = work.sort_values(sort_cols)
        except Exception:
            pass

        for (game_id, topbot), g in work.groupby(["__game", topbot_col], dropna=True):
            side = str(topbot or "").strip().lower()
            if side not in {"top", "bottom", "bot"}:
                continue
            first_row = g.iloc[0]
            pitcher_id = clean_id(first_row.get(pitcher_col))
            pitcher_name = statcast_pitcher_display_name(first_row.get(pname_col)) if pname_col else ""
            date = safe_date(first_row.get("__date"))
            home_team = team_norm(first_row.get(home_team_col))
            away_team = team_norm(first_row.get(away_team_col))
            if side == "top":
                pitcher_team = home_team
                opponent = away_team
                score_col = post_away_col or away_score_col
                fallback_score_col = away_score_col
            else:
                pitcher_team = away_team
                opponent = home_team
                score_col = post_home_col or home_score_col
                fallback_score_col = home_score_col
            scores = pd.to_numeric(g[score_col], errors="coerce") if score_col in g.columns else pd.Series(dtype=float)
            if scores.dropna().empty and fallback_score_col and fallback_score_col in g.columns:
                scores = pd.to_numeric(g[fallback_score_col], errors="coerce")
            if scores.dropna().empty:
                continue
            runs = float(scores.max())
            if not math.isfinite(runs):
                continue
            # Runs in the first inning should be baseball-plausible; this also
            # protects against accidentally reading inning numbers as scores.
            if runs < 0 or runs > 15:
                continue
            uniq = (clean_id(game_id), side, pitcher_id)
            if uniq in seen_pitcher_game_side:
                continue
            seen_pitcher_game_side.add(uniq)
            payload = {
                "runs": runs,
                "source": str(fp),
                "method": "statcast_pitch_level_first_inning_start_pitcher",
                "confidence": "high_statcast_pitch_level",
                "starterMethod": "first_pitcher_in_half_inning",
                "playerId": pitcher_id,
                "player": pitcher_name,
                "team": pitcher_team,
                "opponent": opponent,
                "isHome": True if side == "top" else False,
                "location": "Home" if side == "top" else "Away",
                "gameId": clean_id(game_id),
                "date": date,
            }
            keys = build_keys(pitcher_id, pitcher_name, game_id, date)
            add_lookup(lookup, keys, payload, priority=98)
            audit.append(payload)
            count += 1

    return count


def pitcher_matches_start(row_pitcher_id: Any, row_pitcher_name: Any, start: Dict[str, Any]) -> bool:
    """Match a statcast pitcher row to the analyzer/start row."""
    pid = clean_id(start.get("playerId"))
    if pid and clean_id(row_pitcher_id) == pid:
        return True
    st_name = norm_name(start.get("player"))
    row_name = norm_name(statcast_pitcher_display_name(row_pitcher_name))
    return bool(st_name and row_name and st_name == row_name)


def classify_non_start_current_rows(
    repo: Path,
    mlb_data_dir: Path,
    target_date: str,
    lookup: Dict[str, Dict[str, Any]],
    audit: List[Dict[str, Any]],
    starts_override: Optional[List[Dict[str, Any]]] = None,
) -> Counter:
    """Classify unresolved current-slate pitcher/game rows instead of warning forever.

    The analyzer's recent-game series can include relief/bulk appearances. Those
    rows do not have a pitcher-specific first-inning RA because the pitcher was
    not on the mound in the 1st inning. This function scans the relevant statcast
    game rows and stores a deliberate status lookup entry:
      - relief_or_bulk_after_opener: pitcher appeared, but not as 1st-inning pitcher
      - not_in_statcast_for_game: statcast has the game, but not that pitcher
      - no_statcast_pitch_data: no local statcast rows for that game

    That keeps incremental runs fast and makes the Game Intelligence table say
    "Relief" / "No pitch data" instead of showing blanks or repeating warnings.
    """
    starts = starts_override if starts_override is not None else current_pitcher_series_starts(repo, target_date)
    starts = [s for s in starts if not start_has_lookup(lookup, s)]
    diag = Counter()
    if not starts:
        return diag

    needed_game_ids = {clean_id(s.get("gameId")) for s in starts if clean_id(s.get("gameId"))}
    needed_dates = {safe_date(s.get("date")) for s in starts if safe_date(s.get("date"))}
    files = discover_statcast_files(mlb_data_dir, needed_dates)
    starts_by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for st in starts:
        gid = clean_id(st.get("gameId"))
        if gid:
            starts_by_game[gid].append(st)

    game_info: Dict[str, Dict[str, Any]] = {}
    for fp in files:
        df = read_statcast_table(fp)
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        game_col = find_col(cols, ["game_pk", "gamePk", "game_id", "gameId"])
        date_col = find_col(cols, ["game_date", "gameDate", "date"])
        inn_col = find_col(cols, ["inning"])
        topbot_col = find_col(cols, ["inning_topbot"])
        pitcher_col = find_col(cols, ["pitcher", "pitcherId", "pitcher_id"])
        pname_col = find_col(cols, ["player_name", "playerName", "pitcherName", "pitcher_name"])
        home_team_col = find_col(cols, ["home_team", "homeTeam"])
        away_team_col = find_col(cols, ["away_team", "awayTeam"])
        ab_col = find_col(cols, ["at_bat_number", "atBatNumber"])
        pitch_no_col = find_col(cols, ["pitch_number", "pitchNumber"])
        if not (game_col and pitcher_col and inn_col and topbot_col):
            continue

        work = df.copy()
        work["__game"] = work[game_col].map(clean_id)
        if needed_game_ids:
            work = work[work["__game"].isin(needed_game_ids)]
        if work.empty:
            continue
        if date_col:
            work["__date"] = work[date_col].map(safe_date)
        else:
            work["__date"] = ""
        if not needed_game_ids and needed_dates:
            work = work[work["__date"].isin(needed_dates)]
        if work.empty:
            continue
        sort_cols = [c for c in ["__game", topbot_col, ab_col, pitch_no_col] if c]
        try:
            work = work.sort_values(sort_cols)
        except Exception:
            pass

        for gid, g in work.groupby("__game", dropna=True):
            gid = clean_id(gid)
            if not gid or gid not in starts_by_game:
                continue
            info = game_info.setdefault(gid, {
                "source": str(fp),
                "date": safe_date(g.iloc[0].get("__date")),
                "homeTeam": team_norm(g.iloc[0].get(home_team_col)) if home_team_col else "",
                "awayTeam": team_norm(g.iloc[0].get(away_team_col)) if away_team_col else "",
                "pitchers": [],
                "firstBySide": {},
            })
            # all pitchers who appeared in the game
            for _, r in g[[c for c in [pitcher_col, pname_col] if c]].drop_duplicates().iterrows():
                info["pitchers"].append({
                    "playerId": clean_id(r.get(pitcher_col)),
                    "player": statcast_pitcher_display_name(r.get(pname_col)) if pname_col else "",
                })
            # first pitcher in each half of the 1st inning
            one = g[pd.to_numeric(g[inn_col], errors="coerce") == 1]
            for topbot, gg in one.groupby(topbot_col, dropna=True):
                side = str(topbot or "").strip().lower()
                if side not in {"top", "bottom", "bot"}:
                    continue
                first_row = gg.iloc[0]
                key_side = "top" if side == "top" else "bottom"
                info["firstBySide"][key_side] = {
                    "playerId": clean_id(first_row.get(pitcher_col)),
                    "player": statcast_pitcher_display_name(first_row.get(pname_col)) if pname_col else "",
                }

    for st in starts:
        if start_has_lookup(lookup, st):
            continue
        gid = clean_id(st.get("gameId"))
        info = game_info.get(gid)
        status = "no_statcast_pitch_data"
        note = "No local statcast pitch rows were found for this game, so first-inning starter status could not be verified."
        first_pitcher = {}
        expected_side = ""
        if info:
            st_team = team_norm(st.get("team"))
            is_home = st.get("isHome")
            if is_home is True or (is_home is None and st_team and st_team == team_norm(info.get("homeTeam"))):
                expected_side = "top"      # home pitcher throws top 1
            elif is_home is False or (is_home is None and st_team and st_team == team_norm(info.get("awayTeam"))):
                expected_side = "bottom"   # away pitcher throws bottom 1
            first_pitcher = (info.get("firstBySide") or {}).get(expected_side) or {}
            appeared = any(pitcher_matches_start(p.get("playerId"), p.get("player"), st) for p in info.get("pitchers") or [])
            was_first = pitcher_matches_start(first_pitcher.get("playerId"), first_pitcher.get("player"), st) if first_pitcher else False
            if was_first:
                # This should normally have been captured by extract_statcast_first_inning_lookup.
                status = "unresolved_first_pitcher_no_runs"
                note = "Pitcher appears to be the first-inning pitcher, but a valid first-inning run total was not available."
            elif appeared:
                status = "relief_or_bulk_after_opener"
                fp_name = first_pitcher.get("player") or first_pitcher.get("playerId") or "another pitcher"
                note = f"Pitcher appeared in this game but was not the first pitcher for his team; {fp_name} handled the 1st inning."
            else:
                status = "not_in_statcast_for_game"
                fp_name = first_pitcher.get("player") or first_pitcher.get("playerId") or "the listed first pitcher"
                note = f"Local statcast has the game, but this pitcher was not found in the pitch rows; first-inning pitcher was {fp_name}."

        payload = {
            "runs": None,
            "status": status,
            "display": "Relief" if status == "relief_or_bulk_after_opener" else "No pitch data" if status == "no_statcast_pitch_data" else "Did not start",
            "source": (info or {}).get("source") or "statcast classification",
            "method": "statcast_non_start_classification",
            "confidence": "high_non_start" if status == "relief_or_bulk_after_opener" else "medium_unresolved",
            "starterMethod": st.get("starterMethod"),
            "playerId": st.get("playerId") or "",
            "player": st.get("player") or "",
            "team": team_norm(st.get("team")),
            "opponent": team_norm(st.get("opponent")),
            "isHome": st.get("isHome"),
            "location": "Home" if st.get("isHome") is True else "Away" if st.get("isHome") is False else "",
            "gameId": gid,
            "date": st.get("date") or "",
            "firstPitcherId": first_pitcher.get("playerId") or "",
            "firstPitcher": first_pitcher.get("player") or "",
            "note": note,
        }
        add_lookup(lookup, build_keys(st.get("playerId"), st.get("player"), gid, st.get("date")), payload, priority=45)
        audit.append(payload)
        diag[status] += 1
    return diag


# -------------------------- extraction candidates --------------------------

NAME_COLS = [
    "player", "playerName", "player_name", "pitcher", "pitcherName", "pitcher_name",
    "fullName", "name", "personName", "person_name",
]
ID_COLS = [
    "playerId", "player_id", "personId", "person_id", "pitcherId", "pitcher_id",
    "mlbam_id", "mlbId", "mlb_id", "id",
]
DATE_COLS = ["gameDate", "game_date", "date", "officialDate", "official_date"]
GAME_COLS = ["gamePk", "game_pk", "gameId", "game_id", "gameID", "game"]
TEAM_COLS = ["team", "teamAbbr", "team_abbr", "teamCode", "team_code", "teamName", "team_name", "playerTeam", "pitcherTeam"]
OPP_COLS = ["opp", "opponent", "opponentAbbr", "opponent_abbr", "oppTeam", "opp_team", "battingTeam", "batting_team"]
HOME_AWAY_COLS = ["homeAway", "home_away", "location", "home_or_away", "venueSide"]
IS_HOME_COLS = ["isHome", "is_home", "home", "teamIsHome", "team_is_home"]
ROLE_COLS = ["role", "pitcherRole", "pitcher_role", "position", "gameRole", "game_role"]
START_COLS = ["GS", "gamesStarted", "games_started", "gameStarted", "game_started", "isStarter", "is_starter", "started", "start"]
IP_COLS = ["IP", "ip", "inningsPitched", "innings_pitched", "outs", "OUTS", "out", "outsRecorded", "outs_recorded"]

DIRECT_FIRST_COLS = [
    "first_inning_runs_allowed", "firstInningRunsAllowed", "first_inning_ra", "inning1_runs_allowed",
    "runs_allowed_1st", "ra_1st", "r_1st", "firstRunsAllowed", "first_inning_runs", "runsFirstInning",
]
INNING_COLS = ["inning", "inning_number", "inn", "inningNum", "inning_num"]
RUN_ALLOWED_COLS = ["runs", "R", "r", "runs_allowed", "runsAllowed", "ra", "earnedRuns", "earned_runs", "ER", "er"]

HOME_TEAM_COLS = ["homeTeam", "home_team", "homeAbbr", "home_abbr", "home", "homeName", "home_name"]
AWAY_TEAM_COLS = ["awayTeam", "away_team", "awayAbbr", "away_abbr", "away", "awayName", "away_name"]


def detect_inning_one_col(columns: Iterable[str]) -> Optional[str]:
    # Team-row shape: one team per row, first inning runs in a generic column.
    exact = [
        "r1", "R1", "runs1", "runs_1", "inning1", "inning_1", "inn1", "inn_1",
        "i1", "I1", "score1", "score_1", "first", "firstInning", "first_inning",
        "firstInningRuns", "first_inning_runs", "runsFirstInning", "runs_first_inning",
        "1", "1st", "x1st",
    ]
    c = find_col(columns, exact)
    if c:
        return c
    matches = find_cols_regex(columns, [
        r"^(r|runs|score|inning|inn|i)0?1$",
        r"^(first|firstinning|runsfirstinning|firstinningruns)$",
        r"^(x?1st)$",
    ])
    return matches[0] if matches else None


def detect_side_first_col(columns: Iterable[str], side: str) -> Optional[str]:
    # Game-row shape: one game per row, home and away first inning runs in separate columns.
    side = side.lower()
    candidates = [
        f"{side}_r1", f"{side}R1", f"{side}_runs_1", f"{side}Runs1", f"{side}_inning_1",
        f"{side}Inning1", f"{side}_first", f"{side}First", f"{side}_first_inning_runs",
        f"{side}FirstInningRuns", f"{side}_1st", f"{side}1st",
    ]
    c = find_col(columns, candidates)
    if c:
        return c
    prefix = norm_key(side)
    matches = []
    for col in columns:
        ck = norm_key(col)
        if ck.startswith(prefix) and re.search(r"(r1|runs1|inning1|firstinningruns|first|1st)$", ck):
            matches.append(col)
    return matches[0] if matches else None


def row_is_home(row: Any, home_away_col: Optional[str], is_home_col: Optional[str]) -> Optional[bool]:
    if is_home_col:
        b = parse_boolish(row.get(is_home_col))
        if b is not None:
            return b
    if home_away_col:
        s = str(row.get(home_away_col) or "").strip().lower()
        if s in {"home", "h"}:
            return True
        if s in {"away", "road", "a", "visitor", "visiting"}:
            return False
    return None


# -------------------------- direct pitcher extraction --------------------------

def add_lookup(lookup: Dict[str, Dict[str, Any]], keys: Iterable[str], payload: Dict[str, Any], priority: int) -> None:
    for k in keys:
        if not k or k.endswith(":"):
            continue
        old = lookup.get(k)
        if old is None or priority >= int(old.get("priority", -1)):
            lookup[k] = {**payload, "priority": priority}


def build_keys(player_id: Any, player_name: Any, game_id: Any, date: Any) -> List[str]:
    keys = []
    pid = clean_id(player_id)
    nm = norm_name(player_name)
    gid = clean_id(game_id)
    dt = safe_date(date)
    if pid and gid:
        keys.append(f"id:{pid}|game:{gid}")
    if pid and dt:
        keys.append(f"id:{pid}|date:{dt}")
    if nm and gid:
        keys.append(f"name:{nm}|game:{gid}")
    if nm and dt:
        keys.append(f"name:{nm}|date:{dt}")
    return keys


def extract_direct_first_inning(df: pd.DataFrame, source: Path, lookup: Dict[str, Dict[str, Any]], audit: List[Dict[str, Any]]) -> int:
    columns = list(df.columns)
    dcol = find_col(columns, DIRECT_FIRST_COLS)
    icol = find_col(columns, INNING_COLS)
    rcol = find_col(columns, RUN_ALLOWED_COLS)
    if not dcol and not (icol and rcol):
        return 0
    ncol = find_col(columns, NAME_COLS)
    idcol = find_col(columns, ID_COLS)
    datecol = find_col(columns, DATE_COLS)
    gamecol = find_col(columns, GAME_COLS)
    if not (ncol or idcol) or not (datecol or gamecol):
        return 0

    count = 0
    for _, row in df.iterrows():
        if icol:
            inn = str(clean_scalar(row.get(icol)) or "").strip().lower()
            if inn not in {"1", "1.0", "top 1", "bottom 1", "first", "first inning"}:
                continue
        runs = num(row.get(dcol) if dcol else row.get(rcol))
        if runs is None:
            continue
        player_id = clean_scalar(row.get(idcol)) if idcol else ""
        player_name = clean_scalar(row.get(ncol)) if ncol else ""
        game_id = clean_scalar(row.get(gamecol)) if gamecol else ""
        date = clean_scalar(row.get(datecol)) if datecol else ""
        keys = build_keys(player_id, player_name, game_id, date)
        if not keys:
            continue
        payload = {
            "runs": float(runs),
            "source": str(source),
            "method": "direct_pitcher_first_inning_column" if dcol else "direct_pitcher_inning_row",
            "confidence": "high",
            "playerId": str(player_id or ""),
            "player": str(player_name or ""),
            "gameId": str(game_id or ""),
            "date": safe_date(date),
        }
        add_lookup(lookup, keys, payload, priority=100)
        audit.append(payload)
        count += 1
    return count


# -------------------------- starter + line score inference --------------------------

def extract_starter_candidates(df: pd.DataFrame, source: Path) -> List[Dict[str, Any]]:
    columns = list(df.columns)
    ncol = find_col(columns, NAME_COLS)
    idcol = find_col(columns, ID_COLS)
    datecol = find_col(columns, DATE_COLS)
    gamecol = find_col(columns, GAME_COLS)
    teamcol = find_col(columns, TEAM_COLS)
    oppcol = find_col(columns, OPP_COLS)
    hcol = find_col(columns, HOME_AWAY_COLS)
    ishomecol = find_col(columns, IS_HOME_COLS)
    rolecol = find_col(columns, ROLE_COLS)
    startcol = find_col(columns, START_COLS)
    ipcol = find_col(columns, IP_COLS)

    if not (gamecol or datecol) or not (teamcol or oppcol) or not (ncol or idcol):
        return []

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        player = clean_scalar(row.get(ncol)) if ncol else ""
        player_id = clean_scalar(row.get(idcol)) if idcol else ""
        game_id = clean_scalar(row.get(gamecol)) if gamecol else ""
        date = clean_scalar(row.get(datecol)) if datecol else ""
        team = team_norm(clean_scalar(row.get(teamcol))) if teamcol else ""
        opp = team_norm(clean_scalar(row.get(oppcol))) if oppcol else ""
        if not (player or player_id) or not (game_id or date) or not team:
            continue
        is_home = row_is_home(row, hcol, ishomecol)
        ip = parse_ip(row.get(ipcol)) if ipcol else None
        started = None
        if startcol:
            started = parse_boolish(row.get(startcol))
            if started is None and num(row.get(startcol)) is not None:
                started = num(row.get(startcol)) > 0
        if started is None and rolecol:
            role = str(row.get(rolecol) or "").strip().lower()
            if role in {"sp", "starter", "starting pitcher", "start"} or "starter" in role:
                started = True
            elif role in {"rp", "reliever", "relief"} or "relief" in role:
                started = False
        rows.append({
            "playerId": str(player_id or ""),
            "player": str(player or ""),
            "gameId": str(game_id or ""),
            "date": safe_date(date),
            "team": team,
            "opponent": opp,
            "isHome": is_home,
            "ip": ip,
            "started": started,
            "source": str(source),
        })

    # Prefer true starter rows. If a file has no starter flag, select the max-IP
    # pitcher for each team-game as a lower-confidence fallback.
    flagged = [r for r in rows if r.get("started") is True]
    if flagged:
        for r in flagged:
            r["starterMethod"] = "starter_flag_or_role"
            r["starterConfidence"] = "high"
        return flagged

    by_team_game: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = (r.get("gameId") or r.get("date") or "", r.get("date") or "", r.get("team") or "")
        if key[0] and key[2]:
            by_team_game[key].append(r)
    inferred: List[Dict[str, Any]] = []
    for _, group in by_team_game.items():
        with_ip = [g for g in group if g.get("ip") is not None]
        if not with_ip:
            continue
        best = sorted(with_ip, key=lambda x: x.get("ip") or 0, reverse=True)[0]
        # This is intentionally conservative; if max IP is below 2.0 it is likely
        # not a normal starter sample.
        if (best.get("ip") or 0) >= 2.0:
            best = dict(best)
            best["starterMethod"] = "max_ip_fallback_no_starter_flag"
            best["starterConfidence"] = "medium_low"
            inferred.append(best)
    return inferred


def extract_team_first_runs(df: pd.DataFrame, source: Path) -> List[Dict[str, Any]]:
    columns = list(df.columns)
    datecol = find_col(columns, DATE_COLS)
    gamecol = find_col(columns, GAME_COLS)

    # Shape A: one row per team-game.
    teamcol = find_col(columns, TEAM_COLS)
    hcol = find_col(columns, HOME_AWAY_COLS)
    ishomecol = find_col(columns, IS_HOME_COLS)
    onecol = detect_inning_one_col(columns)

    out: List[Dict[str, Any]] = []
    if onecol and teamcol and (gamecol or datecol):
        for _, row in df.iterrows():
            runs = num(row.get(onecol))
            team = team_norm(row.get(teamcol))
            if runs is None or not team:
                continue
            out.append({
                "gameId": str(clean_scalar(row.get(gamecol)) if gamecol else ""),
                "date": safe_date(clean_scalar(row.get(datecol)) if datecol else ""),
                "team": team,
                "isHome": row_is_home(row, hcol, ishomecol),
                "firstRuns": float(runs),
                "source": str(source),
                "method": "team_row_first_inning_column",
            })

    # Shape B: one row per game with home/away first-inning columns.
    home_team_col = find_col(columns, HOME_TEAM_COLS)
    away_team_col = find_col(columns, AWAY_TEAM_COLS)
    home_first_col = detect_side_first_col(columns, "home")
    away_first_col = detect_side_first_col(columns, "away")
    if home_team_col and away_team_col and home_first_col and away_first_col and (gamecol or datecol):
        for _, row in df.iterrows():
            game_id = str(clean_scalar(row.get(gamecol)) if gamecol else "")
            date = safe_date(clean_scalar(row.get(datecol)) if datecol else "")
            home_team = team_norm(row.get(home_team_col))
            away_team = team_norm(row.get(away_team_col))
            home_runs = num(row.get(home_first_col))
            away_runs = num(row.get(away_first_col))
            if home_team and home_runs is not None:
                out.append({"gameId": game_id, "date": date, "team": home_team, "isHome": True, "firstRuns": float(home_runs), "source": str(source), "method": "game_row_home_first_inning_column"})
            if away_team and away_runs is not None:
                out.append({"gameId": game_id, "date": date, "team": away_team, "isHome": False, "firstRuns": float(away_runs), "source": str(source), "method": "game_row_away_first_inning_column"})

    # Shape C: one row per game with home/away inning arrays or JSON line-score cells.
    home_line_col = find_side_line_array_col(columns, "home")
    away_line_col = find_side_line_array_col(columns, "away")
    if home_team_col and away_team_col and home_line_col and away_line_col and (gamecol or datecol):
        for _, row in df.iterrows():
            game_id = str(clean_scalar(row.get(gamecol)) if gamecol else "")
            date = safe_date(clean_scalar(row.get(datecol)) if datecol else "")
            home_team = team_norm(row.get(home_team_col))
            away_team = team_norm(row.get(away_team_col))
            home_runs = parse_first_from_cell(row.get(home_line_col))
            away_runs = parse_first_from_cell(row.get(away_line_col))
            if home_team and home_runs is not None:
                out.append({"gameId": game_id, "date": date, "team": home_team, "isHome": True, "firstRuns": float(home_runs), "source": str(source), "method": "game_row_home_line_score_array"})
            if away_team and away_runs is not None:
                out.append({"gameId": game_id, "date": date, "team": away_team, "isHome": False, "firstRuns": float(away_runs), "source": str(source), "method": "game_row_away_line_score_array"})
    return out


def pair_starters_with_team_runs(
    starters: List[Dict[str, Any]],
    team_runs: List[Dict[str, Any]],
    lookup: Dict[str, Dict[str, Any]],
    audit: List[Dict[str, Any]],
) -> int:
    by_game_team: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_date_team: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_game_side: Dict[Tuple[str, bool], Dict[str, Any]] = {}
    by_date_side: Dict[Tuple[str, bool], Dict[str, Any]] = {}
    teams_by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    teams_by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for tr in team_runs:
        gid = str(tr.get("gameId") or "")
        dt = tr.get("date") or ""
        tm = tr.get("team") or ""
        if gid and tm:
            by_game_team[(gid, tm)] = tr
            teams_by_game[gid].append(tr)
        if dt and tm:
            by_date_team[(dt, tm)] = tr
            teams_by_date[dt].append(tr)
        if tr.get("isHome") is not None:
            if gid:
                by_game_side[(gid, bool(tr.get("isHome")))] = tr
            if dt:
                by_date_side[(dt, bool(tr.get("isHome")))] = tr

    count = 0
    for st in starters:
        gid = str(st.get("gameId") or "")
        dt = st.get("date") or ""
        team = st.get("team") or ""
        opp = st.get("opponent") or ""
        target: Optional[Dict[str, Any]] = None
        match_method = ""

        # Best: explicit opponent row.
        if opp:
            target = by_game_team.get((gid, opp)) if gid else None
            if target:
                match_method = "opponent_team_first_inning_by_game"
            if not target and dt:
                target = by_date_team.get((dt, opp))
                if target:
                    match_method = "opponent_team_first_inning_by_date"

        # Next: home starter gets away runs; away starter gets home runs.
        if not target and st.get("isHome") is not None:
            opp_is_home = not bool(st.get("isHome"))
            target = by_game_side.get((gid, opp_is_home)) if gid else None
            if target:
                match_method = "opponent_side_first_inning_by_game"
            if not target and dt:
                target = by_date_side.get((dt, opp_is_home))
                if target:
                    match_method = "opponent_side_first_inning_by_date"

        # Last: if exactly two team rows exist for the game/date, use the other team.
        if not target:
            rows = teams_by_game.get(gid) if gid else []
            if not rows and dt:
                rows = teams_by_date.get(dt) or []
            other = [r for r in rows if r.get("team") and r.get("team") != team]
            if len(other) == 1:
                target = other[0]
                match_method = "only_other_team_first_inning"

        if not target:
            continue
        runs = num(target.get("firstRuns"))
        if runs is None:
            continue
        keys = build_keys(st.get("playerId"), st.get("player"), gid, dt)
        if not keys:
            continue
        confidence = "medium"
        priority = 70
        if st.get("starterConfidence") == "high" and "by_game" in match_method:
            confidence = "high_inferred_from_team_box"
            priority = 85
        elif st.get("starterConfidence") == "medium_low":
            confidence = "medium_low_inferred_starter"
            priority = 55
        payload = {
            "runs": float(runs),
            "source": f"starter={st.get('source')} | runs={target.get('source')}",
            "method": match_method,
            "confidence": confidence,
            "starterMethod": st.get("starterMethod"),
            "playerId": st.get("playerId") or "",
            "player": st.get("player") or "",
            "team": team,
            "opponent": target.get("team") or opp,
            "gameId": gid,
            "date": dt,
        }
        add_lookup(lookup, keys, payload, priority=priority)
        audit.append(payload)
        count += 1
    return count


# ----------------------------- main pipeline -----------------------------

def write_outputs(
    repo: Path,
    mlb_data_dir: Path,
    lookup: Dict[str, Dict[str, Any]],
    audit: List[Dict[str, Any]],
    diag: Counter,
) -> Tuple[Path, Path, int]:
    """Write merged lookup/audit outputs and return paths/count."""
    public_lookup = {}
    for k, v in lookup.items():
        vv = dict(v)
        vv.pop("priority", None)
        public_lookup[k] = vv

    out_dir = repo / "data" / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "1.5-force-direct-multi-endpoint",
        "generatedAt": now_utc(),
        "mlbDataDir": str(mlb_data_dir),
        "diagnostics": dict(diag),
        "lookup": public_lookup,
    }
    json_path = out_dir / "pitcher_first_inning_runs.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    audit_path = out_dir / "pitcher_first_inning_runs_audit.csv"
    fieldnames = [
        "date", "gameId", "playerId", "player", "team", "opponent", "runs",
        "status", "display", "confidence", "method", "starterMethod",
        "firstPitcher", "firstPitcherId", "note", "source",
    ]
    clean_rows = dedupe_audit(audit)
    with audit_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in clean_rows:
            writer.writerow(row)
    return json_path, audit_path, len(public_lookup)


def print_summary(diag: Counter, lookup_count: int, json_path: Path, audit_path: Path, incremental: bool) -> None:
    print("\nFirst-inning lookup build complete")
    print(f"  Mode                    : {'incremental append' if incremental else 'full rebuild'}")
    print(f"  Existing lookup keys    : {diag['existing_lookup_keys']}")
    print(f"  Current slate starts    : {diag['current_slate_starts']}")
    print(f"  Missing starts checked  : {diag['missing_current_starts']}")
    print(f"  Files read              : {diag['files_read']}")
    print(f"  Direct pitcher rows     : {diag['direct_pitcher_rows']}")
    print(f"  Starter candidates      : {diag['starter_candidates']}")
    print(f"  Team 1st-inning rows    : {diag['team_first_rows']}")
    print(f"  Paired starter rows     : {diag['paired_starter_rows']}")
    print(f"  Statcast pitcher rows   : {diag['statcast_pitch_level_rows']}")
    print(f"  StatsAPI verified/classified rows: {diag['statsapi_current_pitcher_rows']}")
    print(f"  Classified non-starts   : {diag['classified_non_start_rows']}")
    if diag.get("relief_or_bulk_after_opener"):
        print(f"    relief/bulk rows      : {diag['relief_or_bulk_after_opener']}")
    if diag.get("not_in_statcast_for_game"):
        print(f"    not in statcast game  : {diag['not_in_statcast_for_game']}")
    if diag.get("no_statcast_pitch_data"):
        print(f"    no pitch data rows    : {diag['no_statcast_pitch_data']}")
    print(f"  Lookup keys written     : {lookup_count}")
    print(f"  JSON                    : {json_path}")
    print(f"  Audit                   : {audit_path}")


def run_incremental(repo: Path, mlb_data_dir: Path, target_date: str, no_api_fallback: bool) -> int:
    out_dir = repo / "data" / "derived"
    json_path = out_dir / "pitcher_first_inning_runs.json"
    audit_path = out_dir / "pitcher_first_inning_runs_audit.csv"

    lookup = load_existing_lookup(json_path)
    audit = load_existing_audit(audit_path)
    diag = Counter()
    diag["existing_lookup_keys"] = len(lookup)

    all_starts, missing_starts, source_diag = missing_current_starts(repo, mlb_data_dir, target_date, lookup)
    diag["current_slate_starts"] = len(all_starts)
    diag["missing_current_starts"] = len(missing_starts)
    diag["direct_recent_outing_rows"] = source_diag.get("direct_rows", 0)
    diag["series_recent_outing_rows"] = source_diag.get("series_rows", 0)
    diag["direct_recent_outing_players"] = source_diag.get("direct_players", 0)

    if not missing_starts:
        json_path, audit_path, lookup_count = write_outputs(repo, mlb_data_dir, lookup, audit, diag)
        print_summary(diag, lookup_count, json_path, audit_path, incremental=True)
        print("\nNo new first-inning pitcher-game rows were needed; existing lookup is current for this slate.")
        return 0

    needed_dates = sorted({safe_date(s.get("date")) for s in missing_starts if safe_date(s.get("date"))})
    needed_games = sorted({clean_id(s.get("gameId")) for s in missing_starts if clean_id(s.get("gameId"))})
    print(f"Incremental first-inning lookup: {len(missing_starts)} missing pitcher-game rows")
    print(f"  Needed dates: {', '.join(needed_dates[:12])}{' ...' if len(needed_dates) > 12 else ''}")
    print(f"  Needed games: {len(needed_games)}")

    # Fast local source: only statcast files for the missing last-start dates/gameIds.
    statcast_count = extract_statcast_first_inning_lookup(
        repo, mlb_data_dir, target_date, lookup, audit, starts_override=missing_starts
    )
    diag["statcast_pitch_level_rows"] = statcast_count

    # Fallback only for the same missing rows.
    if not no_api_fallback:
        api_count = add_statsapi_current_pitcher_rows(
            repo, target_date, lookup, audit, starts_override=[s for s in missing_starts if not start_has_lookup(lookup, s)]
        )
        diag["statsapi_current_pitcher_rows"] = api_count

    # Anything still without a numeric 1st-inning value is usually a relief/bulk
    # appearance in the analyzer's recent-game series. Classify it so daily runs
    # do not keep warning/rechecking the same non-start rows.
    class_diag = classify_non_start_current_rows(
        repo, mlb_data_dir, target_date, lookup, audit, starts_override=[s for s in missing_starts if not start_has_lookup(lookup, s)]
    )
    for k, v in class_diag.items():
        diag[k] += v
    diag["classified_non_start_rows"] = sum(class_diag.values())

    json_path, audit_path, lookup_count = write_outputs(repo, mlb_data_dir, lookup, audit, diag)
    print_summary(diag, lookup_count, json_path, audit_path, incremental=True)

    still_missing = [s for s in missing_starts if not start_has_lookup(lookup, s)]
    if still_missing:
        print(f"\nWARNING: {len(still_missing)} current slate pitcher-game rows still unresolved after non-start classification.")
        print("The Game Intelligence page will still build, but inspect the audit for these rows.")
    elif diag.get("classified_non_start_rows"):
        print(f"\nClassified {diag['classified_non_start_rows']} current-slate rows as relief/non-start/no-pitch-data instead of leaving them blank.")
    return 0


def run_full_rebuild(args: argparse.Namespace, repo: Path, mlb_data_dir: Path, target_date: str) -> int:
    files = discover_files(mlb_data_dir, scan_all=args.scan_all, max_files=args.max_files)
    print(f"Full rebuild: scanning {len(files)} parquet/csv files under {mlb_data_dir}")

    lookup: Dict[str, Dict[str, Any]] = {}
    audit: List[Dict[str, Any]] = []
    starters: List[Dict[str, Any]] = []
    team_runs: List[Dict[str, Any]] = []
    diag = Counter()
    diag["existing_lookup_keys"] = 0
    all_starts, source_diag = combined_current_pitcher_starts(repo, mlb_data_dir, target_date)
    diag["current_slate_starts"] = len(all_starts)
    diag["missing_current_starts"] = len(all_starts)
    diag["direct_recent_outing_rows"] = source_diag.get("direct_rows", 0)
    diag["series_recent_outing_rows"] = source_diag.get("series_rows", 0)
    diag["direct_recent_outing_players"] = source_diag.get("direct_players", 0)

    statcast_count = extract_statcast_first_inning_lookup(repo, mlb_data_dir, target_date, lookup, audit)
    diag["statcast_pitch_level_rows"] = statcast_count

    for fp in files:
        df = read_table(fp)
        if df is None or df.empty:
            continue
        diag["files_read"] += 1

        direct_count = extract_direct_first_inning(df, fp, lookup, audit)
        if direct_count:
            diag["direct_pitcher_rows"] += direct_count

        s = extract_starter_candidates(df, fp)
        if s:
            starters.extend(s)
            diag["starter_candidates"] += len(s)

        tr = extract_team_first_runs(df, fp)
        if tr:
            team_runs.extend(tr)
            diag["team_first_rows"] += len(tr)

    paired_count = pair_starters_with_team_runs(starters, team_runs, lookup, audit)
    diag["paired_starter_rows"] = paired_count

    if not args.no_api_fallback:
        api_count = add_statsapi_current_pitcher_rows(
            repo, target_date, lookup, audit, starts_override=all_starts
        )
        diag["statsapi_current_pitcher_rows"] = api_count

    class_diag = classify_non_start_current_rows(
        repo,
        mlb_data_dir,
        target_date,
        lookup,
        audit,
        starts_override=[s for s in all_starts if not start_has_lookup(lookup, s)],
    )
    for k, v in class_diag.items():
        diag[k] += v
    diag["classified_non_start_rows"] = sum(class_diag.values())

    json_path, audit_path, lookup_count = write_outputs(repo, mlb_data_dir, lookup, audit, diag)
    print_summary(diag, lookup_count, json_path, audit_path, incremental=False)
    if not lookup_count:
        print("\nWARNING: No first-inning lookup rows were created.")
        print("Try adding --scan-all, then inspect the audit/printed diagnostics and parquet column names.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--website-repo", default=".", help="Path to letsparlayml.github.io")
    ap.add_argument("--mlb-data-dir", required=True, help="Path to local MLB data folder, e.g. C:\\python\\mlb_data")
    ap.add_argument("--scan-all", action="store_true", help="With --full-rebuild, scan every parquet/csv under mlb-data-dir, not just likely log/box files")
    ap.add_argument("--max-files", type=int, default=2000)
    ap.add_argument("--target-date", default="", help="Optional current slate date. Defaults to site/props targetDate.")
    ap.add_argument("--no-api-fallback", action="store_true", help="Disable free MLB Stats API line-score fallback for current slate pitcher last-5 starts.")
    ap.add_argument("--full-rebuild", action="store_true", help="Recreate the whole lookup by scanning local parquet/csv sources. Default is incremental append only.")
    ap.add_argument(
        "--force-current-direct",
        action="store_true",
        help=(
            "Force the current slate pitchers' latest direct-log outings through "
            "the verified StatsAPI first-inning refresh, including retrying failed cache rows."
        ),
    )
    args = ap.parse_args()

    repo = Path(args.website_repo).resolve()
    mlb_data_dir = Path(args.mlb_data_dir).resolve()
    if not mlb_data_dir.exists():
        raise SystemExit(f"MLB data dir not found: {mlb_data_dir}")

    target_date = args.target_date or load_target_date(repo)

    if args.full_rebuild:
        return run_full_rebuild(args, repo, mlb_data_dir, target_date)
    if args.force_current_direct:
        out_dir = repo / "data" / "derived"
        json_path = out_dir / "pitcher_first_inning_runs.json"
        audit_path = out_dir / "pitcher_first_inning_runs_audit.csv"
        lookup = load_existing_lookup(json_path)
        audit = load_existing_audit(audit_path)
        starts, source_diag = combined_current_pitcher_starts(repo, mlb_data_dir, target_date)
        print(f"Forced direct-log refresh target date: {target_date}")
        print(f"Current direct/series outings discovered: {len(starts)} | diagnostics={source_diag}")
        if not starts:
            print("ERROR: no current pitcher outings were discovered. Check analyzer target date and pitcher entries.")
            return 2
        # Remove failed cache files for the selected games so this run truly retries them.
        cache_dir = repo / "data" / "derived" / "statsapi_first_inning_cache"
        for start_row in starts:
            gid = clean_id(start_row.get("gameId"))
            cp = cache_dir / f"{gid}.json"
            cached = read_json(cp, None)
            if cp.exists() and (not isinstance(cached, dict) or not cached.get("ok")):
                try:
                    cp.unlink()
                except Exception:
                    pass
        diag = Counter()
        diag["existing_lookup_keys"] = len(lookup)
        diag["current_slate_starts"] = len(starts)
        diag["missing_current_starts"] = len(starts)
        diag["direct_recent_outing_rows"] = source_diag.get("direct_rows", 0)
        diag["series_recent_outing_rows"] = source_diag.get("series_rows", 0)
        diag["direct_recent_outing_players"] = source_diag.get("direct_players", 0)
        api_count = add_statsapi_current_pitcher_rows(repo, target_date, lookup, audit, starts_override=starts)
        diag["statsapi_current_pitcher_rows"] = api_count
        class_diag = classify_non_start_current_rows(
            repo, mlb_data_dir, target_date, lookup, audit,
            starts_override=[s for s in starts if not start_has_lookup(lookup, s)],
        )
        for k, v in class_diag.items():
            diag[k] += v
        diag["classified_non_start_rows"] = sum(class_diag.values())
        json_path, audit_path, lookup_count = write_outputs(repo, mlb_data_dir, lookup, audit, diag)
        print_summary(diag, lookup_count, json_path, audit_path, incremental=True)
        unresolved = [s for s in starts if not start_has_lookup(lookup, s)]
        if unresolved:
            print(f"ERROR: {len(unresolved)} forced current direct-log outings remain unresolved.")
            for row in unresolved[:20]:
                print(f"  {row.get('player')} | {row.get('date')} | game {row.get('gameId')}")
            return 3
        return 0
    return run_incremental(repo, mlb_data_dir, target_date, args.no_api_fallback)


if __name__ == "__main__":
    raise SystemExit(main())
