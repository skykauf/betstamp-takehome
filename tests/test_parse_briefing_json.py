"""Briefing JSON may include confidence fields; parser accepts full object."""

from __future__ import annotations

import json

from services.agent import parse_briefing_json


def test_parse_briefing_with_confidence_fields():
    payload = {
        "market_overview": "Slate looks efficient.",
        "market_overview_confidence": "medium",
        "market_overview_confidence_basis": "Scanned 10 games via list_games only.",
        "anomalies": [
            {
                "summary": "Stale line",
                "game_id": "nba_x",
                "sportsbook": "BookA",
                "detail": "6h behind median",
                "confidence": "high",
                "confidence_basis": "list_last_updated_for_staleness_check",
            }
        ],
        "value_opportunities": [
            {
                "summary": "Best away ML",
                "game_id": "nba_x",
                "market": "moneyline_away",
                "math": "100/(170+100)",
                "confidence": "high",
                "confidence_basis": "best_line_for_market",
            }
        ],
        "sportsbook_quality": [
            {
                "rank": 1,
                "sportsbook": "Pinnacle",
                "rationale": "Tight margins",
                "confidence": "low",
                "confidence_basis": "Subjective read across sampled rows",
            }
        ],
    }
    text = json.dumps(payload)
    out = parse_briefing_json(text)
    assert out == payload
    assert out["anomalies"][0]["confidence"] == "high"
