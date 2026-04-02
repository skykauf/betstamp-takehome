"""Streaming tool-call fragment merge (no live API)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from services.agent import _StreamToolAccumulator


def test_stream_tool_accumulator_merges_name_and_arguments():
    a = _StreamToolAccumulator()
    a.feed(
        [
            SimpleNamespace(
                index=0,
                id="call_abc",
                function=SimpleNamespace(name="list_games", arguments=""),
            )
        ]
    )
    a.feed(
        [
            SimpleNamespace(
                index=0,
                id=None,
                function=SimpleNamespace(name=None, arguments='{"foo":'),
            )
        ]
    )
    a.feed(
        [
            SimpleNamespace(
                index=0,
                id=None,
                function=SimpleNamespace(name=None, arguments=" 1}"),
            )
        ]
    )
    out = a.as_api_tool_calls()
    assert len(out) == 1
    assert out[0]["id"] == "call_abc"
    assert out[0]["function"]["name"] == "list_games"
    assert json.loads(out[0]["function"]["arguments"]) == {"foo": 1}


def test_stream_tool_accumulator_multiple_indices():
    a = _StreamToolAccumulator()
    a.feed([SimpleNamespace(index=0, id="a", function=SimpleNamespace(name="x", arguments="{}"))])
    a.feed([SimpleNamespace(index=1, id="b", function=SimpleNamespace(name="y", arguments="{}"))])
    out = a.as_api_tool_calls()
    assert [o["function"]["name"] for o in out] == ["x", "y"]
