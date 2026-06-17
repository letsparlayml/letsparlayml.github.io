# Lets Parlay ML — v86n Site and Offseason Update

## Scope completed

This update changes the site-data pipeline to prefer the new v86n authoritative MLB fields, preserves legacy fallbacks, adds spread/total prices to market snapshots, and changes the active site layout to MLB-only while retaining NBA and NHL historical tracking.

The production `mlb_predictions.xlsx`, the v86n model script, `website_sync_v10_fixed.py`, `results_rollup_fixed.py`, and the model-run batch were not included in the uploaded packages. Therefore, the final validation uses a synthetic one-game v86n workbook containing the exact requested columns rather than claiming a live-slate conversion.

## Site layout after the season change

### Visible and active

- Featured MLB Top Picks
- MLB parlay/watch-card builder
- MLB quick boards by category
- Current MLB game board
- MLB prop analyzer
- Game-detail pages and MLB intelligence
- Line tracker, including archived prices when available
- Results and historical tracking for MLB, NBA, and NHL

### Disabled from the active homepage

- Cross-sport props table
- NBA/NHL quick-look panels
- NBA Props Lab

The offseason products are feature-gated, not deleted. Direct navigation to the NBA Props Lab displays an offseason message and links back to historical results and the MLB analyzer. Existing NBA/NHL data and results remain in place.

`home_top_picks.json` remains active and is rebuilt daily for Featured MLB Top Picks, MLB quick boards, and the parlay/watch-card builder. The builder now excludes pitcher projections that only compare against an average, blocked or repriced game markets, duplicate player exposure, and contradictory same-game legs. It also adjusts raw model probabilities using recent category tracking before selecting a card.

## Market refresh and stale-line design

The active post-prediction batch now refreshes MLB market lines only, then builds the MLB site JSON from `mlb_predictions.xlsx`. The converter compares the workbook market timestamp with the archive timestamp:

1. The workbook snapshot is used when it is current.
2. A newer post-run archive snapshot replaces the workbook snapshot as one atomic bookmaker snapshot.
3. If a selected line or price changed after the model calculation, the affected market is marked `Reprice required` and is not actionable.
4. `marketUpdatedAt`, `marketLineAgeHours`, and `marketLineStatus` are exported. The site displays a stale indicator when appropriate.

A second prediction-only model refresh was **not** added. The model script and model-run batch were not included, so it was not possible to prove that such a call would avoid retraining, duplicate history appends, result overwrites, or update-order conflicts. The safe implemented sequence is post-run market refresh plus display/reprice protection.

## Field mapping

### Games sheet — public projections

| Previous/public source | New preferred source | Backward-compatible fallback |
|---|---|---|
| `pred_home_runs` | `pred_home_runs_authoritative` | `pred_home_runs_cross_model_adj` → `pred_home_runs_dispersion_adj` → `pred_home_runs` |
| `pred_away_runs` | `pred_away_runs_authoritative` | `pred_away_runs_cross_model_adj` → `pred_away_runs_dispersion_adj` → `pred_away_runs` |
| `pred_total` | `pred_total_authoritative` | `pred_total_cross_model_adj` → `pred_total_dispersion_adj` → `pred_total` |
| `pred_margin` | `pred_margin_authoritative` | `pred_margin_cross_model_adj` → `pred_margin_dispersion_adj` → `pred_margin` |
| No source label | `authoritative_game_projection_source` | `legacy_fallback` |
| Existing F5 fields | `pred_home_f5`, `pred_away_f5`, `pred_f5_total` | Unchanged; full-game values are never substituted |

The margin remains home projected runs minus away projected runs.

### Games sheet — market fields

| Legacy/ambiguous field | New preferred field | Fallback/handling |
|---|---|---|
| `market_spread` / `marketSpread` | `away_spread` / `awaySpread` | Legacy field is retained only as away-team-perspective compatibility data |
| Inferred opposite spread | `home_spread` / `homeSpread` | May be derived as `-awaySpread` only for an older valid archive row lacking the explicit field |
| No spread price | `away_spread_odds`, `home_spread_odds` | No assumed `-110`; missing price remains non-actionable |
| `market_spread_raw_archive` | Audit-only `marketSpreadRawArchive` | Never used directly as the displayed selected team line |
| One total point without pair validation | `market_total`, `over_odds`, `under_odds` | Over/Under points must match or the total pair is invalid |
| Unclear perspective | `market_spread_perspective` | Public archive value is explicitly `away` |

### Recommendation routing

| Area | Preferred v86n fields | Fallback |
|---|---|---|
| Moneyline | `model_pick_team`, `model_pick_side`, `calibrated_model_pick_win_prob`, `prob_edge_vs_novig`, `expected_roi`, `bet_recommendation`, `bet_reason`, `model_pick_status`, `calibrated_probability_rejects_score_pick` | Legacy score/win-probability display only when final recommendation fields are absent |
| Total | `total_pick_side`, `total_pick_prob_est`, `total_edge_runs`, `selected_total_odds`, `total_market_implied_novig`, `total_expected_roi`, `total_final_recommendation`, `total_final_reason` | `total_bet_recommendation`, `total_bet_reason` |
| Spread | `spread_pick_side`, `selected_spread_line`, `spread_cover_prob_est`, `spread_edge_runs`, `selected_spread_odds`, `spread_market_implied_novig`, `spread_expected_roi`, `spread_final_recommendation`, `spread_final_reason` | `spread_bet_recommendation`, `spread_bet_reason` |
| Best market | `best_market`, `best_market_pick`, `best_market_score`, second-best/avoided fields and routing flags | Actionable only when the routed market itself passes all line, price, calibration, and reprice gates |

`HOME_SPREAD` always routes to the home team, home spread, and home spread odds. `AWAY_SPREAD` always routes to the away team, away spread, and away spread odds. The selected team is never inferred from the sign alone.

### Pitchers sheet

| Previous public field | New preferred field | Fallback |
|---|---|---|
| `pred_outs` | `pred_outs_authoritative` | `pred_outs` |
| `pred_k` | `pred_k_authoritative` | `pred_k` |
| `pred_bb` | `pred_bb_authoritative` | `pred_bb` |
| `pred_hits_allowed` | `pred_hits_allowed_authoritative` | `pred_hits_allowed` |
| `pred_er` | `pred_er_authoritative` | `pred_er_dispersion_adj` → `pred_er` |

The analyzer and game-detail output also retain the requested outs, strikeout, earned-run distribution, role, workload, and confidence fields.

### Batters sheet

No public batter field-name migration was made. Counts continue to use the final `pred_*` fields, hit probability continues to use `prob_hit` rather than `prob_hit_joint`, and lineup/handedness context remains exported.

## Sample transformed game JSON

```json
{
  "gamePk": 999001,
  "league": "MLB",
  "gameDate": "2026-06-17",
  "awayTeam": "LAD",
  "homeTeam": "COL",
  "modelAwayScore": 4.25,
  "modelHomeScore": 5.35,
  "modelTotal": 9.6,
  "modelHomeSpread": 1.1,
  "authoritativeGameProjectionSource": "v86n_authoritative_fixture",
  "predAwayF5": 2.1,
  "predHomeF5": 2.5,
  "predF5Total": 4.6,
  "awayML": 130.0,
  "homeML": -150.0,
  "awaySpread": 1.5,
  "homeSpread": -1.5,
  "awaySpreadOdds": -125.0,
  "homeSpreadOdds": 105.0,
  "spreadLinePairValid": true,
  "spreadPricePairValid": true,
  "marketTotal": 9.5,
  "overOdds": -108.0,
  "underOdds": -112.0,
  "totalLinePairValid": true,
  "totalPricePairValid": true,
  "marketLineStatus": "CURRENT",
  "marketLineAgeHours": 1.0,
  "modelPickTeam": "COL",
  "modelPickStatus": "ACCEPTED",
  "moneylineActionable": true,
  "spreadPickSide": "HOME_SPREAD",
  "modelSpreadPickLabel": "COL -1.5",
  "spreadFinalRecommendation": "BET",
  "spreadActionable": true,
  "totalPickSide": "OVER",
  "modelTotalPickLabel": "Over 9.5",
  "totalFinalRecommendation": "BET",
  "totalActionable": true,
  "bestMarket": "SPREAD",
  "bestMarketPick": "COL -1.5",
  "bestMarketActionable": true
}
```

## Sample transformed pitcher JSON

```json
{
  "player": "Home Starter",
  "team": "COL",
  "opponent": "LAD",
  "predOuts": 17.2,
  "predK": 6.4,
  "predBB": 1.8,
  "predHitsAllowed": 4.7,
  "predER": 2.15,
  "prob15PlusOuts": 0.74,
  "prob18PlusOuts": 0.48,
  "prob21PlusOuts": 0.19,
  "probKOver3p5": 0.82,
  "probKOver4p5": 0.71,
  "probKOver5p5": 0.58,
  "probKOver6p5": 0.44,
  "pitcherErProb01": 0.38,
  "pitcherErProb23": 0.44,
  "pitcherErProb4Plus": 0.18,
  "pitcherErRiskBucket": "LOW",
  "pitcherRoleType": "STARTER",
  "starterRoleScenario": "NORMAL",
  "starterRoleUncertaintyScore": 0.1,
  "starterRoleScenarioConfidence": 0.9,
  "workloadScenarioMeanOuts": 17.1,
  "roleExpectedOuts": 17.2,
  "roleOutsLeashCap": 20.5,
  "predictionConfidenceScore": 0.81,
  "predictionConfidenceTier": "HIGH"
}
```

## Dry-run comparison on the same synthetic v86n slate

The old and updated converters were run against the same one-game fixture containing deliberately conflicting legacy and authoritative values.

| Output | Original converter | Updated converter |
|---|---:|---:|
| Away projected runs | 2.00 (`pred_away_runs`) | 4.25 (`pred_away_runs_authoritative`) |
| Home projected runs | 3.00 (`pred_home_runs`) | 5.35 (`pred_home_runs_authoritative`) |
| Projected total | 5.00 (`pred_total`) | 9.60 (`pred_total_authoritative`) |
| Home-minus-away margin | 1.00 (`pred_margin`) | 1.10 (`pred_margin_authoritative`) |
| Home starter public ER | 3.40 (`pred_er`) | 2.15 (`pred_er_authoritative`) |
| Spread prices | Not exported | Away -125 / Home +105 |
| Total prices | Not exported | Over -108 / Under -112 |
| Final-market actionability | Not routed through v86n gates | Explicit per-market actionability and reprice gates |

Both copies of the MLB props-analyzer builder were also run against the workbook. Each produced 64 fixture entries and used the authoritative pitcher anchors: ER 2.15, K 6.4, and outs 17.2. The batter hit entry used `prob_hit = 0.73`, not the deliberately conflicting `prob_hit_joint = 0.91`.

## Required validation results

- `awaySpread` and `homeSpread` are exact opposites in valid rows.
- Spread point and price are selected from the same named team outcome and the same bookmaker snapshot.
- Over and Under prices are selected from the same bookmaker and accepted only when both outcomes share the same total point.
- A mismatched Over/Under point pair is flagged invalid and no total is silently assembled.
- Missing spread/total prices remain `PRICE_REQUIRED`; no `-110` is invented.
- `PRICE_REQUIRED` is never converted to `BET` or an actionable routed market.
- A score pick rejected by calibration is not displayed as a moneyline recommendation.
- `pred_er_authoritative` is used publicly, with the requested fallback chain.
- Authoritative game projections are used publicly, with the requested fallback chains.
- F5 projections remain independent full-game-unadjusted values.
- Batter output remains backward-compatible and uses `prob_hit` publicly.
- A newer archive snapshot is applied atomically. Changed lines/prices trigger `Reprice required` rather than reusing model-calculated expected value.
- The direct Excel workbook path and older CSV fallback path both remain supported.

## Results-history safety

The uploaded history files remained byte-for-byte unchanged during all conversion and analyzer dry runs:

| File | Bytes | SHA-256 before and after |
|---|---:|---|
| `results_history.json` | 480,420 | `44bff688ba36b36594aa83999317a4031f0cf47a7ee6f2912ffdb9a620ec19d4` |
| `mlb_prop_results_history.json` | 1,869,156 | `8e6a1e7a81da9debfad8552b6f29ff4b48083f29524227c344e324b7fe5530f4` |

No existing graded prediction, result identifier, daily/weekly/monthly record, or history schema was rewritten.

## Modified files

### Site/application code

- `assets/app.js`
- `assets/game.js`
- `assets/line_tracker.js`
- `assets/props_analyzer.js`
- `assets/props_lab.js`
- `game.html`
- `index.html`
- `line_tracker.html`
- `line_tracker.js` (legacy duplicate kept aligned)
- `props_analyzer.html`
- `results.html`

### Pipeline and market tools

- `tools/build_home_top_picks_json.py`
- `tools/build_mlb_site_json.py`
- `build_mlb_props_analyzer_json.py`
- `tools/build_mlb_props_analyzer_json.py`
- `tools/fetch_market_lines_the_odds_api.py`
- `tools/fetch_game_lines_the_odds_api.py`
- `tools/fetch_mlb_market_lines_the_odds_api.py`
- `tools/refresh_all_market_lines.py`
- `update_live_site_after_predictions.bat`

### Data/configuration

- `data/site.json` — title normalization only
- `data/site_features.json` — new active-season feature configuration

### Handoff documentation

- `V86N_SITE_UPDATE_REPORT.md`

## Files not available for inspection

These referenced production files were not in the uploaded archives and therefore were not changed or certified:

- `C:\python\mlb_model_outputs\mlb_predictions.xlsx`
- `mlb_multi_model_engine_fixed_v86n_lines_pitcher_dispersion_fix.py`
- The model-run/prefetch batch
- `C:\python\website_sync_v10_fixed.py` / `website_sync_v10.py`
- `C:\python\results_rollup_fixed.py`

The included code is ready to consume the production workbook at the expected path, but the first production run should still be reviewed for column spelling and live output counts because that workbook itself was not supplied.
