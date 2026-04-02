"""FastAPI app — Vercel entrypoint (app:app)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.agent import BRIEFING_USER, SYSTEM_PROMPT, parse_briefing_json, run_agent
from services.config import cors_origins
from services.odds_seed import ensure_odds_seeded
from services.thread_store import create_thread, load_messages, save_messages

ROOT = Path(__file__).resolve().parent
# UI lives under static/ (not public/) so Vercel does not deploy a static-only shell
# that never routes /api/* to the Python function.
STATIC = ROOT / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on each serverless cold start (e.g. first site hit on Vercel): schema + idempotent seed.
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
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise


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
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def serve_index():
    index = STATIC / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"message": "Odds Agent API", "docs": "/docs"}
