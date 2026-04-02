# Development log — Betstamp AI Odds Agent

This file is a **required deliverable** for the take-home. Reviewers weight it (~20%) alongside code: how AI tools were used, prompt iteration, trade-offs, and what we would improve with more time.

---

## How to use this log

**Timestamps:** Each log entry uses a level-2 heading with **UTC** time in ISO 8601:

`## YYYY-MM-DDTHH:MM:SSZ — Short title`

Add entries as you build. Each substantive session should touch at least one of:

1. **AI-assisted development** — What did you delegate to AI (Cursor, Copilot, ChatGPT, etc.)? What did you write by hand? What did AI get wrong that you fixed?
2. **Agent prompt / tool design** — How did the system prompt or tool schemas evolve? What did you try that failed?
3. **Key decisions** — LLM choice, stack, architecture — and **why**.
4. **Improvements backlog** — Specific next steps if you had another week.

---

## 2026-04-03T00:30:00Z — Vercel: explicit `builds`/`routes` + `public/` again

**What happened**

- After moving the UI to `static/` only, **production `GET /` became Vercel `NOT_FOUND`** — zero-config never attached a working Python route for this project, so nothing served `/` or `/api/*`.
- Added **`vercel.json`** (`version` 2) with `@vercel/python` **build** for root `app.py` and **routes**: `handle: filesystem` then **`/(.*)` → `app.py`**. Static files (e.g. `public/index.html`) are served from the edge first; API requests fall through to FastAPI.
- Restored **`public/index.html`** (same UI as before); `app.py` again uses `PUBLIC` for `FileResponse` / `StaticFiles` for local `uvicorn`.

**Dashboard**

- If deploys are still all 404, check Vercel **Output Directory** is empty and framework isn’t forcing a static export over the repo root.

---

## 2026-04-02T23:55:00Z — Fix production `/api/brief` 404 (static vs Python on Vercel)

**What happened**

- Production returned Vercel’s plain-text `NOT_FOUND` for `POST /api/brief` while `/` still loaded the UI — consistent with a **static-only edge** for `public/index.html` and no function route for `/api/*`.
- Moved the UI to **`static/index.html`** and serve it only through FastAPI (`FileResponse` + `StaticFiles` under `/static`). Removed the empty `public/` tree so deploys route API traffic to the Python runtime.
- Added root **`pyproject.toml`** (mirrors `requirements.txt`) to reinforce Python project detection; **`redirect_slashes=False`** on `FastAPI` for Vercel path normalization quirks.
- Frontend `fetch` helpers now surface non-JSON error bodies instead of `Unexpected token`.

---

## 2026-04-02T23:30:00Z — Vercel build: remove bad `functions` config

**What happened**

- Deploy failed: `The pattern app.py defined in functions doesn't match any Serverless Functions inside the api directory` — Vercel’s `vercel.json` `functions` map targets **`api/**/*.py`**, not root `app.py`.
- **Removed `vercel.json`** so Vercel uses **zero-config FastAPI** for root `app.py` (see [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)). Re-add a `vercel.json` only if we need custom routes; then use patterns that match real paths (e.g. under `api/`) or the legacy `builds`/`routes` style from Vercel docs.

---

## 2026-04-02T18:00:00Z — Auto-seed Postgres on Vercel cold start

**What happened**

- Added `services/odds_seed.py`: idempotent `CREATE TABLE IF NOT EXISTS` (same as `001_init.sql`) plus compare `COUNT(*)` on `odds_lines` for snapshot `default` vs `len(odds[])` in JSON; re-insert only when counts differ or `force=True`.
- Wrapped seed in `pg_advisory_xact_lock` so concurrent Vercel instances do not interleave deletes/inserts.
- Wired `ensure_odds_seeded()` into FastAPI `lifespan` in `app.py` (via `asyncio.to_thread`) so **each cold start** runs bootstrap/seed when `DATABASE_URL` is set — no manual Supabase SQL or `seed_odds.py` for normal deploys.
- Slimmed `scripts/seed_odds.py` to `ensure_odds_seeded(force=True)` for optional local refresh; README/AGENTS/migration header updated.

**Trade-off**

- App startup performs DDL on a fresh DB (acceptable for a dedicated Supabase project; migration file remains the human-readable reference if you want editor-only DDL instead).

---

## 2026-04-01T23:10:00Z — Python FastAPI on Vercel + Supabase SQL tool

**What happened**

- Wrote `README.md` with explicit objectives, constraints mapping, architecture (FastAPI → OpenAI tools → JSON + optional Postgres), env vars, local/Vercel/Supabase seed steps.
- Moved sample odds to `data/sample_odds_data.json`; `services/odds_repository.py` loads it with cached reads and exposes game/list helpers for tools.
- Implemented `services/agent.py`: OpenAI tool loop, JSON-shaped briefing contract, tools `get_dataset_meta`, `list_games`, `get_odds_for_game`, staleness list, math helpers, and `run_readonly_sql` when `DATABASE_URL` is set (`services/database.py` validates single `SELECT` only; caps rows).
- `supabase/migrations/001_init.sql` + `scripts/seed_odds.py` mirror JSON into `odds_lines` for analyst-style SQL.
- `services/thread_store.py` persists `messages` JSON on `chat_threads` when Postgres is configured; otherwise in-memory (single-instance demo).
- `app.py` + `static/index.html`: `/api/brief`, `/api/chat`, `/api/health`, minimal UI; `requirements.txt`, `pytest.ini`, tests for vig math and SQL validator.

**AI tools**

- Cursor drafted the scaffold, file layout, and agent/tool wiring; local `pytest` run used to verify math and SQL guardrails.

**Decisions**

- **FastAPI** as a single Vercel function (official pattern) vs many `/api/*.py` handlers — UI assets under `static/` served by the app (avoid `public/index.html` static-only trap on Vercel).
- **Supabase** optional: JSON tools always work; SQL tool appears only when the DB is seeded and `DATABASE_URL` is set (clear failure message in tool result if misconfigured).
- **Default model** `gpt-4o-mini` via `OPENAI_MODEL` for cost; swappable for demos.

**If we had more time**

- Streaming SSE for briefing/chat; stricter thread serialization tests; pre-built SQL views for common aggregates to narrow the SQL tool surface.

---

## 2026-04-01T20:45:00Z — Wireframes + sample data linkage

**What happened**

- Documented UI wireframes in `docs/wireframes.md`: page regions (briefing, agent activity, chat), state machine, sequence diagram vs sample JSON, and optional data inspector.
- Grounded layout in actual fields from the sample JSON (`odds[]` rows: `game_id`, teams, `sportsbook`, `markets.*`, `last_updated`); file now lives at `data/sample_odds_data.json`.
- Updated `AGENTS.md` to point at the sample file path for implementers.

**AI tools**

- Cursor: inferred schema from the JSON sample and produced ASCII + Mermaid wireframes.

**Decisions**

- Single-page pattern: one primary CTA → structured briefing → collapsible tool trace → follow-up chat; no separate “games table” as a first-class screen unless we add a debug drawer later.
- Timestamps on devlog entries are **UTC** for consistency across machines.

**If we had more time**

- Clickable anchors from briefing anomaly bullets to a minimal game/book detail strip (still tool-backed).

---

## 2026-04-01T16:00:00Z — Project framework

**What happened**

- Created `AGENTS.md` in the repo root encoding the official brief: goals, deliverables, agent requirements, UI bar, odds math, evaluation weights, and conventions for assistants (focused diffs, no secrets, keep this log current).
- Initialized this `DEVLOG.md` with the structure the evaluators asked for so logging stays a habit from day one.

**AI tools**

- Used Cursor to read the provided PDF brief and translate requirements into `AGENTS.md` and the log scaffold.

**Decisions (provisional)**

- Stack, LLM provider, and app shape were **TBD**; wireframes now constrain UI to a briefing + reasoning + chat SPA (or equivalent CLI).

**If we had more time (placeholder)**

- Flesh out automated checks for odds math (unit tests with known inputs/outputs).
- Add deployment and README once the minimal vertical slice (ingest → tools → briefing → chat) exists.
