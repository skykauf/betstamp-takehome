# Betstamp AI Odds Agent (take-home)

Tool-grounded workflow: **detect** line issues, **analyze** prices (vig, implied probability, best side), **brief** in structured JSON, **chat** with follow-ups. Primary data: `data/sample_odds_data.json` (10 NBA games × 8 books). Optional **Supabase** + `DATABASE_URL` mirrors odds for **read-only SQL** and durable chat threads.

**Stack:** FastAPI (`app.py`), OpenAI Chat Completions + tools, deploy as one Vercel Python function. Instructions: `services/prompts/system_prompt.md`, `briefing_user.md`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # set OPENAI_API_KEY
uvicorn app:app --reload --port 3000
```

Open `http://localhost:3000`. API: `GET /api/health`; **`POST /api/brief`** or **`POST /api/brief/stream`** (SSE); **`POST /api/chat`** or **`POST /api/chat/stream`**.

## Environment

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | Model + tools |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `DATABASE_URL` | No | Postgres → `run_readonly_sql`, seeded odds, thread persistence |
| `MAX_TOOL_ITERATIONS` | No | Tool rounds per request (default **24**, max **64**) |
| `CORS_ORIGINS` | No | Default `*` |

## Architecture

- **Routing:** `vercel.json` sends **`/(.*)`** to **`app.py`** so HTML and `/api/*` share one runtime. UI lives in **`templates/`** (served by FastAPI + `/static/app.js`), not as a static-only root — that pattern previously 404’d API routes on Vercel.
- **Data:** JSON loaded at cold start; tools query **slices** (e.g. one `game_id`). With `DATABASE_URL`, **`services/odds_seed.py`** runs idempotent DDL + seed when row counts drift.
- **Agent:** `services/agent.py` — one tool-dispatch path for streaming and non-streaming (`services/sse.py`).

## Agent capabilities (tools)

List games, per-game lines, staleness list; **`best_line_for_market`**; **`line_vs_consensus`**; **`slate_book_tightness`**; **`scan_cross_book_arbitrage`**; **`build_stake_weights`**; `american_to_implied`, `compute_two_sided_market`; optional **`run_readonly_sql`**. Briefing JSON is **soft-validated** (`services/briefing_schema.py`); anomalies/value rows include **confidence** + **confidence_basis** (bonus).

## Deploy (Vercel)

Connect the repo; set **`OPENAI_API_KEY`** (and **`DATABASE_URL`** if using SQL/threads). Use the **Python / FastAPI** style preset; leave **Output Directory** empty. First cold start can bootstrap the DB from JSON automatically.

Force re-seed locally: `export DATABASE_URL='postgresql://…'` then `python3 scripts/seed_odds.py`.

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -q
```

HTTP, math, arbitrage, briefing schema, streaming helpers, consensus/tightness, stake weights — all mocked where needed (no live OpenAI in CI).

## Repo map

```
app.py                 # FastAPI
vercel.json            # Python build + catch-all route
data/sample_odds_data.json
templates/index.html, app.js
services/
  agent.py, sse.py, math_odds.py, odds_repository.py, odds_seed.py, database.py
  best_line.py, consensus_outlier.py, book_tightness.py, arbitrage.py, stake_weights.py
  briefing_schema.py, tool_schemas.py, prompts/*.md
supabase/migrations/001_init.sql
scripts/seed_odds.py
```

## Further reading

| File | Purpose |
|------|---------|
| [AGENTS.md](AGENTS.md) | Official brief + repo rules for contributors |
| [DEVLOG.md](DEVLOG.md) | Full development log + verbatim prompt thread (evaluator-facing) |
| [DEVLOG_FINAL_SUMMARY.md](DEVLOG_FINAL_SUMMARY.md) | Short timeline of how the build evolved |
| [docs/wireframes.md](docs/wireframes.md) | One-page UI regions and flows |
