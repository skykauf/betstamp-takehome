"""Briefing JSON validation (Pydantic soft-fail)."""

from __future__ import annotations

import json

from services.briefing_schema import parse_briefing_json


def test_parse_briefing_valid_normalizes():
    payload = {
        "market_overview": "Hi",
        "market_overview_confidence": "high",
        "anomalies": [{"summary": "a", "confidence": "low", "confidence_basis": "x"}],
        "value_opportunities": [],
        "sportsbook_quality": [],
        "extra_root_key": 1,
    }
    text = json.dumps(payload)
    out = parse_briefing_json(text)
    assert out is not None
    assert out["market_overview"] == "Hi"
    assert out["extra_root_key"] == 1


def test_parse_briefing_invalid_shape_returns_raw_dict():
    """Wrong types: validation fails; caller still gets the parsed dict."""
    bad = {"anomalies": "not-a-list", "market_overview": "x"}
    out = parse_briefing_json(json.dumps(bad))
    assert out == bad
