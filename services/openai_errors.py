"""Map OpenAI / config errors to HTTP and SSE payloads."""

from __future__ import annotations

from fastapi import HTTPException


def is_missing_openai_key_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and "OPENAI_API_KEY" in str(exc)


def raise_http_if_missing_openai_key(exc: RuntimeError) -> None:
    """Re-raise as HTTP 503 when the API key is missing; otherwise do not return."""
    if is_missing_openai_key_error(exc):
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def sse_error_message(exc: BaseException) -> str:
    return str(exc)
