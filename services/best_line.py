"""Best available American price for one side of a market across books (lowest implied prob = best payout)."""

from __future__ import annotations

from typing import Any

from services import math_odds
from services.odds_repository import get_odds_for_game

# market_side must match tool schema
VALID_SIDES = frozenset(
    {
        "spread_home",
        "spread_away",
        "moneyline_home",
        "moneyline_away",
        "total_over",
        "total_under",
    }
)


def _pick_american_and_line(markets: dict[str, Any], market_side: str) -> tuple[int | None, float | None]:
    """Return (american_odds, display_line or None)."""
    sp = markets.get("spread") or {}
    ml = markets.get("moneyline") or {}
    tot = markets.get("total") or {}
    if market_side == "spread_home":
        return sp.get("home_odds"), sp.get("home_line")
    if market_side == "spread_away":
        return sp.get("away_odds"), sp.get("away_line")
    if market_side == "moneyline_home":
        return ml.get("home_odds"), None
    if market_side == "moneyline_away":
        return ml.get("away_odds"), None
    if market_side == "total_over":
        return tot.get("over_odds"), tot.get("line")
    if market_side == "total_under":
        return tot.get("under_odds"), tot.get("line")
    return None, None


def best_line_for_side(game_id: str, market_side: str) -> dict[str, Any]:
    """
    Across all books for this game, find the best American odds for the chosen side.
    Best = lowest implied probability (highest expected payout).
    """
    if market_side not in VALID_SIDES:
        return {
            "error": f"Invalid market_side. Use one of: {sorted(VALID_SIDES)}",
            "game_id": game_id,
        }

    rows = get_odds_for_game(game_id)
    if not rows:
        return {"error": f"Unknown game_id: {game_id}", "game_id": game_id}

    candidates: list[dict[str, Any]] = []
    for r in rows:
        book = r["sportsbook"]
        markets = r.get("markets") or {}
        american, line = _pick_american_and_line(markets, market_side)
        if american is None or american == 0:
            continue
        try:
            imp = math_odds.american_to_implied_probability(int(american))
        except ValueError:
            continue
        candidates.append(
            {
                "sportsbook": book,
                "american": int(american),
                "implied_probability": round(imp, 6),
                "line": line,
                "last_updated": r.get("last_updated"),
            }
        )

    if not candidates:
        return {
            "error": "No valid odds for that market_side on this game",
            "game_id": game_id,
            "market_side": market_side,
        }

    # Best payout = minimum implied probability
    best = min(candidates, key=lambda c: c["implied_probability"])
    ranked = sorted(candidates, key=lambda c: c["implied_probability"])

    return {
        "game_id": game_id,
        "market_side": market_side,
        "interpretation": "Best line = lowest implied probability (best payout) for this side.",
        "best": best,
        "all_books_ranked_best_to_worst": ranked,
    }
