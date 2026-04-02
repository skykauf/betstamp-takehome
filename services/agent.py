"""OpenAI tool-calling loop for briefing and chat."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from openai import OpenAI

from services import arbitrage, best_line, database, math_odds, odds_repository
from services.briefing_schema import parse_briefing_json
from services.config import max_tool_iterations, openai_api_key, openai_model
from services.tool_schemas import function_tool

logger = logging.getLogger(__name__)

SQL_ROW_CAP = 200

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8").strip()
BRIEFING_USER = (_PROMPTS_DIR / "briefing_user.md").read_text(encoding="utf-8").strip()


def _tool_definitions(include_sql: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        function_tool(
            "get_dataset_meta",
            "Metadata about the loaded odds file (record count, notes, generated timestamp).",
        ),
        function_tool(
            "list_games",
            "List all games in the sample with game_id, teams, commence_time.",
        ),
        function_tool(
            "get_odds_for_game",
            "Return all sportsbook rows for one game_id (spreads, moneylines, totals, last_updated).",
            properties={
                "game_id": {
                    "type": "string",
                    "description": "e.g. nba_20260320_lal_bos",
                }
            },
            required=["game_id"],
        ),
        function_tool(
            "list_last_updated_for_staleness_check",
            "Flat list of (game_id, sportsbook, last_updated) for comparing timestamps across the slate.",
        ),
        function_tool(
            "best_line_for_market",
            (
                "Across all sportsbooks for one game, find the best American odds for a single side. "
                "Best = lowest implied probability (highest payout). Returns best book plus full ranking."
            ),
            properties={
                "game_id": {"type": "string", "description": "e.g. nba_20260320_lal_bos"},
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
            required=["game_id", "market_side"],
        ),
        function_tool(
            "scan_cross_book_arbitrage",
            (
                "Find theoretical two-way arbitrage: for each outcome, take the best (lowest implied "
                "prob) price across sportsbooks. If those implieds sum to under 1.0, list the opportunity. "
                "Supports moneyline; totals and spreads only when the line/pair matches within the game. "
                "Omit game_id to scan all games in the sample."
            ),
            properties={
                "game_id": {
                    "type": "string",
                    "description": "Optional. e.g. nba_20260320_lal_bos. Leave empty to scan entire slate.",
                },
                "include_markets": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["moneyline", "total", "spread"]},
                    "description": "Defaults to all three if omitted or empty.",
                },
            },
        ),
        function_tool(
            "american_to_implied",
            "Convert one American odds price to implied probability (decimal 0–1).",
            properties={"american": {"type": "integer"}},
            required=["american"],
        ),
        function_tool(
            "compute_two_sided_market",
            "Implied probs, vig, and fair (no-vig) probabilities for both sides of a market.",
            properties={
                "odds_side_a": {"type": "integer"},
                "odds_side_b": {"type": "integer"},
            },
            required=["odds_side_a", "odds_side_b"],
        ),
    ]
    if include_sql:
        tools.append(
            function_tool(
                "run_readonly_sql",
                (
                    "Run a single SELECT against Postgres. Tables: odds_snapshots(id, label, loaded_at); "
                    "odds_lines(id, snapshot_id, game_id, sport, home_team, away_team, commence_time, "
                    "sportsbook, markets jsonb, last_updated). Use snapshot label 'default' or join on latest."
                ),
                properties={
                    "sql": {
                        "type": "string",
                        "description": "Single SELECT only; no semicolons; no write DDL/DML.",
                    }
                },
                required=["sql"],
            )
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

    for _ in range(max_tool_iterations()):
        kwargs = _chat_completion_kwargs(model, msgs, tool_defs)
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            logger.exception("OpenAI completion failed")
            raise
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

    for _ in range(max_tool_iterations()):
        kwargs = _chat_completion_kwargs(model, msgs, tool_defs)
        kwargs["stream"] = True

        try:
            stream = client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.exception("OpenAI streaming completion failed")
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
