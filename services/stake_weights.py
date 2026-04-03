"""Two-way stake sizing: equalize payout across outcomes (arbitrage-style weights)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services import best_line, math_odds
from services.odds_repository import get_odds_for_game


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


def _imp(am: int) -> float:
    return math_odds.american_to_implied_probability(int(am))


def _modal_spread_bucket(rows: list[dict]) -> tuple[tuple[float, float], list[dict]] | None:
    by_key: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for r in rows:
        sp = (r.get("markets") or {}).get("spread") or {}
        hl, al = sp.get("home_line"), sp.get("away_line")
        if hl is None or al is None:
            continue
        key = (round(float(hl), 2), round(float(al), 2))
        by_key[key].append(r)
    if not by_key:
        return None
    return max(by_key.items(), key=lambda kv: len(kv[1]))


def _best_spread_legs(game_id: str) -> dict[str, Any]:
    rows = get_odds_for_game(game_id)
    if not rows:
        return {"error": f"Unknown game_id: {game_id}", "game_id": game_id}
    got = _modal_spread_bucket(rows)
    if not got:
        return {
            "error": "No spread markets for this game",
            "game_id": game_id,
        }
    (hl, al), bucket = got
    best_home: dict[str, Any] | None = None
    best_away: dict[str, Any] | None = None
    for r in bucket:
        book = r["sportsbook"]
        sp = (r.get("markets") or {}).get("spread") or {}
        ho, ao = sp.get("home_odds"), sp.get("away_odds")
        if ho is not None and ho != 0:
            p = _imp(int(ho))
            if best_home is None or p < best_home["implied_probability"]:
                best_home = {
                    "sportsbook": book,
                    "american": int(ho),
                    "implied_probability": round(p, 6),
                }
        if ao is not None and ao != 0:
            p = _imp(int(ao))
            if best_away is None or p < best_away["implied_probability"]:
                best_away = {
                    "sportsbook": book,
                    "american": int(ao),
                    "implied_probability": round(p, 6),
                }
    if not best_home or not best_away:
        return {
            "error": "Could not resolve best spread price for both sides on the modal pair",
            "game_id": game_id,
            "spread_home_line": hl,
            "spread_away_line": al,
        }
    return {
        "spread_home_line": hl,
        "spread_away_line": al,
        "best_home": best_home,
        "best_away": best_away,
    }


def _modal_total_bucket(rows: list[dict]) -> tuple[float, list[dict]] | None:
    by_line: dict[float, list[dict]] = defaultdict(list)
    for r in rows:
        tot = (r.get("markets") or {}).get("total") or {}
        line = tot.get("line")
        if line is None:
            continue
        by_line[round(float(line), 2)].append(r)
    if not by_line:
        return None
    return max(by_line.items(), key=lambda kv: len(kv[1]))


def _best_total_legs(game_id: str) -> dict[str, Any]:
    rows = get_odds_for_game(game_id)
    if not rows:
        return {"error": f"Unknown game_id: {game_id}", "game_id": game_id}
    got = _modal_total_bucket(rows)
    if not got:
        return {"error": "No total markets for this game", "game_id": game_id}
    line_val, bucket = got
    best_over: dict[str, Any] | None = None
    best_under: dict[str, Any] | None = None
    for r in bucket:
        book = r["sportsbook"]
        tot = (r.get("markets") or {}).get("total") or {}
        oo, uo = tot.get("over_odds"), tot.get("under_odds")
        if oo is not None and oo != 0:
            p = _imp(int(oo))
            if best_over is None or p < best_over["implied_probability"]:
                best_over = {
                    "sportsbook": book,
                    "american": int(oo),
                    "implied_probability": round(p, 6),
                }
        if uo is not None and uo != 0:
            p = _imp(int(uo))
            if best_under is None or p < best_under["implied_probability"]:
                best_under = {
                    "sportsbook": book,
                    "american": int(uo),
                    "implied_probability": round(p, 6),
                }
    if not best_over or not best_under:
        return {
            "error": "Could not resolve best over/under on the modal total line",
            "game_id": game_id,
            "total_line": line_val,
        }
    return {"total_line": line_val, "best_over": best_over, "best_under": best_under}


def build_stake_weights_for_game(
    game_id: str,
    two_way_market: str,
    total_stake: float | None = None,
) -> dict[str, Any]:
    """
    Stake weights using the **best available American price on each side** across books
    (lowest implied = best payout). Spread/total use the **modal** line or spread pair
    (most common posted number), same idea as cross-book arb aggregation.
    """
    m = two_way_market.strip().lower()
    if m not in ("moneyline", "spread", "total"):
        return {
            "error": "two_way_market must be moneyline, spread, or total",
            "game_id": game_id,
        }

    line_context: dict[str, Any] | None = None
    side_a_meta: dict[str, Any]
    side_b_meta: dict[str, Any]
    label_a: str
    label_b: str

    if m == "moneyline":
        h = best_line.best_line_for_side(game_id, "moneyline_home")
        a = best_line.best_line_for_side(game_id, "moneyline_away")
        if "error" in h:
            return h
        if "error" in a:
            return a
        bh, ba = h["best"], a["best"]
        oa, ob = int(bh["american"]), int(ba["american"])
        label_a, label_b = "moneyline_home", "moneyline_away"
        side_a_meta = {
            "market_side": label_a,
            "sportsbook": bh["sportsbook"],
            "american": oa,
            "implied_probability": bh["implied_probability"],
        }
        side_b_meta = {
            "market_side": label_b,
            "sportsbook": ba["sportsbook"],
            "american": ob,
            "implied_probability": ba["implied_probability"],
        }
    elif m == "spread":
        legs = _best_spread_legs(game_id)
        if "error" in legs:
            return legs
        line_context = {
            "spread_home_line": legs["spread_home_line"],
            "spread_away_line": legs["spread_away_line"],
        }
        bh, ba = legs["best_home"], legs["best_away"]
        oa, ob = bh["american"], ba["american"]
        label_a, label_b = "spread_home", "spread_away"
        side_a_meta = {
            "market_side": label_a,
            "sportsbook": bh["sportsbook"],
            "american": oa,
            "implied_probability": bh["implied_probability"],
        }
        side_b_meta = {
            "market_side": label_b,
            "sportsbook": ba["sportsbook"],
            "american": ob,
            "implied_probability": ba["implied_probability"],
        }
    else:
        legs = _best_total_legs(game_id)
        if "error" in legs:
            return legs
        line_context = {"total_line": legs["total_line"]}
        bo, bu = legs["best_over"], legs["best_under"]
        oa, ob = bo["american"], bu["american"]
        label_a, label_b = "total_over", "total_under"
        side_a_meta = {
            "market_side": label_a,
            "sportsbook": bo["sportsbook"],
            "american": oa,
            "implied_probability": bo["implied_probability"],
        }
        side_b_meta = {
            "market_side": label_b,
            "sportsbook": bu["sportsbook"],
            "american": ob,
            "implied_probability": bu["implied_probability"],
        }

    core = build_stake_weights(oa, ob, total_stake=total_stake)
    if "error" in core:
        return core

    core["pricing_basis"] = "best_cross_book_per_side"
    core["game_id"] = game_id
    core["two_way_market"] = m
    core["side_a_leg"] = side_a_meta
    core["side_b_leg"] = side_b_meta
    if line_context is not None:
        core["line_context"] = line_context
    core["interpretation"] = (
        "Stake weights use the best (lowest implied) American price on each outcome across books. "
        "Spread/total restrict to the modal posted line or pair so both legs are comparable."
    )
    return core
