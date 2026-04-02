"""OpenAI tool-calling loop for briefing and chat."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from services import database, math_odds, odds_repository
from services.config import openai_api_key, openai_model

MAX_TOOL_ITERATIONS = 24
SQL_ROW_CAP = 200

SYSTEM_PROMPT = """You are a senior sports betting markets analyst assistant for Betstamp.

You work ONLY from:
- Tool results that read the sample NBA odds dataset (JSON file on the server, optionally mirrored in Postgres).
- Arithmetic you obtain via the provided math tools (implied probability, vig, fair probabilities).

Rules:
- Use tools to fetch data in small slices (e.g. one game_id at a time). Never invent games, books, or prices.
- When you cite numbers, use the math tools and show the formulas in prose (American negative: |odds|/(|odds|+100); positive: 100/(odds+100); vig = implied sum − 1).
- If the user asks for something not in the data, say you do not have it.
- When DATABASE tools are available, you may run SELECT queries against public odds tables to aggregate across books (e.g. stale lines by last_updated).

Final response format:
When you are done with tools, respond with a single JSON object (no markdown fences) containing:
{
  "market_overview": string,
  "anomalies": [ { "summary": string, "game_id": string|null, "sportsbook": string|null, "detail": string } ],
  "value_opportunities": [ { "summary": string, "game_id": string, "market": string, "math": string } ],
  "sportsbook_quality": [ { "rank": number, "sportsbook": string, "rationale": string } ]
}

For follow-up chat (shorter answers), you may use plain text instead of that JSON if the user asks a simple question — but for the initial daily briefing request, always use the JSON object above.
"""


BRIEFING_USER = """Generate today's market briefing for the sample slate.
Use tools to inspect games and lines, detect stale last_updated outliers and off-market prices vs other books, compute vig and implieds where helpful, and rank sportsbooks by how tight/reasonable their prices look on this slate.
End with the JSON object specified in your instructions."""


def _tool_definitions(include_sql: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_dataset_meta",
                "description": "Metadata about the loaded odds file (record count, notes, generated timestamp).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_games",
                "description": "List all games in the sample with game_id, teams, commence_time.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_odds_for_game",
                "description": "Return all sportsbook rows for one game_id (spreads, moneylines, totals, last_updated).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "e.g. nba_20260320_lal_bos",
                        }
                    },
                    "required": ["game_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_last_updated_for_staleness_check",
                "description": "Flat list of (game_id, sportsbook, last_updated) for comparing timestamps across the slate.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "american_to_implied",
                "description": "Convert one American odds price to implied probability (decimal 0–1).",
                "parameters": {
                    "type": "object",
                    "properties": {"american": {"type": "integer"}},
                    "required": ["american"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_two_sided_market",
                "description": "Implied probs, vig, and fair (no-vig) probabilities for both sides of a market.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "odds_side_a": {"type": "integer"},
                        "odds_side_b": {"type": "integer"},
                    },
                    "required": ["odds_side_a", "odds_side_b"],
                },
            },
        },
    ]
    if include_sql:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "run_readonly_sql",
                    "description": (
                        "Run a single SELECT against Postgres. Tables: odds_snapshots(id, label, loaded_at); "
                        "odds_lines(id, snapshot_id, game_id, sport, home_team, away_team, commence_time, "
                        "sportsbook, markets jsonb, last_updated). Use snapshot label 'default' or join on latest."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "Single SELECT only; no semicolons; no write DDL/DML.",
                            }
                        },
                        "required": ["sql"],
                    },
                },
            }
        )
    return tools


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "get_dataset_meta":
        return odds_repository.dataset_meta()
    if name == "list_games":
        return {"games": odds_repository.list_games()}
    if name == "get_odds_for_game":
        gid = arguments["game_id"]
        lines = odds_repository.get_odds_for_game(gid)
        if not lines:
            return {"error": f"Unknown game_id: {gid}", "lines": []}
        return {"game_id": gid, "line_count": len(lines), "lines": lines}
    if name == "list_last_updated_for_staleness_check":
        rows = odds_repository.all_last_updated_times()
        return {
            "entries": [
                {"game_id": g, "sportsbook": s, "last_updated": t} for g, s, t in rows
            ]
        }
    if name == "american_to_implied":
        p = math_odds.american_to_implied_probability(int(arguments["american"]))
        return {"american": arguments["american"], "implied_probability": p}
    if name == "compute_two_sided_market":
        return math_odds.two_sided_market(
            int(arguments["odds_side_a"]), int(arguments["odds_side_b"])
        )
    if name == "run_readonly_sql":
        rows = database.run_readonly_sql(arguments["sql"])
        truncated = len(rows) > SQL_ROW_CAP
        return {
            "rows": rows[:SQL_ROW_CAP],
            "row_count": len(rows),
            "truncated": truncated,
        }
    return {"error": f"unknown tool: {name}"}


def _append_assistant_with_tools(msg: Any, out: list[dict[str, Any]]) -> None:
    tc = msg.tool_calls or []
    out.append(
        {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "arguments": t.function.arguments or "{}",
                    },
                }
                for t in tc
            ],
        }
    )


def run_agent(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """
    Returns (updated_messages, final_assistant_text, tool_trace).
    """
    client = OpenAI(api_key=openai_api_key())
    model = openai_model()
    include_sql = database.db_available()
    tools = _tool_definitions(include_sql=include_sql)
    msgs = [dict(m) for m in messages]
    trace: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": msgs,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        if msg.tool_calls:
            _append_assistant_with_tools(msg, msgs)
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = _call_tool(name, args)
                except Exception as e:
                    result = {"error": str(e)}
                trace.append(
                    {
                        "tool": name,
                        "arguments": args,
                        "ok": "error" not in result,
                    }
                )
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            continue

        text = (msg.content or "").strip()
        msgs.append({"role": "assistant", "content": msg.content or ""})
        return msgs, text, trace

    msgs.append(
        {
            "role": "assistant",
            "content": '{"error":"max tool iterations exceeded"}',
        }
    )
    return msgs, msgs[-1]["content"], trace


def parse_briefing_json(final_text: str) -> dict[str, Any] | None:
    try:
        return json.loads(final_text)
    except json.JSONDecodeError:
        return None
