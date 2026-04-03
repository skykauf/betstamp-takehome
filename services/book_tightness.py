"""
Per-sportsbook tightness: average two-way vig across ML / spread / total rows in the sample.

Lower avg_vig_percent ≈ tighter markets (better for bettors on that axis).
"""

from __future__ import annotations

import statistics
from typing import Any

from services import math_odds
from services.odds_repository import all_odds_rows


def _row_market_vigs(markets: dict[str, Any]) -> list[float]:
    vigs: list[float] = []
    ml = markets.get("moneyline") or {}
    ho, ao = ml.get("home_odds"), ml.get("away_odds")
    if ho is not None and ao is not None and ho != 0 and ao != 0:
        try:
            vigs.append(
                math_odds.two_sided_market(int(ho), int(ao))["vig_percent"]
            )
        except ValueError:
            pass

    sp = markets.get("spread") or {}
    sho, sao = sp.get("home_odds"), sp.get("away_odds")
    if sho is not None and sao is not None and sho != 0 and sao != 0:
        try:
            vigs.append(
                math_odds.two_sided_market(int(sho), int(sao))["vig_percent"]
            )
        except ValueError:
            pass

    tot = markets.get("total") or {}
    oo, uo = tot.get("over_odds"), tot.get("under_odds")
    if oo is not None and uo is not None and oo != 0 and uo != 0:
        try:
            vigs.append(
                math_odds.two_sided_market(int(oo), int(uo))["vig_percent"]
            )
        except ValueError:
            pass

    return vigs


def slate_book_tightness() -> dict[str, Any]:
    """
    For each sportsbook, average vig% over game-rows where at least one two-way market exists.
    Rank ascending (tightest first).
    """
    odds = all_odds_rows()
    per_book: dict[str, list[float]] = {}

    for row in odds:
        book = row.get("sportsbook")
        if not book:
            continue
        markets = row.get("markets") or {}
        vigs = _row_market_vigs(markets)
        if not vigs:
            continue
        per_book.setdefault(book, []).append(sum(vigs) / len(vigs))

    if not per_book:
        return {
            "error": "No two-way markets found in sample data",
            "books_ranked": [],
        }

    ranked: list[dict[str, Any]] = []
    for book, vigs in sorted(per_book.items()):
        ranked.append(
            {
                "sportsbook": book,
                "game_rows_used": len(vigs),
                "avg_vig_percent": round(statistics.mean(vigs), 4),
                "median_vig_percent": round(statistics.median(vigs), 4),
                "min_vig_percent": round(min(vigs), 4),
                "max_vig_percent": round(max(vigs), 4),
            }
        )

    ranked.sort(key=lambda x: x["avg_vig_percent"])

    return {
        "interpretation": (
            "Per book, average of (ML vig%, spread vig%, total vig%) for each game-row that has "
            "those markets — then mean across games. Lower avg_vig_percent suggests tighter "
            "two-way pricing on average for this snapshot (not live closing lines)."
        ),
        "book_count": len(ranked),
        "books_ranked_tightest_first": ranked,
    }
