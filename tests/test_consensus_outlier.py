"""line_vs_consensus — synthetic + sample game."""

from __future__ import annotations

from unittest.mock import patch

from services import consensus_outlier


def test_line_vs_consensus_moneyline_median_and_deviation():
    rows = [
        {
            "game_id": "g1",
            "sportsbook": "A",
            "markets": {"moneyline": {"home_odds": -200, "away_odds": 170}},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "game_id": "g1",
            "sportsbook": "B",
            "markets": {"moneyline": {"home_odds": -190, "away_odds": 160}},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "game_id": "g1",
            "sportsbook": "C",
            "markets": {"moneyline": {"home_odds": -200, "away_odds": 170}},
            "last_updated": "2026-01-01T00:00:00Z",
        },
    ]
    with patch("services.consensus_outlier.get_odds_for_game", return_value=rows):
        out = consensus_outlier.line_vs_consensus("g1", "moneyline_home")
    assert "error" not in out
    assert out["books_in_cohort"] == 3
    assert out["median_implied_probability"] > 0
    names = {b["sportsbook"] for b in out["by_book"]}
    assert names == {"A", "B", "C"}


def test_line_vs_consensus_unknown_game():
    with patch("services.consensus_outlier.get_odds_for_game", return_value=[]):
        out = consensus_outlier.line_vs_consensus("missing", "moneyline_home")
    assert "error" in out


def test_line_vs_consensus_real_sample_game():
    out = consensus_outlier.line_vs_consensus(
        "nba_20260320_lal_bos", "moneyline_home"
    )
    assert "error" not in out
    assert out["books_in_cohort"] >= 4
