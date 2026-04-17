#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import math
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any
from shutil import rmtree

import numpy as np
import pandas as pd

DEFAULT_WEBSITE_REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEARCH_ROOTS = [
    DEFAULT_WEBSITE_REPO,
    Path.cwd(),
    Path(r"C:\python"),
    Path(r"C:\python\data_nba"),
    Path.home(),
]


# ---------- shared helpers ----------
def iso_date(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    try:
        ts = pd.to_datetime(value)
        if pd.isna(ts):
            return ""
        return ts.date().isoformat()
    except Exception:
        return str(value).strip()


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except Exception:
        return None


def safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def clean_str(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def coalesce_named_column(df: pd.DataFrame, target: str, candidates: list[str]) -> pd.DataFrame:
    df = df.copy()
    existing = [c for c in candidates if c in df.columns]
    if not existing:
        return df

    if target not in df.columns:
        df[target] = np.nan

    out = df[target]
    for c in existing:
        s = df[c]
        if s.dtype == object:
            s = s.replace("", np.nan)
        out = out.where(out.notna(), s)

    df[target] = out

    drop_cols = [c for c in existing if c != target]
    if drop_cols:
        df = df.drop(columns=drop_cols, errors="ignore")

    return df


def normalize_game_numeric_id(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\.0+$", "", s)
    return s


def find_latest_file(patterns, roots):
    candidates = []
    for root in roots:
        root_path = Path(root) if root else None
        if not root_path or not root_path.exists():
            continue
        for pattern in patterns:
            candidates.extend(root_path.rglob(pattern))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_all_files(patterns, roots) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        root_path = Path(root) if root else None
        if not root_path or not root_path.exists():
            continue
        for pattern in patterns:
            for p in root_path.rglob(pattern):
                if p.is_file():
                    key = str(p.resolve()) if p.exists() else str(p)
                    if key not in seen:
                        seen.add(key)
                        candidates.append(p)
    return candidates


def _extract_date_window_token(path: Path | None) -> str:
    if path is None:
        return ""
    m = re.search(r"(20\d{6}_20\d{6})", path.name)
    return m.group(1) if m else ""


def _path_priority(path: Path, website_repo: Path) -> tuple[int, int]:
    txt = str(path).lower()
    repo_txt = str(website_repo).lower()
    if txt.startswith(repo_txt):
        return (0, 0)
    if "models_v1" in txt:
        return (1, 0)
    if "data_nba" in txt:
        return (2, 0)
    if "\\python\\" in txt or "/python/" in txt:
        return (3, 0)
    return (9, 0)


def _choose_best_candidate(
    candidates: list[Path],
    *,
    website_repo: Path,
    preferred_token: str = "",
) -> Path | None:
    if not candidates:
        return None

    def score(p: Path):
        token = _extract_date_window_token(p)
        token_match = 0 if preferred_token and token == preferred_token else 1
        pri = _path_priority(p, website_repo)
        return (token_match, *pri, -p.stat().st_mtime)

    return sorted(candidates, key=score)[0]


def resolve_artifacts(
    *,
    website_repo: Path,
    workbook: Path | None,
    player_df: Path | None,
    upcoming: Path | None,
    analyzer_script: Path | None,
) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    search_roots = [website_repo, *DEFAULT_SEARCH_ROOTS]

    workbook_path = Path(workbook) if workbook else None
    player_df_path = Path(player_df) if player_df else None
    upcoming_path = Path(upcoming) if upcoming else None
    analyzer_script_path = Path(analyzer_script) if analyzer_script else None

    workbook_candidates = find_all_files(["props_all_in_one_*.xlsx", "*props_all_in_one*.xlsx"], search_roots)
    upcoming_candidates = find_all_files(["player_props_upcoming_*.csv"], search_roots)
    player_df_candidates = find_all_files(["player_df.parquet"], search_roots)
    if workbook_path is None:
        workbook_path = _choose_best_candidate(workbook_candidates, website_repo=website_repo)
    preferred_token = _extract_date_window_token(workbook_path)

    if upcoming_path is None:
        upcoming_path = _choose_best_candidate(
            upcoming_candidates,
            website_repo=website_repo,
            preferred_token=preferred_token,
        )

    if player_df_path is None:
        player_df_path = _choose_best_candidate(player_df_candidates, website_repo=website_repo)

    if analyzer_script_path is None:
        sibling_exact = website_repo / "tools" / "nba_props_analyzer.py"
        analyzer_script_path = sibling_exact if sibling_exact.exists() else None

    return workbook_path, player_df_path, upcoming_path, analyzer_script_path


def load_games_map(games_path: Path) -> dict[str, dict]:
    payload = json.loads(games_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for item in payload or []:
        game_num = normalize_game_numeric_id(item.get("gameId") or item.get("id"))
        if game_num:
            out[game_num] = item
    return out


def derive_team_context(row: pd.Series, games_map: dict[str, dict]) -> tuple[str, str, str]:
    game = games_map.get(normalize_game_numeric_id(row.get("GAME_ID"))) or {}
    away = clean_str(game.get("awayTeam"))
    home = clean_str(game.get("homeTeam"))
    team_side = clean_str(row.get("TEAM_SIDE")).lower()
    is_home = safe_int(row.get("IS_HOME"))
    if team_side == "home" or is_home == 1:
        return home, away, "Home"
    if team_side == "away" or is_home == 0:
        return away, home, "Away"
    return "", "", ""


def canonical_injury_status(value) -> str:
    raw = clean_str(value).lower()
    if not raw:
        return ""
    mapping = {
        "p": "Probable",
        "probable": "Probable",
        "q": "Questionable",
        "questionable": "Questionable",
        "gtd": "Questionable",
        "out": "Out",
        "o": "Out",
        "doubtful": "Doubtful",
        "d": "Doubtful",
    }
    return mapping.get(raw, raw.title())


def normalize_lookup_token(value: Any) -> str:
    text = clean_str(value).lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_injury_lookup(injury_data: dict) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    players = injury_data.get("players") or injury_data.get("entries") or []
    for entry in players:
        player_key = normalize_lookup_token(entry.get("player") or entry.get("player_name"))
        team_key = clean_str(entry.get("team") or entry.get("team_abbr"))
        if not player_key:
            continue
        payload = {
            "status": canonical_injury_status(entry.get("status")),
            "note": clean_str(entry.get("note") or entry.get("injury_note")),
            "gameDate": iso_date(entry.get("gameDate") or entry.get("game_date")),
            "team": team_key,
            "lastUpdated": clean_str(entry.get("lastUpdated") or entry.get("last_updated") or entry.get("updated_at")),
        }
        out[(player_key, team_key)] = payload
        out.setdefault((player_key, ""), payload)
    return out



# ---------- analyzer integration ----------
TEAM_ID_TO_ABBR = {
    "1610612737": "ATL", "1610612738": "BOS", "1610612739": "CLE", "1610612740": "NOP",
    "1610612741": "CHI", "1610612742": "DAL", "1610612743": "DEN", "1610612744": "GSW",
    "1610612745": "HOU", "1610612746": "LAC", "1610612747": "LAL", "1610612748": "MIA",
    "1610612749": "MIL", "1610612750": "MIN", "1610612751": "BKN", "1610612752": "NYK",
    "1610612753": "ORL", "1610612754": "IND", "1610612755": "PHI", "1610612756": "PHX",
    "1610612757": "POR", "1610612758": "SAC", "1610612759": "SAS", "1610612760": "OKC",
    "1610612761": "TOR", "1610612762": "UTA", "1610612763": "MEM", "1610612764": "WAS",
    "1610612765": "DET", "1610612766": "CHA",
}

DATE_CANDIDATES = [
    "GAME_DATE", "GAME_DATE_EST", "GAME_DATE_LOCAL", "GAME_DATE_DT",
    "GAME_DT", "DATE", "GAME_START_DATE", "GAME_DAY",
    "game_date", "gameDate", "start_date", "START_DATE",
]
GAME_ID_CANDIDATES = ["GAME_ID", "game_id"]

def _first_existing(cols: list[str], available: pd.Index) -> str | None:
    for c in cols:
        if c in available:
            return c
    return None

def _norm_name(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _norm_name_series(series: pd.Series) -> pd.Series:
    return series.astype(str).map(_norm_name)

def _norm_id_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    s = re.sub(r"\.0+$", "", s)
    return s

def _norm_id_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\.0+$", "", regex=True)

def _coerce_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")

def _team_id_to_abbr(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    s = re.sub(r"\.0+$", "", s)
    return TEAM_ID_TO_ABBR.get(s, s)

def percentile_rank(x: float, arr: np.ndarray) -> float:
    arr = arr[np.isfinite(arr)]
    if arr.size == 0 or not np.isfinite(x):
        return float("nan")
    return float((arr <= x).mean())

def parse_date_from_game_id_anywhere(game_id: str) -> pd.Timestamp | None:
    if game_id is None:
        return None
    s = str(game_id).strip()
    m = re.search(r"(\d{8})", s)
    if not m:
        return None
    try:
        return pd.to_datetime(m.group(1), format="%Y%m%d", errors="raise")
    except Exception:
        return None

class _BuiltinAnalyzerModule:
    _norm_id_str = staticmethod(_norm_id_str)
    _norm_id_series = staticmethod(_norm_id_series)
    _safe_float = staticmethod(safe_float)
    _coerce_date = staticmethod(_coerce_date)
    percentile_rank = staticmethod(percentile_rank)
    _team_id_to_abbr = staticmethod(_team_id_to_abbr)

class LocalNBAPropsAnalyzer:
    def __init__(self, hist_path: Path, upcoming_path: Path | None = None):
        self.hist_path = Path(hist_path)
        self.upcoming_path = Path(upcoming_path) if upcoming_path else None
        self.player_df: pd.DataFrame | None = None
        self.upcoming_df: pd.DataFrame | None = None

        self.col_player_id = "PLAYER_ID"
        self.col_player_name = None
        self.col_game_id = None
        self.col_game_date = None
        self.col_team_id = None
        self.col_team_side = None
        self.col_opp_team_id = None
        self.col_is_home = None
        self.col_min = None
        self.stat_cols: dict[str, str] = {}

    def _try_read_dataframe(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        suf = path.suffix.lower()
        if suf == ".parquet":
            return pd.read_parquet(path)
        if suf in (".csv", ".txt"):
            return pd.read_csv(path)
        raise ValueError(f"Unsupported file type: {path.suffix}")

    def load(self) -> None:
        self.player_df = self._try_read_dataframe(self.hist_path).copy()
        self._detect_columns()
        self._dedupe_historical()
        self._ensure_game_date()
        self._clean_types()
        self._add_derived_opp_metrics(self.player_df)
        self._load_upcoming_if_available()

    def _detect_columns(self) -> None:
        assert self.player_df is not None
        cols = self.player_df.columns
        self.col_player_name = _first_existing(["PLAYER_NAME", "PLAYER", "NAME"], cols)
        self.col_game_id = _first_existing(GAME_ID_CANDIDATES, cols)
        self.col_game_date = _first_existing(DATE_CANDIDATES, cols)
        self.col_team_id = _first_existing(["TEAM_ID", "team_id"], cols)
        self.col_team_side = _first_existing(["TEAM_SIDE", "team_side"], cols)
        self.col_opp_team_id = _first_existing(["OPP_TEAM_ID", "OPPONENT_TEAM_ID", "opp_team_id"], cols)
        self.col_is_home = _first_existing(["IS_HOME", "HOME", "is_home"], cols)
        self.col_min = _first_existing(["MIN", "MINUTES", "minutes"], cols)

        self.stat_cols["PTS"] = _first_existing(["PTS", "POINTS"], cols) or "PTS"
        self.stat_cols["REB"] = _first_existing(["REB", "REBOUNDS"], cols) or "REB"
        self.stat_cols["AST"] = _first_existing(["AST", "ASSISTS"], cols) or "AST"
        self.stat_cols["TPM"] = _first_existing(["TPM", "FG3M", "FG3M_TOTAL", "FG3M_STAT"], cols) or "TPM"
        pra_col = _first_existing(["PRA"], cols)
        if pra_col is not None:
            self.stat_cols["PRA"] = pra_col

        required = [self.col_player_name, self.col_game_id, self.col_team_id, self.col_min]
        if any(x is None for x in required):
            raise ValueError(
                f"Missing required columns in historical player_df: "
                f"player_name={self.col_player_name}, game_id={self.col_game_id}, "
                f"team_id={self.col_team_id}, min={self.col_min}"
            )

    def _dedupe_historical(self) -> None:
        assert self.player_df is not None
        keys = [self.col_player_id, self.col_game_id]
        if self.col_team_side and self.col_team_side in self.player_df.columns:
            keys.append(self.col_team_side)
        if self.col_team_id and self.col_team_id in self.player_df.columns:
            keys.append(self.col_team_id)
        self.player_df = self.player_df.drop_duplicates(subset=keys, keep="last").copy()

    def _ensure_game_date(self) -> None:
        assert self.player_df is not None
        if self.col_game_date is not None:
            return
        parsed = self.player_df[self.col_game_id].astype(str).map(parse_date_from_game_id_anywhere)
        self.player_df["GAME_DATE"] = parsed
        self.col_game_date = "GAME_DATE"

    def _clean_types(self) -> None:
        assert self.player_df is not None
        self.player_df[self.col_player_id] = _norm_id_series(self.player_df[self.col_player_id])
        self.player_df[self.col_team_id] = _norm_id_series(self.player_df[self.col_team_id])
        if self.col_opp_team_id and self.col_opp_team_id in self.player_df.columns:
            self.player_df[self.col_opp_team_id] = _norm_id_series(self.player_df[self.col_opp_team_id])

        self.player_df[self.col_min] = pd.to_numeric(self.player_df[self.col_min], errors="coerce").fillna(0.0)
        for _, c in self.stat_cols.items():
            if c in self.player_df.columns:
                self.player_df[c] = pd.to_numeric(self.player_df[c], errors="coerce")

        if "PRA" not in self.stat_cols or self.stat_cols.get("PRA") not in self.player_df.columns:
            pts, reb, ast = self.stat_cols["PTS"], self.stat_cols["REB"], self.stat_cols["AST"]
            if pts in self.player_df.columns and reb in self.player_df.columns and ast in self.player_df.columns:
                self.player_df["PRA_calc"] = (
                    self.player_df[pts].fillna(0) + self.player_df[reb].fillna(0) + self.player_df[ast].fillna(0)
                )
                self.stat_cols["PRA"] = "PRA_calc"

        if self.col_game_date and self.col_game_date in self.player_df.columns:
            self.player_df[self.col_game_date] = _coerce_date(self.player_df[self.col_game_date])

        inferred_is_home = False
        if self.col_is_home and self.col_is_home in self.player_df.columns:
            s = self.player_df[self.col_is_home]
            if pd.api.types.is_numeric_dtype(s):
                v = pd.to_numeric(s, errors="coerce")
                self.player_df[self.col_is_home] = (v > 0.5).astype(int)
            else:
                s2 = s.astype(str).str.upper().str.strip().str.replace(r"\.0+$", "", regex=True)
                self.player_df[self.col_is_home] = s2.isin(["1", "TRUE", "T", "HOME", "H", "YES", "Y"]).astype(int)
            inferred_is_home = True

        if self.col_team_side and self.col_team_side in self.player_df.columns:
            side = self.player_df[self.col_team_side].astype(str).str.upper().str.strip()
            side_home = side.isin(["HOME", "H", "VS", "V", "HOST"]).astype(int)
            if not inferred_is_home:
                self.player_df["IS_HOME"] = side_home
                self.col_is_home = "IS_HOME"
                inferred_is_home = True
            else:
                cur = self.player_df[self.col_is_home]
                if cur.nunique(dropna=True) <= 1 and side_home.nunique(dropna=True) > 1:
                    self.player_df[self.col_is_home] = side_home

        if (not inferred_is_home) and "MATCHUP" in self.player_df.columns:
            m = self.player_df["MATCHUP"].astype(str)
            is_home = m.str.contains(r"\bVS\b|VS\.|vs\.|\bHOME\b", regex=True, case=False)
            is_away = m.str.contains("@", regex=False)
            self.player_df["IS_HOME"] = np.where(is_home, 1, np.where(is_away, 0, np.nan))
            self.player_df["IS_HOME"] = pd.to_numeric(self.player_df["IS_HOME"], errors="coerce").fillna(0).astype(int)
            self.col_is_home = "IS_HOME"

        if self.col_game_date and self.player_df[self.col_game_date].notna().any():
            self.player_df = self.player_df.sort_values(
                [self.col_player_id, self.col_game_date, self.col_game_id],
                na_position="first",
                kind="mergesort",
            ).reset_index(drop=True)
        else:
            self.player_df = self.player_df.sort_values(
                [self.col_player_id, self.col_game_id],
                kind="mergesort",
            ).reset_index(drop=True)

        self.player_df["GAME_SEQ"] = self.player_df.groupby(self.col_player_id).cumcount() + 1

    def _load_upcoming_if_available(self) -> None:
        if self.upcoming_path is None or not self.upcoming_path.exists():
            self.upcoming_df = None
            return
        self.upcoming_df = pd.read_csv(self.upcoming_path).copy()
        self._clean_upcoming()

    def _clean_upcoming(self) -> None:
        if self.upcoming_df is None:
            return
        for c in ["PLAYER_ID", "TEAM_ID", "OPP_TEAM_ID"]:
            if c in self.upcoming_df.columns:
                self.upcoming_df[c] = _norm_id_series(self.upcoming_df[c])
        if "GAME_DATE" in self.upcoming_df.columns:
            self.upcoming_df["GAME_DATE"] = _coerce_date(self.upcoming_df["GAME_DATE"])
        self._add_derived_opp_metrics(self.upcoming_df)

    def _add_derived_opp_metrics(self, df: pd.DataFrame | None) -> None:
        if df is None or df.empty:
            return
        for suf in ("_r10", "_r5", "_r3", ""):
            pts_col = f"OPP_PTS_ALLOWED{suf}"
            drtg_col = f"OPP_DRtg{suf}"
            pos_col = f"OPP_POS_EST{suf}"
            if pts_col in df.columns and drtg_col in df.columns and pos_col not in df.columns:
                pts = pd.to_numeric(df[pts_col], errors="coerce")
                dr = pd.to_numeric(df[drtg_col], errors="coerce")
                with np.errstate(divide="ignore", invalid="ignore"):
                    df[pos_col] = 100.0 * pts / dr

    def _metric_candidates_for_stat(self, stat: str) -> list[str]:
        stat = stat.upper()
        if stat == "PTS":
            bases = ["OPP_PTS_ALLOWED", "OPP_DRtg", "OPP_POSS_ALLOWED", "OPP_POS_EST"]
        elif stat == "REB":
            bases = [
                "OPP_REB_ALLOWED", "OPP_TRB_ALLOWED", "OPP_REB", "OPP_TRB",
                "OPP_DREB_ALLOWED", "OPP_OREB_ALLOWED", "OPP_REB_PCT", "OPP_DREB_PCT",
                "OPP_OREB_PCT", "OPP_POS_EST", "OPP_PTS_ALLOWED", "OPP_DRtg",
            ]
        elif stat == "AST":
            bases = ["OPP_AST_ALLOWED", "OPP_AST", "OPP_DRtg"]
        elif stat == "TPM":
            bases = ["OPP_3PM_ALLOWED", "OPP_FG3M_ALLOWED", "OPP_3PA_ALLOWED", "OPP_FG3A_ALLOWED", "OPP_3P_PCT_ALLOWED", "OPP_DRtg"]
        elif stat == "PRA":
            bases = ["OPP_PTS_ALLOWED", "OPP_DRtg", "OPP_POSS_ALLOWED", "OPP_POS_EST"]
        else:
            bases = ["OPP_DRtg"]
        out = []
        for base in bases:
            out.extend([f"{base}_r10", f"{base}_r5", f"{base}_r3", base])
        return out

    def _pick_metric_col(self, df: pd.DataFrame, stat: str) -> str | None:
        for c in self._metric_candidates_for_stat(stat):
            if c in df.columns:
                return c
        return None

    def _metric_cols_for_stat_in_both(self, stat: str, hist_df: pd.DataFrame, up_row: pd.Series | None, max_cols: int = 3) -> list[str]:
        if up_row is None:
            return []
        cols = []
        for c in self._metric_candidates_for_stat(stat):
            if c in hist_df.columns and c in up_row.index:
                hv = pd.to_numeric(hist_df[c], errors="coerce")
                uv = safe_float(up_row[c])
                if hv.notna().sum() >= 8 and uv is not None and np.isfinite(uv):
                    cols.append(c)
            if len(cols) >= max_cols:
                break
        return cols

    def _get_upcoming_row(self, player_id: str, player_name: str | None = None) -> pd.Series | None:
        if self.upcoming_df is None or self.upcoming_df.empty:
            return None
        up_cols = self.upcoming_df.columns
        id_col = _first_existing(["PLAYER_ID", "player_id", "PLAYERID", "playerid"], up_cols)
        name_col = _first_existing(["PLAYER_NAME", "PLAYER", "NAME", "player_name", "player", "name"], up_cols)
        pid = _norm_id_str(player_id)
        sub = pd.DataFrame()
        if id_col is not None:
            sub = self.upcoming_df[_norm_id_series(self.upcoming_df[id_col]) == pid].copy()
        if sub.empty and player_name and name_col is not None:
            pn = _norm_name(str(player_name))
            sub = self.upcoming_df[_norm_name_series(self.upcoming_df[name_col]) == pn].copy()
        if sub.empty:
            return None
        if "GAME_DATE" in sub.columns:
            sub["GAME_DATE"] = _coerce_date(sub["GAME_DATE"])
            if sub["GAME_DATE"].notna().any():
                today = pd.Timestamp.now().normalize()
                future = sub[sub["GAME_DATE"].dt.normalize() >= today].copy()
                if not future.empty:
                    sub = future
                sub = sub.sort_values("GAME_DATE", kind="mergesort")
        non_null_counts = sub.notna().sum(axis=1)
        sub = sub.assign(_nn=non_null_counts).sort_values("_nn", ascending=False, kind="mergesort")
        return sub.iloc[0].drop(labels=["_nn"], errors="ignore")

def import_analyzer_module(path: Path | None):
    if path is None:
        return _BuiltinAnalyzerModule()
    import importlib.util
    spec = importlib.util.spec_from_file_location("nba_props_analyzer_module", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analyzer script from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
def stats_block(df: pd.DataFrame, stat_col: str) -> dict[str, Any]:
    y = pd.to_numeric(df[stat_col], errors="coerce").dropna() if stat_col in df.columns else pd.Series(dtype=float)
    if y.empty:
        return {"n": 0, "avg": None, "median": None, "std": None, "max": None}
    return {
        "n": int(len(y)),
        "avg": float(y.mean()),
        "median": float(y.median()),
        "std": float(y.std(ddof=0)),
        "max": float(y.max()),
    }


def split_blocks(df: pd.DataFrame, stat_col: str, home_col: str | None) -> dict[str, dict[str, Any]]:
    out = {"overall": stats_block(df, stat_col)}
    if home_col and home_col in df.columns:
        h = pd.to_numeric(df[home_col], errors="coerce").fillna(0).astype(int) == 1
        out["home"] = stats_block(df[h], stat_col)
        out["away"] = stats_block(df[~h], stat_col)
    return out


def looks_like_team_id(s: pd.Series) -> bool:
    x = s.dropna().astype(str).str.strip().str.replace(r"\.0+$", "", regex=True)
    if x.empty:
        return False
    return (x.str.fullmatch(r"\d{8,12}").mean() >= 0.7)


def make_opp_series(df: pd.DataFrame, analyzer, module) -> pd.Series:
    if "OPP_ABBR" in df.columns:
        return df["OPP_ABBR"].astype(str)
    for c in ["OPP_TEAM_ABBR", "OPPONENT_ABBREVIATION", "OPPONENT_ABBR"]:
        if c in df.columns:
            return df[c].astype(str)
    if "MATCHUP" in df.columns:
        m = df["MATCHUP"].astype(str).str.strip()
        opp = m.str.extract(r"(?:vs\.?|@)\s*([A-Z]{2,4})\s*$", expand=False)
        if opp.notna().any():
            return opp.fillna("")
    if "OPP" in df.columns and not looks_like_team_id(df["OPP"]):
        return df["OPP"].astype(str)
    if "OPP_TEAM_ID" in df.columns:
        return df["OPP_TEAM_ID"].astype(str).map(module._team_id_to_abbr).fillna(df["OPP_TEAM_ID"].astype(str))
    return pd.Series([""] * len(df), index=df.index)


def build_game_logs(df: pd.DataFrame, stat_col: str, analyzer, module) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    out = []
    opp_series = make_opp_series(df, analyzer, module)
    for idx, row in df.iterrows():
        value = safe_float(row.get(stat_col))
        minutes = safe_float(row.get("MIN"))
        game_date = iso_date(row.get(analyzer.col_game_date)) if analyzer.col_game_date else ""
        is_home = safe_int(row.get(analyzer.col_is_home)) if analyzer.col_is_home and analyzer.col_is_home in row.index else None
        out.append({
            "gameId": normalize_game_numeric_id(row.get(analyzer.col_game_id)) if analyzer.col_game_id else "",
            "gameDate": game_date,
            "seq": safe_int(row.get("GAME_SEQ")),
            "value": value,
            "minutes": minutes,
            "opp": clean_str(opp_series.loc[idx]) if idx in opp_series.index else "",
            "isHome": is_home,
            "location": "Home" if is_home == 1 else "Away" if is_home == 0 else "",
            "simBin": clean_str(row.get("_sim_bin") or "all"),
            "simScore": safe_float(row.get("_sim_score")),
            "simPct": safe_float(row.get("_sim_pct")),
        })
    out.sort(key=lambda g: (g.get("gameDate") or "", g.get("seq") or 0, g.get("gameId") or ""))
    return out


def prepare_series(
    analyzer,
    module,
    player_id: str,
    player_name: str,
    stat: str,
    series_game_date: str,
    similar_n: int = 10,
    season_type: str | list[str] | tuple[str, ...] | set[str] | None = "All",
) -> tuple[dict[str, Any], pd.Series | None]:
    assert analyzer.player_df is not None

    stat = clean_str(stat).upper()
    if stat not in analyzer.stat_cols:
        raise ValueError(f"Unknown stat: {stat}")

    stat_col = analyzer.stat_cols[stat]
    pid = module._norm_id_str(player_id)

    def _normalize_types(value) -> set[str]:
        if value is None:
            return set()
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        out = set()
        for x in vals:
            s = str(x).replace("_", " ").strip().lower()
            if not s:
                continue
            if s in {"regular season", "reg season", "regular"}:
                out.add("regular season")
            elif s in {"play-in", "play in", "playin"}:
                out.add("play-in")
            elif s in {"playoffs", "playoff"}:
                out.add("playoffs")
            elif s == "all":
                out.add("all")
            else:
                out.add(s)
        return out

    df_all = analyzer.player_df[analyzer.player_df[analyzer.col_player_id] == pid].copy()
    df_all = df_all[df_all[analyzer.col_min] > 0].copy()
    if df_all.empty:
        raise ValueError(f"No historical games with minutes for {player_name} {stat}")

    if "SEASON_TYPE" in df_all.columns:
        requested_types = _normalize_types(season_type)
        available_types = _normalize_types(df_all["SEASON_TYPE"].astype(str).tolist())
        has_postseason_rows = bool(available_types & {"play-in", "playoffs"})

        should_filter = (
            requested_types
            and "all" not in requested_types
            and not (requested_types == {"regular season"} and has_postseason_rows)
        )

        if should_filter:
            df_filtered = df_all[
                df_all["SEASON_TYPE"]
                .astype(str)
                .str.replace("_", " ", regex=False)
                .str.strip()
                .str.lower()
                .isin(requested_types)
            ].copy()
            if not df_filtered.empty:
                df_all = df_filtered

    if analyzer.col_game_date and analyzer.col_game_date in df_all.columns and df_all[analyzer.col_game_date].notna().any():
        df_all[analyzer.col_game_date] = pd.to_datetime(
            module._coerce_date(df_all[analyzer.col_game_date]),
            errors="coerce"
        ).dt.normalize()

        cutoff_ts = pd.to_datetime(series_game_date, errors="coerce")
        if pd.notna(cutoff_ts):
            cutoff_ts = pd.Timestamp(cutoff_ts).normalize()
            df_all = df_all[
                df_all[analyzer.col_game_date].isna()
                | (df_all[analyzer.col_game_date] <= cutoff_ts)
            ].copy()

        df_all = df_all.sort_values(analyzer.col_game_date, na_position="first").copy()
        xcol = analyzer.col_game_date
    else:
        df_all = df_all.sort_values("GAME_SEQ").copy()
        xcol = "GAME_SEQ"

    if df_all.empty:
        raise ValueError(f"No historical games available for {player_name} {stat} before {series_game_date}")

    up_row = analyzer._get_upcoming_row(pid, player_name)
    opp_team_id = None
    target_metric = None
    metric_col_up = None

    if up_row is not None:
        if "OPP_TEAM_ID" in up_row.index:
            opp_team_id = clean_str(up_row.get("OPP_TEAM_ID"))
        metric_col_up = analyzer._pick_metric_col(analyzer.upcoming_df, stat) if analyzer.upcoming_df is not None else None
        if metric_col_up and metric_col_up in up_row.index:
            target_metric = module._safe_float(up_row.get(metric_col_up))

    metric_col_hist = analyzer._pick_metric_col(df_all, stat)
    sim_metric_cols = (
        analyzer._metric_cols_for_stat_in_both(stat, df_all, up_row, max_cols=3)
        if up_row is not None else []
    )

    df_display = df_all.copy()
    similar_block = None
    similarity_mode = "none"

    if sim_metric_cols and up_row is not None:
        df_all_sim = df_all.copy()
        score_parts = []
        usable_sim_metric_cols = []

        for c in sim_metric_cols:
            if c not in df_all_sim.columns or c not in up_row.index:
                continue

            hv = pd.to_numeric(df_all_sim[c], errors="coerce")
            tv = module._safe_float(up_row.get(c))
            if tv is None or not np.isfinite(tv):
                continue

            scale = float(hv.std(ddof=0))
            if not np.isfinite(scale) or scale <= 1e-9:
                q75, q25 = hv.quantile(0.75), hv.quantile(0.25)
                iqr = float(q75 - q25) if pd.notna(q75) and pd.notna(q25) else np.nan
                scale = (iqr / 1.349) if np.isfinite(iqr) and iqr > 1e-9 else 1.0

            part = ((hv - tv).abs() / scale).clip(lower=0, upper=8)
            sim_col = f"_sim_{c}"
            df_all_sim[sim_col] = part
            score_parts.append(sim_col)
            usable_sim_metric_cols.append(c)

        sim_metric_cols = usable_sim_metric_cols

        if score_parts:
            df_all_sim["_sim_score"] = df_all_sim[score_parts].mean(axis=1, skipna=True)
            valid = df_all_sim["_sim_score"].notna()
            if valid.any():
                score_pct = df_all_sim.loc[valid, "_sim_score"].rank(method="average", pct=True)
                df_all_sim.loc[valid, "_sim_pct"] = score_pct
                df_all_sim.loc[valid, "_sim_bin"] = pd.cut(
                    df_all_sim.loc[valid, "_sim_pct"],
                    bins=[-0.001, 0.25, 0.50, 0.75, 1.0],
                    labels=["Closest 25%", "Close 25%", "Mid 25%", "Far 25%"],
                    include_lowest=True,
                ).astype(str)

                key_cols = [c for c in [analyzer.col_player_id, analyzer.col_game_id] if c in df_all_sim.columns and c in df_display.columns]
                take_cols = [c for c in key_cols + ["_sim_score", "_sim_pct", "_sim_bin"] if c in df_all_sim.columns]

                if key_cols:
                    df_display = df_display.drop(
                        columns=[c for c in ["_sim_score", "_sim_pct", "_sim_bin"] if c in df_display.columns],
                        errors="ignore",
                    )
                    df_display = df_display.merge(
                        df_all_sim[take_cols].drop_duplicates(subset=key_cols, keep="last"),
                        on=key_cols,
                        how="left",
                    )
                else:
                    df_display["_sim_score"] = df_all_sim["_sim_score"].values
                    df_display["_sim_pct"] = df_all_sim["_sim_pct"].values
                    df_display["_sim_bin"] = df_all_sim["_sim_bin"].values

                df_display["_sim_bin"] = df_display["_sim_bin"].fillna("Unknown")
                similar_block = df_all_sim.loc[valid].sort_values("_sim_score").head(similar_n).copy()
                similarity_mode = "composite_zscore_quantiles"

    if similar_block is None and metric_col_hist and target_metric is not None and np.isfinite(target_metric):
        df_display["_metric"] = pd.to_numeric(df_display[metric_col_hist], errors="coerce")
        df_display["_absdiff"] = (df_display["_metric"] - target_metric).abs()
        bins = [-1.0, 1.5, 3.0, 5.0, 999.0]
        labels = ["≤1.5", "1.5–3", "3–5", "5+"]
        df_display["_sim_bin"] = pd.cut(df_display["_absdiff"], bins=bins, labels=labels, include_lowest=True)
        similar_block = df_display.sort_values("_absdiff").head(similar_n).copy()
        similarity_mode = "single_metric_absdiff"

    if "_sim_bin" not in df_display.columns:
        df_display["_sim_bin"] = "all"

    if analyzer.col_game_date and analyzer.col_game_date in df_display.columns and df_display[analyzer.col_game_date].notna().any():
        df_recent = df_display[df_display[analyzer.col_game_date].notna()].tail(25).copy()
        if len(df_recent) < 25:
            df_recent = df_display.tail(25).copy()
    else:
        df_recent = df_display.tail(25).copy()

    model_pred = None
    model_mu = None
    model_sigma = None
    exp_min = None
    if up_row is not None:
        pred_col = f"pred_{stat}"
        mu_col = f"{stat.lower()}_mu"
        sig_col = f"{stat.lower()}_sigma"
        model_pred = safe_float(up_row.get(pred_col)) if pred_col in up_row.index else None
        model_mu = safe_float(up_row.get(mu_col)) if mu_col in up_row.index else None
        model_sigma = safe_float(up_row.get(sig_col)) if sig_col in up_row.index else None
        exp_min = safe_float(up_row.get("EXP_MIN") or up_row.get("MIN") or up_row.get("min_proj"))

    matchup_percentile = None
    if analyzer.upcoming_df is not None and metric_col_up and target_metric is not None and np.isfinite(target_metric):
        if metric_col_up in analyzer.upcoming_df.columns and "OPP_TEAM_ID" in analyzer.upcoming_df.columns:
            tmp = analyzer.upcoming_df[["OPP_TEAM_ID", metric_col_up]].dropna().copy()
            tmp["OPP_TEAM_ID"] = module._norm_id_series(tmp["OPP_TEAM_ID"])
            tmp[metric_col_up] = pd.to_numeric(tmp[metric_col_up], errors="coerce")
            team_metric = tmp.groupby("OPP_TEAM_ID")[metric_col_up].mean()
            if len(team_metric):
                matchup_percentile = float(module.percentile_rank(target_metric, team_metric.values))

    series_payload = {
        "playerId": safe_int(player_id) or clean_str(player_id),
        "player": player_name,
        "stat": stat,
        "statDisplay": stat,
        "gameDate": series_game_date,
        "recentWindow": 25,
        "xAxis": xcol,
        "oppTeamIdUpcoming": opp_team_id,
        "matchupMetricCol": metric_col_up or metric_col_hist,
        "matchupMetricValue": safe_float(target_metric),
        "matchupPercentileAmongTeams": matchup_percentile,
        "similarityMetricCols": sim_metric_cols,
        "similarityMode": similarity_mode,
        "modelPred": model_pred,
        "modelMu": model_mu,
        "modelSigma": model_sigma,
        "expMin": exp_min,
        "samples": {
            "recent": split_blocks(df_recent, stat_col, analyzer.col_is_home),
            "overall": split_blocks(df_display, stat_col, analyzer.col_is_home),
            "similar": stats_block(similar_block, stat_col) if similar_block is not None and not similar_block.empty else {"n": 0, "avg": None, "median": None, "std": None, "max": None},
        },
        "games": build_game_logs(df_display, stat_col, analyzer, module),
        "similarGames": build_game_logs(similar_block if similar_block is not None else pd.DataFrame(), stat_col, analyzer, module),
    }
    return series_payload, up_row

def entry_from_row(row: pd.Series, games_map: dict[str, dict], series_key: str) -> dict[str, Any]:
    team, opp, location = derive_team_context(row, games_map)
    stat = clean_str(row.get("stat") or row.get("stat_display")).upper()
    line = safe_float(row.get("line"))
    line_slug = (str(int(line)) if line is not None and float(line).is_integer() else clean_str(line).replace('.', '_')) if line is not None else "na"
    return {
        "id": f"{series_key}|{line_slug}",
        "seriesKey": series_key,
        "gameDate": iso_date(row.get("GAME_DATE")),
        "gameId": safe_int(row.get("GAME_ID")),
        "player": clean_str(row.get("PLAYER_NAME")),
        "playerId": safe_int(row.get("PLAYER_ID")),
        "team": team,
        "opp": opp,
        "location": location,
        "matchup": f"{team} vs {opp}" if team and opp else "",
        "stat": stat,
        "stat_display": clean_str(row.get("stat_display") or stat),
        "line": line,
        "board": clean_str(row.get("board")),
        "board_score": safe_float(row.get("board_score")),
        "prob_cons": safe_float(row.get("prob_cons")),
        "fair_american": safe_float(row.get("fair_american")),
        "avg_anchor": safe_float(row.get("avg_anchor")),
        "pred_anchor": safe_float(row.get("pred_anchor")),
        "mu_cons": safe_float(row.get("mu_cons")),
        "pred_minus_line": safe_float(row.get("pred_minus_line")),
        "avg_minus_line": safe_float(row.get("avg_minus_line")),
        "line_to_avg": safe_float(row.get("line_to_avg")),
        "line_to_pred": safe_float(row.get("line_to_pred")),
        "matchup_score": safe_float(row.get("matchup_score")),
        "minutes_score": safe_float(row.get("minutes_score")),
        "stability_score": safe_float(row.get("stability_score")),
        "agreement_score": safe_float(row.get("agreement_score")),
        "hit_score": safe_float(row.get("hit_score")),
        "sim_avg": safe_float(row.get("sim_avg")),
        "expMin": safe_float(row.get("EXP_MIN") or row.get("MIN")),
        "reason_flags": clean_str(row.get("reason_flags")),
        "driver_1_for": clean_str(row.get("driver_1_for")),
        "driver_2_for": clean_str(row.get("driver_2_for")),
        "driver_3_for": clean_str(row.get("driver_3_for")),
        "driver_1_against": clean_str(row.get("driver_1_against")),
        "driver_2_against": clean_str(row.get("driver_2_against")),
        "driver_summary": clean_str(row.get("driver_summary")),
        "boardDriver": clean_str(row.get("board_driver")),
        "summary": clean_str(row.get("board_driver") or row.get("driver_summary") or row.get("reason_flags")),
        "hit_r5": safe_float(row.get("hit_r5")),
        "hit_r10": safe_float(row.get("hit_r10")),
        "hit_r25": safe_float(row.get("hit_r25")),
    }


def build_payload(workbook_path: Path, games_path: Path, player_df_path: Path, upcoming_path: Path, analyzer_script: Path | None, injuries_path: Path | None = None) -> dict[str, Any]:
    games_map = load_games_map(games_path)
    xls = pd.ExcelFile(workbook_path)
    all_sheet = "all_candidates" if "all_candidates" in xls.sheet_names else xls.sheet_names[0]
    all_df = pd.read_excel(workbook_path, sheet_name=all_sheet)

    # normalize workbook columns after upstream merges/ranker changes
    all_df = coalesce_named_column(all_df, "PLAYER_NAME", ["PLAYER_NAME", "PLAYER_NAME_x", "PLAYER_NAME_y"])
    all_df = coalesce_named_column(all_df, "PLAYER_ID", ["PLAYER_ID", "PLAYER_ID_x", "PLAYER_ID_y"])
    all_df = coalesce_named_column(all_df, "GAME_ID", ["GAME_ID", "GAME_ID_x", "GAME_ID_y"])
    all_df = coalesce_named_column(all_df, "GAME_DATE", ["GAME_DATE", "GAME_DATE_x", "GAME_DATE_y"])
    all_df = coalesce_named_column(all_df, "TEAM_SIDE", ["TEAM_SIDE", "TEAM_SIDE_x", "TEAM_SIDE_y"])
    all_df = coalesce_named_column(all_df, "IS_HOME", ["IS_HOME", "IS_HOME_x", "IS_HOME_y"])

    all_df = all_df.dropna(subset=["PLAYER_ID", "PLAYER_NAME", "stat", "line"]).copy()
    all_df["GAME_DATE"] = pd.to_datetime(all_df["GAME_DATE"], errors="coerce")
    all_df["__date"] = all_df["GAME_DATE"].map(iso_date)
    all_df["__pid"] = all_df["PLAYER_ID"].astype(str).str.replace(r"\.0+$", "", regex=True)
    all_df["__stat"] = all_df["stat"].astype(str).str.upper().str.strip()

    if analyzer_script is not None and Path(analyzer_script).exists():
        module = import_analyzer_module(analyzer_script)
        analyzer = module.NBAPropsAnalyzer(hist_path=player_df_path, upcoming_path=upcoming_path)
    else:
        module = _BuiltinAnalyzerModule()
        analyzer = LocalNBAPropsAnalyzer(hist_path=player_df_path, upcoming_path=upcoming_path)
    analyzer.load()

    injuries_lookup = {}
    if injuries_path and injuries_path.exists():
        injuries_lookup = build_injury_lookup(json.loads(injuries_path.read_text(encoding="utf-8")))

    series_payloads: dict[str, dict] = {}
    entries: list[dict[str, Any]] = []

    grouped = all_df.groupby(["__date", "__pid", "__stat"], sort=True)
    for (game_date, pid, stat), group in grouped:
        sample = group.iloc[0]
        player_name = clean_str(sample.get("PLAYER_NAME"))
        series_key = f"{game_date}|{pid}|{stat}"
        try:
            series_payload, _ = prepare_series(analyzer, module, pid, player_name, stat, game_date)
        except Exception as exc:
            series_payload = {
                "playerId": safe_int(pid) or pid,
                "player": player_name,
                "stat": stat,
                "statDisplay": clean_str(sample.get("stat_display") or stat),
                "gameDate": game_date,
                "error": clean_str(exc),
                "recentWindow": 25,
                "samples": {"recent": {"overall": {"n": 0, "avg": None, "median": None, "std": None, "max": None}}, "overall": {"overall": {"n": 0, "avg": None, "median": None, "std": None, "max": None}}, "similar": {"n": 0, "avg": None, "median": None, "std": None, "max": None}},
                "games": [],
                "similarGames": [],
            }
        team, opp, location = derive_team_context(sample, games_map)
        series_payload["team"] = team
        series_payload["opp"] = opp
        series_payload["location"] = location
        series_payload["matchup"] = f"{team} vs {opp}" if team and opp else ""
        injury = injuries_lookup.get((normalize_lookup_token(player_name), team)) or injuries_lookup.get((normalize_lookup_token(player_name), ""))
        if injury:
            series_payload["injuryStatus"] = injury.get("status")
            series_payload["injuryNote"] = injury.get("note")
            series_payload["injuryUpdated"] = injury.get("lastUpdated")
        series_payloads[series_key] = series_payload
        for _, row in group.iterrows():
            entry = entry_from_row(row, games_map, series_key)
            if injury:
                entry["injuryStatus"] = injury.get("status")
                entry["injuryNote"] = injury.get("note")
            entries.append(entry)

    entries.sort(key=lambda x: (x.get("gameDate") or "", x.get("player") or "", x.get("stat") or "", safe_float(x.get("line")) or -999))
    dates = sorted([d for d in entries and {e.get("gameDate") for e in entries} if d])
    today_iso = datetime.now().date().isoformat()
    target_date = ""
    if dates:
        if today_iso in dates:
            target_date = today_iso
        else:
            future_dates = [d for d in dates if d >= today_iso]
            target_date = (future_dates[0] if future_dates else dates[-1])

    series_index = {}
    for series_key, payload in series_payloads.items():
        game_date = clean_str(payload.get("gameDate") or target_date or "undated")
        safe_date = re.sub(r"[^0-9-]+", "_", game_date or "undated") or "undated"
        player_id = clean_str(payload.get("playerId") or "unknown")
        stat = clean_str(payload.get("stat") or "STAT").lower()
        safe_stat = re.sub(r"[^a-z0-9_]+", "_", stat) or "stat"
        rel_path = f"data/nba_props_analyzer/{safe_date}/{player_id}_{safe_stat}.json"
        series_index[series_key] = rel_path

    return {
        "targetDate": target_date,
        "dates": dates,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sourceWorkbook": str(workbook_path),
        "sourceUpcoming": str(upcoming_path),
        "sourceHistory": str(player_df_path),
        "entryCount": len(entries),
        "seriesCount": len(series_payloads),
        "entries": entries,
        "seriesIndex": series_index,
        "series": series_payloads,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build nba_props_analyzer.json from workbook, upcoming props, and player history.")
    ap.add_argument("--website-repo", type=Path, default=DEFAULT_WEBSITE_REPO)
    ap.add_argument("--workbook", type=Path, default=None)
    ap.add_argument("--games-json", type=Path, default=None)
    ap.add_argument("--player-df", type=Path, default=None)
    ap.add_argument("--upcoming", type=Path, default=None)
    ap.add_argument("--analyzer-script", type=Path, default=None)
    ap.add_argument("--injuries-json", type=Path, default=None)
    args = ap.parse_args()

    website_repo = args.website_repo
    data_dir = website_repo / "data"
    games_path = args.games_json or (data_dir / "games.json")
    injuries_path = args.injuries_json or (data_dir / "nba_injuries.json")

    workbook_path, player_df_path, upcoming_path, analyzer_script = resolve_artifacts(
        website_repo=website_repo,
        workbook=args.workbook,
        player_df=args.player_df,
        upcoming=args.upcoming,
        analyzer_script=args.analyzer_script,
    )

    print(f"[INFO] Using workbook: {workbook_path}")
    print(f"[INFO] Using player_df: {player_df_path}")
    print(f"[INFO] Using upcoming CSV: {upcoming_path}")
    print(f"[INFO] Using analyzer script: {analyzer_script if analyzer_script is not None else 'builtin LocalNBAPropsAnalyzer'}")

    wb_token = _extract_date_window_token(Path(workbook_path)) if workbook_path else ""
    up_token = _extract_date_window_token(Path(upcoming_path)) if upcoming_path else ""
    if wb_token and up_token and wb_token != up_token:
        print(f"[WARN] Workbook/upcoming date-window mismatch: workbook={wb_token} upcoming={up_token}")

    required_paths = [("games.json", games_path), ("workbook", workbook_path), ("player_df.parquet", player_df_path), ("upcoming CSV", upcoming_path)]
    for label, path in required_paths:
        if path is None or not Path(path).exists():
            raise FileNotFoundError(f"Could not find required {label}. Pass it explicitly.")
    if analyzer_script is not None and not Path(analyzer_script).exists():
        raise FileNotFoundError(f"Could not find analyzer script: {analyzer_script}")

    payload = build_payload(
        workbook_path=Path(workbook_path),
        games_path=Path(games_path),
        player_df_path=Path(player_df_path),
        upcoming_path=Path(upcoming_path),
        analyzer_script=Path(analyzer_script) if analyzer_script is not None else None,
        injuries_path=Path(injuries_path) if injuries_path and Path(injuries_path).exists() else None,
    )

    details_dir = data_dir / "nba_props_analyzer"
    if details_dir.exists():
        rmtree(details_dir)
    details_dir.mkdir(parents=True, exist_ok=True)

    series_payloads = payload.pop("series", {})
    series_index = payload.get("seriesIndex", {})
    for series_key, rel_path in series_index.items():
        detail_path = website_repo / rel_path
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_payload = series_payloads.get(series_key, {})
        detail_path.write_text(json.dumps(detail_payload, separators=(",", ":")), encoding="utf-8")

    out_path = data_dir / "nba_props_analyzer.json"
    out_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote analyzer index -> {out_path}")
    print(f"Wrote analyzer detail files -> {details_dir}")
    print(f"Entries: {payload['entryCount']}")
    print(f"Series: {payload['seriesCount']}")
    print(f"Target date: {payload['targetDate']}")


if __name__ == "__main__":
    main()
