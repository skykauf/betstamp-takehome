"""
Consensus vs book for one game side: median implied among books, per-book deviation and z-score.

Spread/total: only books on the **modal** line (most common posted line) so prices are comparable.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from services import math_odds
from services.best_line import VALID_SIDES, american_line_for_side
from services.odds_repository import get_odds_for_game


def _modal_line_rounded(lines: list[float]) -> float | None:
    if not lines:
        return None
    keys = [round(x, 2) for x in lines]
    return Counter(keys).most_common(1)[0][0]


def line_vs_consensus(game_id: str, market_side: str) -> dict[str, Any]:
    """
    Compare each book's price for one side to the cross-book consensus (median implied prob).

    Outliers: large |deviation_from_median_implied| or |z_score| (when sample std > 0).
    """
    if market_side not in VALID_SIDES:
        return {
            "error": f"Invalid market_side. Use one of: {sorted(VALID_SIDES)}",
            "game_id": game_id,
        }

    rows = get_odds_for_game(game_id)
    if not rows:
        return {"error": f"Unknown game_id: {game_id}", "game_id": game_id}

    raw: list[dict[str, Any]] = []
    for r in rows:
        book = r["sportsbook"]
        markets = r.get("markets") or {}
        american, line = american_line_for_side(markets, market_side)
        if american is None or american == 0:
            continue
        try:
            imp = math_odds.american_to_implied_probability(int(american))
        except ValueError:
            continue
        ln = float(line) if line is not None else None
        raw.append(
            {
                "sportsbook": book,
                "american": int(american),
                "implied_probability": round(imp, 6),
                "line": ln,
                "last_updated": r.get("last_updated"),
            }
        )

    if not raw:
        return {
            "error": "No valid odds for that market_side on this game",
            "game_id": game_id,
            "market_side": market_side,
        }

    # Moneyline: all books. Spread/total: restrict to modal line so we compare like-for-like.
    if market_side.startswith("moneyline"):
        cohort = raw
        consensus_line_used = None
    else:
        line_vals = [x["line"] for x in raw if x["line"] is not None]
        mode = _modal_line_rounded(line_vals)
        if mode is None:
            cohort = raw
            consensus_line_used = None
        else:
            cohort = [x for x in raw if x["line"] is not None and round(x["line"], 2) == mode]
            consensus_line_used = mode
        if len(cohort) < 2 and len(raw) >= 2:
            cohort = raw
            consensus_line_used = None

    implieds = [c["implied_probability"] for c in cohort]
    med = float(statistics.median(implieds))
    mean_imp = float(statistics.mean(implieds))
    stdev = float(statistics.pstdev(implieds)) if len(implieds) > 1 else 0.0

    by_book: list[dict[str, Any]] = []
    for c in cohort:
        imp = c["implied_probability"]
        dev = round(imp - med, 6)
        if stdev > 1e-8:
            z = round((imp - mean_imp) / stdev, 4)
        else:
            z = None
        by_book.append(
            {
                "sportsbook": c["sportsbook"],
                "american": c["american"],
                "implied_probability": imp,
                "line": c["line"],
                "deviation_from_median_implied": dev,
                "z_score_vs_cohort": z,
                "last_updated": c.get("last_updated"),
            }
        )

    by_book.sort(key=lambda x: abs(x["deviation_from_median_implied"]), reverse=True)

    max_abs_dev = max(abs(x["deviation_from_median_implied"]) for x in by_book)
    outlier_hint = [
        x["sportsbook"]
        for x in by_book
        if abs(x["deviation_from_median_implied"]) >= max_abs_dev - 1e-6
        and max_abs_dev > 0.005
    ]

    return {
        "game_id": game_id,
        "market_side": market_side,
        "books_in_cohort": len(cohort),
        "consensus_line_used": consensus_line_used,
        "median_implied_probability": round(med, 6),
        "mean_implied_probability": round(mean_imp, 6),
        "cohort_implied_stdev": round(stdev, 6) if len(implieds) > 1 else 0.0,
        "interpretation": (
            "Median implied prob is the consensus for this side among comparable books. "
            "Positive deviation_from_median_implied = this book prices the side with higher implied "
            "(typically worse for the bettor on that side vs consensus). "
            "Large |z_score_vs_cohort| flags statistical outliers when variance exists."
        ),
        "likely_outliers_by_deviation": outlier_hint,
        "by_book": by_book,
    }
