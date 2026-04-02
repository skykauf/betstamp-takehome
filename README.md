# Betstamp AI Odds Agent (take-home)

AI-powered workflow that **detects** line anomalies, **analyzes** prices (vig, implied probability, best available odds), and **briefs** an analyst—plus **follow-up chat** grounded in the same data.

## Objectives

1. **Detect** — Flag stale `last_updated` timestamps, off-market outliers, and related data-quality issues in the sample slate.
2. **Analyze** — Compute real numbers (American → implied probability, vig, no-vig fair %, best line per side) and show the math in agent output where useful.
3. **Brief** — Produce a structured daily-style briefing: market overview, anomalies, value angles, and sportsbook quality rankings.
4. **Converse** — After the briefing, answer questions via chat with **tool-backed** reasoning (JSON file + optional Supabase SQL), not guesswork.
5. **Ship** — Runnable locally and on **Vercel**; invite **jbetstamp** on GitHub if the repo is private; submit a **working deployed URL**.

## Constraints (from the brief)

| Constraint | How this repo addresses it |
|------------|----------------------------|
| Tool use / function calling — do not rely on dumping the full dataset into context | Agent exposes tools: list games, fetch lines by `game_id`, staleness list, **`best_line_for_market`**, **`scan_cross_book_arbitrage`**, odds math helpers, optional **read-only SQL** against Postgres. |
| Visible, correct math | `services/math_odds.py` implements formulas; agent instructions require citing calculations. |
| Structured briefing + book rankings | JSON sections (overview, anomalies, value, rankings); **confidence** + **confidence_basis** on each anomaly/value row (bonus); UI renders both. |
| Grounded follow-ups; admit unknowns | System prompt + tools; no fabricating books/games not in data. |
| Simple UI | `templates/index.html` + `templates/app.js` (mounted at `/static/…`) — bundled with the app (not only `public/`). |
| Development log | `DEVLOG.md` (required by evaluators). |

## Architecture

```
FastAPI `app.py` (`GET /` + `/api/*`)  →  OpenAI (tool calls); UI in `templates/` ships inside the function bundle
                              ↓
                    data/sample_odds_data.json (always)
                              ↓
                    Supabase Postgres (optional) — auto-created tables + seeded odds on each function cold start when `DATABASE_URL` is set
```

- **Runtime:** Python 3.12+, **FastAPI** (`app.py`), deployed as a single Vercel function.
- **LLM:** OpenAI Chat Completions with tool definitions (configurable model via env).
- **Primary data:** `data/sample_odds_data.json` (10 games × 8 books). Loaded at cold start; tools read **slices** (e.g. one `game_id` at a time).
- **Supabase:** Optional `DATABASE_URL`. On **each serverless cold start** (first request after idle), the app runs idempotent `CREATE TABLE IF NOT EXISTS` (same as `supabase/migrations/001_init.sql`) and **seeds `odds_lines`** from `data/sample_odds_data.json` if the row count does not match the file (transaction + advisory lock so concurrent instances stay safe). No manual SQL editor or seed script is required for deploys. The agent then gets the **`run_readonly_sql`** tool. When `DATABASE_URL` is unset, JSON-only tools still work.

## Setup

### Prerequisites

- Python 3.12+
- [Vercel CLI](https://vercel.com/docs/cli) (optional, for `vercel dev`)
- OpenAI API key
- (Optional) Supabase project — **Settings → Database → Connection string** (URI, with password)

### Environment variables

Copy `.env.example` to `.env` for local use. Never commit secrets.

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | LLM + tool orchestration |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `DATABASE_URL` | No | Supabase Postgres for `run_readonly_sql` tool |
| `CORS_ORIGINS` | No | Comma-separated origins; default `*` for take-home |
| `MAX_TOOL_ITERATIONS` | No | Cap on agent tool rounds per request (default **24**, max **64**) |

### Local run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 3000
```

Open `http://localhost:3000` for the UI. API: `POST /api/brief`, `POST /api/chat`.

### Supabase (optional)

1. Create a Supabase project and copy **Settings → Database → Connection string** (URI) into Vercel as `DATABASE_URL` (and `.env` locally). Use a role that can create tables (the default `postgres` connection string is fine).
2. **No manual migration or seed is required** for production: opening the site (or any request that cold-starts the function) runs schema bootstrap + odds seed automatically.
3. **Optional:** `supabase/migrations/001_init.sql` remains the reference DDL if you prefer to apply schema in the Supabase SQL editor instead of via the app.
4. **Optional local refresh:** force a full re-insert from JSON:

```bash
export DATABASE_URL='postgresql://...'
python scripts/seed_odds.py
```

### Deploy (Vercel)

1. **Framework preset (Build & Deployment):** **Python** — as in the Vercel dashboard — is the right family: install is `pip install -r requirements.txt` and the runtime is Python. This repo also sets **`"framework": "fastapi"`** in `vercel.json` so Git deploys target the FastAPI builder when Vercel reads the file; if your UI lists a separate **FastAPI** preset, choosing it is equivalent and fine.
2. Connect the GitHub repo. **`vercel.json`** uses legacy **`builds` + `routes`**: **`app.py`** is built with **`@vercel/python`**, and **`/(.*)` → `app.py`** sends **all** requests (including **`GET /`**) to FastAPI. The UI lives under **`templates/`** (`index.html` + `app.js` served via **`/static/app.js`**) so it ships inside the Python bundle — files in **`public/`** are not available to `FileResponse` inside the function on Vercel.
3. In **Project → Settings → General**, leave **Output Directory** empty (override off). A wrong output directory can yield all-404 deployments.
4. Set `OPENAI_API_KEY` (and `DATABASE_URL` if using Supabase) under **Environment Variables**.
5. Deploy. The first request that cold-starts `app.py` runs DB seed when configured; `GET /` should return the HTML UI from `templates/`, `POST /api/brief` JSON.

## API sketch

- **`POST /api/brief`** — Body: `{}`. Returns `{ thread_id, briefing, tool_trace }` in one JSON response (non-streaming).
- **`POST /api/brief/stream`** — Body: `{}`. **SSE**: `start` (with `thread_id`), then `tool` / `delta` like chat, then **`brief_done`** with `{ thread_id, briefing, tool_trace }` after the model finishes and the server parses JSON. UI uses this for live briefing tool visibility.
- **`POST /api/chat/stream`** — Same JSON body as chat. **SSE** (`text/event-stream`): `data: {"event":"delta","text":"..."}` for final-assistant tokens, `{"event":"tool","name",...}` while tools run, then `{"event":"done","reply","tool_trace","messages"}`. The UI uses this by default.
- **`POST /api/chat`** — Same body; returns `{ reply, tool_trace }` in one JSON response (handy for curl/scripts).

Threads and messages are persisted when `DATABASE_URL` is set. Without it, **`thread_store`** keeps threads in an in-process dict (**one Python process only** — not shared across Vercel instances). Use Postgres when you need durable or multi-instance chat. On startup, the app logs a **warning** if `OPENAI_API_KEY` is missing.

System and briefing user prompts live under **`services/prompts/*.md`** (loaded at import). Briefing JSON is optionally validated with **Pydantic** (`services/briefing_schema.py`); invalid shapes still return the raw dict for the UI, with a log line.

## Project layout

```
vercel.json            # builds + routes: filesystem then catch-all → app.py
app.py                 # FastAPI entry (explicit Python build target)
requirements.txt
data/sample_odds_data.json
templates/index.html
templates/app.js
pyproject.toml
services/
  prompts/             # system_prompt.md, briefing_user.md (agent instructions)
  config.py            # env settings
  briefing_schema.py   # parse + soft-validate briefing JSON
  openai_errors.py     # map missing API key → HTTP 503 / SSE errors
  tool_schemas.py      # helper to build OpenAI function tool JSON
  math_odds.py         # implied prob, vig, no-vig
  odds_repository.py  # JSON + optional DB reads
  best_line.py          # cross-book best price per game side
  arbitrage.py          # cross-book two-way arb scan (ML / total / spread)
  odds_seed.py         # cold-start schema + idempotent seed
  database.py          # connection + safe SELECT helper
  agent.py             # tool loop + system prompt
  sse.py               # SSE formatting + shared agent stream iterator
scripts/seed_odds.py   # optional force re-seed from JSON
supabase/migrations/001_init.sql
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -q
```

`tests/test_app.py` exercises HTTP routes with **mocks** (no live OpenAI). `tests/test_briefing_schema.py` covers Pydantic validation fallbacks.

## Further reading

- Product rules for contributors: `AGENTS.md`
- UI wireframes: `docs/wireframes.md`
- Process / AI usage: `DEVLOG.md`
