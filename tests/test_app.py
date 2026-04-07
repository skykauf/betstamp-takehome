"""FastAPI route smoke tests (no OpenAI calls)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False)
def test_healthz_ready(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
def test_healthz_not_ready_missing_key(client):
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()["detail"]
    assert body["ok"] is False
    assert body["has_openai_key"] is False


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False)
@patch("app.dataset_meta", side_effect=FileNotFoundError("Missing odds file"))
def test_healthz_not_ready_missing_dataset(_, client):
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()["detail"]
    assert body["ok"] is False
    assert body["dataset_loaded"] is False
    assert "Missing odds file" in body["dataset_error"]


def test_api_chat_unknown_thread(client):
    r = client.post(
        "/api/chat",
        json={"thread_id": str(uuid.uuid4()), "message": "hello"},
    )
    assert r.status_code == 404


@patch("app.run_agent")
def test_api_brief_json(mock_run, client):
    mock_run.return_value = (
        [],
        json.dumps(
            {
                "market_overview": "ok",
                "anomalies": [],
                "value_opportunities": [],
                "sportsbook_quality": [],
            }
        ),
        [],
    )
    r = client.post("/api/brief", json={})
    assert r.status_code == 200
    body = r.json()
    assert "thread_id" in body
    assert body["briefing"]["market_overview"] == "ok"


@patch("services.sse.run_agent_stream")
def test_api_brief_stream_emits_brief_done(mock_stream, client):
    tid = str(uuid.uuid4())

    def fake_stream(msgs):
        yield {"event": "tool", "name": "list_games", "arguments": {}}
        yield {
            "event": "done",
            "reply": '{"market_overview":"x","anomalies":[],"value_opportunities":[],"sportsbook_quality":[]}',
            "tool_trace": [{"tool": "list_games", "arguments": {}, "ok": True}],
            "messages": msgs
            + [{"role": "assistant", "content": '{"market_overview":"x"}'}],
        }

    mock_stream.side_effect = fake_stream

    with patch("app.create_thread", return_value=tid):
        r = client.post("/api/brief/stream", json={})
    assert r.status_code == 200
    text = r.text
    assert "brief_done" in text
    assert tid in text


@patch("app.load_messages")
@patch("app.run_agent")
def test_api_chat_json(mock_run, mock_load, client):
    mock_load.return_value = [{"role": "system", "content": "x"}]
    mock_run.return_value = (
        [],
        "plain reply",
        [{"tool": "list_games", "arguments": {}, "ok": True}],
    )
    tid = str(uuid.uuid4())
    r = client.post("/api/chat", json={"thread_id": tid, "message": "hi"})
    assert r.status_code == 200
    assert r.json()["reply"] == "plain reply"
    mock_run.assert_called_once()
