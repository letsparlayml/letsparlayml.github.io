
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
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


def pick_sheet(xls: pd.ExcelFile, candidates: list[str]) -> str | None:
    names = set(xls.sheet_names)
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


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
    all_df = pd.read_excel(workbook_path, sheet_name=all_sheet)

    sections_by_sheet = {}
    for section, candidates in SHEET_MAP.items():
        sheet_name = pick_sheet(xls, candidates)
        if sheet_name:
            sections_by_sheet[section] = board_rows_from_sheet(pd.read_excel(workbook_path, sheet_name=sheet_name), games_map)
        else:
            sections_by_sheet[section] = []

    role_up, role_down = build_role_sections(all_df, games_map)

    all_rows = board_rows_from_sheet(all_df, games_map)
    dates = sorted([d for d in pd.Series(all_df["GAME_DATE"]).map(iso_date).dropna().unique().tolist() if d])

    by_date = {}
    for date in dates:
        day_all = [r for r in all_rows if r.get("gameDate") == date]
        by_date[date] = {
            "meta": {
                "propCount": len(day_all),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
                "sourceWorkbook": str(workbook_path),
            },
            "allProps": day_all,
            "sections": {
                "consensus": [r for r in sections_by_sheet["consensus"] if r.get("gameDate") == date],
                "floor": [r for r in sections_by_sheet["floor"] if r.get("gameDate") == date],
                "consistency": [r for r in sections_by_sheet["consistency"] if r.get("gameDate") == date],
                "ceiling": [r for r in sections_by_sheet["ceiling"] if r.get("gameDate") == date],
                "roleUp": [r for r in role_up if r.get("gameDate") == date],
                "roleDown": [r for r in role_down if r.get("gameDate") == date],
            },
        }

    today_iso = datetime.now().date().isoformat()
    target_date = today_iso if today_iso in dates else (dates[0] if dates else "")

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
        workbook_path = find_latest_file(
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
