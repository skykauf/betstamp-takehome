from __future__ import annotations

import os
from functools import lru_cache


@lru_cache
def openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


@lru_cache
def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()


def database_url() -> str | None:
    u = os.environ.get("DATABASE_URL", "").strip()
    return u or None


def cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]
