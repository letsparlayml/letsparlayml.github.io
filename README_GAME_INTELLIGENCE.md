# Game Intelligence V2

This version replaces the placeholder-style matchup text with a static research report generated from the existing site data.

## Run in the Docs preview repo

```powershell
cd C:\Docs\letsparlayml.github.io
.\build_game_intelligence_preview.bat
python -m http.server 8000
```

Open `http://localhost:8000`, then go to an MLB game detail page.

## What the builder creates

- `data/game_intelligence/index.json`
- `data/game_intelligence/mlb_YYYY-MM-DD_AWAY_HOME_GAMEPK.json`
- `data/prediction_snapshots/mlb/YYYY-MM-DD/*.json`

## Data used

Primary source:

- `data/mlb_props_analyzer.json`
- `data/mlb_props_analyzer/YYYY-MM-DD/*.json`
- `data/games.json`
- `data/results_history.json`

Optional local enrichment:

- `C:\python\mlb_data\pitcher_game_logs`
- `C:\python\mlb_data\batter_game_logs`

The optional raw logs are used when available to populate first-inning starter history and richer batter split notes. If those columns are not present, the report does not fake them; it states that no local first-inning log was found.

## What changed from V1

- Pitching section no longer duplicates projected stats.
- Actual dated starts are shown as box rows when available.
- Analyzer L3/L5/L10 windows are shown separately and clearly labeled when actual start rows are not available.
- Batter section now uses recent hit rates, location splits, opponent history, similar-game samples, TB/HRR hit rates, strikeout context, and optional raw splits.
- Cold bats now require actual weak recent profiles or K risk instead of repeating prediction/weather text.
- Prediction movement is snapshot-based and needs two runs in the same day.
