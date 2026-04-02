"""American odds → implied probability, vig, no-vig (fair) normalization."""

from __future__ import annotations


def american_to_implied_probability(american: int) -> float:
    if american == 0:
        raise ValueError("American odds cannot be zero")
    if american < 0:
        a = abs(american)
        return a / (a + 100)
    return 100 / (american + 100)


def two_sided_market(odds_side_a: int, odds_side_b: int) -> dict:
    """Both sides of a market (e.g. spread home/away, ML home/away, O/U)."""
    p_a = american_to_implied_probability(odds_side_a)
    p_b = american_to_implied_probability(odds_side_b)
    total = p_a + p_b
    vig = total - 1.0
    fair_a = p_a / total if total else 0.0
    fair_b = p_b / total if total else 0.0
    return {
        "implied_probability_side_a": round(p_a, 6),
        "implied_probability_side_b": round(p_b, 6),
        "implied_sum": round(total, 6),
        "vig_decimal": round(vig, 6),
        "vig_percent": round(vig * 100, 4),
        "fair_probability_side_a": round(fair_a, 6),
        "fair_probability_side_b": round(fair_b, 6),
    }
