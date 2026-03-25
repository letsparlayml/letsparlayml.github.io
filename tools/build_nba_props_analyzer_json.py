#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

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


def normalize_game_numeric_id(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\.0+$", "", s)
    return s


def find_latest_file(patterns, roots):
    candidates = []
    for root in roots:
        if not root or not Path(root).exists():
            continue
        for pattern in patterns:
            candidates.extend(Path(root).glob(pattern))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


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
def import_analyzer_module(path: Path):
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


def prepare_series(analyzer, module, player_id: str, player_name: str, stat: str, series_game_date: str, similar_n: int = 10, season_type: str = "Regular_Season") -> tuple[dict[str, Any], pd.Series | None]:
    assert analyzer.player_df is not None
    stat = clean_str(stat).upper()
    if stat not in analyzer.stat_cols:
        raise ValueError(f"Unknown stat: {stat}")

    stat_col = analyzer.stat_cols[stat]
    pid = module._norm_id_str(player_id)

    df_all = analyzer.player_df[analyzer.player_df[analyzer.col_player_id] == pid].copy()
    if season_type and "SEASON_TYPE" in df_all.columns:
        df_all = df_all[df_all["SEASON_TYPE"] == season_type].copy()
    df_all = df_all[df_all[analyzer.col_min] > 0].copy()
    if df_all.empty:
        raise ValueError(f"No historical games with minutes for {player_name} {stat}")

    if analyzer.col_game_date and df_all[analyzer.col_game_date].notna().any():
        df_all[analyzer.col_game_date] = module._coerce_date(df_all[analyzer.col_game_date])
        df_all = df_all.sort_values(analyzer.col_game_date, na_position="first").copy()
        xcol = analyzer.col_game_date
    else:
        df_all = df_all.sort_values("GAME_SEQ").copy()
        xcol = "GAME_SEQ"

    up_row = analyzer._get_upcoming_row(pid, player_name)
    opp_team_id = None
    target_metric = None
    metric_col_up = None
    if up_row is not None:
        if "OPP_TEAM_ID" in up_row.index:
            opp_team_id = clean_str(up_row.get("OPP_TEAM_ID"))
        metric_col_up = analyzer._pick_metric_col(analyzer.upcoming_df, stat) if analyzer.upcoming_df is not None else None
        if metric_col_up and metric_col_up in up_row.index:
            target_metric = module._safe_float(up_row[metric_col_up])

    metric_col_hist = analyzer._pick_metric_col(df_all, stat)
    sim_metric_cols = analyzer._metric_cols_for_stat_in_both(stat, df_all, up_row, max_cols=3)

    df_display = df_all.copy()
    similar_block = None
    similarity_mode = "none"

    if sim_metric_cols:
        df_all_sim = df_all.copy()
        score_parts = []
        for c in sim_metric_cols:
            hv = pd.to_numeric(df_all_sim[c], errors="coerce")
            tv = module._safe_float(up_row[c])
            scale = float(hv.std(ddof=0))
            if not np.isfinite(scale) or scale <= 1e-9:
                q75, q25 = hv.quantile(0.75), hv.quantile(0.25)
                iqr = float(q75 - q25) if pd.notna(q75) and pd.notna(q25) else np.nan
                scale = (iqr / 1.349) if np.isfinite(iqr) and iqr > 1e-9 else 1.0
            part = ((hv - tv).abs() / scale).clip(lower=0, upper=8)
            df_all_sim[f"_sim_{c}"] = part
            score_parts.append(f"_sim_{c}")
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
                key_cols = [analyzer.col_player_id, analyzer.col_game_id]
                take_cols = [c for c in key_cols + ["_sim_score", "_sim_pct", "_sim_bin"] if c in df_all_sim.columns]
                df_display = df_display.drop(columns=[c for c in ["_sim_score", "_sim_pct", "_sim_bin"] if c in df_display.columns], errors="ignore")
                df_display = df_display.merge(
                    df_all_sim[take_cols].drop_duplicates(subset=key_cols, keep="last"),
                    on=key_cols,
                    how="left",
                )
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

    if analyzer.col_game_date and df_display[analyzer.col_game_date].notna().any():
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


def build_payload(workbook_path: Path, games_path: Path, player_df_path: Path, upcoming_path: Path, analyzer_script: Path, injuries_path: Path | None = None) -> dict[str, Any]:
    games_map = load_games_map(games_path)
    xls = pd.ExcelFile(workbook_path)
    all_sheet = "all_candidates" if "all_candidates" in xls.sheet_names else xls.sheet_names[0]
    all_df = pd.read_excel(workbook_path, sheet_name=all_sheet)
    all_df = all_df.dropna(subset=["PLAYER_ID", "PLAYER_NAME", "stat", "line"]).copy()
    all_df["GAME_DATE"] = pd.to_datetime(all_df["GAME_DATE"], errors="coerce")
    all_df["__date"] = all_df["GAME_DATE"].map(iso_date)
    all_df["__pid"] = all_df["PLAYER_ID"].astype(str).str.replace(r"\.0+$", "", regex=True)
    all_df["__stat"] = all_df["stat"].astype(str).str.upper().str.strip()

    module = import_analyzer_module(analyzer_script)
    analyzer = module.NBAPropsAnalyzer(hist_path=player_df_path, upcoming_path=upcoming_path)
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
    target_date = today_iso if today_iso in dates else (dates[0] if dates else "")

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

    workbook_path = args.workbook or find_latest_file(["props_all_in_one_*.xlsx", "*props_all_in_one*.xlsx"], [website_repo, *DEFAULT_SEARCH_ROOTS])
    player_df_path = args.player_df or find_latest_file(["player_df.parquet"], [website_repo, *DEFAULT_SEARCH_ROOTS])
    upcoming_path = args.upcoming or find_latest_file(["player_props_upcoming_*.csv"], [website_repo, *DEFAULT_SEARCH_ROOTS])
    analyzer_script = args.analyzer_script or find_latest_file(["nba_props_analyzer*.py"], [website_repo, *DEFAULT_SEARCH_ROOTS])

    for label, path in [("games.json", games_path), ("workbook", workbook_path), ("player_df.parquet", player_df_path), ("upcoming CSV", upcoming_path), ("analyzer script", analyzer_script)]:
        if path is None or not Path(path).exists():
            raise FileNotFoundError(f"Could not find required {label}. Pass it explicitly.")

    payload = build_payload(
        workbook_path=Path(workbook_path),
        games_path=Path(games_path),
        player_df_path=Path(player_df_path),
        upcoming_path=Path(upcoming_path),
        analyzer_script=Path(analyzer_script),
        injuries_path=Path(injuries_path) if injuries_path and Path(injuries_path).exists() else None,
    )

    out_path = data_dir / "nba_props_analyzer.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote analyzer JSON -> {out_path}")
    print(f"Entries: {payload['entryCount']}")
    print(f"Series: {payload['seriesCount']}")
    print(f"Target date: {payload['targetDate']}")


if __name__ == "__main__":
    main()
