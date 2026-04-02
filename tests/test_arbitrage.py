"""Arbitrage scan: synthetic rows where best-home + best-away implied < 1."""

from __future__ import annotations

import pytest

from services import arbitrage


def _row(book: str, home_ml: int, away_ml: int) -> dict:
    return {
        "game_id": "test_game",
        "sportsbook": book,
        "markets": {"moneyline": {"home_odds": home_ml, "away_odds": away_ml}},
    }


def test_moneyline_arbitrage_detected():
    # Book A: bad for arb. Book B: home +120 (0.4545). Book C: away +130 (0.4348)
    # Best home +120, best away +130 -> sum ~0.889 < 1
    rows = [
        _row("A", -200, 170),
        _row("B", 120, -130),
        _row("C", -150, 130),
    ]
    m = arbitrage._moneyline_scan("test_game", rows)
    assert m is not None
    assert m["has_arbitrage"] is True
    assert m["home_leg"]["sportsbook"] == "B"
    assert m["home_leg"]["american"] == 120
    assert m["away_leg"]["sportsbook"] == "A"
    assert m["away_leg"]["american"] == 170
    assert m["cross_book"] is True
    assert m["implied_probability_sum"] < 1.0


def test_moneyline_no_arbitrage_tight_market():
    rows = [
        _row("A", -110, -110),
        _row("B", -108, -112),
    ]
    m = arbitrage._moneyline_scan("test_game", rows)
    assert m is not None
    assert m["has_arbitrage"] is False


def test_scan_tool_unknown_market():
    r = arbitrage.scan_cross_book_arbitrage(
        game_id="x", include_markets=["monopoly"]
    )
    assert "error" in r


def test_total_arbitrage_synthetic():
    rows = [
        {
            "game_id": "g1",
            "sportsbook": "B1",
            "markets": {"total": {"line": 220.0, "over_odds": 100, "under_odds": 100}},
        },
        {
            "game_id": "g1",
            "sportsbook": "B2",
            "markets": {"total": {"line": 220.0, "over_odds": 200, "under_odds": 200}},
        },
    ]
    # Best over: +200 -> 33.33%, best under: +200 -> 33.33% -> sum 0.666 < 1
    out = arbitrage._total_scans("g1", rows)
    assert len(out) == 1
    assert out[0]["has_arbitrage"] is True
    assert out[0]["total_line"] == 220.0
