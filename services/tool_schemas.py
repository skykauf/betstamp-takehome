"""OpenAI function-calling schema fragments (DRY tool definitions)."""

from __future__ import annotations

from typing import Any


def function_tool(
    name: str,
    description: str,
    *,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        params["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params,
        },
    }
