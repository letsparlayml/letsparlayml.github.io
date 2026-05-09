#!/usr/bin/env python
r"""
Build a starter first-inning runs allowed lookup for Game Intelligence.

This script scans local MLB parquet/CSV files, finds each starting pitcher, finds
how many runs the opposing team scored in the 1st inning, and writes lookup keys
that tools/build_game_intelligence.py can attach to pitcher last-5-start rows.

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
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    site = read_json(repo / "data" / "site.json", {}) or {}
    return str(props.get("targetDate") or site.get("targetDate") or "")


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


def current_pitcher_series_starts(repo: Path, target_date: str) -> List[Dict[str, Any]]:
    """Get only the current slate's projected pitchers and their last actual games.

    This is much smaller and more reliable than trying to infer every historical
    starter from local parquet columns. It uses the same analyzer series that is
    already feeding the pitching matchup table.
    """
    props = read_json(repo / "data" / "mlb_props_analyzer.json", {}) or {}
    if not target_date:
        target_date = str(props.get("targetDate") or "")
    entries = [e for e in (props.get("entries") or [])
               if str(e.get("gameDate") or "") == target_date
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


def fetch_statsapi_first_inning(repo: Path, game_pk: str, sleep_seconds: float = 0.0) -> Optional[Dict[str, Any]]:
    cache_dir = repo / "data" / "derived" / "statsapi_first_inning_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{game_pk}.json"
    cached = read_json(cache_path, None)
    if isinstance(cached, dict) and cached.get("ok"):
        return cached
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LetsParlayML-GameIntelligence/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if sleep_seconds:
            time.sleep(sleep_seconds)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, Exception) as exc:
        write_json(cache_path, {"ok": False, "gamePk": game_pk, "error": str(exc), "generatedAt": now_utc()})
        return None

    game_data = data.get("gameData") or {}
    teams = game_data.get("teams") or {}
    away_team = teams.get("away") or {}
    home_team = teams.get("home") or {}
    innings = (((data.get("liveData") or {}).get("linescore") or {}).get("innings") or [])
    if not innings:
        write_json(cache_path, {"ok": False, "gamePk": game_pk, "error": "no innings in feed", "generatedAt": now_utc()})
        return None
    first = innings[0]
    away_runs = num(((first.get("away") or {}).get("runs")))
    home_runs = num(((first.get("home") or {}).get("runs")))
    payload = {
        "ok": True,
        "gamePk": game_pk,
        "generatedAt": now_utc(),
        "away": {
            "abbr": team_norm(away_team.get("abbreviation") or away_team.get("teamCode") or away_team.get("fileCode") or away_team.get("name")),
            "id": str(away_team.get("id") or ""),
            "runs1": away_runs,
        },
        "home": {
            "abbr": team_norm(home_team.get("abbreviation") or home_team.get("teamCode") or home_team.get("fileCode") or home_team.get("name")),
            "id": str(home_team.get("id") or ""),
            "runs1": home_runs,
        },
        "source": url,
    }
    write_json(cache_path, payload)
    return payload


def add_statsapi_current_pitcher_rows(repo: Path, target_date: str, lookup: Dict[str, Dict[str, Any]], audit: List[Dict[str, Any]]) -> int:
    starts = current_pitcher_series_starts(repo, target_date)
    if not starts:
        return 0
    feed_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    count = 0
    api_failures = 0
    for st in starts:
        gid = str(st.get("gameId") or "")
        if not gid:
            continue
        if gid not in feed_cache:
            feed_cache[gid] = fetch_statsapi_first_inning(repo, gid)
            if not feed_cache[gid] or not feed_cache[gid].get("ok"):
                api_failures += 1
                if api_failures >= 3:
                    print("WARN: StatsAPI fallback stopped after 3 failed game fetches. Local parquet/csv lookup will still be used.")
                    break
        feed = feed_cache.get(gid)
        if not feed or not feed.get("ok"):
            continue
        # Starter's allowed runs are the opponent's first-inning runs.
        runs = None
        pitcher_team = team_norm(st.get("team"))
        is_home = st.get("isHome")
        if is_home is True:
            runs = feed.get("away", {}).get("runs1")
        elif is_home is False:
            runs = feed.get("home", {}).get("runs1")
        else:
            home_abbr = team_norm(feed.get("home", {}).get("abbr"))
            away_abbr = team_norm(feed.get("away", {}).get("abbr"))
            if pitcher_team and pitcher_team == home_abbr:
                runs = feed.get("away", {}).get("runs1")
            elif pitcher_team and pitcher_team == away_abbr:
                runs = feed.get("home", {}).get("runs1")
        if runs is None:
            continue
        payload = {
            "runs": float(runs),
            "source": feed.get("source") or f"statsapi game {gid}",
            "method": "statsapi_first_inning_from_current_pitcher_series",
            "confidence": "high_statsapi",
            "starterMethod": st.get("starterMethod"),
            "playerId": st.get("playerId") or "",
            "player": st.get("player") or "",
            "team": pitcher_team,
            "opponent": st.get("opponent") or "",
            "isHome": is_home,
            "location": "Home" if is_home is True else "Away" if is_home is False else "",
            "gameId": gid,
            "date": st.get("date") or "",
        }
        keys = build_keys(st.get("playerId"), st.get("player"), gid, st.get("date"))
        add_lookup(lookup, keys, payload, priority=82)
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
) -> int:
    """Use statcast pitch-level parquets to identify the actual first-inning pitcher.

    This is the reliable local source in this project. The team box parquets have
    full-game totals, not inning splits. Statcast has pitch rows with game_pk,
    inning, inning_topbot, pitcher id, player_name, and post_home/post_away score.
    For Top 1, the home pitcher allowed the away team's first-inning runs. For
    Bottom 1, the away pitcher allowed the home team's first-inning runs.
    """
    starts = current_pitcher_series_starts(repo, target_date)
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

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--website-repo", default=".", help="Path to letsparlayml.github.io")
    ap.add_argument("--mlb-data-dir", required=True, help="Path to local MLB data folder, e.g. C:\\python\\mlb_data")
    ap.add_argument("--scan-all", action="store_true", help="Scan every parquet/csv under mlb-data-dir, not just likely log/box files")
    ap.add_argument("--max-files", type=int, default=2000)
    ap.add_argument("--target-date", default="", help="Optional current slate date. Defaults to site/props targetDate.")
    ap.add_argument("--no-api-fallback", action="store_true", help="Disable free MLB Stats API line-score fallback for current slate pitcher last-5 starts.")
    args = ap.parse_args()

    repo = Path(args.website_repo).resolve()
    mlb_data_dir = Path(args.mlb_data_dir).resolve()
    if not mlb_data_dir.exists():
        raise SystemExit(f"MLB data dir not found: {mlb_data_dir}")

    target_date = args.target_date or load_target_date(repo)

    files = discover_files(mlb_data_dir, scan_all=args.scan_all, max_files=args.max_files)
    print(f"Scanning {len(files)} parquet/csv files under {mlb_data_dir}")

    lookup: Dict[str, Dict[str, Any]] = {}
    audit: List[Dict[str, Any]] = []
    starters: List[Dict[str, Any]] = []
    team_runs: List[Dict[str, Any]] = []
    diag = Counter()

    # Project-specific reliable source: statcast pitch-level parquet rows.
    # This directly identifies the first pitcher in each first-inning half.
    statcast_count = extract_statcast_first_inning_lookup(repo, mlb_data_dir, target_date, lookup, audit)
    diag["statcast_pitch_level_rows"] = statcast_count

    for fp in files:
        df = read_table(fp)
        if df is None or df.empty:
            continue
        diag["files_read"] += 1
        cols = list(df.columns)

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
        api_count = add_statsapi_current_pitcher_rows(repo, target_date, lookup, audit)
        diag["statsapi_current_pitcher_rows"] = api_count

    # Remove internal priority from public lookup.
    public_lookup = {}
    for k, v in lookup.items():
        vv = dict(v)
        vv.pop("priority", None)
        public_lookup[k] = vv

    out_dir = repo / "data" / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "1.0",
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
        "confidence", "method", "starterMethod", "source",
    ]
    with audit_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in audit:
            writer.writerow(row)

    print("\nFirst-inning lookup build complete")
    print(f"  Files read              : {diag['files_read']}")
    print(f"  Direct pitcher rows     : {diag['direct_pitcher_rows']}")
    print(f"  Starter candidates      : {diag['starter_candidates']}")
    print(f"  Team 1st-inning rows    : {diag['team_first_rows']}")
    print(f"  Paired starter rows     : {diag['paired_starter_rows']}")
    print(f"  Statcast pitcher rows   : {diag['statcast_pitch_level_rows']}")
    print(f"  StatsAPI current rows   : {diag['statsapi_current_pitcher_rows']}")
    print(f"  Lookup keys written     : {len(public_lookup)}")
    print(f"  JSON                    : {json_path}")
    print(f"  Audit                   : {audit_path}")

    if not public_lookup:
        print("\nWARNING: No first-inning lookup rows were created.")
        print("Try adding --scan-all, then inspect the audit/printed diagnostics and parquet column names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
