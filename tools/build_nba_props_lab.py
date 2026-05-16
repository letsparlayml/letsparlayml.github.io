
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, date
from pathlib import Path

import pandas as pd


DEFAULT_WEBSITE_REPO = Path(r"C:\python\letsparlayml.github.io")
DEFAULT_SEARCH_ROOTS = [
    Path(r"C:\python\data_nba\models_v1"),
    Path(r"C:\python\data_nba"),
    Path(r"C:\python"),
]

SHEET_MAP = {
    "consensus": ["overall_consensus"],
    "floor": ["floor_overlap", "floor_balanced", "floor_strict"],
    "consistency": ["consistency_overlap", "consistency_agreement", "consistency_stable"],
    "ceiling": ["ceiling_overlap", "ceiling_matchup", "ceiling_form"],
}


def iso_date(value) -> str:
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.date().isoformat()
    except Exception:
        return ""


def safe_float(value):
    try:
        if pd.isna(value):
            return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None


def safe_int(value):
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except Exception:
        return None


def clean_str(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def normalize_game_numeric_id(value) -> str:
    raw = clean_str(value)
    match = re.search(r"(\d{7,})", raw)
    return match.group(1) if match else ""


def find_latest_file(patterns, roots):
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            candidates.extend(root.rglob(pattern))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_window_token(path: Path | None) -> str:
    if path is None:
        return ""
    m = re.search(r"(20\d{6}_20\d{6})", path.name)
    return m.group(1) if m else ""


def extract_window_bounds(path: Path | None) -> tuple[date | None, date | None]:
    token = extract_window_token(path)
    if not token:
        return None, None
    try:
        start_s, end_s = token.split("_", 1)
        start_d = datetime.strptime(start_s, "%Y%m%d").date()
        end_d = datetime.strptime(end_s, "%Y%m%d").date()
        return start_d, end_d
    except Exception:
        return None, None


def choose_best_file(patterns, roots, *, today: date | None = None, preferred_tokens: list[str] | None = None) -> Path | None:
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            candidates.extend(root.rglob(pattern))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None

    today = today or datetime.now().date()
    preferred_tokens = [t for t in (preferred_tokens or []) if t]

    def score(path: Path):
        token = extract_window_token(path)
        start_d, end_d = extract_window_bounds(path)

        contains_today = 1 if (start_d and end_d and start_d <= today <= end_d) else 0
        token_preferred = 1 if token and token in preferred_tokens else 0

        root_pref = 0
        pstr = str(path).lower()
        if "data_nba\\models_v1" in pstr:
            root_pref = 4
        elif "letsparlayml.github.io" in pstr:
            root_pref = 3
        elif "data_nba" in pstr:
            root_pref = 2
        elif pstr.startswith("c:\\python"):
            root_pref = 1

        token_sort = token or ""
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = 0.0

        return (token_preferred, contains_today, token_sort, root_pref, mtime)

    return max(candidates, key=score)


def choose_target_date(dates: list[str]) -> str:
    dates = sorted([d for d in dates if d])
    if not dates:
        return ""
    today_iso = datetime.now().date().isoformat()
    if today_iso in dates:
        return today_iso
    future_dates = [d for d in dates if d >= today_iso]
    if future_dates:
        return future_dates[0]
    return dates[-1]


def coalesce_named_column(df: pd.DataFrame, target: str, candidates: list[str]) -> pd.DataFrame:
    df = df.copy()
    existing = [c for c in candidates if c in df.columns]
    if not existing:
        return df

    if target not in df.columns:
        df[target] = pd.NA

    out = df[target]
    for c in existing:
        s = df[c]
        if getattr(s, "dtype", None) == object:
            s = s.replace("", pd.NA)
        out = out.where(out.notna(), s)

    df[target] = out

    drop_cols = [c for c in existing if c != target]
    if drop_cols:
        df = df.drop(columns=drop_cols, errors="ignore")
    return df


def normalize_props_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    out = coalesce_named_column(out, "PLAYER_NAME", ["PLAYER_NAME", "PLAYER_NAME_x", "PLAYER_NAME_y"])
    out = coalesce_named_column(out, "PLAYER_ID", ["PLAYER_ID", "PLAYER_ID_x", "PLAYER_ID_y"])
    out = coalesce_named_column(out, "GAME_ID", ["GAME_ID", "GAME_ID_x", "GAME_ID_y"])
    out = coalesce_named_column(out, "GAME_DATE", ["GAME_DATE", "GAME_DATE_x", "GAME_DATE_y"])
    out = coalesce_named_column(out, "TEAM_SIDE", ["TEAM_SIDE", "TEAM_SIDE_x", "TEAM_SIDE_y"])
    out = coalesce_named_column(out, "TEAM_ABBR", ["TEAM_ABBR", "TEAM_ABBR_x", "TEAM_ABBR_y"])
    out = coalesce_named_column(out, "OPP_ABBR", ["OPP_ABBR", "OPP_ABBR_x", "OPP_ABBR_y"])
    return out


def load_games_map(games_path: Path) -> dict[str, dict]:
    games = json.loads(games_path.read_text(encoding="utf-8"))
    out = {}
    for g in games:
        gid = normalize_game_numeric_id(g.get("id") or g.get("gameId") or g.get("GAME_ID"))
        if not gid:
            continue
        out[gid] = {
            "gameDate": clean_str(g.get("gameDate")),
            "awayTeam": clean_str(g.get("awayTeam")),
            "homeTeam": clean_str(g.get("homeTeam")),
        }
    return out


def derive_team_context(row: pd.Series, games_map: dict[str, dict]) -> tuple[str, str, str]:
    gid = normalize_game_numeric_id(row.get("GAME_ID"))
    gm = games_map.get(gid, {})
    away = clean_str(gm.get("awayTeam"))
    home = clean_str(gm.get("homeTeam"))
    side = clean_str(row.get("TEAM_SIDE")).lower()
    if side == "home":
        return home, away, "Home"
    if side == "away":
        return away, home, "Away"
    return clean_str(row.get("TEAM_ABBR")), clean_str(row.get("OPP_ABBR")), ""


def pick_stat_hit(row: pd.Series, window: int):
    stat = clean_str(row.get("stat") or row.get("stat_display")).upper()
    line = safe_int(row.get("line"))
    if line is None:
        return None
    key = f"hit_{stat}_{line}_r{window}"
    if key in row.index:
        return safe_float(row.get(key))
    return None


def build_summary(row: pd.Series) -> str:
    parts = []
    for key in ["board_driver", "driver_summary", "reason_flags"]:
        text = clean_str(row.get(key))
        if text and text not in parts:
            parts.append(text)
    return " | ".join(parts[:2])


def board_rows_from_sheet(df: pd.DataFrame, games_map: dict[str, dict]) -> list[dict]:
    if df is None or df.empty:
        return []
    rows = []
    for _, row in df.iterrows():
        team, opp, location = derive_team_context(row, games_map)
        game_date = iso_date(row.get("GAME_DATE"))
        stat = clean_str(row.get("stat") or row.get("stat_display")).upper()
        item = {
            "gameDate": game_date,
            "gameId": safe_int(row.get("GAME_ID")),
            "player": clean_str(row.get("PLAYER_NAME")),
            "playerId": safe_int(row.get("PLAYER_ID")),
            "team": team,
            "opp": opp,
            "location": location,
            "matchup": f"{team} vs {opp}" if team and opp else "",
            "stat": stat,
            "stat_display": clean_str(row.get("stat_display") or stat),
            "line": safe_float(row.get("line")),
            "board": clean_str(row.get("board")),
            "board_rank_date": safe_int(row.get("board_rank_date")),
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
            "expMin": safe_float(row.get("EXP_MIN") or row.get("MIN") or row.get("expMin")),
            "days_seen": safe_int(row.get("days_seen")),
            "board_score_change": safe_float(row.get("board_score_change")),
            "prob_change": safe_float(row.get("prob_change")),
            "hit_r5": safe_float(row.get("hit_r5")) if "hit_r5" in row.index else pick_stat_hit(row, 5),
            "hit_r10": safe_float(row.get("hit_r10")) if "hit_r10" in row.index else pick_stat_hit(row, 10),
            "hit_r25": safe_float(row.get("hit_r25")) if "hit_r25" in row.index else pick_stat_hit(row, 25),
            "reason_flags": clean_str(row.get("reason_flags")),
            "driver_1_for": clean_str(row.get("driver_1_for")),
            "driver_2_for": clean_str(row.get("driver_2_for")),
            "driver_3_for": clean_str(row.get("driver_3_for")),
            "driver_1_against": clean_str(row.get("driver_1_against")),
            "driver_2_against": clean_str(row.get("driver_2_against")),
            "driver_summary": clean_str(row.get("driver_summary")),
            "boardDriver": clean_str(row.get("board_driver")),
            "summary": build_summary(row),
        }
        rows.append(item)
    rows.sort(key=lambda x: (
        x.get("board_rank_date") is None,
        x.get("board_rank_date") if x.get("board_rank_date") is not None else 10**9,
        -(x.get("prob_cons") or -1),
    ))
    return rows


def load_section_rows(workbook_path: Path, xls: pd.ExcelFile, candidates: list[str], games_map: dict[str, dict]) -> list[dict]:
    """Load and combine every matching strategy sheet for a section.

    The previous builder used only the first matching sheet. That made, for
    example, a populated ceiling_form sheet invisible whenever ceiling_overlap
    also existed but had no rows for the selected date.
    """
    rows: list[dict] = []
    seen = set()
    names = set(xls.sheet_names)
    for candidate in candidates:
        if candidate not in names:
            continue
        sheet_rows = board_rows_from_sheet(normalize_props_df(pd.read_excel(workbook_path, sheet_name=candidate)), games_map)
        for row in sheet_rows:
            key = prop_lookup_key(row, True)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    rows.sort(key=lambda x: (
        x.get("board_rank_date") is None,
        x.get("board_rank_date") if x.get("board_rank_date") is not None else 10**9,
        -(x.get("prob_cons") or -1),
    ))
    return rows



def prop_lookup_key(item: dict | pd.Series, include_player_id: bool = True) -> tuple:
    line_value = safe_float(item.get("line"))
    player_id = safe_int(item.get("playerId")) if include_player_id else None
    return (
        clean_str(item.get("gameDate")),
        safe_int(item.get("gameId")),
        player_id,
        clean_str(item.get("player")).lower(),
        clean_str(item.get("stat")).upper(),
        round(line_value, 3) if line_value is not None else None,
    )


def prop_family_key(item: dict) -> tuple:
    player_id = safe_int(item.get("playerId"))
    return (
        clean_str(item.get("gameDate")),
        safe_int(item.get("gameId")),
        player_id if player_id is not None else clean_str(item.get("player")).lower(),
        clean_str(item.get("stat")).upper(),
    )


def prop_sort_score(item: dict, section: str) -> float:
    prob = safe_float(item.get("prob_cons")) or 0.0
    pred_gap = safe_float(item.get("pred_minus_line")) or 0.0
    avg_gap = safe_float(item.get("avg_minus_line")) or 0.0
    hit = safe_float(item.get("hit_score")) or 0.0
    stability = safe_float(item.get("stability_score")) or 0.0
    agreement = safe_float(item.get("agreement_score")) or 0.0
    matchup = safe_float(item.get("matchup_score")) or 0.0
    line = safe_float(item.get("line")) or 0.0
    avg_anchor = safe_float(item.get("avg_anchor")) or 0.0
    elevated = max(0.0, line - avg_anchor)
    if section == "ceiling":
        return prob * 1.1 + hit * 0.25 + stability * 0.15 + matchup * 0.20 + elevated * 0.04
    if section == "consistency":
        return prob * 0.75 + stability * 0.25 + agreement * 0.20 + hit * 0.15
    if section == "floor":
        return prob * 0.90 + max(pred_gap, 0.0) * 0.04 + max(avg_gap, 0.0) * 0.03 + stability * 0.10
    return prob * 0.85 + max(pred_gap, 0.0) * 0.04 + matchup * 0.15 + agreement * 0.10


def is_ceiling_candidate(item: dict) -> bool:
    prob = safe_float(item.get("prob_cons")) or 0.0
    pred_gap = safe_float(item.get("pred_minus_line")) or 0.0
    hit = safe_float(item.get("hit_score")) or 0.0
    stability = safe_float(item.get("stability_score")) or 0.0
    matchup = safe_float(item.get("matchup_score")) or 0.0
    line = safe_float(item.get("line"))
    avg_anchor = safe_float(item.get("avg_anchor"))
    elevated_line = line is not None and avg_anchor is not None and line >= avg_anchor
    return prob >= 0.40 and (pred_gap >= 0.20 or elevated_line) and (hit >= 0.40 or stability >= 0.85 or matchup >= 0.15)


def is_consistency_candidate(item: dict) -> bool:
    prob = safe_float(item.get("prob_cons")) or 0.0
    stability = safe_float(item.get("stability_score")) or 0.0
    agreement = safe_float(item.get("agreement_score")) or 0.0
    hit = safe_float(item.get("hit_score")) or 0.0
    return prob >= 0.48 and (stability >= 0.85 or agreement >= 0.70 or hit >= 0.58)


def is_floor_candidate(item: dict) -> bool:
    prob = safe_float(item.get("prob_cons")) or 0.0
    pred_gap = safe_float(item.get("pred_minus_line")) or 0.0
    avg_gap = safe_float(item.get("avg_minus_line")) or 0.0
    stability = safe_float(item.get("stability_score")) or 0.0
    return prob >= 0.56 and (pred_gap >= 0.0 or avg_gap >= -0.25 or stability >= 0.88)


def is_consensus_candidate(item: dict) -> bool:
    prob = safe_float(item.get("prob_cons")) or 0.0
    return prob >= 0.50


def dedupe_exact(items: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for item in items:
        if not clean_str(item.get("player")) or not clean_str(item.get("stat")):
            continue
        key = prop_lookup_key(item, True)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def ladder_replacement(item: dict, all_rows: list[dict]) -> dict:
    base_line = safe_float(item.get("line"))
    if base_line is None:
        return item
    family = prop_family_key(item)
    options = []
    for row in all_rows:
        if prop_family_key(row) != family:
            continue
        line = safe_float(row.get("line"))
        prob = safe_float(row.get("prob_cons")) or 0.0
        if line is None or line <= base_line:
            continue
        if prob < 0.40:
            continue
        if not is_ceiling_candidate(row):
            continue
        candidate = dict(row)
        candidate["board"] = "ceiling_ladder"
        candidate["summary"] = candidate.get("summary") or item.get("summary")
        candidate["boardDriver"] = candidate.get("boardDriver") or "Higher-line ladder version of a strong base prop."
        options.append(candidate)
    if not options:
        return item
    options.sort(key=lambda row: (safe_float(row.get("line")) or 0.0, prop_sort_score(row, "ceiling")), reverse=True)
    return options[0]


def assign_strategy_sections(raw_sections: dict[str, list[dict]], day_all: list[dict]) -> dict[str, list[dict]]:
    enriched = {
        key: dedupe_exact(enrich_board_rows(rows, day_all))
        for key, rows in raw_sections.items()
    }

    ceiling_pool = [ladder_replacement(row, day_all) for row in enriched.get("ceiling", [])]
    ceiling_pool = [row for row in dedupe_exact(ceiling_pool) if is_ceiling_candidate(row)]

    assigned: dict[str, list[dict]] = {"consensus": [], "floor": [], "consistency": [], "ceiling": []}
    used_exact = set()
    used_family_named = set()

    # Priority matters: put true upside/ladders first, then stable repeatable props,
    # then lower-line floor spots. Consensus is filled last so the same exact prop
    # does not show up in multiple strategy buckets.
    priority_defs = [
        ("ceiling", ceiling_pool, is_ceiling_candidate),
        ("consistency", enriched.get("consistency", []), is_consistency_candidate),
        ("floor", enriched.get("floor", []), is_floor_candidate),
    ]

    for section, rows, predicate in priority_defs:
        candidates = [row for row in dedupe_exact(rows) if predicate(row)]
        candidates.sort(key=lambda row: prop_sort_score(row, section), reverse=True)
        for row in candidates:
            exact = prop_lookup_key(row, True)
            if exact in used_exact:
                continue
            used_exact.add(exact)
            used_family_named.add(prop_family_key(row))
            assigned[section].append(row)

    def add_consensus_candidates(rows: list[dict], *, avoid_named_family: bool, strict_role: bool) -> None:
        candidates = []
        for row in dedupe_exact(rows):
            exact = prop_lookup_key(row, True)
            family = prop_family_key(row)
            if exact in used_exact:
                continue
            if avoid_named_family and family in used_family_named:
                continue
            if not is_consensus_candidate(row):
                continue
            if strict_role and (is_ceiling_candidate(row) or is_consistency_candidate(row) or is_floor_candidate(row)):
                continue
            candidates.append(row)
        candidates.sort(key=lambda row: prop_sort_score(row, "consensus"), reverse=True)
        for row in candidates:
            exact = prop_lookup_key(row, True)
            if exact in used_exact:
                continue
            used_exact.add(exact)
            assigned["consensus"].append(row)
            if len(assigned["consensus"]) >= 8:
                break

    # First use the source consensus sheets, then backfill from all candidates with
    # matchup/projection signals. The staged fallback keeps the board populated
    # without allowing exact duplicate player/stat/line/game rows across buckets.
    add_consensus_candidates(enriched.get("consensus", []), avoid_named_family=True, strict_role=True)
    if len(assigned["consensus"]) < 4:
        add_consensus_candidates(day_all, avoid_named_family=True, strict_role=True)
    if len(assigned["consensus"]) < 4:
        add_consensus_candidates(enriched.get("consensus", []), avoid_named_family=True, strict_role=False)
    if len(assigned["consensus"]) < 4:
        add_consensus_candidates(day_all, avoid_named_family=False, strict_role=False)

    return assigned

def enrich_board_rows(items: list[dict], all_rows: list[dict]) -> list[dict]:
    exact_lookup = {prop_lookup_key(row, True): row for row in all_rows}
    fallback_lookup = {prop_lookup_key(row, False): row for row in all_rows}

    enriched = []
    for item in items:
        source = exact_lookup.get(prop_lookup_key(item, True)) or fallback_lookup.get(prop_lookup_key(item, False))
        if not source:
            enriched.append(item)
            continue

        merged = dict(item)
        for key, value in source.items():
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        enriched.append(merged)
    return enriched


def build_role_sections(all_df: pd.DataFrame, games_map: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    if all_df is None or all_df.empty:
        return [], []

    df = all_df.copy()
    df["trend_gap"] = pd.to_numeric(df.get("pred_anchor"), errors="coerce") - pd.to_numeric(df.get("avg_anchor"), errors="coerce")
    df["pred_minus_line_num"] = pd.to_numeric(df.get("pred_minus_line"), errors="coerce")
    df["prob_cons_num"] = pd.to_numeric(df.get("prob_cons"), errors="coerce")
    df["board_sort"] = df["prob_cons_num"].fillna(0)

    # prefer props with at least some signal
    role_up_df = df[df["trend_gap"].notna()].sort_values(
        by=["trend_gap", "prob_cons_num"], ascending=[False, False]
    ).head(24)

    role_down_df = df[df["trend_gap"].notna()].sort_values(
        by=["trend_gap", "prob_cons_num"], ascending=[True, False]
    ).head(24)

    def convert(source_df: pd.DataFrame) -> list[dict]:
        rows = []
        for _, row in source_df.iterrows():
            team, opp, location = derive_team_context(row, games_map)
            rows.append({
                "gameDate": iso_date(row.get("GAME_DATE")),
                "gameId": safe_int(row.get("GAME_ID")),
                "player": clean_str(row.get("PLAYER_NAME")),
                "playerId": safe_int(row.get("PLAYER_ID")),
                "team": team,
                "opp": opp,
                "location": location,
                "matchup": f"{team} vs {opp}" if team and opp else "",
                "stat": clean_str(row.get("stat") or row.get("stat_display")).upper(),
                "stat_display": clean_str(row.get("stat_display") or row.get("stat")),
                "line": safe_float(row.get("line")),
                "prob_cons": safe_float(row.get("prob_cons")),
                "avg_anchor": safe_float(row.get("avg_anchor")),
                "pred_anchor": safe_float(row.get("pred_anchor")),
                "mu_cons": safe_float(row.get("mu_cons")),
                "trend_gap": safe_float(row.get("trend_gap")),
                "expMin": safe_float(row.get("EXP_MIN") or row.get("MIN")),
                "summary": build_summary(row),
                "boardDriver": clean_str(row.get("board_driver")),
                "hit_r10": safe_float(row.get("hit_r10")) if "hit_r10" in row.index else pick_stat_hit(row, 10),
                "hit_r25": safe_float(row.get("hit_r25")) if "hit_r25" in row.index else pick_stat_hit(row, 25),
            })
        return rows

    return convert(role_up_df), convert(role_down_df)


def build_payload(workbook_path: Path, games_path: Path) -> dict:
    xls = pd.ExcelFile(workbook_path)
    games_map = load_games_map(games_path)

    all_sheet = "all_candidates" if "all_candidates" in xls.sheet_names else xls.sheet_names[0]
    all_df = normalize_props_df(pd.read_excel(workbook_path, sheet_name=all_sheet))

    sections_by_sheet = {
        section: load_section_rows(workbook_path, xls, candidates, games_map)
        for section, candidates in SHEET_MAP.items()
    }

    role_up, role_down = build_role_sections(all_df, games_map)

    all_rows = board_rows_from_sheet(all_df, games_map)
    dates = sorted([d for d in pd.Series(all_df["GAME_DATE"]).map(iso_date).dropna().unique().tolist() if d])

    by_date = {}
    for date in dates:
        day_all = [r for r in all_rows if r.get("gameDate") == date]
        raw_day_sections = {
            "consensus": [r for r in sections_by_sheet["consensus"] if r.get("gameDate") == date],
            "floor": [r for r in sections_by_sheet["floor"] if r.get("gameDate") == date],
            "consistency": [r for r in sections_by_sheet["consistency"] if r.get("gameDate") == date],
            "ceiling": [r for r in sections_by_sheet["ceiling"] if r.get("gameDate") == date],
        }
        strategy_sections = assign_strategy_sections(raw_day_sections, day_all)
        by_date[date] = {
            "meta": {
                "propCount": len(day_all),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
                "sourceWorkbook": str(workbook_path),
            },
            "allProps": day_all,
            "sections": {
                "consensus": strategy_sections["consensus"],
                "floor": strategy_sections["floor"],
                "consistency": strategy_sections["consistency"],
                "ceiling": strategy_sections["ceiling"],
                "roleUp": [r for r in role_up if r.get("gameDate") == date],
                "roleDown": [r for r in role_down if r.get("gameDate") == date],
            },
        }

    target_date = choose_target_date(dates)

    return {
        "targetDate": target_date,
        "dates": dates,
        "byDate": by_date,
        "sourceWorkbook": str(workbook_path),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    parser = argparse.ArgumentParser(description="Build nba_props_lab.json from props workbook.")
    parser.add_argument("--website-repo", type=Path, default=DEFAULT_WEBSITE_REPO)
    parser.add_argument("--workbook", type=Path, default=None, help="Explicit props_all_in_one workbook path")
    parser.add_argument("--games-json", type=Path, default=None, help="Explicit games.json path")
    args = parser.parse_args()

    website_repo = args.website_repo
    data_dir = website_repo / "data"
    games_path = args.games_json or (data_dir / "games.json")
    if not games_path.exists():
        raise FileNotFoundError(f"games.json not found: {games_path}")

    workbook_path = args.workbook
    if workbook_path is None:
        workbook_path = choose_best_file(
            ["props_all_in_one_*.xlsx", "*props_all_in_one*.xlsx"],
            [website_repo, *DEFAULT_SEARCH_ROOTS],
        )
    if workbook_path is None or not workbook_path.exists():
        raise FileNotFoundError("Could not find a props_all_in_one workbook. Pass --workbook explicitly.")

    payload = build_payload(workbook_path, games_path)
    out_path = data_dir / "nba_props_lab.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote props lab JSON -> {out_path}")
    print(f"Workbook: {workbook_path}")
    print(f"Dates: {payload.get('dates', [])[:5]}{'...' if len(payload.get('dates', [])) > 5 else ''}")
    if payload.get("targetDate"):
        day = payload["byDate"].get(payload["targetDate"], {})
        sections = day.get("sections", {})
        print(
            "Target date:",
            payload["targetDate"],
            "| props:",
            len(day.get("allProps", [])),
            "| consensus:",
            len(sections.get("consensus", [])),
            "| floor:",
            len(sections.get("floor", [])),
            "| consistency:",
            len(sections.get("consistency", [])),
            "| ceiling:",
            len(sections.get("ceiling", [])),
        )


if __name__ == "__main__":
    main()
