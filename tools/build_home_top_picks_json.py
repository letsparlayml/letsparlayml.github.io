#!/usr/bin/env python3
"""Build a compact homepage snapshot for LetsParlayML.

This keeps the public homepage fast and beginner-friendly by extracting only the
featured cards, quick boards, parlay candidates, and recent accountability
records from the larger model/result payloads.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "home_top_picks.json"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except json.JSONDecodeError:
        return fallback


def num(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def pct(value: Any) -> float | None:
    n = num(value)
    if n is None:
        return None
    return n / 100.0 if n > 1 else n


def fmt_num(value: Any, digits: int = 1) -> str:
    n = num(value)
    if n is None:
        return "—"
    return f"{n:.{digits}f}"


def fmt_american(value: Any) -> str:
    n = num(value)
    if n is None:
        return ""
    rounded = int(round(n))
    return f"+{rounded}" if rounded > 0 else str(rounded)


def normalize_result(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "win" in raw:
        return "Win"
    if "loss" in raw or "lose" in raw:
        return "Loss"
    if "push" in raw:
        return "Push"
    return ""


def safe_date(value: Any) -> str:
    return str(value or "").strip()[:10]


def is_tbd_player(row: dict[str, Any]) -> bool:
    player = str(row.get("player") or "").lower()
    return any(token in player for token in ("tbd", "to be determined", "probable starter"))


def is_hidden_injury(row: dict[str, Any]) -> bool:
    status = str(row.get("injuryStatus") or row.get("status") or "").strip().lower()
    return status in {"out", "doubtful", "o", "d"}


def pitcher_projected_ip(row: dict[str, Any]) -> float | None:
    for key in ("expMin", "contextMetricValue", "projectedIP", "predictedIP", "ip", "IP"):
        value = num(row.get(key))
        if value is not None:
            return value
    for key in ("summary", "driver_summary", "boardDriver"):
        text = str(row.get(key) or "")
        match = re.search(r"projected\s+([0-9]+(?:\.[0-9]+)?)\s*IP", text, flags=re.IGNORECASE)
        if match:
            return num(match.group(1))
    return None


def is_probable_starting_pitcher(row: dict[str, Any], *, min_ip: float = 3.0) -> bool:
    """Filter bullpen/openers out of SP-only homepage boards."""
    if str(row.get("playerType") or row.get("role") or "").lower() != "pitcher":
        return False
    projected_ip = pitcher_projected_ip(row)
    if projected_ip is not None and projected_ip < min_ip:
        return False
    text = " ".join(str(row.get(k) or "") for k in ("summary", "driver_summary", "boardDriver", "reason_flags")).lower()
    if any(token in text for token in ("relief", "opener", "bulk", "bullpen")) and (projected_ip is None or projected_ip < 4.0):
        return False
    return True


def line_matches(row: dict[str, Any], wanted: float | None) -> bool:
    if wanted is None:
        return True
    line = num(row.get("line"))
    return line is not None and abs(line - wanted) < 1e-9


def canonical_nba_stat(stat: Any) -> str:
    raw = str(stat or "").upper().strip()
    return {"TPM": "3PM", "THREES": "3PM", "3P": "3PM"}.get(raw, raw)


def stat_label(stat: str) -> str:
    key = canonical_nba_stat(stat)
    labels = {
        "H": "Hits",
        "HRR": "Hits + Runs + RBI",
        "R": "Runs",
        "RBI": "RBIs",
        "OUTS": "Pitcher Outs",
        "TB": "Total Bases",
        "K": "Pitcher Ks",
        "HA": "Pitcher Hits Allowed",
        "ER": "Pitcher Earned Runs",
        "NRFI": "NRFI",
        "YRFI": "YRFI",
        "ML": "Moneyline",
        "TOTAL": "Game Total",
        "SPREAD": "Spread",
        "PTS": "Points",
        "REB": "Rebounds",
        "AST": "Assists",
        "PRA": "Points + Rebounds + Assists",
        "PR": "Points + Rebounds",
        "PA": "Points + Assists",
        "RA": "Rebounds + Assists",
        "3PM": "Made 3s",
        "BLK": "Blocks",
        "STL": "Steals",
        "TO": "Turnovers",
    }
    return labels.get(key, key)


def summarize_rows(rows: Iterable[dict[str, Any]], result_field: str = "result", limit: int = 30) -> dict[str, Any]:
    ordered = sorted(list(rows), key=lambda r: safe_date(r.get("date")), reverse=True)[:limit]
    wins = losses = pushes = 0
    for row in ordered:
        outcome = normalize_result(row.get(result_field))
        if outcome == "Win":
            wins += 1
        elif outcome == "Loss":
            losses += 1
        elif outcome == "Push":
            pushes += 1
    decisions = wins + losses
    total = wins + losses + pushes
    rate = (wins / decisions) if decisions else None
    if decisions < 5:
        trend = "Limited"
        tone = "neutral"
    elif rate is not None and rate >= 0.60:
        trend = "Hot"
        tone = "hot"
    elif rate is not None and rate <= 0.45:
        trend = "Cold"
        tone = "cold"
    else:
        trend = "Neutral"
        tone = "neutral"
    pct_text = f"{rate * 100:.0f}%" if rate is not None else "—"
    record = f"{wins}-{losses}" + (f"-{pushes}" if pushes else "")
    return {
        "sample": total,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "record": record,
        "winRate": rate,
        "pctText": pct_text,
        "trend": trend,
        "tone": tone,
        "label": f"Last {total}: {record} ({pct_text})" if total else "No settled history yet",
    }


def prop_tracker(prop_results: list[dict[str, Any]], stat: str, *, line: float | None = None, limit: int = 30) -> dict[str, Any]:
    stat = stat.upper()
    rows = [
        r for r in prop_results
        if str(r.get("stat") or "").upper() == stat
        and (line is None or line_matches(r, line))
        and normalize_result(r.get("result"))
    ]
    summary = summarize_rows(rows, "result", limit=limit)
    summary["scope"] = f"{stat_label(stat)} category"
    return summary


def game_tracker(results: list[dict[str, Any]], field: str, league: str | None = None, limit: int = 40) -> dict[str, Any]:
    rows = [r for r in results if normalize_result(r.get(field))]
    if league:
        rows = [r for r in rows if str(r.get("league") or "").upper() == league.upper()]
    summary = summarize_rows(rows, field, limit=limit)
    label_map = {"mlResult": "Game winner", "spreadResult": "Spread", "totalResult": "Total"}
    summary["scope"] = f"{league.upper() + ' ' if league else ''}{label_map.get(field, field)} results"
    return summary


def nrfi_yrfi_tracker(results: list[dict[str, Any]], pick: str | None = None, limit: int = 40) -> dict[str, Any]:
    """Track first-inning model picks, not full-game totals.

    MLB result rows store labels such as "NRFI Win" or "YRFI Loss" in
    nrfiResult. Homepage NRFI/YRFI cards should use that field instead of
    totalResult, otherwise the hot/cold badge is really grading full-game
    overs/unders.
    """
    wanted = str(pick or "").upper().strip()
    rows = []
    for row in results:
        if str(row.get("league") or "").upper() != "MLB":
            continue
        label = str(row.get("nrfiResult") or row.get("firstInningResult") or "").strip()
        if not normalize_result(label):
            continue
        if wanted in {"NRFI", "YRFI"} and not label.upper().startswith(wanted):
            continue
        enriched = dict(row)
        enriched["_nrfiYrfiResult"] = label
        rows.append(enriched)

    summary = summarize_rows(rows, "_nrfiYrfiResult", limit=limit)
    summary["scope"] = f"MLB {wanted} results" if wanted in {"NRFI", "YRFI"} else "MLB NRFI/YRFI results"
    return summary


def row_score(row: dict[str, Any], *, prefer_model_gap: bool = False) -> float:
    prob = pct(row.get("prob_cons")) or 0.0
    pred = num(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"), 0.0) or 0.0
    avg = num(row.get("avg_anchor"), 0.0) or 0.0
    line = num(row.get("line"), 0.0) or 0.0
    hit_score = num(row.get("hit_score"), 0.0) or 0.0
    gap = pred - max(line, 0.0)
    avg_gap = pred - avg
    if prefer_model_gap:
        return avg_gap * 1.25 + pred * 0.15 + prob * 0.20
    return prob * 0.60 + hit_score * 0.15 + max(gap, -2.0) * 0.10 + max(pred, 0.0) * 0.02


def choose_prop_rows(entries: list[dict[str, Any]], date: str, stat: str, *, role: str | None = None,
                     line: float | None = None, limit: int = 8, unique_player: bool = True,
                     reverse: bool = True, prefer_model_gap: bool = False) -> list[dict[str, Any]]:
    rows = []
    for row in entries:
        if safe_date(row.get("gameDate") or row.get("date")) != date:
            continue
        if str(row.get("stat") or "").upper() != stat.upper():
            continue
        if role and str(row.get("playerType") or row.get("role") or "").lower() != role.lower():
            continue
        if line is not None and not line_matches(row, line):
            continue
        if is_tbd_player(row) or is_hidden_injury(row):
            continue
        rows.append(row)

    rows.sort(key=lambda r: row_score(r, prefer_model_gap=prefer_model_gap), reverse=reverse)
    if not unique_player:
        return rows[:limit]
    seen = set()
    out = []
    for row in rows:
        key = (str(row.get("playerId") or row.get("player") or "").lower(), canonical_nba_stat(row.get("stat")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def prop_url(row: dict[str, Any]) -> str:
    from urllib.parse import urlencode

    params = {
        "league": "MLB",
        "date": safe_date(row.get("gameDate") or row.get("date")),
        "stat": str(row.get("stat") or "").upper(),
    }
    if row.get("playerId"):
        params["playerId"] = str(row.get("playerId"))
    elif row.get("player"):
        params["player"] = str(row.get("player"))
    if row.get("line") not in (None, ""):
        params["line"] = str(row.get("line"))
    return "props_analyzer.html?" + urlencode(params)


def compact_prop(row: dict[str, Any], tracker: dict[str, Any] | None = None, *, card_type: str = "prop") -> dict[str, Any]:
    stat = str(row.get("stat") or "").upper()
    prob = pct(row.get("prob_cons"))
    model = num(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"))
    avg = num(row.get("avg_anchor"))
    line = num(row.get("line"))
    title = stat_label(stat)
    is_pitcher = str(row.get("playerType") or row.get("role") or "").lower() == "pitcher" or stat in {"HA", "ER"}
    if is_pitcher and stat in {"K", "HA", "ER"}:
        # Homepage pitcher boards should compare model projection to pitcher average, not
        # display analyzer placeholder/alternate lines. True book lines can be added later
        # after a pitcher-line scraper is wired in.
        line = None
    if stat == "ER" and card_type == "pitcher-low-er":
        title = "Lowest SP ER Projection"
        prob = None
    elif stat == "ER" and card_type == "pitcher-high-er":
        title = "Highest SP ER Projection"
        prob = None
    if stat == "H":
        pick = f"{row.get('player', '')} 0.5+ hit"
    elif stat == "TB" and line == 1.5:
        pick = f"{row.get('player', '')} 1.5+ total bases"
    elif stat == "HRR":
        pick = f"{row.get('player', '')} over {fmt_num(line, 1)} HRR"
    elif stat == "K" and str(row.get("playerType") or "").lower() == "pitcher":
        pick = f"{row.get('player', '')} Ks: model {fmt_num(model)} vs avg {fmt_num(avg)}"
    elif stat == "ER" and card_type == "pitcher-low-er":
        pick = f"{row.get('player', '')} low ER signal: {fmt_num(model)}"
    elif stat == "ER" and card_type == "pitcher-high-er":
        pick = f"{row.get('player', '')} high ER risk: {fmt_num(model)}"
    elif stat == "ER":
        pick = f"{row.get('player', '')} ER projection: {fmt_num(model)}"
    elif stat == "HA":
        pick = f"{row.get('player', '')} hits allowed: model {fmt_num(model)} vs avg {fmt_num(avg)}"
    else:
        pick = f"{row.get('player', '')} {stat_label(stat)}"

    return {
        "id": str(row.get("id") or f"{stat}|{row.get('player')}|{row.get('line')}")[:120],
        "type": card_type,
        "league": "MLB",
        "category": title,
        "stat": stat,
        "player": row.get("player") or "",
        "team": row.get("team") or "",
        "opp": row.get("opp") or "",
        "matchup": row.get("matchup") or "",
        "line": line,
        "model": model,
        "average": avg,
        "probability": prob,
        "confidence": "High" if prob is not None and prob >= 0.68 else ("Medium" if prob is not None and prob >= 0.58 else "Lean"),
        "title": title,
        "pick": pick,
        "reason": row.get("boardDriver") or row.get("summary") or row.get("driver_summary") or "Model and recent-form signal.",
        "href": prop_url(row),
        "tracking": tracker or {},
        "gameId": row.get("gameId"),
        "playable": bool(line is not None and stat in {"H", "HRR", "TB"}),
        "actionable": bool(line is not None and stat in {"H", "HRR", "TB"}),
        "recentHitRate10": pct(row.get("hit_r10")),
        "recentHitRate25": pct(row.get("hit_r25")),
        "modelEdge": (model - line) if model is not None and line is not None else None,
    }


def compact_market_value(row: dict[str, Any]) -> dict[str, Any]:
    probability = pct(row.get("modelProbability"))
    edge = pct(row.get("probabilityEdge"))
    roi = pct(row.get("expectedRoi"))
    status = str(row.get("recommendation") or "PASS").upper()
    book_key = str(row.get("bookmakerKey") or "").lower()
    price = num(row.get("price"))
    line = num(row.get("line"))
    player = str(row.get("player") or "")
    stat = str(row.get("stat") or "").upper()
    side = str(row.get("side") or "").upper()
    pick = str(row.get("pick") or f"{player} {side.title()} {fmt_num(line, 1)} {stat_label(stat)}")
    return {
        "id": str(row.get("id") or f"VALUE|{book_key}|{player}|{stat}|{line}|{side}")[:180],
        "type": "prop",
        "league": "MLB",
        "category": stat_label(stat),
        "stat": stat,
        "player": player,
        "playerId": row.get("playerId"),
        "team": row.get("team") or "",
        "opp": row.get("opp") or "",
        "matchup": row.get("matchup") or "",
        "gameId": row.get("gameId") or row.get("eventId"),
        "line": line,
        "side": side,
        "model": num(row.get("modelProjection")),
        "probability": probability,
        "marketProbability": pct(row.get("marketNoVigProbability")),
        "probabilityEdge": edge,
        "expectedRoi": roi,
        "selectedOdds": price,
        "bookmakerKey": book_key,
        "bookmakerTitle": row.get("bookmakerTitle") or book_key,
        "marketUpdatedAt": row.get("marketUpdatedAt"),
        "marketAgeHours": num(row.get("marketAgeHours")),
        "probabilitySource": row.get("probabilitySource"),
        "valueStatus": status,
        "title": f"{status}: {stat_label(stat)}",
        "pick": pick,
        "reason": row.get("recommendationReason") or "Model-versus-market value signal.",
        "href": row.get("href") or "props_analyzer.html?league=MLB",
        "tracking": row.get("tracking") or {},
        "playable": status in {"VALUE", "LEAN"} and price is not None and row.get("marketPairValid") is True,
        "actionable": status in {"VALUE", "LEAN"} and price is not None and row.get("marketPairValid") is True,
        "priceRequired": price is None,
        "linePairValid": row.get("marketPairValid") is True,
        "roleGate": row.get("roleGate"),
        "matchStatus": row.get("matchStatus"),
    }


def bookmaker_from_game(game: dict[str, Any]) -> tuple[str, str]:
    key = str(game.get("bookmakerKey") or game.get("marketBookmakerKey") or "").strip().lower()
    title = str(game.get("bookmakerTitle") or game.get("marketBookmakerTitle") or "").strip()
    source = str(game.get("marketLineSource") or game.get("marketSource") or "")
    if not title and "•" in source:
        title = source.split("•", 1)[1].strip()
    if not key and title:
        normalized = re.sub(r"[^a-z0-9]+", "", title.lower())
        aliases = {"draftkings": "draftkings", "fanduel": "fanduel", "betmgm": "betmgm", "caesars": "caesars", "espnbet": "espnbet", "betrivers": "betrivers", "pinnacle": "pinnacle", "bet365": "bet365"}
        key = aliases.get(normalized, normalized)
    return key, title or key


def nba_prop_url(row: dict[str, Any]) -> str:
    from urllib.parse import urlencode

    params = {
        "league": "NBA",
        "date": safe_date(row.get("gameDate") or row.get("date")),
        "stat": str(row.get("stat") or "").upper(),
    }
    if row.get("playerId"):
        params["playerId"] = str(row.get("playerId"))
    elif row.get("player"):
        params["player"] = str(row.get("player"))
    if row.get("line") not in (None, ""):
        params["line"] = str(row.get("line"))
    return "props_analyzer.html?" + urlencode(params)


def compact_nba_prop(row: dict[str, Any], tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    stat = canonical_nba_stat(row.get("stat"))
    prob = pct(row.get("prob_cons") if row.get("prob_cons") is not None else row.get("probability"))
    model = num(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"))
    avg = num(row.get("avg_anchor"))
    line = num(row.get("line"))
    player = row.get("player") or ""
    matchup = row.get("matchup") or ""
    if not matchup:
        matchup = "NBA matchup"
    direction = "over" if model is None or line is None or model >= line else "under"
    return {
        "id": str(row.get("id") or f"NBA|{stat}|{player}|{line}")[:120],
        "type": "prop",
        "league": "NBA",
        "category": stat_label(stat),
        "stat": stat,
        "player": player,
        "team": row.get("team") or "",
        "opp": row.get("opp") or "",
        "matchup": matchup,
        "line": line,
        "model": model,
        "average": avg,
        "probability": prob,
        "confidence": "High" if prob is not None and prob >= 0.68 else ("Medium" if prob is not None and prob >= 0.58 else "Lean"),
        "title": stat_label(stat),
        "pick": f"{player} {direction} {fmt_num(line, 1)} {stat}" if line is not None else f"{player} {stat}",
        "reason": row.get("boardDriver") or row.get("summary") or row.get("driver_summary") or "NBA model prop signal.",
        "href": nba_prop_url(row),
        "tracking": tracker or {},
        "gameId": row.get("gameId") or row.get("matchup") or row.get("id"),
    }


def nba_playable_line(row: dict[str, Any]) -> bool:
    """Keep the parlay builder on realistic sportsbook-style NBA lines.

    The analyzer often contains alternate lines. Some are technically high
    probability but not useful for users, such as a star scorer at 15 points or
    an elite rebounder at 5 boards. Those can stay in the analyzer, but the
    homepage builder should use lines close enough to the player's normal range
    to be playable.
    """
    stat = canonical_nba_stat(row.get("stat"))
    line = num(row.get("line"))
    if line is None:
        return False

    avg = num(row.get("avg_anchor"))
    pred = num(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"))

    # Absolute floors remove very low alternate lines before ratio checks.
    absolute_floor = {
        "PTS": 8.0,
        "REB": 3.0,
        "AST": 2.0,
        "PRA": 14.0,
        "PR": 10.0,
        "PA": 10.0,
        "RA": 8.0,
        "3PM": 1.5,
        "BLK": 0.5,
        "STL": 0.5,
        "TO": 1.5,
    }
    if line < absolute_floor.get(stat, 0.0):
        return False

    # Ratio floors remove alt lines that are far under recent production.
    # Example: Gobert 5 rebounds with a 10+ average, Edwards 15 points with a
    # 23+ average. The better playable versions remain available.
    ratio_floor = {
        "PTS": 0.78,
        "REB": 0.78,
        "AST": 0.72,
        "PRA": 0.74,
        "PR": 0.74,
        "PA": 0.74,
        "RA": 0.74,
        "3PM": 0.62,
        "BLK": 0.45,
        "STL": 0.45,
        "TO": 0.60,
    }
    floor = ratio_floor.get(stat)
    if floor is not None and avg is not None and avg > 0 and (line / avg) < floor:
        return False

    # Also reject extreme discounts to the model projection, but use a softer
    # cutoff so genuinely good edges are not removed solely for being favorable.
    if floor is not None and pred is not None and pred > 0 and (line / pred) < max(0.55, floor - 0.12):
        return False

    return True


def choose_nba_prop_rows(entries: list[dict[str, Any]], date: str, *, limit: int = 36) -> list[dict[str, Any]]:
    rows = []
    for row in entries:
        if safe_date(row.get("gameDate") or row.get("date")) != date:
            continue
        if is_tbd_player(row) or is_hidden_injury(row):
            continue
        prob = pct(row.get("prob_cons") if row.get("prob_cons") is not None else row.get("probability"))
        if prob is None or prob < 0.54:
            continue
        stat = canonical_nba_stat(row.get("stat"))
        if stat not in {"PTS", "REB", "AST", "PRA", "PR", "PA", "RA", "3PM", "BLK", "STL", "TO"}:
            continue
        if not nba_playable_line(row):
            continue
        pred = num(row.get("pred_anchor") if row.get("pred_anchor") is not None else row.get("mu_cons"))
        line = num(row.get("line"))
        if pred is not None and line is not None and abs(pred - line) < 0.35:
            continue
        rows.append(row)
    rows.sort(key=lambda r: (
        pct(r.get("prob_cons") if r.get("prob_cons") is not None else r.get("probability")) or 0,
        num(r.get("hit_score"), 0) or 0,
    ), reverse=True)
    seen: set[tuple[str, str]] = set()
    out = []
    for row in rows:
        key = (str(row.get("playerId") or row.get("player") or "").lower(), canonical_nba_stat(row.get("stat")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def game_url(game: dict[str, Any]) -> str:
    return "game.html?id=" + str(game.get("id") or "")



def calibrated_moneyline_pick(game: dict[str, Any]) -> tuple[str, float | None, float | None, bool]:
    """Return public calibrated ML team, probability, odds, and flip status."""
    away_team = str(game.get("awayTeam") or "")
    home_team = str(game.get("homeTeam") or "")

    team = str(game.get("calibratedMoneylineTeam") or "")
    probability = pct(game.get("calibratedMoneylineWinProb"))
    flipped = bool(game.get("calibratedMoneylineFlipped"))

    if team not in {away_team, home_team} or probability is None:
        raw_team = str(game.get("modelPickTeam") or "")
        raw_probability = pct(
            game.get("calibratedModelPickWinProb")
            if game.get("calibratedModelPickWinProb") is not None
            else game.get("modelMoneylineProb")
        )
        if raw_team in {away_team, home_team} and raw_probability is not None:
            if raw_probability < 0.5:
                team = home_team if raw_team == away_team else away_team
                probability = 1.0 - raw_probability
                flipped = True
            else:
                team = raw_team
                probability = raw_probability
                flipped = False

    if team not in {away_team, home_team} or probability is None:
        away_probability = pct(game.get("awayWinProb"))
        home_probability = pct(game.get("homeWinProb"))
        if away_probability is not None or home_probability is not None:
            if (away_probability if away_probability is not None else -1) >= (home_probability if home_probability is not None else -1):
                team, probability = away_team, away_probability
            else:
                team, probability = home_team, home_probability

    odds = num(game.get("homeML")) if team == home_team else num(game.get("awayML")) if team == away_team else None
    return team, probability, odds, flipped


def calibrated_moneyline_reason(game: dict[str, Any], team: str, probability: float | None) -> str:
    away_score = num(game.get("modelAwayScore"))
    home_score = num(game.get("modelHomeScore"))
    away_team = str(game.get("awayTeam") or "")
    home_team = str(game.get("homeTeam") or "")
    if away_score is None or home_score is None or not team:
        return f"Calibrated win probability {(probability or 0) * 100:.0f}%"

    score_team = away_team if away_score > home_score else home_team if home_score > away_score else ""
    if score_team and score_team != team:
        return (
            f"Calibrated ML probability favors {team}, while the average score projection leans "
            f"{score_team} {fmt_num(home_score, 1)}-{fmt_num(away_score, 1)}. "
            f"The ML pick follows the calibrated chance of winning."
        )
    return f"Calibrated win probability {(probability or 0) * 100:.0f}%"

def compact_game(game: dict[str, Any], tracker: dict[str, Any], *, kind: str, title: str, pick: str,
                 probability: float | None, reason: str) -> dict[str, Any]:
    return {
        "id": str(game.get("id") or f"{game.get('awayTeam')}@{game.get('homeTeam')}|{kind}"),
        "type": "game",
        "league": game.get("league") or "",
        "category": title,
        "stat": kind,
        "matchup": f"{game.get('awayTeam', '')} @ {game.get('homeTeam', '')}",
        "title": title,
        "pick": pick,
        "probability": probability,
        "modelAwayScore": num(game.get("modelAwayScore")),
        "modelHomeScore": num(game.get("modelHomeScore")),
        "modelTotal": num(game.get("modelTotal")),
        "marketTotal": num(game.get("marketTotal")),
        "confidence": ("High" if probability is not None and probability >= 0.68 else ("Medium" if probability is not None and probability >= 0.58 else "Lean")) if probability is not None else (game.get("confidence") or ""),
        "reason": reason,
        "href": game_url(game),
        "tracking": tracker,
        **game_leg_metadata(game, kind),
    }


def game_leg_metadata(game: dict[str, Any], kind: str) -> dict[str, Any]:
    market = str(kind or "").upper()
    price_required = bool(game.get("marketRoutingPriceRequired"))
    calibration_rejected = bool(game.get("calibratedProbabilityRejectsScorePick"))
    selected_odds = None
    actionable = False
    reprice_required = False
    line_pair_valid = True

    if market == "ML":
        _, _, selected_odds, _ = calibrated_moneyline_pick(game)
        reprice_required = bool(game.get("moneylineRepriceRequired"))
        actionable = game.get("moneylineActionable") is True
        if game.get("moneylineActionable") is None:
            actionable = selected_odds is not None and not calibration_rejected and not reprice_required and not price_required
    elif market == "SPREAD":
        selected_odds = num(game.get("currentSelectedSpreadOdds") if game.get("currentSelectedSpreadOdds") is not None else game.get("selectedSpreadOdds"))
        reprice_required = bool(game.get("spreadRepriceRequired"))
        line_pair_valid = game.get("spreadLinePairValid") is not False
        actionable = game.get("spreadActionable") is True
        if game.get("spreadActionable") is None:
            actionable = selected_odds is not None and num(game.get("selectedSpreadLine")) is not None and line_pair_valid and not reprice_required and not price_required
    elif market == "TOTAL":
        selected_odds = num(game.get("currentSelectedTotalOdds") if game.get("currentSelectedTotalOdds") is not None else game.get("selectedTotalOdds"))
        reprice_required = bool(game.get("totalRepriceRequired"))
        line_pair_valid = game.get("totalLinePairValid") is not False and game.get("totalPricePairValid") is not False
        actionable = game.get("totalActionable") is True
        if game.get("totalActionable") is None:
            actionable = selected_odds is not None and num(game.get("marketTotal")) is not None and line_pair_valid and not reprice_required and not price_required

    playable = bool(actionable and selected_odds is not None and line_pair_valid and not reprice_required and not price_required and not calibration_rejected)
    return {
        "playable": playable,
        "actionable": actionable,
        "selectedOdds": selected_odds,
        "priceRequired": price_required,
        "repriceRequired": reprice_required,
        "linePairValid": line_pair_valid,
        "calibrationRejected": calibration_rejected,
        "expectedRoi": num(game.get("expectedRoi") if market == "ML" else game.get("spreadExpectedRoi") if market == "SPREAD" else game.get("totalExpectedRoi") if market == "TOTAL" else None),
        "bookmakerKey": bookmaker_from_game(game)[0],
        "bookmakerTitle": bookmaker_from_game(game)[1],
        "marketUpdatedAt": game.get("marketLineUpdated") or game.get("marketUpdatedAt"),
    }


def total_pick_from_game(g: dict[str, Any]) -> tuple[float, str, str]:
    """Return (probability, side, reason) for the actual market total.

    Prefer exact market probabilities. If an exact probability is unavailable for
    the actual line, derive a conservative probability from model-vs-market gap
    instead of borrowing an alternate 7.5/8.5 probability and mislabeling it.
    """
    final_rec = str(g.get('totalFinalRecommendation') or '').upper()
    if 'PRICE_REQUIRED' in final_rec or 'NO_BET' in final_rec or g.get('marketRoutingPriceRequired') is True or g.get('totalRepriceRequired') is True or (final_rec and g.get('totalActionable') is False):
        return 0.0, '', ''
    over_p = pct(g.get("marketOverProb"))
    under_p = pct(g.get("marketUnderProb"))
    market_total = num(g.get("marketTotal"))
    model_total = num(g.get("modelTotal"))
    league = str(g.get("league") or "").upper()

    if over_p is not None or under_p is not None:
        if (over_p or 0) >= (under_p or 0):
            return over_p or 0.0, "Over", "Exact probability for the current market total."
        return under_p or 0.0, "Under", "Exact probability for the current market total."

    if market_total is not None and model_total is not None:
        gap = model_total - market_total
        min_gap = 3.0 if league == "NBA" else 0.45 if league == "NHL" else 0.55
        if abs(gap) >= min_gap:
            side = "Over" if gap > 0 else "Under"
            return derived_total_probability(league, gap), side, f"Model total {fmt_num(model_total, 1)} vs market {fmt_num(market_total, 1)}."

    if market_total is None:
        fallback_over = pct(g.get("fallbackOverProb"))
        fallback_under = pct(g.get("fallbackUnderProb"))
        if fallback_over is not None or fallback_under is not None:
            if (fallback_over or 0) >= (fallback_under or 0):
                return fallback_over or 0.0, "Over", "Fallback total probability; market total pending."
            return fallback_under or 0.0, "Under", "Fallback total probability; market total pending."

    return 0.0, "", ""


def choose_game_cards(games: list[dict[str, Any]], date: str, results_history: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    today = [g for g in games if safe_date(g.get("gameDate")) == date]
    high_conf: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []

    # The condensed game board should show one strongest signal per game after
    # comparing ML, spread, total, and NRFI/YRFI. The old logic omitted spread,
    # only considered Overs, and applied a separate gate to ML, which caused the
    # board to be filled almost entirely by first-inning signals.
    for g in today:
        league = str(g.get("league") or "").upper()
        matchup = f"{g.get('awayTeam')} @ {g.get('homeTeam')}"
        candidates: list[dict[str, Any]] = []

        # Moneyline: calibrated_model_pick_win_prob belongs to modelPickTeam.
        # When it is below 50%, the public side flips to the opponent.
        team, probability, odds, _ = calibrated_moneyline_pick(g)
        if probability is not None and odds is not None and team:
            candidates.append({
                "id": g.get("id"), "league": league, "matchup": matchup,
                "pick": f"ML · {team} ({fmt_american(odds)})",
                "probability": probability,
                "modelScore": calibrated_moneyline_reason(g, team, probability),
                "href": game_url(g), "market": "ML", "priced": True,
            })

        # Spread: compare both sides when the exact +/-1.5 probabilities exist.
        away_line = num(g.get("awaySpread") if g.get("awaySpread") is not None else g.get("marketSpread"))
        home_line = num(g.get("homeSpread"))
        if home_line is None and away_line is not None:
            home_line = -away_line
        spread_candidates: list[tuple[float, str, float, float | None]] = []
        if away_line is not None and home_line is not None:
            if abs(away_line - 1.5) < 0.11:
                ap = pct(g.get("awayPlus1p5Prob")); hp = pct(g.get("homeMinus1p5Prob"))
            elif abs(away_line + 1.5) < 0.11:
                ap = pct(g.get("awayMinus1p5Prob")); hp = pct(g.get("homePlus1p5Prob"))
            else:
                ap = hp = None
            if ap is not None:
                spread_candidates.append((ap, str(g.get("awayTeam") or "Away"), away_line, num(g.get("awaySpreadOdds"))))
            if hp is not None:
                spread_candidates.append((hp, str(g.get("homeTeam") or "Home"), home_line, num(g.get("homeSpreadOdds"))))

        if not spread_candidates:
            stored_prob = pct(g.get("spreadCoverProbEst") if g.get("spreadCoverProbEst") is not None else g.get("modelSpreadPickProb"))
            stored_side = str(g.get("spreadPickSide") or "").upper()
            if stored_side == "HOME_SPREAD" and home_line is not None:
                spread_candidates.append((stored_prob or 0.0, str(g.get("homeTeam") or "Home"), home_line, num(g.get("homeSpreadOdds"))))
            elif stored_side == "AWAY_SPREAD" and away_line is not None:
                spread_candidates.append((stored_prob or 0.0, str(g.get("awayTeam") or "Away"), away_line, num(g.get("awaySpreadOdds"))))

        valid_spreads = [item for item in spread_candidates if item[0] > 0 and item[3] is not None]
        if valid_spreads:
            probability, team, line, odds = max(valid_spreads, key=lambda item: item[0])
            sign = "+" if line > 0 else ""
            candidates.append({
                "id": g.get("id"), "league": league, "matchup": matchup,
                "pick": f"SPREAD · {team} {sign}{fmt_num(line, 1)} ({fmt_american(odds)})",
                "probability": probability,
                "modelScore": f"Cover probability {probability * 100:.0f}%",
                "href": game_url(g), "market": "SPREAD", "priced": True,
            })

        # Total: compare both exact current-line probabilities. If unavailable,
        # use the selected total side/probability only as a fallback.
        market_total = num(g.get("marketTotal"))
        over_prob = pct(g.get("marketOverProb"))
        under_prob = pct(g.get("marketUnderProb"))
        total_side = ""
        total_prob = None
        if over_prob is not None or under_prob is not None:
            if (over_prob if over_prob is not None else -1) >= (under_prob if under_prob is not None else -1):
                total_side, total_prob = "Over", over_prob
            else:
                total_side, total_prob = "Under", under_prob
        else:
            stored_side = str(g.get("totalPickSide") or "").upper()
            stored_prob = pct(g.get("totalPickProbEst") if g.get("totalPickProbEst") is not None else g.get("modelTotalPickProb"))
            if stored_side in {"OVER", "UNDER"} and stored_prob is not None:
                total_side, total_prob = stored_side.title(), stored_prob
        total_odds = num(g.get("overOdds")) if total_side == "Over" else num(g.get("underOdds")) if total_side == "Under" else None
        if market_total is not None and total_prob is not None and total_odds is not None:
            candidates.append({
                "id": g.get("id"), "league": league, "matchup": matchup,
                "pick": f"TOTAL · {total_side} {fmt_num(market_total, 1)} ({fmt_american(total_odds)})",
                "probability": total_prob,
                "modelScore": f"Model total {fmt_num(g.get('modelTotal'), 1)} · {total_side} probability {total_prob * 100:.0f}%",
                "href": game_url(g), "market": "TOTAL", "priced": True,
            })

        # First inning remains eligible, but it competes against the three main
        # markets instead of being appended automatically for every game.
        if league == "MLB":
            nrfi_prob = pct(g.get("nrfiProb"))
            yrfi_prob = pct(g.get("yrfiProb"))
            if nrfi_prob is not None or yrfi_prob is not None:
                if (nrfi_prob if nrfi_prob is not None else -1) >= (yrfi_prob if yrfi_prob is not None else -1):
                    side, probability = "NRFI", nrfi_prob
                else:
                    side, probability = "YRFI", yrfi_prob
                if probability is not None:
                    candidates.append({
                        "id": g.get("id"), "league": league, "matchup": matchup,
                        "pick": side, "probability": probability,
                        "modelScore": f"NRFI {(nrfi_prob or 0) * 100:.0f}% / YRFI {(yrfi_prob or 0) * 100:.0f}%",
                        "href": game_url(g), "market": side, "priced": False,
                    })

        if candidates:
            best = max(candidates, key=lambda item: (item.get("probability") or 0, bool(item.get("priced"))))
            high_conf.append(best)

    high_conf.sort(key=lambda x: ((x.get("probability") or 0), bool(x.get("priced"))), reverse=True)

    # Preserve the featured-card selection below; this is separate from the
    # condensed one-best-market-per-game board.
    calibrated_ml_candidates = []
    for game in today:
        team, probability, odds, _ = calibrated_moneyline_pick(game)
        if team and probability is not None and odds is not None:
            calibrated_ml_candidates.append((probability, game, team))
    calibrated_ml_candidates.sort(key=lambda item: item[0], reverse=True)
    top_ml_entry = next((item for item in calibrated_ml_candidates if item[0] >= 0.58), None)
    if top_ml_entry:
        probability, top_ml, team = top_ml_entry
        cards.append(compact_game(
            top_ml, game_tracker(results_history, "mlResult", str(top_ml.get("league") or ""), 40),
            kind="ML", title="Strongest Game Lean", pick=f"{team} ML",
            probability=probability, reason=calibrated_moneyline_reason(top_ml, team, probability)
        ))

    total_candidates = []
    for g in today:
        prob, side, total_reason = total_pick_from_game(g)
        if side:
            total_candidates.append((prob, g, side, total_reason))
    total_candidates.sort(key=lambda x: x[0], reverse=True)
    if total_candidates and total_candidates[0][0] >= 0.56:
        prob, g, side, total_reason = total_candidates[0]
        line = g.get("marketTotal") if g.get("marketTotal") not in (None, "") else ""
        cards.append(compact_game(
            g, game_tracker(results_history, "totalResult", str(g.get("league") or ""), 40),
            kind="TOTAL", title="Best Game Total Signal", pick=f"{side} {fmt_num(line, 1) if line != '' else ''}".strip(),
            probability=prob, reason=total_reason or g.get("summary") or "Top total probability signal on today’s board."
        ))

    nrfi_candidates = []
    for g in today:
        if str(g.get("league") or "").upper() != "MLB":
            continue
        n = pct(g.get("nrfiProb")) or 0
        y = pct(g.get("yrfiProb")) or 0
        nrfi_candidates.append((max(n, y), g, "NRFI" if n >= y else "YRFI"))
    nrfi_candidates.sort(key=lambda x: x[0], reverse=True)
    if nrfi_candidates and nrfi_candidates[0][0] >= 0.52:
        prob, g, side = nrfi_candidates[0]
        cards.append(compact_game(
            g, nrfi_yrfi_tracker(results_history, side, 40),
            kind=side, title="Best NRFI/YRFI Signal", pick=side,
            probability=prob, reason=g.get("summary") or "Top first-inning probability signal."
        ))

    return cards, high_conf[:12]

def parse_summary_probability(summary: str, pattern: str) -> float | None:
    match = re.search(pattern, summary or "", flags=re.IGNORECASE)
    if not match:
        return None
    return pct(match.group(1))


def format_spread_pick(team: str, spread: Any) -> str:
    line = num(spread)
    if line is None:
        return f"{team} cover"
    sign = "+" if line > 0 else ""
    return f"{team} {sign}{fmt_num(line, 1)}"


def american_favorite(home_ml: Any, away_ml: Any) -> str | None:
    home = num(home_ml)
    away = num(away_ml)
    if home is None or away is None:
        return None
    # Negative American odds are favorites. If both signs match, the smaller
    # numeric value is the stronger favorite (-150 over -120, +110 over +140).
    return "home" if home < away else "away"


def signed_spread_for_team(game: dict[str, Any], team: str | None, summary_says_home: bool | None = None) -> float | None:
    home = str(game.get('homeTeam') or '')
    away = str(game.get('awayTeam') or '')
    team_raw = str(team or '')
    home_line = num(game.get('homeSpread'))
    away_line = num(game.get('awaySpread'))
    if away_line is None:
        away_line = num(game.get('marketSpread'))  # legacy away-team perspective
    if home_line is None and away_line is not None:
        home_line = -away_line
    if team_raw == home or (summary_says_home is True and not team_raw):
        return home_line
    if team_raw == away or (summary_says_home is False and not team_raw):
        return away_line
    return None

def format_game_spread_pick(game: dict[str, Any], team: str, summary_says_home: bool | None = None) -> str:
    return format_spread_pick(team, signed_spread_for_team(game, team, summary_says_home))



def model_home_margin(game: dict[str, Any]) -> float | None:
    margin = num(game.get("modelHomeSpread"))
    if margin is not None:
        return margin
    home_score = num(game.get("modelHomeScore"))
    away_score = num(game.get("modelAwayScore"))
    if home_score is None or away_score is None:
        return None
    return home_score - away_score


def derived_spread_probability(league: str, edge_points: float) -> float:
    """Conservative spread probability from model-vs-market edge.

    This is intentionally capped well below the raw game win probabilities. A
    team covering a spread is a different event from winning the game, so stale
    summary text such as "Home cover 87%" should not be carried forward after
    a real sportsbook line is attached.
    """
    league = league.upper()
    scale = 0.018 if league == "NBA" else 0.075 if league == "NHL" else 0.060
    cap = 0.67 if league == "NBA" else 0.68
    return min(cap, 0.50 + abs(edge_points) * scale)


def spread_edge_threshold(league: str) -> float:
    league = league.upper()
    if league == "NBA":
        return 1.5
    if league == "NHL":
        return 0.25
    return 0.35


def derived_spread_pick(game: dict[str, Any]) -> tuple[str, float, float, str] | None:
    """Return (team, signed_line, probability, reason) from actual market spread.

    The games payload may contain stale cover probabilities created before the
    market line was available. Prefer a structured modelSpreadPick when present;
    otherwise use the current market spread and model margin directly.
    """
    if game.get('spreadLinePairValid') is False or game.get('marketRoutingPriceRequired') is True or game.get('spreadRepriceRequired') is True:
        return None
    final_rec = str(game.get('spreadFinalRecommendation') or '').upper()
    if 'PRICE_REQUIRED' in final_rec or 'NO_BET' in final_rec or (final_rec and game.get('spreadActionable') is False):
        return None
    direct_label = str(game.get("modelSpreadPickLabel") or "").strip()
    direct_prob = pct(game.get("modelSpreadPickProb"))
    if direct_label and direct_prob is not None:
        m = re.match(r"^(.+?)\s+([+-]?\d+(?:\.\d+)?)$", direct_label)
        if m:
            return m.group(1).strip(), float(m.group(2)), direct_prob, game.get("summary") or "Model run-line probability for the actual market line."

    league = str(game.get("league") or "").upper()
    home = str(game.get("homeTeam") or "")
    away = str(game.get("awayTeam") or "")
    if not home or not away:
        return None
    margin = model_home_margin(game)
    home_line = signed_spread_for_team(game, home, True)
    away_line = signed_spread_for_team(game, away, False)
    if margin is None or home_line is None or away_line is None:
        return None

    home_edge = margin + home_line
    edge = abs(home_edge)
    if edge < spread_edge_threshold(league):
        return None

    if home_edge >= 0:
        team = home
        signed_line = home_line
        team_margin_text = f"{home} by {fmt_num(margin, 1)}" if margin >= 0 else f"{away} by {fmt_num(abs(margin), 1)}"
    else:
        team = away
        signed_line = away_line
        team_margin_text = f"{home} by {fmt_num(margin, 1)}" if margin >= 0 else f"{away} by {fmt_num(abs(margin), 1)}"
    prob = derived_spread_probability(league, edge)
    reason = f"Model margin {team_margin_text} vs market {format_spread_pick(home, home_line)} / {format_spread_pick(away, away_line)}."
    return team, signed_line, prob, reason

def derived_total_probability(league: str, gap: float) -> float:
    league = league.upper()
    scale = 0.012 if league == "NBA" else 0.055 if league == "NHL" else 0.035
    cap = 0.70 if league == "NBA" else 0.67
    return min(cap, 0.52 + abs(gap) * scale)


def build_game_parlay_candidates(games: list[dict[str, Any]], date: str, results_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for g in games:
        if safe_date(g.get("gameDate")) != date:
            continue
        league = str(g.get("league") or "").upper()
        matchup = f"{g.get('awayTeam', '')} @ {g.get('homeTeam', '')}"
        summary = str(g.get("summary") or "")

        # Formal parlay eligibility still respects recommendation gates, while
        # the selected team/probability pair follows the calibrated ML side.
        ml_team, ml_probability, ml_odds, ml_flipped = calibrated_moneyline_pick(g)
        if (
            g.get('moneylineActionable') is not False
            and not g.get('calibratedProbabilityRejectsScorePick')
            and not ml_flipped
            and ml_team
            and ml_probability is not None
            and ml_probability >= 0.55
            and ml_odds is not None
        ):
            candidates.append(compact_game(
                g, game_tracker(results_history, "mlResult", league, 40),
                kind="ML", title="Game Winner", pick=f"{ml_team} ML",
                probability=ml_probability, reason=calibrated_moneyline_reason(g, ml_team, ml_probability)
            ))

        spread_pick = derived_spread_pick(g)
        if spread_pick is not None:
            team, signed_line, cover_prob, spread_reason = spread_pick
            candidates.append(compact_game(
                g, game_tracker(results_history, "spreadResult", league, 40),
                kind="SPREAD", title="Spread Signal", pick=format_spread_pick(team, signed_line),
                probability=cover_prob, reason=spread_reason
            ))
        else:
            has_v86n_spread_decision = bool(g.get('spreadFinalRecommendation') or g.get('spreadPickSide'))
            if has_v86n_spread_decision and g.get('spreadActionable') is False:
                cover_prob = None
            else:
                cover_prob = pct(g.get("marketCoverProb") if g.get("marketCoverProb") is not None else g.get("favoriteCoverProb"))
            # Ignore stale cover probabilities from summaries generated before
            # real lines were attached. Those summaries can say things like
            # "Home cover 87% • Spread line pending" and should not feed the
            # parlay builder once marketSpread exists.
            pending_summary = "line pending" in summary.lower()
            if cover_prob is None and not pending_summary:
                cover_prob = parse_summary_probability(summary, r"(?:home|away)\s+cover\s+([0-9]+(?:\.[0-9]+)?)%")
            if cover_prob is not None and cover_prob >= 0.54:
                home_match = re.search(r"home\s+cover", summary, flags=re.IGNORECASE)
                away_match = re.search(r"away\s+cover", summary, flags=re.IGNORECASE)
                summary_says_home = True if home_match else (False if away_match else None)
                team = g.get("homeTeam") if summary_says_home is True else g.get("awayTeam") if summary_says_home is False else (g.get("favoriteWinLabel") or "Team")
                candidates.append(compact_game(
                    g, game_tracker(results_history, "spreadResult", league, 40),
                    kind="SPREAD", title="Spread Signal", pick=g.get("marketCoverLabel") or format_game_spread_pick(g, team or "Team", summary_says_home),
                    probability=cover_prob, reason=g.get("summary") or "Model spread-cover signal."
                ))

        # NHL/non-MLB summaries sometimes carry the only win-probability text.
        summary_win = parse_summary_probability(summary, r"\b[A-Z]{2,4}\s+([0-9]+(?:\.[0-9]+)?)%\s+win")
        if g.get('moneylineActionable') is not False and summary_win is not None and summary_win >= 0.54:
            team_match = re.search(r"\b([A-Z]{2,4})\s+[0-9]+(?:\.[0-9]+)?%\s+win", summary)
            team = team_match.group(1) if team_match else (g.get("homeTeam") or "Team")
            candidates.append(compact_game(
                g, game_tracker(results_history, "mlResult", league, 40),
                kind="ML", title="Game Winner", pick=f"{team} win signal",
                probability=summary_win, reason=g.get("summary") or "Model win signal from game summary."
            ))

        total_prob, total_side, total_reason = total_pick_from_game(g)
        if total_side and total_prob >= 0.54:
            market_total = num(g.get("marketTotal"))
            candidates.append(compact_game(
                g, game_tracker(results_history, "totalResult", league, 40),
                kind="TOTAL", title="Game Total", pick=f"{total_side} {fmt_num(market_total, 1) if market_total is not None else ''}".strip(),
                probability=total_prob, reason=total_reason or "Model total probability signal."
            ))

        if league == "MLB":
            n = pct(g.get("nrfiProb")) or 0
            y = pct(g.get("yrfiProb")) or 0
            if max(n, y) >= 0.52:
                side = "NRFI" if n >= y else "YRFI"
                candidates.append(compact_game(
                    g, nrfi_yrfi_tracker(results_history, side, 40),
                    kind=side, title="NRFI/YRFI", pick=side,
                    probability=max(n, y), reason=g.get("summary") or "First-inning model signal."
                ))
    return candidates


def balanced_pool(items: list[dict[str, Any]], *, per_league: int = 32, total_limit: int = 120) -> list[dict[str, Any]]:
    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_league[str(item.get("league") or "OTHER").upper()].append(item)
    output: list[dict[str, Any]] = []
    for league, league_items in sorted(by_league.items()):
        league_items.sort(key=lambda c: c.get("probability") or 0, reverse=True)
        output.extend(league_items[:per_league])
    output.sort(key=lambda c: c.get("probability") or 0, reverse=True)
    return output[:total_limit]


def board_payload(rows: list[dict[str, Any]], tracker: dict[str, Any], *, card_type: str = "prop") -> list[dict[str, Any]]:
    return [compact_prop(r, tracker, card_type=card_type) for r in rows]


def main() -> None:
    meta = read_json(DATA / "site.json", {})
    target = meta.get("targetDate") or datetime.now(timezone.utc).date().isoformat()
    next_date = meta.get("nextDate") or ""
    games = read_json(DATA / "games.json", [])
    analyzer = read_json(DATA / "mlb_props_analyzer.json", {"entries": []})
    entries = analyzer.get("entries", []) if isinstance(analyzer, dict) else []
    prop_value_payload = read_json(DATA / "mlb_prop_values.json", {"values": [], "allOffers": []})
    prop_value_rows = prop_value_payload.get("values", []) if isinstance(prop_value_payload, dict) else []
    prop_value_all_offers = prop_value_payload.get("allOffers", []) if isinstance(prop_value_payload, dict) else []
    feature_config = read_json(DATA / 'site_features.json', {})
    active_leagues = {str(x).upper() for x in feature_config.get('activeLeagues', ['MLB'])}
    nba_analyzer = read_json(DATA / "nba_props_analyzer.json", {"entries": []}) if 'NBA' in active_leagues else {'entries': []}
    nba_entries = nba_analyzer.get("entries", []) if isinstance(nba_analyzer, dict) else []
    prop_results = read_json(DATA / "mlb_prop_results_history.json", [])
    results_history = read_json(DATA / "results_history.json", [])

    trackers = {
        "H": prop_tracker(prop_results, "H", line=0.5, limit=30),
        "HRR": prop_tracker(prop_results, "HRR", line=1.5, limit=30),
        "TB": prop_tracker(prop_results, "TB", line=1.5, limit=30),
        "K": prop_tracker(prop_results, "K", limit=30),
        "HA": prop_tracker(prop_results, "HA", limit=30),
        "ER": prop_tracker(prop_results, "ER", limit=30),
    }

    hits = choose_prop_rows(entries, target, "H", role="batter", line=0.5, limit=8)
    hrr = choose_prop_rows(entries, target, "HRR", role="batter", line=1.5, limit=8)
    tb15 = choose_prop_rows(entries, target, "TB", role="batter", line=1.5, limit=8)
    pitcher_k = choose_prop_rows(entries, target, "K", role="pitcher", limit=8, prefer_model_gap=True)
    pitcher_ha = choose_prop_rows(entries, target, "HA", role="pitcher", limit=8)
    starter_er_rows = [
        r for r in choose_prop_rows(entries, target, "ER", role="pitcher", limit=80, unique_player=True)
        if is_probable_starting_pitcher(r)
    ]
    pitcher_er_low = sorted(
        starter_er_rows,
        key=lambda r: num(r.get("pred_anchor") if r.get("pred_anchor") is not None else r.get("mu_cons"), 999) or 999,
    )[:5]
    pitcher_er_high = sorted(
        starter_er_rows,
        key=lambda r: num(r.get("pred_anchor") if r.get("pred_anchor") is not None else r.get("mu_cons"), 0) or 0,
        reverse=True,
    )[:5]

    active_games = [g for g in games if str(g.get("league") or "").upper() in active_leagues]
    game_cards, high_conf_games = choose_game_cards(active_games, target, results_history)
    game_parlay_candidates = build_game_parlay_candidates(active_games, target, results_history)
    nba_prop_rows = choose_nba_prop_rows(nba_entries, target, limit=40)
    game_matchups = {}
    for g in active_games:
        matchup = f"{g.get('awayTeam', '')} @ {g.get('homeTeam', '')}".strip()
        for raw_key in (g.get("id"), g.get("gamePk")):
            if raw_key not in (None, ""):
                game_matchups[str(raw_key)] = matchup
                if "-" in str(raw_key):
                    game_matchups[str(raw_key).split("-")[-1]] = matchup

    market_value_cards = [
        compact_market_value(row) for row in prop_value_rows
        if safe_date(row.get("date")) == target and str(row.get("recommendation") or "").upper() in {"VALUE", "LEAN", "WATCH"}
    ]
    market_value_cards.sort(key=lambda card: (
        {"VALUE": 3, "LEAN": 2, "WATCH": 1}.get(str(card.get("valueStatus") or ""), 0),
        card.get("expectedRoi") if card.get("expectedRoi") is not None else -999,
        card.get("probabilityEdge") if card.get("probabilityEdge") is not None else -999,
    ), reverse=True)

    top_cards: list[dict[str, Any]] = []
    if game_cards:
        top_cards.extend(game_cards[:3])
    if hits:
        top_cards.append(compact_prop(hits[0], trackers["H"]))
    if hrr:
        top_cards.append(compact_prop(hrr[0], trackers["HRR"]))
    if tb15:
        top_cards.append(compact_prop(tb15[0], trackers["TB"]))
    if pitcher_k:
        top_cards.append(compact_prop(pitcher_k[0], trackers["K"]))
    if pitcher_ha:
        top_cards.append(compact_prop(pitcher_ha[0], trackers["HA"]))
    if pitcher_er_low:
        top_cards.append(compact_prop(pitcher_er_low[0], trackers["ER"], card_type="pitcher-low-er"))
    if pitcher_er_high:
        top_cards.append(compact_prop(pitcher_er_high[0], trackers["ER"], card_type="pitcher-high-er"))

    # Put probability-backed cards first, while keeping model-signal cards visible.
    top_cards = sorted(top_cards, key=lambda c: (c.get("probability") is not None, c.get("probability") or 0), reverse=True)[:10]

    parlay_pool = []
    # Once real prop prices exist, use exact book/line/price value rows. Until the
    # first successful scrape, preserve the older static MLB prop pool as a
    # research/watch-card fallback.
    market_parlay_cards = [
        compact_market_value(row) for row in prop_value_all_offers
        if safe_date(row.get("date")) == target
        and str(row.get("recommendation") or "").upper() in {"VALUE", "LEAN"}
    ]
    if market_parlay_cards:
        parlay_pool.extend(card for card in market_parlay_cards if card.get("playable") is True)
    else:
        for group in (hits[:10], hrr[:10], tb15[:10]):
            for row in group:
                card = compact_prop(row, trackers.get(str(row.get("stat") or "").upper(), {}), card_type="parlay")
                if card.get("playable") is True and card.get("probability") is not None and card["probability"] >= 0.53:
                    parlay_pool.append(card)

    # NBA props: the site already has analyzer entries, so expose a compact slice
    # to the parlay builder instead of making the builder look MLB-only.
    for row in nba_prop_rows:
        card = compact_nba_prop(row, {})
        if card.get("matchup") == "NBA matchup":
            gid = str(row.get("gameId") or "")
            if gid in game_matchups:
                card["matchup"] = game_matchups[gid]
                card["gameId"] = gid
        if card.get("probability") is not None and card["probability"] >= 0.53:
            parlay_pool.append(card)

    # Game signals across MLB/NBA/NHL: these add spread, total, winner, and NRFI/YRFI
    # options without requiring player-prop lines for every league.
    for card in game_parlay_candidates:
        if card.get("playable") is True and card.get("probability") is not None and card["probability"] >= 0.52:
            parlay_pool.append({
                **card,
                "type": "game",
                "category": card.get("category") or "Game Signal",
                "title": card.get("pick") or "Game Signal",
                "gameId": card.get("id") or card.get("gameId"),
            })

    seen_pool = set()
    deduped_pool = []
    for item in sorted(parlay_pool, key=lambda c: c.get("probability") or 0, reverse=True):
        key = (item.get("league"), item.get("player") or item.get("matchup"), item.get("stat") or item.get("pick"), item.get("gameId") or item.get("id"))
        if key in seen_pool:
            continue
        seen_pool.add(key)
        deduped_pool.append(item)
    deduped_pool = balanced_pool(deduped_pool, per_league=40, total_limit=120)

    output = {
        "targetDate": target,
        "nextDate": next_date,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parlayLogicVersion": "mlb-priced-value-v3",
        "parlayRules": {
            "activeLeagues": sorted(active_leagues),
            "requiresPlayableLine": True,
            "pitcherAverageOnlyProjectionsExcluded": True,
            "blockedOrRepricedGameMarketsExcluded": True,
            "sameBookLineAndPriceRequiredWhenMarketDataExists": True,
            "valueRecommendationsPreferred": True,
        },
        "trackingSummary": {
            "props": trackers,
            "games": {
                "ml": game_tracker(results_history, "mlResult", None, 60),
                "spread": game_tracker(results_history, "spreadResult", None, 60),
                "total": game_tracker(results_history, "totalResult", None, 60),
                "nrfiYrfi": nrfi_yrfi_tracker(results_history, None, 60),
            },
        },
        "topCards": top_cards,
        "bestValueProps": market_value_cards[:12],
        "bookmakers": sorted({
            str(card.get("bookmakerKey") or "") for card in parlay_pool if card.get("bookmakerKey")
        }),
        "marketValueGeneratedAt": prop_value_payload.get("generatedAt") if isinstance(prop_value_payload, dict) else None,
        "mlbBoards": {
            "hits": board_payload(hits, trackers["H"]),
            "hrr": board_payload(hrr, trackers["HRR"]),
            "totalBases": board_payload(tb15, trackers["TB"]),
            "pitcherKs": board_payload(pitcher_k, trackers["K"]),
            "pitcherHA": board_payload(pitcher_ha, trackers["HA"]),
            "pitcherERLow": board_payload(pitcher_er_low, trackers["ER"], card_type="pitcher-low-er"),
            "pitcherERHigh": board_payload(pitcher_er_high, trackers["ER"], card_type="pitcher-high-er"),
        },
        "highConfidenceGames": high_conf_games,
        "parlayPool": deduped_pool,
    }

    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} with {len(top_cards)} top cards and {len(deduped_pool)} parlay candidates")


if __name__ == "__main__":
    main()
