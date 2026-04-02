"""
Cross-book arbitrage scan: best price per side across books.

Theoretical arb when the sum of implied probabilities (best home + best away, etc.)
is strictly < 1.0 — before stake sizing, limits, and fees.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services import math_odds
from services.odds_repository import get_odds_for_game, list_games

_EPS = 1e-9

_MARKETS = frozenset({"moneyline", "total", "spread"})


def _imp(am: int) -> float:
    return math_odds.american_to_implied_probability(int(am))


def _moneyline_scan(game_id: str, rows: list[dict]) -> dict[str, Any] | None:
    best_home: dict[str, Any] | None = None
    best_away: dict[str, Any] | None = None
    for r in rows:
        book = r["sportsbook"]
        ml = r.get("markets") or {}
        m = ml.get("moneyline") or {}
        ho, ao = m.get("home_odds"), m.get("away_odds")
        if ho is not None and ho != 0:
            p = _imp(ho)
            if best_home is None or p < best_home["implied_probability"]:
                best_home = {
                    "sportsbook": book,
                    "american": int(ho),
                    "implied_probability": round(p, 6),
                }
        if ao is not None and ao != 0:
            p = _imp(ao)
            if best_away is None or p < best_away["implied_probability"]:
                best_away = {
                    "sportsbook": book,
                    "american": int(ao),
                    "implied_probability": round(p, 6),
                }
    if not best_home or not best_away:
        return None
    s = best_home["implied_probability"] + best_away["implied_probability"]
    return {
        "game_id": game_id,
        "market": "moneyline",
        "has_arbitrage": s < 1.0 - _EPS,
        "implied_probability_sum": round(s, 6),
        "edge_percent": round(max(0.0, (1.0 - s) * 100), 4),
        "home_leg": best_home,
        "away_leg": best_away,
        "cross_book": best_home["sportsbook"] != best_away["sportsbook"],
    }


def _total_scans(game_id: str, rows: list[dict]) -> list[dict[str, Any]]:
    by_line: dict[float, list[dict]] = defaultdict(list)
    for r in rows:
        tot = (r.get("markets") or {}).get("total") or {}
        line = tot.get("line")
        if line is None:
            continue
        key = round(float(line), 2)
        by_line[key].append(r)

    out: list[dict[str, Any]] = []
    for line_val, bucket in by_line.items():
        best_over = None
        best_under = None
        for r in bucket:
            book = r["sportsbook"]
            tot = (r.get("markets") or {}).get("total") or {}
            oo, uo = tot.get("over_odds"), tot.get("under_odds")
            if oo is not None and oo != 0:
                p = _imp(oo)
                if best_over is None or p < best_over["implied_probability"]:
                    best_over = {
                        "sportsbook": book,
                        "american": int(oo),
                        "implied_probability": round(p, 6),
                    }
            if uo is not None and uo != 0:
                p = _imp(uo)
                if best_under is None or p < best_under["implied_probability"]:
                    best_under = {
                        "sportsbook": book,
                        "american": int(uo),
                        "implied_probability": round(p, 6),
                    }
        if not best_over or not best_under:
            continue
        s = best_over["implied_probability"] + best_under["implied_probability"]
        if s >= 1.0 - _EPS:
            continue
        out.append(
            {
                "game_id": game_id,
                "market": "total",
                "total_line": line_val,
                "has_arbitrage": True,
                "implied_probability_sum": round(s, 6),
                "edge_percent": round((1.0 - s) * 100, 4),
                "over_leg": best_over,
                "under_leg": best_under,
                "cross_book": best_over["sportsbook"] != best_under["sportsbook"],
            }
        )
    return out


def _spread_scans(game_id: str, rows: list[dict]) -> list[dict[str, Any]]:
    by_key: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for r in rows:
        sp = (r.get("markets") or {}).get("spread") or {}
        hl, al = sp.get("home_line"), sp.get("away_line")
        if hl is None or al is None:
            continue
        key = (round(float(hl), 2), round(float(al), 2))
        by_key[key].append(r)

    out: list[dict[str, Any]] = []
    for (hl, al), bucket in by_key.items():
        best_home = None
        best_away = None
        for r in bucket:
            book = r["sportsbook"]
            sp = (r.get("markets") or {}).get("spread") or {}
            ho, ao = sp.get("home_odds"), sp.get("away_odds")
            if ho is not None and ho != 0:
                p = _imp(ho)
                if best_home is None or p < best_home["implied_probability"]:
                    best_home = {
                        "sportsbook": book,
                        "american": int(ho),
                        "implied_probability": round(p, 6),
                        "home_line": hl,
                        "away_line": al,
                    }
            if ao is not None and ao != 0:
                p = _imp(ao)
                if best_away is None or p < best_away["implied_probability"]:
                    best_away = {
                        "sportsbook": book,
                        "american": int(ao),
                        "implied_probability": round(p, 6),
                        "home_line": hl,
                        "away_line": al,
                    }
        if not best_home or not best_away:
            continue
        s = best_home["implied_probability"] + best_away["implied_probability"]
        if s >= 1.0 - _EPS:
            continue
        out.append(
            {
                "game_id": game_id,
                "market": "spread",
                "spread_home_line": hl,
                "spread_away_line": al,
                "has_arbitrage": True,
                "implied_probability_sum": round(s, 6),
                "edge_percent": round((1.0 - s) * 100, 4),
                "home_spread_leg": best_home,
                "away_spread_leg": best_away,
                "cross_book": best_home["sportsbook"] != best_away["sportsbook"],
            }
        )
    return out


def scan_cross_book_arbitrage(
    game_id: str | None = None,
    include_markets: list[str] | None = None,
) -> dict[str, Any]:
    """
    Scan slate (or one game) for strict two-way arb using best implied per side across books.
    Only returns rows where implied sum < 1.
    """
    markets = include_markets if include_markets else ["moneyline", "total", "spread"]
    bad = [m for m in markets if m not in _MARKETS]
    if bad:
        return {"error": f"Unknown market(s): {bad}. Use: moneyline, total, spread."}

    gids = [game_id] if game_id else [g["game_id"] for g in list_games()]
    opportunities: list[dict[str, Any]] = []

    for gid in gids:
        rows = get_odds_for_game(gid)
        if not rows:
            if game_id:
                return {"error": f"Unknown game_id: {game_id}", "opportunities": []}
            continue
        if "moneyline" in markets:
            m = _moneyline_scan(gid, rows)
            if m and m.get("has_arbitrage"):
                opportunities.append(m)
        if "total" in markets:
            opportunities.extend(_total_scans(gid, rows))
        if "spread" in markets:
            opportunities.extend(_spread_scans(gid, rows))

    return {
        "interpretation": (
            "Each opportunity uses the lowest implied probability (best price) on each side across books "
            "for the same market structure (same total line or spread pair). Sum < 1 implies theoretical "
            "arbitrage before stake weights, limits, and line movement. Verify cross_book for true "
            "two-book execution."
        ),
        "game_id_filter": game_id,
        "markets_scanned": markets,
        "opportunities": opportunities,
        "opportunity_count": len(opportunities),
    }
