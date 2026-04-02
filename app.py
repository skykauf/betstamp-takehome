"""FastAPI app — Vercel entrypoint (app:app)."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.agent import (
    BRIEFING_USER,
    SYSTEM_PROMPT,
    parse_briefing_json,
    run_agent,
)
from services.config import cors_origins
from services.sse import (
    AgentStreamOutcome,
    SSE_MEDIA_TYPE,
    STREAMING_HEADERS,
    format_sse_event,
    iter_agent_sse_events,
)
from services.odds_seed import ensure_odds_seeded
from services.openai_errors import (
    raise_http_if_missing_openai_key,
    sse_error_message,
)
from services.thread_store import create_thread, load_messages, save_messages

ROOT = Path(__file__).resolve().parent
# UI must live outside public/: Vercel does not ship public/ inside the Python function
# bundle, so FileResponse(public/index.html) fails at runtime and falls back to JSON.
TEMPLATES = ROOT / "templates"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on each serverless cold start (e.g. first site hit on Vercel): schema + idempotent seed.
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        logger.warning(
            "OPENAI_API_KEY is unset; /api/brief and /api/chat will error until configured."
        )
    result = await asyncio.to_thread(ensure_odds_seeded)
    if result.get("status") == "error":
        logger.warning("ensure_odds_seeded: %s", result.get("error"))
    else:
        logger.info("ensure_odds_seeded: %s", result)
    yield


app = FastAPI(
    title="Betstamp Odds Agent API",
    lifespan=lifespan,
    redirect_slashes=False,
)

_origins = cors_origins()
_allow_credentials = False if _origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatBody(BaseModel):
    thread_id: str = Field(..., description="UUID from POST /api/brief")
    message: str = Field(..., min_length=1)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/brief")
def api_brief():
    try:
        thread_id = create_thread()
        messages: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": BRIEFING_USER},
        ]
        updated, final_text, tool_trace = run_agent(messages)
        save_messages(thread_id, updated)
        structured = parse_briefing_json(final_text)
        return {
            "thread_id": thread_id,
            "briefing": structured if structured is not None else {"raw_markdown": final_text},
            "tool_trace": tool_trace,
        }
    except RuntimeError as e:
        raise_http_if_missing_openai_key(e)
        raise
    except Exception:
        logger.exception("api_brief failed")
        raise


@app.post("/api/brief/stream")
def api_brief_stream():
    """SSE: same tool loop as /api/brief; streams tool/delta events, then brief_done with parsed JSON."""

    def event_gen():
        tid = create_thread()
        msgs: list = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": BRIEFING_USER},
        ]
        outcome = AgentStreamOutcome()
        yield format_sse_event({"event": "start", "thread_id": tid})
        try:
            for line in iter_agent_sse_events(
                msgs, forward_terminal_done=False, outcome=outcome
            ):
                yield line
        except RuntimeError as e:
            yield format_sse_event({"event": "error", "message": sse_error_message(e)})
            return
        except Exception as e:
            logger.exception("api_brief_stream failed")
            yield format_sse_event({"event": "error", "message": sse_error_message(e)})
            return

        if outcome.final_messages is not None:
            save_messages(tid, outcome.final_messages)
            structured = parse_briefing_json(outcome.last_reply)
            briefing_payload = (
                structured
                if structured is not None
                else {"raw_markdown": outcome.last_reply}
            )
            yield format_sse_event(
                {
                    "event": "brief_done",
                    "thread_id": tid,
                    "briefing": briefing_payload,
                    "tool_trace": outcome.last_trace,
                }
            )

    return StreamingResponse(event_gen(), media_type=SSE_MEDIA_TYPE, headers=STREAMING_HEADERS)


@app.post("/api/chat")
def api_chat(body: ChatBody):
    existing = load_messages(body.thread_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    messages = list(existing)
    messages.append({"role": "user", "content": body.message})
    try:
        updated, final_text, tool_trace = run_agent(messages)
        save_messages(body.thread_id, updated)
        return {"reply": final_text, "tool_trace": tool_trace}
    except RuntimeError as e:
        raise_http_if_missing_openai_key(e)
        raise
    except Exception:
        logger.exception("api_chat failed")
        raise


@app.post("/api/chat/stream")
def api_chat_stream(body: ChatBody):
    existing = load_messages(body.thread_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    messages = list(existing)
    messages.append({"role": "user", "content": body.message})

    def event_gen():
        outcome = AgentStreamOutcome()
        try:
            for line in iter_agent_sse_events(
                messages, forward_terminal_done=True, outcome=outcome
            ):
                yield line
        except RuntimeError as e:
            yield format_sse_event({"event": "error", "message": sse_error_message(e)})
        except Exception as e:
            logger.exception("api_chat_stream failed")
            yield format_sse_event({"event": "error", "message": sse_error_message(e)})
        finally:
            if outcome.final_messages is not None:
                save_messages(body.thread_id, outcome.final_messages)

    return StreamingResponse(event_gen(), media_type=SSE_MEDIA_TYPE, headers=STREAMING_HEADERS)


if TEMPLATES.is_dir():
    app.mount("/static", StaticFiles(directory=str(TEMPLATES)), name="static")


@app.get("/")
async def serve_index():
    index = TEMPLATES / "index.html"
    if index.is_file():
        return FileResponse(index)
    logger.error("Missing templates/index.html at %s", index)
    return {"message": "Odds Agent API", "docs": "/docs", "error": "templates/index.html missing"}
