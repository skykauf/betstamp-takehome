"""Two-way stake sizing: equalize payout across outcomes (arbitrage-style weights)."""

from __future__ import annotations

from services import math_odds


def american_to_decimal(american: int) -> float:
    if american == 0:
        raise ValueError("American odds cannot be zero")
    if american < 0:
        return 1.0 + 100.0 / abs(float(american))
    return 1.0 + float(american) / 100.0


def build_stake_weights(
    odds_side_a: int,
    odds_side_b: int,
    total_stake: float | None = None,
) -> dict:
    """
    Stake fractions so that total return is the same whether A or B wins:
    S_A / S_B = D_B / D_A  =>  stake_fraction_A = D_B / (D_A + D_B).

    When implied probabilities (from these two prices) sum to < 1, that common
    return exceeds total stake — a theoretical arb. Otherwise weights still
    equalize payout but the guaranteed return is below stake.
    """
    d_a = american_to_decimal(int(odds_side_a))
    d_b = american_to_decimal(int(odds_side_b))
    denom = d_a + d_b
    if denom <= 0:
        return {"error": "Invalid decimal odds sum"}

    frac_a = d_b / denom
    frac_b = d_a / denom

    p_a = math_odds.american_to_implied_probability(int(odds_side_a))
    p_b = math_odds.american_to_implied_probability(int(odds_side_b))
    implied_sum = p_a + p_b
    edge = 1.0 - implied_sum

    if total_stake is not None and total_stake <= 0:
        return {"error": "total_stake must be positive when provided"}

    out: dict = {
        "odds_side_a": int(odds_side_a),
        "odds_side_b": int(odds_side_b),
        "decimal_odds_side_a": round(d_a, 6),
        "decimal_odds_side_b": round(d_b, 6),
        "stake_fraction_side_a": round(frac_a, 6),
        "stake_fraction_side_b": round(frac_b, 6),
        "implied_probability_sum": round(implied_sum, 6),
        "theoretical_edge_percent": round(edge * 100, 4),
        "is_strict_two_way_arb": implied_sum < 1.0 - 1e-9,
        "formula": (
            "Equal payout: stake_A / stake_B = decimal_B / decimal_A; "
            "fraction_A = decimal_B / (decimal_A + decimal_B). "
            "Decimal from American: favorite negative → 1 + 100/|odds|; "
            "underdog positive → 1 + odds/100."
        ),
    }

    payout = frac_a * d_a
    out["payout_multiple_of_total_stake"] = round(payout, 6)
    out["guaranteed_roi_percent_if_equalized"] = round((payout - 1.0) * 100, 4)

    if total_stake is not None:
        amt_a = round(frac_a * float(total_stake), 2)
        amt_b = round(frac_b * float(total_stake), 2)
        out["total_stake"] = float(total_stake)
        out["stake_amount_side_a"] = amt_a
        out["stake_amount_side_b"] = amt_b
        out["equal_payout_amount"] = round(amt_a * d_a, 2)

    return out
