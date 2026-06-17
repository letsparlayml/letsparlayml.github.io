from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_WEBSITE_REPO = Path(r"C:\python\letsparlayml.github.io")
DEFAULT_MLB_OUTPUT_DIR = Path(r"C:\python\mlb_model_outputs")
DISPLAY_TIMEZONE = "America/Denver"




def normalize_team_token(value: Any) -> str:
    return ''.join(ch for ch in clean_str(value).upper() if ch.isalnum())


def parse_matchup(matchup: Any) -> tuple[str, str]:
    raw = clean_str(matchup)
    if not raw or '@' not in raw:
        return '', ''
    away, home = raw.split('@', 1)
    return clean_str(away), clean_str(home)


def market_matchup_key(game_date: str, away_team: Any, home_team: Any) -> str:
    return f"{clean_str(game_date)}|{normalize_team_token(away_team)}|{normalize_team_token(home_team)}"


def iso_timestamp(value: Any) -> str:
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return ''
    return ts.isoformat().replace('+00:00', 'Z')


def market_age_hours(value: Any) -> float | None:
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return None
    now = pd.Timestamp.now(tz='UTC')
    return max(0.0, float((now - ts).total_seconds() / 3600.0))


def choose_total_prob_fields(total_line: Any, row: pd.Series, *, allow_fallback: bool = True) -> tuple[str, float | None, float | None]:
    """Choose probabilities for the actual market total without mixing alt lines.

    The model output currently carries half-point total probabilities such as
    over_7p5_prob and over_8p5_prob. Those map cleanly to half-point market
    totals. For integer lines, the push outcome matters, so we only fill the
    side(s) that can be computed exactly from adjacent half-point probabilities:

    * Over 8.0 = P(total >= 9) = over_8p5_prob
    * Under 8.0 = P(total <= 7) = 1 - over_7p5_prob

    If the exact market total cannot be supported by the available fields, return
    the line label with None probabilities. Downstream cards can then use a
    model-vs-market derived lean instead of falsely labeling an 8.5 probability
    as an 8.0/9.0/etc. probability.
    """
    total = safe_float(total_line)
    over75 = safe_float(row.get('over_7p5_prob'))
    over85 = safe_float(row.get('over_8p5_prob'))

    if total is not None:
        label = f"Total {total:.1f}"
        if abs(total - 7.5) < 0.11:
            return f"Over {total:.1f}", over75, (1 - over75) if over75 is not None else None
        if abs(total - 8.5) < 0.11:
            return f"Over {total:.1f}", over85, (1 - over85) if over85 is not None else None
        if abs(total - 7.0) < 0.11:
            return label, over75, None
        if abs(total - 8.0) < 0.11:
            under = (1 - over75) if over75 is not None else None
            return label, over85, under
        if abs(total - 9.0) < 0.11:
            under = (1 - over85) if over85 is not None else None
            return label, None, under
        return label, None, None

    if allow_fallback:
        if over85 is not None:
            return 'Over 8.5', over85, 1 - over85
        if over75 is not None:
            return 'Over 7.5', over75, 1 - over75
    return '', None, None


def choose_win_team_and_prob(row: pd.Series) -> tuple[str, float | None]:
    home_team = clean_str(row.get('home_team'))
    away_team = clean_str(row.get('away_team'))
    home_win = safe_float(row.get('home_win_prob'))
    away_win = safe_float(row.get('away_win_prob'))
    favorite_team = clean_str(row.get('favorite_team'))
    if favorite_team:
        if favorite_team == home_team:
            return favorite_team, home_win
        if favorite_team == away_team:
            return favorite_team, away_win
    if (home_win or 0) >= (away_win or 0):
        return home_team, home_win
    return away_team, away_win


def choose_market_runline_pick(row: pd.Series, market_spread: float | None) -> tuple[str, float | None, str]:
    """Return the model's preferred side of the actual market run line.

    marketSpread is stored from the away-team perspective:
      +1.5 means away +1.5 / home -1.5
      -1.5 means away -1.5 / home +1.5

    The card should not blindly show the favorite. It should show whichever side
    the model makes more likely against the actual line.
    """
    home = clean_str(row.get('home_team'))
    away = clean_str(row.get('away_team'))
    if market_spread is not None and abs(abs(market_spread) - 1.5) < 0.11:
        if market_spread > 0:
            # Away is +1.5, home is -1.5. Pick the more likely side.
            candidates = [
                (safe_float(row.get('home_minus1p5_prob')), f"{home} -1.5", home),
                (safe_float(row.get('away_plus1p5_prob')), f"{away} +1.5", away),
            ]
        else:
            # Away is -1.5, home is +1.5. Pick the more likely side.
            candidates = [
                (safe_float(row.get('away_minus1p5_prob')), f"{away} -1.5", away),
                (safe_float(row.get('home_plus1p5_prob')), f"{home} +1.5", home),
            ]
        candidates = [c for c in candidates if c[0] is not None]
        if candidates:
            prob, label, team = max(candidates, key=lambda x: x[0])
            return label, prob, team

    favorite_team, _ = choose_win_team_and_prob(row)
    if favorite_team == home:
        fav_prob = safe_float(row.get('home_minus1p5_prob'))
        dog_prob = safe_float(row.get('away_plus1p5_prob'))
        candidates = [(fav_prob, f"{home} -1.5", home), (dog_prob, f"{away} +1.5", away)]
    elif favorite_team == away:
        fav_prob = safe_float(row.get('away_minus1p5_prob'))
        dog_prob = safe_float(row.get('home_plus1p5_prob'))
        candidates = [(fav_prob, f"{away} -1.5", away), (dog_prob, f"{home} +1.5", home)]
    else:
        candidates = []
    candidates = [c for c in candidates if c[0] is not None]
    if candidates:
        prob, label, team = max(candidates, key=lambda x: x[0])
        return label, prob, team
    return '', None, ''


def choose_market_total_pick(total_line: Any, row: pd.Series) -> tuple[str, float | None]:
    total_label, over_prob, under_prob = choose_total_prob_fields(total_line, row, allow_fallback=False)
    total = safe_float(total_line)
    if total is not None and (over_prob is not None or under_prob is not None):
        if (over_prob or 0) >= (under_prob or 0):
            return f"Over {total:.1f}", over_prob
        return f"Under {total:.1f}", under_prob
    fallback_label, fallback_over, fallback_under = choose_total_prob_fields(None, row, allow_fallback=True)
    if fallback_label and (fallback_over is not None or fallback_under is not None):
        line_match = re.search(r"(\d+(?:\.\d+)?)", fallback_label)
        line = line_match.group(1) if line_match else fallback_label.replace('Over ', '')
        if (fallback_over or 0) >= (fallback_under or 0):
            return f"Over {line}", fallback_over
        return f"Under {line}", fallback_under
    return '', None


def derive_market_context(row: pd.Series, market_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    market_entry = market_entry or {}
    home_team = clean_str(row.get('home_team'))
    away_team = clean_str(row.get('away_team'))

    model_market_updated_at = first_text(row, ['market_updated_at'])
    archive_market_captured_at = first_text(market_entry, ['capturedAt', 'fetchedAtUtc', 'archivedAt'])
    archive_book_updated_at = first_text(market_entry, ['updatedAt'])
    archive_market_updated_at = archive_market_captured_at or archive_book_updated_at or first_text(market_entry, ['__file_updated'])
    model_market_ts = pd.to_datetime(model_market_updated_at, errors='coerce', utc=True)
    archive_market_ts = pd.to_datetime(archive_market_updated_at, errors='coerce', utc=True)
    use_archive_snapshot = bool(market_entry) and (
        pd.isna(model_market_ts) or (not pd.isna(archive_market_ts) and archive_market_ts > model_market_ts)
    )

    def n(row_fields: list[str], market_fields: list[str]) -> float | None:
        # A bookmaker snapshot is atomic: when the post-run archive is newer,
        # do not fill missing point/price fields from the older model snapshot.
        if use_archive_snapshot:
            return first_number(market_entry, market_fields)
        value = first_number(row, row_fields)
        return value if value is not None else first_number(market_entry, market_fields)

    def t(row_fields: list[str], market_fields: list[str]) -> str:
        if use_archive_snapshot:
            return first_text(market_entry, market_fields)
        value = first_text(row, row_fields)
        return value or first_text(market_entry, market_fields)

    away_ml = n(['away_ml'], ['awayML', 'awayMoneyline', 'marketAwayML'])
    home_ml = n(['home_ml'], ['homeML', 'homeMoneyline', 'marketHomeML'])

    # The workbook's raw archive spread is an audit value from the away-team
    # perspective. Explicit away/home lines are the only public display fields.
    model_market_spread_raw_archive = first_number(row, ['market_spread_raw_archive'])
    current_market_spread_raw_archive = first_number(market_entry, ['marketSpread', 'awaySpread']) if use_archive_snapshot else model_market_spread_raw_archive
    market_spread_raw_archive = current_market_spread_raw_archive if current_market_spread_raw_archive is not None else model_market_spread_raw_archive
    away_spread = n(['away_spread'], ['awaySpread'])
    home_spread = n(['home_spread'], ['homeSpread'])
    if away_spread is None and home_spread is not None:
        away_spread = -home_spread
    if home_spread is None and away_spread is not None:
        home_spread = -away_spread
    if away_spread is None and market_spread_raw_archive is not None:
        away_spread = market_spread_raw_archive
        home_spread = -market_spread_raw_archive

    away_spread_odds = n(['away_spread_odds'], ['awaySpreadOdds', 'awaySpreadPrice'])
    home_spread_odds = n(['home_spread_odds'], ['homeSpreadOdds', 'homeSpreadPrice'])
    market_total = n(['market_total'], ['marketTotal'])
    over_odds = n(['over_odds'], ['overOdds', 'overPrice'])
    under_odds = n(['under_odds'], ['underOdds', 'underPrice'])

    if use_archive_snapshot:
        line_pair_valid = first_boolish(market_entry, ['spreadLinePairValid'])
        spread_price_pair_valid = first_boolish(market_entry, ['spreadPricePairValid'])
        total_line_pair_valid = first_boolish(market_entry, ['totalLinePairValid'])
        total_price_pair_valid = first_boolish(market_entry, ['totalPricePairValid'])
    else:
        line_pair_valid = first_boolish(row, ['spread_line_pair_valid'])
        if line_pair_valid is None:
            line_pair_valid = first_boolish(market_entry, ['spreadLinePairValid'])
        spread_price_pair_valid = first_boolish(row, ['spread_price_pair_valid'])
        if spread_price_pair_valid is None:
            spread_price_pair_valid = first_boolish(market_entry, ['spreadPricePairValid'])
        total_line_pair_valid = first_boolish(row, ['total_line_pair_valid'])
        if total_line_pair_valid is None:
            total_line_pair_valid = first_boolish(market_entry, ['totalLinePairValid'])
        total_price_pair_valid = first_boolish(row, ['total_price_pair_valid'])
        if total_price_pair_valid is None:
            total_price_pair_valid = first_boolish(market_entry, ['totalPricePairValid'])
    if line_pair_valid is None:
        line_pair_valid = away_spread is not None and home_spread is not None and abs(away_spread + home_spread) < 0.001
    if spread_price_pair_valid is None:
        spread_price_pair_valid = bool(line_pair_valid and away_spread_odds is not None and home_spread_odds is not None)
    if total_line_pair_valid is None:
        total_line_pair_valid = market_total is not None
    if total_price_pair_valid is None:
        total_price_pair_valid = bool(total_line_pair_valid and market_total is not None and over_odds is not None and under_odds is not None)

    # Invalid spread pairs remain available only through audit fields. They are
    # deliberately removed from public line/recommendation fields.
    display_away_spread = away_spread if line_pair_valid else None
    display_home_spread = home_spread if line_pair_valid else None

    market_source = t(['market_source'], ['source'])
    market_updated_at = archive_market_updated_at if use_archive_snapshot else (model_market_updated_at or archive_market_updated_at)
    market_line_age_hours = n(['market_line_age_hours'], ['marketLineAgeHours'])
    if market_line_age_hours is None:
        market_line_age_hours = market_age_hours(market_updated_at)
    market_line_status = t(['market_line_status'], ['marketLineStatus'])
    if not market_line_status:
        if market_line_age_hours is None:
            market_line_status = 'UNKNOWN'
        elif market_line_age_hours > 6.0:
            market_line_status = 'STALE'
        else:
            market_line_status = 'CURRENT'
    market_price_status = t(['market_price_status'], ['marketPriceStatus'])
    if not market_price_status:
        if spread_price_pair_valid and total_price_pair_valid and away_ml is not None and home_ml is not None:
            market_price_status = 'COMPLETE'
        elif (away_spread is not None or market_total is not None) and not (spread_price_pair_valid or total_price_pair_valid):
            market_price_status = 'PRICE_REQUIRED'
        else:
            market_price_status = 'PARTIAL'

    # Moneyline recommendation/calibration fields.
    model_pick_team = first_text(row, ['model_pick_team'])
    model_pick_side = first_text(row, ['model_pick_side'])
    model_pick_prob = first_number(row, ['calibrated_model_pick_win_prob'])
    bet_recommendation = first_text(row, ['bet_recommendation'])
    bet_reason = first_text(row, ['bet_reason'])
    model_pick_status = first_text(row, ['model_pick_status'])
    calibration_rejects = first_boolish(row, ['calibrated_probability_rejects_score_pick']) is True or model_pick_status.upper() == 'SCORE_PICK_REJECTED_BY_CALIBRATION'
    if not model_pick_team:
        model_pick_team, legacy_prob = choose_win_team_and_prob(row)
        if model_pick_prob is None:
            model_pick_prob = legacy_prob
    model_away_ml = first_number(row, ['away_ml'])
    model_home_ml = first_number(row, ['home_ml'])
    model_pick_current_odds = home_ml if model_pick_team == home_team else away_ml if model_pick_team == away_team else None
    model_pick_original_odds = model_home_ml if model_pick_team == home_team else model_away_ml if model_pick_team == away_team else None
    moneyline_reprice_required = bool(use_archive_snapshot and model_pick_original_odds is not None and (
        model_pick_current_odds is None or abs(model_pick_original_odds - model_pick_current_odds) > 0.001
    ))
    moneyline_actionable = bool(model_pick_team and model_pick_current_odds is not None and not calibration_rejects and recommendation_is_actionable(bet_recommendation) and not moneyline_reprice_required)

    # Spread final recommendation. Side determines team; never infer it from sign.
    spread_side = first_text(row, ['spread_pick_side'])
    selected_spread_line = first_number(row, ['selected_spread_line'])
    spread_prob = first_number(row, ['spread_cover_prob_est'])
    spread_final_rec = first_text(row, ['spread_final_recommendation', 'spread_bet_recommendation'])
    spread_final_reason = first_text(row, ['spread_final_reason', 'spread_bet_reason'])
    spread_team = ''
    spread_label = ''
    spread_odds = first_number(row, ['selected_spread_odds'])
    if spread_side.upper() == 'HOME_SPREAD':
        spread_team = home_team
        selected_spread_line = display_home_spread if selected_spread_line is None else selected_spread_line
        spread_odds = home_spread_odds if spread_odds is None else spread_odds
    elif spread_side.upper() == 'AWAY_SPREAD':
        spread_team = away_team
        selected_spread_line = display_away_spread if selected_spread_line is None else selected_spread_line
        spread_odds = away_spread_odds if spread_odds is None else spread_odds
    current_side_odds = home_spread_odds if spread_side.upper() == 'HOME_SPREAD' else away_spread_odds if spread_side.upper() == 'AWAY_SPREAD' else None
    if spread_team and selected_spread_line is not None:
        spread_label = f'{spread_team} {selected_spread_line:+.1f}'
    model_away_spread = first_number(row, ['away_spread'])
    model_home_spread = first_number(row, ['home_spread'])
    model_away_spread_odds = first_number(row, ['away_spread_odds'])
    model_home_spread_odds = first_number(row, ['home_spread_odds'])
    current_side_line = display_home_spread if spread_side.upper() == 'HOME_SPREAD' else display_away_spread if spread_side.upper() == 'AWAY_SPREAD' else None
    model_side_line = model_home_spread if spread_side.upper() == 'HOME_SPREAD' else model_away_spread if spread_side.upper() == 'AWAY_SPREAD' else None
    model_side_odds = model_home_spread_odds if spread_side.upper() == 'HOME_SPREAD' else model_away_spread_odds if spread_side.upper() == 'AWAY_SPREAD' else None
    model_selected_spread_odds = first_number(row, ['selected_spread_odds'])
    comparison_spread_odds = model_selected_spread_odds if model_selected_spread_odds is not None else model_side_odds
    spread_reprice_required = bool(use_archive_snapshot and (
        (model_side_line is not None and current_side_line is not None and abs(model_side_line - current_side_line) > 0.001)
        or (comparison_spread_odds is not None and current_side_odds is not None and abs(comparison_spread_odds - current_side_odds) > 0.001)
        or (model_side_line is not None and current_side_line is None)
        or (comparison_spread_odds is not None and current_side_odds is None)
    ))
    actionable_spread_odds = current_side_odds if use_archive_snapshot else spread_odds
    spread_actionable = bool(line_pair_valid and spread_label and recommendation_is_actionable(spread_final_rec) and actionable_spread_odds is not None and not spread_reprice_required)

    # Total final recommendation.
    total_side = first_text(row, ['total_pick_side'])
    total_prob = first_number(row, ['total_pick_prob_est'])
    selected_total_odds = first_number(row, ['selected_total_odds'])
    if selected_total_odds is None:
        selected_total_odds = over_odds if total_side.upper() == 'OVER' else under_odds if total_side.upper() == 'UNDER' else None
    total_final_rec = first_text(row, ['total_final_recommendation', 'total_bet_recommendation'])
    total_final_reason = first_text(row, ['total_final_reason', 'total_bet_reason'])
    total_label = f'{total_side.title()} {market_total:.1f}' if total_side.upper() in {'OVER', 'UNDER'} and market_total is not None else ''
    model_market_total = first_number(row, ['market_total'])
    model_selected_total_odds = first_number(row, ['selected_total_odds'])
    current_selected_total_odds = over_odds if total_side.upper() == 'OVER' else under_odds if total_side.upper() == 'UNDER' else None
    total_reprice_required = bool(use_archive_snapshot and (
        (model_market_total is not None and market_total is not None and abs(model_market_total - market_total) > 0.001)
        or (model_selected_total_odds is not None and current_selected_total_odds is not None and abs(model_selected_total_odds - current_selected_total_odds) > 0.001)
        or (model_market_total is not None and market_total is None)
        or (model_selected_total_odds is not None and current_selected_total_odds is None)
    ))
    actionable_total_odds = current_selected_total_odds if use_archive_snapshot else selected_total_odds
    total_actionable = bool(total_label and recommendation_is_actionable(total_final_rec) and actionable_total_odds is not None and total_price_pair_valid and not total_reprice_required)

    # Legacy probability/display fallback only when v86n final fields are absent.
    if not spread_label and line_pair_valid:
        spread_label, spread_prob, spread_team = choose_market_runline_pick(row, display_away_spread)
    if not total_label:
        total_label, total_prob = choose_market_total_pick(market_total, row)
    total_market_label, market_over_prob, market_under_prob = choose_total_prob_fields(market_total, row, allow_fallback=False)
    fallback_total_label, fallback_over_prob, fallback_under_prob = choose_total_prob_fields(None, row, allow_fallback=True)

    favorite_team, favorite_win_prob = choose_win_team_and_prob(row)
    best_market = first_text(row, ['best_market']).upper()
    routed_market_actionable = {
        'MONEYLINE': moneyline_actionable,
        'ML': moneyline_actionable,
        'SPREAD': spread_actionable,
        'TOTAL': total_actionable,
    }.get(best_market, False)
    routing_price_required = first_boolish(row, ['market_routing_price_required']) is True
    best_market_actionable = bool(routed_market_actionable and not routing_price_required and not (moneyline_reprice_required or spread_reprice_required or total_reprice_required))
    return {
        'favoriteTeam': favorite_team,
        'favoriteWinLabel': f'{favorite_team} win' if favorite_team else 'Favorite win',
        'favoriteWinProb': favorite_win_prob,
        'modelMoneylineLabel': f'{model_pick_team} ML' if model_pick_team and not calibration_rejects else '',
        'modelMoneylineProb': model_pick_prob,
        'moneylineActionable': moneyline_actionable,
        'moneylineRepriceRequired': moneyline_reprice_required,
        'modelPickTeam': model_pick_team, 'modelPickSide': model_pick_side,
        'calibratedModelPickWinProb': model_pick_prob,
        'probEdgeVsNovig': first_number(row, ['prob_edge_vs_novig']),
        'expectedRoi': first_number(row, ['expected_roi']),
        'betRecommendation': bet_recommendation, 'betReason': bet_reason,
        'modelPickStatus': model_pick_status,
        'calibratedProbabilityRejectsScorePick': calibration_rejects,
        'marketSpread': display_away_spread, 'marketSpreadPerspective': 'away',
        'marketSpreadRawArchive': market_spread_raw_archive,
        'awaySpread': display_away_spread, 'homeSpread': display_home_spread,
        'awaySpreadOdds': away_spread_odds, 'homeSpreadOdds': home_spread_odds,
        'spreadLinePairValid': bool(line_pair_valid), 'spreadPricePairValid': bool(spread_price_pair_valid),
        'spreadRepriceRequired': spread_reprice_required,
        'spreadLineStatus': first_text(row, ['spread_line_status']),
        'modelSpreadPickLabel': spread_label, 'modelSpreadPickProb': spread_prob, 'modelSpreadPickTeam': spread_team,
        'spreadPickSide': spread_side, 'selectedSpreadLine': selected_spread_line,
        'spreadCoverProbEst': spread_prob, 'spreadEdgeRuns': first_number(row, ['spread_edge_runs']),
        'selectedSpreadOdds': spread_odds, 'currentSelectedSpreadOdds': current_side_odds, 'spreadMarketImpliedNovig': first_number(row, ['spread_market_implied_novig']),
        'spreadExpectedRoi': first_number(row, ['spread_expected_roi']),
        'spreadFinalRecommendation': spread_final_rec, 'spreadFinalReason': spread_final_reason,
        'spreadActionable': spread_actionable,
        'marketTotal': market_total, 'overOdds': over_odds, 'underOdds': under_odds,
        'totalLinePairValid': bool(total_line_pair_valid), 'totalPricePairValid': bool(total_price_pair_valid),
        'totalRepriceRequired': total_reprice_required,
        'modelTotalPickLabel': total_label, 'modelTotalPickProb': total_prob,
        'totalPickSide': total_side, 'totalPickProbEst': total_prob,
        'totalEdgeRuns': first_number(row, ['total_edge_runs']), 'selectedTotalOdds': selected_total_odds, 'currentSelectedTotalOdds': current_selected_total_odds,
        'totalMarketImpliedNovig': first_number(row, ['total_market_implied_novig']),
        'totalExpectedRoi': first_number(row, ['total_expected_roi']),
        'totalFinalRecommendation': total_final_rec, 'totalFinalReason': total_final_reason,
        'totalActionable': total_actionable,
        'marketTotalLabel': total_market_label, 'marketOverProb': market_over_prob, 'marketUnderProb': market_under_prob,
        'fallbackTotalLabel': fallback_total_label, 'fallbackOverProb': fallback_over_prob, 'fallbackUnderProb': fallback_under_prob,
        'awayML': away_ml, 'homeML': home_ml,
        'awayMoneyline': away_ml, 'homeMoneyline': home_ml,
        'marketAwayML': away_ml, 'marketHomeML': home_ml,
        'marketLineSource': market_source, 'marketSource': market_source, 'marketLineUpdated': market_updated_at,
        'marketUpdatedAt': market_updated_at, 'marketCapturedAt': archive_market_captured_at, 'modelMarketUpdatedAt': model_market_updated_at,
        'marketSnapshotSource': 'post_run_archive' if use_archive_snapshot else 'model_workbook',
        'marketSnapshotMismatch': bool(moneyline_reprice_required or spread_reprice_required or total_reprice_required),
        'marketLineAgeHours': market_line_age_hours,
        'marketLineStatus': market_line_status, 'marketPriceStatus': market_price_status,
        'bookmakerKey': first_text(market_entry, ['bookmakerKey']) if use_archive_snapshot else first_text(row, ['bookmaker_key', 'bookmakerKey']),
        'bookmakerTitle': first_text(market_entry, ['bookmakerTitle']) if use_archive_snapshot else first_text(row, ['bookmaker_title', 'bookmakerTitle']),
        'eventId': first_text(market_entry, ['eventId', 'event_id']) if use_archive_snapshot else first_text(row, ['event_id', 'eventId']),
        'bestMarket': first_text(row, ['best_market']), 'bestMarketPick': first_text(row, ['best_market_pick']),
        'bestMarketScore': first_number(row, ['best_market_score']),
        'secondBestMarket': first_text(row, ['second_best_market']), 'secondBestMarketPick': first_text(row, ['second_best_market_pick']),
        'secondBestMarketScore': first_number(row, ['second_best_market_score']),
        'avoidedMarket': first_text(row, ['avoided_market']), 'marketRoutingReason': first_text(row, ['market_routing_reason']),
        'marketRoutingPriceRequired': routing_price_required,
        'marketRoutingCorrelationWarning': first_boolish(row, ['market_routing_correlation_warning']) is True,
        'bestMarketActionable': best_market_actionable,
    }

def load_market_entries_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.suffix.lower() == '.json':
            raw = load_json(path, [])
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            if isinstance(raw, dict):
                for key in ('items', 'rows', 'entries', 'data'):
                    val = raw.get(key)
                    if isinstance(val, list):
                        return [x for x in val if isinstance(x, dict)]
                return []
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(path)
            return df.to_dict(orient='records')
    except Exception:
        return []
    return []


def load_mlb_market_lines(repo: Path, mlb_output_dir: Path) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], int]:
    candidates = [
        # Dedicated append-only captures are preferred. Legacy rollup scripts may
        # rebuild market_lines_archive.json, but they do not own this file.
        repo / 'data' / 'market_line_snapshots.json',
        repo / 'data' / 'market_lines_archive.json',
        repo / 'data' / 'mlb_market_lines.json',
        repo / 'data' / 'mlb_market_lines.csv',
        mlb_output_dir / 'market_lines_archive.json',
        mlb_output_dir / 'mlb_market_lines.json',
        mlb_output_dir / 'mlb_market_lines.csv',
    ]

    by_pk: dict[int, dict[str, Any]] = {}
    by_matchup: dict[str, dict[str, Any]] = {}
    parsed = 0

    for path in candidates:
        if not path.exists():
            continue
        file_updated = iso_timestamp(path.stat().st_mtime)
        for entry in load_market_entries_from_path(path):
            league = clean_str(entry.get('league'))
            if league and league.upper() != 'MLB':
                continue
            away_team = clean_str(entry.get('awayTeam'))
            home_team = clean_str(entry.get('homeTeam'))
            if (not away_team or not home_team) and clean_str(entry.get('matchup')):
                away_team, home_team = parse_matchup(entry.get('matchup'))
            game_date = clean_str(entry.get('date')) or local_date(entry.get('gameDate')) or iso_date(entry.get('gameDate'))
            game_pk = safe_int(entry.get('gamePk'))
            market_spread = safe_float(entry.get('marketSpread') if entry.get('marketSpread') is not None else entry.get('spread'))
            market_total = safe_float(entry.get('marketTotal') if entry.get('marketTotal') is not None else entry.get('total'))
            market_away_ml = safe_float(entry.get('marketAwayML') if entry.get('marketAwayML') is not None else (entry.get('awayML') if entry.get('awayML') is not None else entry.get('awayMoneyline')))
            market_home_ml = safe_float(entry.get('marketHomeML') if entry.get('marketHomeML') is not None else (entry.get('homeML') if entry.get('homeML') is not None else entry.get('homeMoneyline')))
            if not away_team or not home_team or not game_date:
                continue
            if market_spread is None and market_total is None and market_away_ml is None and market_home_ml is None:
                continue
            parsed += 1
            away_spread = safe_float(entry.get('awaySpread') if entry.get('awaySpread') is not None else market_spread)
            home_spread = safe_float(entry.get('homeSpread'))
            if home_spread is None and away_spread is not None:
                home_spread = -away_spread
            normalized = {
                'gamePk': game_pk, 'eventId': clean_str(entry.get('eventId')),
                'date': game_date, 'gameDate': clean_str(entry.get('gameDate')),
                'awayTeam': away_team, 'homeTeam': home_team,
                'marketSpread': away_spread, 'marketSpreadPerspective': clean_str(entry.get('marketSpreadPerspective')) or 'away',
                'awaySpread': away_spread, 'homeSpread': home_spread,
                'awaySpreadOdds': safe_float(entry.get('awaySpreadOdds') if entry.get('awaySpreadOdds') is not None else entry.get('awaySpreadPrice')),
                'homeSpreadOdds': safe_float(entry.get('homeSpreadOdds') if entry.get('homeSpreadOdds') is not None else entry.get('homeSpreadPrice')),
                'spreadLinePairValid': entry.get('spreadLinePairValid'),
                'spreadPricePairValid': entry.get('spreadPricePairValid'),
                'marketTotal': market_total,
                'overOdds': safe_float(entry.get('overOdds') if entry.get('overOdds') is not None else entry.get('overPrice')),
                'underOdds': safe_float(entry.get('underOdds') if entry.get('underOdds') is not None else entry.get('underPrice')),
                'totalLinePairValid': entry.get('totalLinePairValid'),
                'totalPricePairValid': entry.get('totalPricePairValid'),
                'marketPriceStatus': clean_str(entry.get('marketPriceStatus')),
                'marketAwayML': market_away_ml, 'marketHomeML': market_home_ml,
                'awayML': market_away_ml, 'homeML': market_home_ml,
                'awayMoneyline': market_away_ml, 'homeMoneyline': market_home_ml,
                'bookmakerKey': clean_str(entry.get('bookmakerKey')), 'bookmakerTitle': clean_str(entry.get('bookmakerTitle')),
                'source': clean_str(entry.get('source')) or path.name,
                'updatedAt': clean_str(entry.get('updatedAt')) or file_updated,
                'capturedAt': clean_str(entry.get('capturedAt') or entry.get('fetchedAtUtc') or entry.get('archivedAt')),
                '__rank': (clean_str(entry.get('capturedAt') or entry.get('fetchedAtUtc') or entry.get('archivedAt') or entry.get('updatedAt')) or file_updated, str(path)),
                '__file_updated': file_updated,
            }
            if game_pk is not None:
                existing = by_pk.get(game_pk)
                if not existing or normalized['__rank'] >= existing.get('__rank', ('', '')):
                    by_pk[game_pk] = normalized
            matchup_key = market_matchup_key(game_date, away_team, home_team)
            existing = by_matchup.get(matchup_key)
            if not existing or normalized['__rank'] >= existing.get('__rank', ('', '')):
                by_matchup[matchup_key] = normalized

    for mapping in (by_pk, by_matchup):
        for item in mapping.values():
            item.pop('__rank', None)
    return by_pk, by_matchup, parsed

def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def safe_float(value: Any):
    try:
        if pd.isna(value):
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None



def first_number(row: Any, candidates: list[str]) -> float | None:
    for name in candidates:
        try:
            value = row.get(name)
        except Exception:
            value = None
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    return None


def first_text(row: Any, candidates: list[str]) -> str:
    for name in candidates:
        try:
            value = row.get(name)
        except Exception:
            value = None
        text = clean_str(value)
        if text:
            return text
    return ''


def first_boolish(row: Any, candidates: list[str]) -> bool | None:
    for name in candidates:
        try:
            value = row.get(name)
        except Exception:
            value = None
        if value in (None, ''):
            continue
        if isinstance(value, bool):
            return value
        text = str(value).strip().upper()
        if text in {'1', 'TRUE', 'YES', 'Y', 'VALID'}:
            return True
        if text in {'0', 'FALSE', 'NO', 'N', 'INVALID'}:
            return False
    return None


def game_projection_values(row: pd.Series) -> dict[str, Any]:
    home = first_number(row, ['pred_home_runs_authoritative', 'pred_home_runs_cross_model_adj', 'pred_home_runs_dispersion_adj', 'pred_home_runs'])
    away = first_number(row, ['pred_away_runs_authoritative', 'pred_away_runs_cross_model_adj', 'pred_away_runs_dispersion_adj', 'pred_away_runs'])
    total = first_number(row, ['pred_total_authoritative', 'pred_total_cross_model_adj', 'pred_total_dispersion_adj', 'pred_total'])
    margin = first_number(row, ['pred_margin_authoritative', 'pred_margin_cross_model_adj', 'pred_margin_dispersion_adj', 'pred_margin'])
    if margin is None and home is not None and away is not None:
        margin = home - away
    if total is None and home is not None and away is not None:
        total = home + away
    return {
        'home': home, 'away': away, 'total': total, 'margin': margin,
        'source': first_text(row, ['authoritative_game_projection_source']) or 'legacy_fallback',
    }


def pitcher_projection_value(row: pd.Series, stat: str) -> float | None:
    mapping = {
        'outs': ['pred_outs_authoritative', 'pred_outs'],
        'k': ['pred_k_authoritative', 'pred_k'],
        'bb': ['pred_bb_authoritative', 'pred_bb'],
        'hits_allowed': ['pred_hits_allowed_authoritative', 'pred_hits_allowed'],
        'er': ['pred_er_authoritative', 'pred_er_dispersion_adj', 'pred_er'],
    }
    return first_number(row, mapping[stat])


def recommendation_is_price_required(value: Any) -> bool:
    return 'PRICE_REQUIRED' in clean_str(value).upper()


def recommendation_is_actionable(value: Any) -> bool:
    text = clean_str(value).upper().replace(' ', '_')
    if not text or 'PRICE_REQUIRED' in text or 'NO_BET' in text or text in {'PASS', 'AVOID'}:
        return False
    return text == 'BET' or text.startswith('BET_') or text.endswith('_BET')

def safe_int(value: Any):
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except Exception:
        return None


def iso_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return ""
    return ts.date().isoformat()


def local_date(value: Any, tz_name: str = DISPLAY_TIMEZONE) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return ""
    if getattr(ts, "tzinfo", None) is None:
        return ts.date().isoformat()
    return ts.tz_convert(tz_name).date().isoformat()


def game_display_date(row: pd.Series, tz_name: str = DISPLAY_TIMEZONE) -> str:
    # gameDate_mlb_local is the model's authoritative MLB-local calendar date.
    # Keep gameDate only as the UTC start timestamp; using its UTC calendar date
    # for slate grouping moves late evening games into the following day.
    for field in ('gameDate_mlb_local', 'target_game_date'):
        value = row.get(field)
        ts = pd.to_datetime(value, errors="coerce")
        if not pd.isna(ts):
            return ts.date().isoformat()

    # Backward-compatible fallback for older workbooks that predate the explicit
    # MLB-local date columns. Timezone-aware timestamps are converted to Denver;
    # naive values preserve their written calendar date.
    game_dt = local_date(row.get('gameDate'), tz_name)
    if game_dt:
        return game_dt
    return iso_date(row.get('gameDate'))

def iso_datetime_utc(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return ""
    return ts.isoformat().replace('+00:00', 'Z')


def pct_text(prob: Any) -> str:
    val = safe_float(prob)
    if val is None:
        return ""
    return f"{round(val * 100):.0f}%"


def confidence_label(prob_values: list[float | None]) -> str:
    vals = [v for v in prob_values if isinstance(v, (int, float))]
    if not vals:
        return "Low"
    peak = max(vals)
    if peak >= 0.72:
        return "High"
    if peak >= 0.60:
        return "Medium"
    return "Low"


def market_line_from_market_name(name: str):
    raw = clean_str(name).lower()
    if raw == 'hit':
        return 0.5
    if raw == 'hr':
        return 0.5
    if raw == '2+ total bases':
        return 1.5
    if '1.5' in raw:
        return 1.5
    return None


def market_stat_display(name: str) -> str:
    raw = clean_str(name)
    lowered = raw.lower()
    if lowered == 'hit':
        return 'Hits'
    if lowered == 'hr':
        return 'HR'
    if lowered == '2+ total bases':
        return '2+ Total Bases'
    if lowered == 'hrr over 1.5':
        return 'HRR'
    return raw


def prop_confidence(prob: float | None) -> str:
    if prob is None:
        return 'Low'
    if prob >= 0.78:
        return 'High'
    if prob >= 0.66:
        return 'Medium'
    return 'Low'


def build_summary(row: pd.Series, context: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    home = clean_str(row.get('home_team'))
    away = clean_str(row.get('away_team'))
    home_win = safe_float(row.get('home_win_prob'))
    away_win = safe_float(row.get('away_win_prob'))
    nrfi = safe_float(row.get('nrfi_prob'))
    context = context or {}

    if nrfi is not None:
        parts.append(f"NRFI {pct_text(nrfi)}")

    if home_win is not None or away_win is not None:
        if (home_win or 0) >= (away_win or 0):
            parts.append(f"{home} win {pct_text(home_win)}")
        else:
            parts.append(f"{away} win {pct_text(away_win)}")

    spread_pick_label = clean_str(context.get('modelSpreadPickLabel'))
    spread_pick_prob = safe_float(context.get('modelSpreadPickProb'))
    spread_final_rec = clean_str(context.get('spreadFinalRecommendation'))
    spread_can_show = context.get('spreadActionable') is True or not spread_final_rec
    if spread_pick_label and spread_pick_prob is not None and spread_can_show:
        parts.append(f"{spread_pick_label} {pct_text(spread_pick_prob)}")
    else:
        market_cover_label = clean_str(context.get('marketCoverLabel'))
        market_cover_prob = safe_float(context.get('marketCoverProb'))
        if market_cover_label and market_cover_prob is not None:
            parts.append(f"{market_cover_label} {pct_text(market_cover_prob)}")

    total_pick_label = clean_str(context.get('modelTotalPickLabel'))
    total_pick_prob = safe_float(context.get('modelTotalPickProb'))
    total_final_rec = clean_str(context.get('totalFinalRecommendation'))
    total_can_show = context.get('totalActionable') is True or not total_final_rec
    if total_pick_label and total_pick_prob is not None and total_can_show:
        parts.append(f"{total_pick_label} {pct_text(total_pick_prob)}")

    return ' • '.join(parts[:4]) or 'MLB model preview'



def game_identity_key(row: pd.Series) -> str:
    game_pk = safe_int(row.get('gamePk'))
    if game_pk is not None:
        return f"gamepk|{game_pk}"
    target_date = game_display_date(row)
    away = clean_str(row.get('away_team')).upper()
    home = clean_str(row.get('home_team')).upper()
    game_time = iso_datetime_utc(row.get('gameDate'))
    return f"{target_date}|{away}|{home}|{game_time}"


def movement_point_from_row(row: pd.Series, market_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    projection = game_projection_values(row)
    home_runs = projection['home']
    away_runs = projection['away']
    context = derive_market_context(row, market_entry)
    return {
        'date': local_date(row.get('forecast_generated_date')) or game_display_date(row),
        'predictedAway': away_runs,
        'predictedHome': home_runs,
        'modelHomeSpread': home_runs - away_runs if home_runs is not None and away_runs is not None else None,
        'marketSpread': context.get('marketSpread'),
        'modelTotal': projection['total'],
        'marketTotal': context.get('marketTotal'),
        'nrfiProb': safe_float(row.get('nrfi_prob')),
        'homeWinProb': safe_float(row.get('home_win_prob')),
        'awayWinProb': safe_float(row.get('away_win_prob')),
        'favoriteWinLabel': context.get('favoriteWinLabel'),
        'favoriteWinProb': context.get('favoriteWinProb'),
        'favoriteCoverLabel': context.get('favoriteCoverLabel'),
        'favoriteCoverProb': context.get('favoriteCoverProb'),
        'marketCoverLabel': context.get('marketCoverLabel'),
        'marketCoverProb': context.get('marketCoverProb'),
        'marketTotalLabel': context.get('marketTotalLabel'),
        'marketOverProb': context.get('marketOverProb'),
        'marketUnderProb': context.get('marketUnderProb'),
        'fallbackTotalLabel': context.get('fallbackTotalLabel'),
        'fallbackOverProb': context.get('fallbackOverProb'),
        'fallbackUnderProb': context.get('fallbackUnderProb'),
        'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
        'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
        'over7p5Prob': safe_float(row.get('over_7p5_prob')),
        'over8p5Prob': safe_float(row.get('over_8p5_prob')),
        'note': 'Snapshot'
    }


def build_movement(movement_rows: pd.DataFrame, market_entry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if movement_rows is None or movement_rows.empty:
        return []
    work = movement_rows.copy()
    work['__forecast_date'] = work['forecast_generated_date'].map(iso_date)
    work = work.sort_values(['__forecast_date', 'gameDate', 'home_team', 'away_team'])
    points: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for _, row in work.iterrows():
        point = movement_point_from_row(row, market_entry=market_entry)
        point_date = clean_str(point.get('date'))
        if not point_date:
            continue
        if point_date in seen_dates:
            points[-1] = point
        else:
            seen_dates.add(point_date)
            points.append(point)
    return points


def trimmed_pitcher_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    if df is None or df.empty:
        return out
    sort_cols = [c for c in ['is_home', 'team', 'player_name'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, True, True][:len(sort_cols)])
    for _, row in df.iterrows():
        item = {
            'playerId': safe_int(row.get('player_id')),
            'player': clean_str(row.get('player_name') or row.get('fullName')),
            'team': clean_str(row.get('team')),
            'opponent': clean_str(row.get('opponent')),
            'hand': clean_str(row.get('pitchHand')),
            'isHome': bool(row.get('is_home')) if clean_str(row.get('is_home')) != '' else None,
            'predOuts': pitcher_projection_value(row, 'outs'),
            'predIP': safe_float(row.get('pred_ip')),
            'predK': pitcher_projection_value(row, 'k'),
            'predBB': pitcher_projection_value(row, 'bb'),
            'predHitsAllowed': pitcher_projection_value(row, 'hits_allowed'),
            'predER': pitcher_projection_value(row, 'er'),
            'pitcherRoleType': clean_str(row.get('pitcher_role_type')),
            'starterRoleScenario': clean_str(row.get('starter_role_scenario')),
            'starterRoleUncertaintyScore': safe_float(row.get('starter_role_uncertainty_score')),
            'starterRoleScenarioConfidence': safe_float(row.get('starter_role_scenario_confidence')),
            'workloadScenarioMeanOuts': safe_float(row.get('workload_scenario_mean_outs')),
            'roleExpectedOuts': safe_float(row.get('role_expected_outs')),
            'roleOutsLeashCap': safe_float(row.get('role_outs_leash_cap')),
            'predictionConfidenceScore': safe_float(row.get('prediction_confidence_score')),
            'predictionConfidenceTier': clean_str(row.get('prediction_confidence_tier')),
            'pitcherErProb01': safe_float(row.get('pitcher_er_prob_0_1')),
            'pitcherErProb23': safe_float(row.get('pitcher_er_prob_2_3')),
            'pitcherErProb4Plus': safe_float(row.get('pitcher_er_prob_4plus')),
            'pitcherErRiskBucket': clean_str(row.get('pitcher_er_risk_bucket_individual')),
            'prob15PlusOuts': safe_float(row.get('prob_15plus_outs')),
            'prob18PlusOuts': safe_float(row.get('prob_18plus_outs')),
            'prob21PlusOuts': safe_float(row.get('prob_21plus_outs')),
            'probKOver3p5': safe_float(row.get('prob_k_over_3p5')),
            'probKOver4p5': safe_float(row.get('prob_k_over_4p5')),
            'probKOver5p5': safe_float(row.get('prob_k_over_5p5')),
            'probKOver6p5': safe_float(row.get('prob_k_over_6p5')),
        }
        out.append(item)
    return out


def batter_sort_score(row: pd.Series) -> float:
    order = safe_float(row.get('projected_batting_order'))
    order_bonus = 20 - order if order is not None else 0
    prob_hit = safe_float(row.get('prob_hit')) or 0
    prob_tb2 = safe_float(row.get('prob_tb2plus')) or 0
    prob_hr = safe_float(row.get('prob_hr')) or 0
    return order_bonus + prob_hit * 10 + prob_tb2 * 8 + prob_hr * 12


def trimmed_batter_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    if df is None or df.empty:
        return out
    sort_df = df.copy()
    sort_df['__score__'] = sort_df.apply(batter_sort_score, axis=1)
    sort_df = sort_df.sort_values(['team', 'projected_batting_order', '__score__', 'player_name'], ascending=[True, True, False, True], na_position='last')
    for _, row in sort_df.iterrows():
        pred_hits = safe_float(row.get('pred_hits'))
        pred_runs = safe_float(row.get('pred_runs'))
        pred_rbi = safe_float(row.get('pred_rbi'))
        pred_hrr = None
        if pred_hits is not None or pred_runs is not None or pred_rbi is not None:
            pred_hrr = (pred_hits or 0) + (pred_runs or 0) + (pred_rbi or 0)
        else:
            pred_hrr = safe_float(row.get('pred_hrr'))
        item = {
            'playerId': safe_int(row.get('player_id')),
            'player': clean_str(row.get('player_name')),
            'team': clean_str(row.get('team')),
            'opponent': clean_str(row.get('opponent')),
            'order': safe_int(row.get('projected_batting_order') if clean_str(row.get('projected_batting_order')) != '' else row.get('batting_order')),
            'batSide': clean_str(row.get('batSide')),
            'oppPitchHand': clean_str(row.get('opp_pitch_hand') or row.get('oppPitchHand') or row.get('pitchHand')),
            'predHits': pred_hits,
            'predTB': safe_float(row.get('pred_total_bases')),
            'predDoubles': safe_float(row.get('pred_doubles')),
            'predHR': safe_float(row.get('pred_hr')),
            'predK': safe_float(row.get('pred_k')),
            'predBB': safe_float(row.get('pred_bb')),
            'predRBI': pred_rbi,
            'predRuns': pred_runs,
            'predSB': safe_float(row.get('pred_sb')),
            'predHRR': pred_hrr,
            'probHit': safe_float(row.get('prob_hit')),
            'probTB2Plus': safe_float(row.get('prob_tb2plus')),
            'probTB3Plus': safe_float(row.get('prob_tb3plus')),
            'probDouble': safe_float(row.get('prob_double')),
            'probHR': safe_float(row.get('prob_hr')),
            'probK': safe_float(row.get('prob_k')),
            'probBB': safe_float(row.get('prob_bb')),
            'probSB': safe_float(row.get('prob_sb')),
            'probHRR2Plus': safe_float(row.get('prob_hrr2plus')),
            'lineupSource': clean_str(row.get('lineup_source')),
            'lineupStatus': clean_str(row.get('lineup_status')),
            'officialLineup': first_boolish(row, ['official_lineup']),
            'lineupConfirmed': first_boolish(row, ['lineup_confirmed']),
            'lineupPaCertaintyScore': safe_float(row.get('lineup_pa_certainty_score')),
            'projectedLineupMethod': clean_str(row.get('projected_lineup_method')),
            'projectedHandStartRate': safe_float(row.get('projected_hand_start_rate')),
            'projectedHandPaRate': safe_float(row.get('projected_hand_pa_rate')),
            'projectedHandMatchGames': safe_float(row.get('projected_hand_match_games')),
            'projectedHandReliability': safe_float(row.get('projected_hand_reliability')),
            'playerVsOppHandGamesSampleEst': safe_float(row.get('player_vs_opp_hand_games_sample_est')),
            'playerVsOppHandAbSampleEst': safe_float(row.get('player_vs_opp_hand_ab_sample_est')),
            'playerVsOppHandSplitConfidence': safe_float(row.get('player_vs_opp_hand_split_confidence')),
        }
        out.append(item)
    return out


def build_game_lookup(game_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    lookup = {}
    for _, row in game_df.iterrows():
        game_date = game_display_date(row)
        home = clean_str(row.get('home_team'))
        away = clean_str(row.get('away_team'))
        game_pk = safe_int(row.get('gamePk'))
        if game_date and home and away:
            lookup[(game_date, home, away)] = {'gamePk': game_pk, 'homeTeam': home, 'awayTeam': away}
            lookup[(game_date, away, home)] = {'gamePk': game_pk, 'homeTeam': home, 'awayTeam': away}
    return lookup


def build_props_from_workbook(workbook_path: Path | None, game_lookup: dict[tuple[str, str, str], dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not workbook_path or not workbook_path.exists():
        return []
    xls = pd.ExcelFile(workbook_path)
    sheet_name = 'All_Picks' if 'All_Picks' in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet_name)
    if df.empty:
        return []

    sort_cols = [c for c in ['over_prob', 'over_prob_pct', 'projection'] if c in df.columns]
    ascending = [False] * len(sort_cols)
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    rows = []
    for _, row in df.head(limit).iterrows():
        game_date = game_display_date(row)
        team = clean_str(row.get('team'))
        opp = clean_str(row.get('opponent'))
        lookup = game_lookup.get((game_date, team, opp), {})
        over_prob = safe_float(row.get('over_prob'))
        item = {
            'league': 'MLB',
            'gameDate': game_date,
            'gameId': lookup.get('gamePk'),
            'player': clean_str(row.get('player_name')),
            'team': team,
            'opp': opp,
            'stat': market_stat_display(row.get('market')),
            'stat_display': market_stat_display(row.get('market')),
            'line': market_line_from_market_name(row.get('market')),
            'modelPrediction': safe_float(row.get('projection')),
            'probability': over_prob,
            'confidence': prop_confidence(over_prob),
            'note': f"{team} vs {opp} • {pct_text(over_prob)} to clear",
        }
        rows.append(item)
    return rows



def build_game_objects(
    game_df: pd.DataFrame,
    movement_lookup: dict[str, pd.DataFrame] | None = None,
    market_lines_by_pk: dict[int, dict[str, Any]] | None = None,
    market_lines_by_matchup: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[str]]:
    movement_lookup = movement_lookup or {}
    market_lines_by_pk = market_lines_by_pk or {}
    market_lines_by_matchup = market_lines_by_matchup or {}
    games = []
    by_pk: dict[int, dict[str, Any]] = {}
    dates = sorted({game_display_date(row) for _, row in game_df.iterrows() if game_display_date(row)})
    for _, row in game_df.sort_values(['target_game_date', 'gameDate', 'home_team', 'away_team']).iterrows():
        game_pk = safe_int(row.get('gamePk'))
        target_date = game_display_date(row)
        game_time = iso_datetime_utc(row.get('gameDate'))
        projection = game_projection_values(row)
        home_runs = projection['home']
        away_runs = projection['away']
        model_spread = projection['margin']
        identity = game_identity_key(row)
        movement_rows = movement_lookup.get(identity)
        market_entry = market_lines_by_pk.get(game_pk) if game_pk is not None else None
        if market_entry is None:
            market_entry = market_lines_by_matchup.get(market_matchup_key(target_date, row.get('away_team'), row.get('home_team')))
        context = derive_market_context(row, market_entry)
        obj = {
            'id': f"mlb-{game_pk}",
            'gamePk': game_pk,
            'league': 'MLB',
            'gameDate': target_date,
            'gameDateTimeUtc': game_time,
            'awayTeam': clean_str(row.get('away_team')),
            'homeTeam': clean_str(row.get('home_team')),
            'marketSpread': context.get('marketSpread'),
            'marketTotal': context.get('marketTotal'),
            'marketAwayML': context.get('marketAwayML'), 'marketHomeML': context.get('marketHomeML'),
            'awayML': context.get('awayML'), 'homeML': context.get('homeML'),
            'awayMoneyline': context.get('awayMoneyline'), 'homeMoneyline': context.get('homeMoneyline'),
            'awaySpread': context.get('awaySpread'), 'homeSpread': context.get('homeSpread'),
            'awaySpreadOdds': context.get('awaySpreadOdds'), 'homeSpreadOdds': context.get('homeSpreadOdds'),
            'marketSpreadPerspective': context.get('marketSpreadPerspective'),
            'marketSpreadRawArchive': context.get('marketSpreadRawArchive'),
            'spreadLinePairValid': context.get('spreadLinePairValid'), 'spreadPricePairValid': context.get('spreadPricePairValid'),
            'spreadLineStatus': context.get('spreadLineStatus'),
            'overOdds': context.get('overOdds'), 'underOdds': context.get('underOdds'),
            'totalLinePairValid': context.get('totalLinePairValid'), 'totalPricePairValid': context.get('totalPricePairValid'), 'marketPriceStatus': context.get('marketPriceStatus'),
            'modelAwayScore': away_runs,
            'modelHomeScore': home_runs,
            'modelHomeSpread': model_spread,
            'modelTotal': projection['total'],
            'authoritativeGameProjectionSource': projection['source'],
            'homeWinProb': safe_float(row.get('home_win_prob')),
            'awayWinProb': safe_float(row.get('away_win_prob')),
            'favoriteWinLabel': context.get('favoriteWinLabel'),
            'favoriteWinProb': context.get('favoriteWinProb'),
            'modelMoneylineLabel': context.get('modelMoneylineLabel'),
            'modelMoneylineProb': context.get('modelMoneylineProb'),
            'nrfiProb': safe_float(row.get('nrfi_prob')),
            'yrfiProb': safe_float(row.get('yrfi_prob')),
            'homeMinus1p5Prob': safe_float(row.get('home_minus1p5_prob')),
            'awayPlus1p5Prob': safe_float(row.get('away_plus1p5_prob')),
            'awayMinus1p5Prob': safe_float(row.get('away_minus1p5_prob')),
            'homePlus1p5Prob': safe_float(row.get('home_plus1p5_prob')),
            'favoriteMinus1p5Prob': safe_float(row.get('favorite_minus1p5_prob')),
            'underdogPlus1p5Prob': safe_float(row.get('underdog_plus1p5_prob')),
            'favoriteCoverLabel': context.get('favoriteCoverLabel'),
            'favoriteCoverProb': context.get('favoriteCoverProb'),
            'modelSpreadPickLabel': context.get('modelSpreadPickLabel'),
            'modelSpreadPickProb': context.get('modelSpreadPickProb'),
            'modelSpreadPickTeam': context.get('modelSpreadPickTeam'),
            'modelTotalPickLabel': context.get('modelTotalPickLabel'),
            'modelTotalPickProb': context.get('modelTotalPickProb'),
            'moneylineActionable': context.get('moneylineActionable'), 'moneylineRepriceRequired': context.get('moneylineRepriceRequired'),
            'modelPickTeam': context.get('modelPickTeam'), 'modelPickSide': context.get('modelPickSide'),
            'calibratedModelPickWinProb': context.get('calibratedModelPickWinProb'),
            'probEdgeVsNovig': context.get('probEdgeVsNovig'), 'expectedRoi': context.get('expectedRoi'),
            'betRecommendation': context.get('betRecommendation'), 'betReason': context.get('betReason'),
            'modelPickStatus': context.get('modelPickStatus'),
            'calibratedProbabilityRejectsScorePick': context.get('calibratedProbabilityRejectsScorePick'),
            'spreadPickSide': context.get('spreadPickSide'), 'selectedSpreadLine': context.get('selectedSpreadLine'),
            'spreadCoverProbEst': context.get('spreadCoverProbEst'), 'spreadEdgeRuns': context.get('spreadEdgeRuns'),
            'selectedSpreadOdds': context.get('selectedSpreadOdds'), 'currentSelectedSpreadOdds': context.get('currentSelectedSpreadOdds'), 'spreadMarketImpliedNovig': context.get('spreadMarketImpliedNovig'),
            'spreadExpectedRoi': context.get('spreadExpectedRoi'),
            'spreadFinalRecommendation': context.get('spreadFinalRecommendation'), 'spreadFinalReason': context.get('spreadFinalReason'),
            'spreadActionable': context.get('spreadActionable'), 'spreadRepriceRequired': context.get('spreadRepriceRequired'),
            'totalPickSide': context.get('totalPickSide'), 'totalPickProbEst': context.get('totalPickProbEst'),
            'totalEdgeRuns': context.get('totalEdgeRuns'), 'selectedTotalOdds': context.get('selectedTotalOdds'), 'currentSelectedTotalOdds': context.get('currentSelectedTotalOdds'),
            'totalMarketImpliedNovig': context.get('totalMarketImpliedNovig'), 'totalExpectedRoi': context.get('totalExpectedRoi'),
            'totalFinalRecommendation': context.get('totalFinalRecommendation'), 'totalFinalReason': context.get('totalFinalReason'),
            'totalActionable': context.get('totalActionable'), 'totalRepriceRequired': context.get('totalRepriceRequired'),
            'bestMarket': context.get('bestMarket'), 'bestMarketPick': context.get('bestMarketPick'), 'bestMarketScore': context.get('bestMarketScore'),
            'secondBestMarket': context.get('secondBestMarket'), 'secondBestMarketPick': context.get('secondBestMarketPick'), 'secondBestMarketScore': context.get('secondBestMarketScore'),
            'avoidedMarket': context.get('avoidedMarket'), 'marketRoutingReason': context.get('marketRoutingReason'),
            'marketRoutingPriceRequired': context.get('marketRoutingPriceRequired'),
            'marketRoutingCorrelationWarning': context.get('marketRoutingCorrelationWarning'),
            'bestMarketActionable': context.get('bestMarketActionable'),
            'marketCoverLabel': context.get('marketCoverLabel'),
            'marketCoverProb': context.get('marketCoverProb'),
            'over7p5Prob': safe_float(row.get('over_7p5_prob')),
            'over8p5Prob': safe_float(row.get('over_8p5_prob')),
            'marketTotalLabel': context.get('marketTotalLabel'),
            'marketOverProb': context.get('marketOverProb'),
            'marketUnderProb': context.get('marketUnderProb'),
            'fallbackTotalLabel': context.get('fallbackTotalLabel'),
            'fallbackOverProb': context.get('fallbackOverProb'),
            'fallbackUnderProb': context.get('fallbackUnderProb'),
            'oneRunGameProb': safe_float(row.get('one_run_game_prob')),
            'homeBy1Prob': safe_float(row.get('home_by_1_prob')),
            'awayBy1Prob': safe_float(row.get('away_by_1_prob')),
            'tieAfter9Prob': safe_float(row.get('tie_after9_prob')),
            'medianTotal': safe_float(row.get('median_total')),
            'medianMargin': safe_float(row.get('median_margin')),
            'confidence': confidence_label([
                safe_float(row.get('nrfi_prob')),
                safe_float(row.get('home_win_prob')),
                safe_float(row.get('away_win_prob')),
                safe_float(row.get('home_minus1p5_prob')),
                safe_float(row.get('away_minus1p5_prob')),
                safe_float(row.get('over_7p5_prob')),
                safe_float(row.get('over_8p5_prob')),
            ]),
            'predictionConfidenceScore': safe_float(row.get('prediction_confidence_score')),
            'predictionConfidenceTier': clean_str(row.get('prediction_confidence_tier')),
            'reconciliationRecommendationGate': clean_str(row.get('reconciliation_recommendation_gate')),
            'crossModelWarningLevel': clean_str(row.get('cross_model_warning_level')),
            'contradictionReason': clean_str(row.get('contradiction_reason')),
            'crossModelContradictionScore': safe_float(row.get('cross_model_contradiction_score')),
            'modelAgreementConfidence': safe_float(row.get('model_agreement_confidence')),
            'lineupConfidence': safe_float(row.get('lineup_confidence')),
            'startingPitcherConfidence': safe_float(row.get('starting_pitcher_confidence')),
            'summary': build_summary(row, context),
            'movement': build_movement(movement_rows if movement_rows is not None else pd.DataFrame([row]), market_entry=market_entry),
            'marketSpreadText': 'Pending' if context.get('marketSpread') is None else context.get('marketCoverLabel') or 'Available',
            'marketTotalText': 'Pending' if context.get('marketTotal') is None else context.get('marketTotalLabel') or f"{context.get('marketTotal')}",
            'marketLineSource': context.get('marketLineSource'),
            'marketLineUpdated': context.get('marketLineUpdated'),
            'marketUpdatedAt': context.get('marketUpdatedAt'), 'marketCapturedAt': context.get('marketCapturedAt'),
            'marketLineAgeHours': context.get('marketLineAgeHours'),
            'marketLineStatus': context.get('marketLineStatus'), 'modelMarketUpdatedAt': context.get('modelMarketUpdatedAt'),
            'marketSnapshotSource': context.get('marketSnapshotSource'), 'marketSnapshotMismatch': context.get('marketSnapshotMismatch'),
            'bookmakerKey': context.get('bookmakerKey'), 'bookmakerTitle': context.get('bookmakerTitle'), 'eventId': context.get('eventId'),
            'detailPath': f"data/mlb_game_details/{target_date}/{game_pk}.json"
        }
        games.append(obj)
        if game_pk is not None:
            by_pk[game_pk] = obj
    return games, by_pk, dates


def build_game_details(game_df: pd.DataFrame, pitcher_df: pd.DataFrame, batter_df: pd.DataFrame, by_pk: dict[int, dict[str, Any]], out_root: Path) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    pitcher_groups = dict(tuple(pitcher_df.groupby('gamePk', sort=False))) if not pitcher_df.empty else {}
    batter_groups = dict(tuple(batter_df.groupby('gamePk', sort=False))) if not batter_df.empty else {}

    for game_pk, game in by_pk.items():
        row = game_df.loc[game_df['gamePk'] == game_pk].iloc[0]
        detail = {
            'gamePk': game_pk,
            'league': 'MLB',
            'gameDate': game.get('gameDate'),
            'gameDateTimeUtc': game.get('gameDateTimeUtc'),
            'awayTeam': game.get('awayTeam'),
            'homeTeam': game.get('homeTeam'),
            'metrics': {
                'modelAwayScore': game.get('modelAwayScore'), 'modelHomeScore': game.get('modelHomeScore'),
                'modelTotal': game.get('modelTotal'), 'modelHomeSpread': game.get('modelHomeSpread'),
                'authoritativeGameProjectionSource': game.get('authoritativeGameProjectionSource'),
                'homeWinProb': game.get('homeWinProb'),
                'awayWinProb': game.get('awayWinProb'),
                'favoriteWinLabel': game.get('favoriteWinLabel'),
                'favoriteWinProb': game.get('favoriteWinProb'),
                'nrfiProb': game.get('nrfiProb'),
                'yrfiProb': game.get('yrfiProb'),
                'homeMinus1p5Prob': game.get('homeMinus1p5Prob'),
                'awayPlus1p5Prob': game.get('awayPlus1p5Prob'),
                'awayMinus1p5Prob': game.get('awayMinus1p5Prob'),
                'homePlus1p5Prob': game.get('homePlus1p5Prob'),
                'favoriteCoverLabel': game.get('favoriteCoverLabel'),
                'favoriteCoverProb': game.get('favoriteCoverProb'),
                'marketCoverLabel': game.get('marketCoverLabel'),
                'marketCoverProb': game.get('marketCoverProb'),
                'over7p5Prob': game.get('over7p5Prob'),
                'over8p5Prob': game.get('over8p5Prob'),
                'marketSpread': game.get('marketSpread'), 'awaySpread': game.get('awaySpread'), 'homeSpread': game.get('homeSpread'),
                'awaySpreadOdds': game.get('awaySpreadOdds'), 'homeSpreadOdds': game.get('homeSpreadOdds'),
                'spreadLinePairValid': game.get('spreadLinePairValid'),
                'marketTotal': game.get('marketTotal'), 'overOdds': game.get('overOdds'), 'underOdds': game.get('underOdds'),
                'totalPricePairValid': game.get('totalPricePairValid'),
                'marketTotalLabel': game.get('marketTotalLabel'),
                'marketOverProb': game.get('marketOverProb'),
                'marketUnderProb': game.get('marketUnderProb'),
                'fallbackTotalLabel': game.get('fallbackTotalLabel'),
                'fallbackOverProb': game.get('fallbackOverProb'),
                'fallbackUnderProb': game.get('fallbackUnderProb'),
                'oneRunGameProb': game.get('oneRunGameProb'),
                'tieAfter9Prob': game.get('tieAfter9Prob'),
                'medianTotal': game.get('medianTotal'),
                'medianMargin': game.get('medianMargin'),
                'marketLineSource': game.get('marketLineSource'),
                'marketAwayML': game.get('marketAwayML'),
                'marketHomeML': game.get('marketHomeML'),
                'marketLineUpdated': game.get('marketLineUpdated'), 'marketCapturedAt': game.get('marketCapturedAt'), 'marketLineAgeHours': game.get('marketLineAgeHours'),
                'marketLineStatus': game.get('marketLineStatus'), 'marketPriceStatus': game.get('marketPriceStatus'),
                'predHomeF5': safe_float(row.get('pred_home_f5')),
                'predAwayF5': safe_float(row.get('pred_away_f5')),
                'predF5Total': safe_float(row.get('pred_f5_total')),
            },
            'pitchers': trimmed_pitcher_rows(pitcher_groups.get(game_pk, pd.DataFrame())),
            'batters': trimmed_batter_rows(batter_groups.get(game_pk, pd.DataFrame())),
        }
        out_path = out_root / game.get('gameDate') / f'{game_pk}.json'
        write_json(out_path, detail)



def load_model_workbook(path: Path | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not path or not path.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    xls = pd.ExcelFile(path)
    required = {'Games', 'Pitchers', 'Batters'}
    missing = required.difference(xls.sheet_names)
    if missing:
        raise ValueError(f'Model workbook is missing required sheets: {sorted(missing)}')
    return (
        pd.read_excel(xls, sheet_name='Games'),
        pd.read_excel(xls, sheet_name='Pitchers'),
        pd.read_excel(xls, sheet_name='Batters'),
    )


def prepare_current_game_frame(df: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    work = df.copy()
    work['__source_file'] = str(source_path)
    work['__source_mtime'] = source_path.stat().st_mtime if source_path.exists() else 0
    work['__forecast_date'] = work.get('forecast_generated_date', pd.Series([None] * len(work))).map(iso_date)
    work['__identity_key'] = work.apply(game_identity_key, axis=1)
    return work


def find_latest(pattern: str, root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = list(root.rglob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_all_game_forecasts(root: Path) -> pd.DataFrame:
    if not root.exists():
        return pd.DataFrame()
    candidates = sorted(root.rglob('game_predictions_*.csv'))
    frames: list[pd.DataFrame] = []
    for path in candidates:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.copy()
        df['__source_file'] = str(path)
        df['__source_mtime'] = path.stat().st_mtime
        df['__forecast_date'] = df.get('forecast_generated_date', pd.Series([None] * len(df))).map(iso_date)
        df['__identity_key'] = df.apply(game_identity_key, axis=1)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_games = pd.concat(frames, ignore_index=True)
    all_games = all_games.sort_values(['__forecast_date', '__source_mtime', '__source_file', 'gameDate', 'home_team', 'away_team'])
    # De-duplicate the same game within the same forecast date, keeping the newest file.
    all_games = all_games.drop_duplicates(subset=['__identity_key', '__forecast_date'], keep='last')
    return all_games


def split_latest_and_movement(all_game_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    if all_game_df is None or all_game_df.empty:
        return pd.DataFrame(), {}
    latest_rows = (
        all_game_df
        .sort_values(['__identity_key', '__forecast_date', '__source_mtime', '__source_file'])
        .drop_duplicates(subset=['__identity_key'], keep='last')
        .copy()
    )
    movement_lookup = {key: grp.copy() for key, grp in all_game_df.groupby('__identity_key', sort=False)}
    return latest_rows, movement_lookup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build local-preview MLB site JSON files.')
    parser.add_argument('--website-repo', type=Path, default=DEFAULT_WEBSITE_REPO)
    parser.add_argument('--mlb-output-dir', type=Path, default=DEFAULT_MLB_OUTPUT_DIR)
    parser.add_argument('--game-csv', type=Path)
    parser.add_argument('--pitcher-csv', type=Path)
    parser.add_argument('--batter-csv', type=Path)
    parser.add_argument('--picks-workbook', type=Path)
    parser.add_argument('--model-workbook', type=Path, help='v86n workbook containing Games, Pitchers, and Batters sheets.')
    parser.add_argument('--top-props-limit', type=int, default=24)
    return parser.parse_args()



def main() -> int:
    args = parse_args()
    repo = args.website_repo
    data_dir = repo / 'data'

    pitcher_csv = args.pitcher_csv or find_latest('pitcher_predictions_*.csv', args.mlb_output_dir)
    batter_csv = args.batter_csv or find_latest('batter_predictions_*.csv', args.mlb_output_dir)
    workbook = args.picks_workbook or find_latest('top_batter_picks*.xlsx', args.mlb_output_dir)
    model_workbook = args.model_workbook or (args.mlb_output_dir / 'mlb_predictions.xlsx')
    workbook_game_df, workbook_pitcher_df, workbook_batter_df = load_model_workbook(model_workbook)

    all_game_df = load_all_game_forecasts(args.mlb_output_dir)
    if not workbook_game_df.empty:
        current = prepare_current_game_frame(workbook_game_df, model_workbook)
        all_game_df = pd.concat([all_game_df, current], ignore_index=True) if not all_game_df.empty else current
        all_game_df = all_game_df.sort_values(['__forecast_date', '__source_mtime', '__source_file', 'gameDate', 'home_team', 'away_team'])
        all_game_df = all_game_df.drop_duplicates(subset=['__identity_key', '__forecast_date'], keep='last')
        latest_game_df = current
        movement_lookup = {key: grp.copy() for key, grp in all_game_df.groupby('__identity_key', sort=False)}
    elif args.game_csv:
        latest_game_df = prepare_current_game_frame(pd.read_csv(args.game_csv), args.game_csv)
        all_game_df = latest_game_df.copy()
        movement_lookup = {key: grp.copy() for key, grp in latest_game_df.groupby('__identity_key', sort=False)}
    else:
        latest_game_df, movement_lookup = split_latest_and_movement(all_game_df)

    if latest_game_df is None or latest_game_df.empty:
        raise SystemExit('Could not find the v86n Games sheet or any MLB game_predictions CSVs.')

    if not workbook_pitcher_df.empty:
        pitcher_df = workbook_pitcher_df
    elif pitcher_csv and pitcher_csv.exists():
        pitcher_df = pd.read_csv(pitcher_csv)
    else:
        raise SystemExit('Could not find the v86n Pitchers sheet or an MLB pitcher_predictions CSV.')

    if not workbook_batter_df.empty:
        batter_df = workbook_batter_df
    elif batter_csv and batter_csv.exists():
        batter_df = pd.read_csv(batter_csv)
    else:
        raise SystemExit('Could not find the v86n Batters sheet or an MLB batter_predictions CSV.')
    market_lines_by_pk, market_lines_by_matchup, market_line_rows = load_mlb_market_lines(repo, args.mlb_output_dir)

    mlb_games, by_pk, mlb_dates = build_game_objects(
        latest_game_df,
        movement_lookup,
        market_lines_by_pk=market_lines_by_pk,
        market_lines_by_matchup=market_lines_by_matchup,
    )
    build_game_details(latest_game_df, pitcher_df, batter_df, by_pk, data_dir / 'mlb_game_details')

    existing_games = load_json(data_dir / 'games.json', [])
    keep_games = [g for g in existing_games if clean_str(g.get('league')).upper() != 'MLB']
    combined_games = keep_games + mlb_games
    combined_games.sort(key=lambda g: (clean_str(g.get('gameDate')), clean_str(g.get('league')), clean_str(g.get('awayTeam')), clean_str(g.get('homeTeam'))))
    write_json(data_dir / 'games.json', combined_games)

    existing_props = load_json(data_dir / 'props.json', [])
    keep_props = [p for p in existing_props if clean_str(p.get('league')).upper() != 'MLB']
    game_lookup = build_game_lookup(latest_game_df)
    mlb_props = build_props_from_workbook(workbook, game_lookup, args.top_props_limit)
    combined_props = keep_props + mlb_props
    write_json(data_dir / 'props.json', combined_props)

    site = load_json(data_dir / 'site.json', {})
    feature_config = load_json(data_dir / 'site_features.json', {})
    active_leagues = [clean_str(x).upper() for x in feature_config.get('activeLeagues', ['MLB']) if clean_str(x)]
    site['leagues'] = active_leagues or ['MLB']
    if latest_game_df.get('forecast_generated_date') is not None and not latest_game_df.empty:
        latest_forecast = max((iso_date(v) for v in latest_game_df['forecast_generated_date']), default='')
        if latest_forecast:
            site['lastUpdated'] = latest_forecast
    write_json(data_dir / 'site.json', site)

    movement_sizes = [len(g.get('movement') or []) for g in mlb_games]
    max_points = max(movement_sizes) if movement_sizes else 0
    matched_market_lines = sum(1 for g in mlb_games if g.get('marketSpread') is not None or g.get('marketTotal') is not None)
    print(f'Loaded {len(all_game_df)} total MLB forecast rows across all game prediction files.')
    print(f'Loaded {market_line_rows} MLB market-line archive rows; matched {matched_market_lines} current MLB games.')
    print(f'Wrote {len(mlb_games)} MLB games into {data_dir / "games.json"}')
    print(f'MLB movement points per game: min={min(movement_sizes) if movement_sizes else 0}, max={max_points}')
    print(f'Wrote {len(mlb_props)} MLB homepage props into {data_dir / "props.json"}')
    print(f'Wrote MLB detail files under {data_dir / "mlb_game_details"}')
    return 0


if __name__ == '__main__':

    raise SystemExit(main())
