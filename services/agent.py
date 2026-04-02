"""OpenAI tool-calling loop for briefing and chat."""

from __future__ import annotations

import json
from typing import Any, Iterator

from openai import OpenAI

from services import arbitrage, best_line, database, math_odds, odds_repository
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
- Use **best_line_for_market** when comparing prices across books for a specific game and side (spread / ML / total).
- Use **scan_cross_book_arbitrage** to find strict two-way arbs (best implied per side across books; sum < 1) on moneyline, totals (matching line), and spreads (matching pair).

Follow-up chat — grounding (mandatory):
- If the user asks about **staleness, last_updated, which book is oldest/newest, time gaps, specific odds, vig, best line, a named game or sportsbook, or any fact verifiable from the dataset**, you **must call at least one tool in that turn** before answering. Do **not** answer those questions from memory of the earlier briefing alone.
- For **purely meta** questions (e.g. how the app works, what you can do) with no numeric or book-specific claims, tools are optional.
- When you give book- or time-specific answers after using tools, cite what you queried (e.g. staleness list, best_line result).

Final response format (initial briefing only):
When you are done with tools for the **daily briefing** request, respond with a single JSON object (no markdown fences) containing:
{
  "market_overview": string,
  "market_overview_confidence": "high"|"medium"|"low"|null,
  "market_overview_confidence_basis": string|null,
  "anomalies": [ {
    "summary": string, "game_id": string|null, "sportsbook": string|null, "detail": string,
    "confidence": "high"|"medium"|"low", "confidence_basis": string
  } ],
  "value_opportunities": [ {
    "summary": string, "game_id": string, "market": string, "math": string,
    "confidence": "high"|"medium"|"low", "confidence_basis": string
  } ],
  "sportsbook_quality": [ {
    "rank": number, "sportsbook": string, "rationale": string,
    "confidence": "high"|"medium"|"low"|null, "confidence_basis": string|null
  } ]
}

**Confidence (required on anomalies and value_opportunities):** Set **confidence** and **confidence_basis** from tool evidence, not intuition alone.
- **high** — Direct proof from tools (e.g. concrete last_updated gaps vs staleness list, computed implieds/vig, arb scan numeric result).
- **medium** — Clear comparison but incomplete coverage of the slate or one book missing.
- **low** — Heuristic, thin data, or subjective read.
Never label **high** unless **confidence_basis** names the supporting tool output or numbers.

**Optional:** **market_overview_confidence** (+ basis) for the slate summary; per-row **confidence** on **sportsbook_quality** (rankings are subjective — often medium/low).

For **follow-up** messages, reply in **plain text** (not that JSON), but still obey the tool-use rules above when the question is data-grounded.
"""


BRIEFING_USER = """Generate today's market briefing for the sample slate.
Use tools to inspect games and lines, detect stale last_updated outliers and off-market prices vs other books, compute vig and implieds where helpful, use best_line_for_market where useful for value angles, call scan_cross_book_arbitrage (whole slate or per game) to report any cross-book arbitrage-style edges, and rank sportsbooks by how tight/reasonable their prices look on this slate.
Every anomaly and value_opportunity row must include confidence + confidence_basis tied to tool evidence. Optionally add market_overview_confidence fields and per-book confidence on rankings.
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
                "name": "best_line_for_market",
                "description": (
                    "Across all sportsbooks for one game, find the best American odds for a single side. "
                    "Best = lowest implied probability (highest payout). Returns best book plus full ranking."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "e.g. nba_20260320_lal_bos",
                        },
                        "market_side": {
                            "type": "string",
                            "enum": [
                                "spread_home",
                                "spread_away",
                                "moneyline_home",
                                "moneyline_away",
                                "total_over",
                                "total_under",
                            ],
                            "description": "Which side of which market to optimize.",
                        },
                    },
                    "required": ["game_id", "market_side"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_cross_book_arbitrage",
                "description": (
                    "Find theoretical two-way arbitrage: for each outcome, take the best (lowest implied "
                    "prob) price across sportsbooks. If those implieds sum to under 1.0, list the opportunity. "
                    "Supports moneyline; totals and spreads only when the line/pair matches within the game. "
                    "Omit game_id to scan all games in the sample."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Optional. e.g. nba_20260320_lal_bos. Leave empty to scan entire slate.",
                        },
                        "include_markets": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["moneyline", "total", "spread"],
                            },
                            "description": "Defaults to all three if omitted or empty.",
                        },
                    },
                },
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
    if name == "best_line_for_market":
        return best_line.best_line_for_side(
            str(arguments["game_id"]),
            str(arguments["market_side"]),
        )
    if name == "scan_cross_book_arbitrage":
        gid = arguments.get("game_id")
        if isinstance(gid, str) and gid.strip() == "":
            gid = None
        inc = arguments.get("include_markets")
        if isinstance(inc, list) and len(inc) == 0:
            inc = None
        return arbitrage.scan_cross_book_arbitrage(
            game_id=gid,
            include_markets=inc,
        )
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


def _parse_tool_arguments(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _tool_calls_from_api_message(msg: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "type": "function",
            "function": {
                "name": t.function.name,
                "arguments": t.function.arguments or "{}",
            },
        }
        for t in (msg.tool_calls or [])
    ]


def _chat_completion_kwargs(
    model: str, msgs: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": model, "messages": msgs}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return kwargs


def _run_tool_calls(
    msgs: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    assistant_content: str | None,
    tool_call_dicts: list[dict[str, Any]],
    *,
    collect_tool_sse_events: bool,
) -> list[dict[str, Any]]:
    """Append assistant+tool messages; optionally collect ``tool`` SSE-shaped events."""
    sse_tool_events: list[dict[str, Any]] = []
    msgs.append(
        {
            "role": "assistant",
            "content": assistant_content if assistant_content else None,
            "tool_calls": tool_call_dicts,
        }
    )
    for tcd in tool_call_dicts:
        name = tcd["function"]["name"]
        args = _parse_tool_arguments(tcd["function"].get("arguments"))
        if collect_tool_sse_events:
            sse_tool_events.append({"event": "tool", "name": name, "arguments": args})
        try:
            result = _call_tool(name, args)
        except Exception as e:
            result = {"error": str(e)}
        trace.append(
            {"tool": name, "arguments": args, "ok": "error" not in result}
        )
        msgs.append(
            {
                "role": "tool",
                "tool_call_id": tcd["id"],
                "content": json.dumps(result, default=str),
            }
        )
    return sse_tool_events


def _max_iterations_payload() -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": '{"error":"max tool iterations exceeded"}',
    }


def run_agent(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """
    Returns (updated_messages, final_assistant_text, tool_trace).
    """
    client = OpenAI(api_key=openai_api_key())
    model = openai_model()
    include_sql = database.db_available()
    tool_defs = _tool_definitions(include_sql=include_sql)
    msgs = [dict(m) for m in messages]
    trace: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs = _chat_completion_kwargs(model, msgs, tool_defs)
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_call_dicts = _tool_calls_from_api_message(msg)

        if tool_call_dicts:
            _run_tool_calls(
                msgs,
                trace,
                msg.content,
                tool_call_dicts,
                collect_tool_sse_events=False,
            )
            continue

        text = (msg.content or "").strip()
        msgs.append({"role": "assistant", "content": msg.content or ""})
        return msgs, text, trace

    msgs.append(_max_iterations_payload())
    return msgs, msgs[-1]["content"], trace


class _StreamToolAccumulator:
    """Merge streamed tool_call fragments (by index) into API-shaped tool_calls."""

    def __init__(self) -> None:
        self._by_index: dict[int, dict[str, str]] = {}

    def feed(self, delta_tool_calls: list[Any] | None) -> None:
        if not delta_tool_calls:
            return
        for tc in delta_tool_calls:
            idx = tc.index
            if idx not in self._by_index:
                self._by_index[idx] = {"id": "", "name": "", "arguments": ""}
            if getattr(tc, "id", None):
                self._by_index[idx]["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    self._by_index[idx]["name"] = fn.name
                if getattr(fn, "arguments", None):
                    self._by_index[idx]["arguments"] += fn.arguments

    def as_api_tool_calls(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx in sorted(self._by_index.keys()):
            t = self._by_index[idx]
            out.append(
                {
                    "id": t["id"],
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "arguments": t["arguments"] or "{}",
                    },
                }
            )
        return out


def run_agent_stream(
    messages: list[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """
    Stream one chat turn (same tool loop as run_agent).

    Yields SSE-friendly dicts:
    - {"event": "delta", "text": str} — final-assistant tokens only (suppressed during tool rounds)
    - {"event": "tool", "name": str, "arguments": dict} — before each tool execution
    - {"event": "done", "reply": str, "tool_trace": list, "messages": list} — terminal; includes full messages for persistence
    - {"event": "error", "message": str} — terminal without messages
    """
    client = OpenAI(api_key=openai_api_key())
    model = openai_model()
    include_sql = database.db_available()
    tool_defs = _tool_definitions(include_sql=include_sql)
    msgs: list[dict[str, Any]] = [dict(m) for m in messages]
    trace: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs = _chat_completion_kwargs(model, msgs, tool_defs)
        kwargs["stream"] = True

        try:
            stream = client.chat.completions.create(**kwargs)
        except Exception as e:
            yield {"event": "error", "message": str(e)}
            return

        accum = _StreamToolAccumulator()
        content_parts: list[str] = []
        saw_tool_delta = False

        for chunk in stream:
            if not chunk.choices:
                continue
            ch = chunk.choices[0]
            d = ch.delta
            if d is None:
                continue
            if d.tool_calls:
                saw_tool_delta = True
                accum.feed(d.tool_calls)
            if d.content and not saw_tool_delta:
                content_parts.append(d.content)
                yield {"event": "delta", "text": d.content}

        full_content = "".join(content_parts)
        tool_call_dicts = accum.as_api_tool_calls()

        if tool_call_dicts:
            for ev in _run_tool_calls(
                msgs,
                trace,
                full_content or None,
                tool_call_dicts,
                collect_tool_sse_events=True,
            ):
                yield ev
            continue

        msgs.append({"role": "assistant", "content": full_content or ""})
        text = full_content.strip()
        yield {
            "event": "done",
            "reply": text,
            "tool_trace": trace,
            "messages": msgs,
        }
        return

    msgs.append(_max_iterations_payload())
    yield {
        "event": "done",
        "reply": msgs[-1]["content"],
        "tool_trace": trace,
        "messages": msgs,
    }


def parse_briefing_json(final_text: str) -> dict[str, Any] | None:
    try:
        return json.loads(final_text)
    except json.JSONDecodeError:
        return None
