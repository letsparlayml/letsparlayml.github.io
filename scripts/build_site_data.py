"""
Minimal helper script to convert your local CSV exports into website JSON.

This is intentionally simple so you can adapt it to your own files.
Edit the input paths and column mappings below.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"

# Update these to match your real files.
GAMES_CSV = BASE / "incoming_games.csv"
PROPS_CSV = BASE / "incoming_props.csv"
RESULTS_CSV = BASE / "incoming_results.csv"


def build_games() -> list[dict]:
    if not GAMES_CSV.exists():
        return []

    df = pd.read_csv(GAMES_CSV)
    out = []
    for _, row in df.iterrows():
        out.append(
            {
                "id": str(row.get("id", "")),
                "league": row.get("league", "NBA"),
                "gameDate": str(row.get("game_date", "")),
                "awayTeam": row.get("away_team", ""),
                "homeTeam": row.get("home_team", ""),
                "marketSpread": float(row.get("market_spread", 0)),
                "marketTotal": float(row.get("market_total", 0)),
                "modelAwayScore": float(row.get("model_away_score", 0)),
                "modelHomeScore": float(row.get("model_home_score", 0)),
                "modelHomeSpread": float(row.get("model_home_spread", 0)),
                "modelTotal": float(row.get("model_total", 0)),
                "confidence": row.get("confidence", "Medium"),
                "summary": row.get("summary", ""),
                "movement": []
            }
        )
    return out


def build_props() -> list[dict]:
    if not PROPS_CSV.exists():
        return []

    df = pd.read_csv(PROPS_CSV)
    return df.to_dict(orient="records")


def build_results() -> list[dict]:
    if not RESULTS_CSV.exists():
        return []

    df = pd.read_csv(RESULTS_CSV)
    return df.to_dict(orient="records")


def save_json(path: Path, payload: list[dict] | dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(
        DATA_DIR / "site.json",
        {
            "siteTitle": "Sports Predictions Showcase",
            "leagues": ["NBA", "NHL", "CBB"],
            "lastUpdated": pd.Timestamp.now(tz="America/Denver").strftime("%Y-%m-%d %H:%M MT"),
        },
    )
    save_json(DATA_DIR / "games.json", build_games())
    save_json(DATA_DIR / "props.json", build_props())
    save_json(DATA_DIR / "results.json", build_results())
    print("Wrote website JSON files to", DATA_DIR)
