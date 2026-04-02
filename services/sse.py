"""SSE helpers for agent streaming endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator

from services.agent import run_agent_stream

SSE_MEDIA_TYPE = "text/event-stream"

STREAMING_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@dataclass
class AgentStreamOutcome:
    """Filled when the inner agent stream emits a terminal ``done`` event."""

    final_messages: list[dict[str, Any]] | None = None
    last_reply: str = ""
    last_trace: list[Any] = field(default_factory=list)


def iter_agent_sse_events(
    messages: list[dict[str, Any]],
    *,
    forward_terminal_done: bool,
    outcome: AgentStreamOutcome,
) -> Iterator[str]:
    """
    Map ``run_agent_stream`` dict events to SSE lines; capture terminal state on ``done``.

    If ``forward_terminal_done`` is False (briefing), the ``done`` event is not sent to the client.
    """
    for evt in run_agent_stream(messages):
        if evt.get("event") == "done":
            outcome.final_messages = evt.get("messages")
            outcome.last_reply = evt.get("reply", "") or ""
            outcome.last_trace = evt.get("tool_trace") or []
            if forward_terminal_done:
                yield format_sse_event(evt)
            continue
        yield format_sse_event(evt)
