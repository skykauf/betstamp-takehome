"""Parse and lightly validate briefing JSON from the model."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

ConfidenceLevel = Literal["high", "medium", "low"]


class BriefingPayload(BaseModel):
    """Expected briefing shape; unknown top-level keys preserved via extra."""

    model_config = ConfigDict(extra="allow")

    market_overview: str | None = None
    market_overview_confidence: ConfidenceLevel | None = None
    market_overview_confidence_basis: str | None = None
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    value_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    sportsbook_quality: list[dict[str, Any]] = Field(default_factory=list)


def parse_briefing_json(final_text: str) -> dict[str, Any] | None:
    """
    Parse model output as JSON; validate known fields with Pydantic.
    On validation failure, log and return the raw dict so the UI can still render.
    """
    try:
        data = json.loads(final_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        model = BriefingPayload.model_validate(data)
        out = model.model_dump(mode="json", exclude_none=False)
        extra = model.__pydantic_extra__ or {}
        for k, v in extra.items():
            out[k] = v
        return out
    except ValidationError as e:
        logger.warning("Briefing JSON schema soft-fail: %s", e)
        return data
