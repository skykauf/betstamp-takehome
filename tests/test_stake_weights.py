"""build_stake_weights — equal-payout fractions and optional dollar amounts."""

from __future__ import annotations

from services import stake_weights


def test_equal_lines_split_50_50():
    out = stake_weights.build_stake_weights(-110, -110)
    assert "error" not in out
    assert out["stake_fraction_side_a"] == out["stake_fraction_side_b"]
    assert abs(out["stake_fraction_side_a"] + out["stake_fraction_side_b"] - 1.0) < 1e-6


def test_payout_equalized():
    out = stake_weights.build_stake_weights(150, -120)
    fa, fb = out["stake_fraction_side_a"], out["stake_fraction_side_b"]
    da, db = out["decimal_odds_side_a"], out["decimal_odds_side_b"]
    assert abs(fa * da - fb * db) < 1e-5


def test_strict_arb_flag_positive_edge():
    out = stake_weights.build_stake_weights(200, 200)
    assert out["is_strict_two_way_arb"] is True
    assert out["theoretical_edge_percent"] > 0
    assert out["guaranteed_roi_percent_if_equalized"] > 0


def test_total_stake_amounts_sum():
    out = stake_weights.build_stake_weights(-110, -105, total_stake=1000.0)
    assert abs(out["stake_amount_side_a"] + out["stake_amount_side_b"] - 1000.0) < 0.05
    pa = out["stake_amount_side_a"] * out["decimal_odds_side_a"]
    pb = out["stake_amount_side_b"] * out["decimal_odds_side_b"]
    assert abs(pa - pb) < 0.02


def test_invalid_total_stake():
    out = stake_weights.build_stake_weights(-110, -110, total_stake=0)
    assert "error" in out


def test_build_stake_weights_for_game_moneyline_uses_best_lines():
    out = stake_weights.build_stake_weights_for_game(
        "nba_20260320_lal_bos", "moneyline"
    )
    assert "error" not in out
    assert out.get("pricing_basis") == "best_cross_book_per_side"
    assert out["game_id"] == "nba_20260320_lal_bos"
    assert out["two_way_market"] == "moneyline"
    assert "side_a_leg" in out and "side_b_leg" in out
    assert out["odds_side_a"] == out["side_a_leg"]["american"]
    assert out["odds_side_b"] == out["side_b_leg"]["american"]


def test_build_stake_weights_for_game_bad_market():
    out = stake_weights.build_stake_weights_for_game(
        "nba_20260320_lal_bos", "props"
    )
    assert "error" in out
