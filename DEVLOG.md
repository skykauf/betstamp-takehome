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

## 2026-04-04T04:30:00Z — Consensus vs outlier + slate vig/tightness tools

**What happened**

- **`services/consensus_outlier.py` — `line_vs_consensus(game_id, market_side)`:** cohort implied median/mean, per-book deviation and z-score vs cohort; moneyline uses all books; spread/total use the **modal** line (two decimals) then compare implieds on that line.
- **`services/book_tightness.py` — `slate_book_tightness()`:** per odds row, average two-way vig where ML/spread/total pairs exist; aggregate mean/median/min/max per book and **`books_ranked_tightest_first`**.
- **`services/odds_repository.py`:** **`all_odds_rows()`** for slate-wide scans without reaching into private loader state.
- **`services/best_line.py`:** **`american_line_for_side`** exposed (was private helper) for reuse.
- **Agent:** tools **`line_vs_consensus`** and **`slate_book_tightness`** wired in **`services/agent.py`**.
- **Prompts:** system + briefing user nudge the model to use these for outlier stories and quantitative book rankings.
- **Tests:** **`tests/test_consensus_outlier.py`**, **`tests/test_book_tightness.py`**.

**Decisions**

- Modal line for spread/total keeps the cohort apples-to-apples without averaging across different handicaps.

---

## 2026-04-04T03:00:00Z — Code quality pass (prompts file, validation, tests, errors)

**What happened**

- **Prompts:** `SYSTEM_PROMPT` / `BRIEFING_USER` moved to **`services/prompts/*.md`**, loaded at import.
- **`services/briefing_schema.py`:** Pydantic **`BriefingPayload`** with `extra="allow"`; **`parse_briefing_json`** validates when possible, logs **`ValidationError`**, returns raw dict on soft-fail. Re-exported from **`services.agent`** for existing imports.
- **`services/tool_schemas.function_tool`:** DRY OpenAI function definitions; **`agent._tool_definitions`** refactored.
- **`services/openai_errors.py`:** **`raise_http_if_missing_openai_key`**, **`sse_error_message`** for consistent 503 / SSE errors.
- **`config.max_tool_iterations()`** env **`MAX_TOOL_ITERATIONS`** (default 24, clamped 1–64).
- **`app.py`:** Lifespan warns when **`OPENAI_API_KEY`** unset; **`logger.exception`** on unexpected handler errors; stream handlers log failures.
- **`thread_store`:** Docstring clarifies in-memory vs Postgres / multi-instance.
- **Tests:** **`tests/test_app.py`** (health, chat 404, mocked brief + brief stream + chat); **`tests/test_briefing_schema.py`**.
- **Deps:** explicit **`pydantic`**, **`httpx`** (TestClient) in **`requirements.txt`**.

---

## 2026-04-04T02:00:00Z — Refactor: shared SSE + tool loop + `app.js`

**What happened**

- **`services/sse.py`:** `format_sse_event`, `STREAMING_HEADERS`, `SSE_MEDIA_TYPE`, `AgentStreamOutcome`, and **`iter_agent_sse_events`** (forwards `run_agent_stream`, optionally suppresses terminal `done`, captures outcome).
- **`app.py`:** `/api/chat/stream` and `/api/brief/stream` use the shared iterator + **`finally`** save; removed duplicate JSON/header strings; dropped unused `json` import.
- **`services/agent.py`:** Shared **`_chat_completion_kwargs`**, **`_run_tool_calls`** (tool SSE events optional), **`_tool_calls_from_api_message`**, **`_parse_tool_arguments`**, **`_max_iterations_payload`** — **`run_agent`** and **`run_agent_stream`** both use the same tool-dispatch path.
- **Frontend:** Logic moved to **`templates/app.js`** (IIFE); **`readFetchErrorBody`** dedupes stream error parsing; **`index.html`** loads **`/static/app.js`**.

---

## 2026-04-04T01:00:00Z — More demo follow-up prompts (PDF-aligned)

**What happened**

- Expanded **`templates/index.html`** example questions to mirror the brief: Knicks game scrutiny (`nba_20260320_gsw_nyk`), books to avoid, outlier vs consensus, vig comparison, no-vig fair %, best value vs next-best, arb, staleness, sanity-check rankings. Short button labels + full tool-grounded `data-q` text.

---

## 2026-04-04T00:15:00Z — Streaming briefing (`/api/brief/stream` + activity panel)

**What happened**

- **`POST /api/brief/stream`:** Reuses **`run_agent_stream`** with the usual system + briefing user messages; forwards **`tool`** and **`delta`** SSE events; absorbs the internal **`done`** and emits **`brief_done`** with parsed **`briefing`**, **`tool_trace`**, and **`thread_id`** after **`save_messages`**.
- **UI:** **Briefing activity** section lists each tool call as it runs; optional **Model output (streaming)** pre shows final JSON tokens; section hides when **`brief_done`** arrives (full trace remains under Agent activity). **Run daily briefing** now uses the stream endpoint.

---

## 2026-04-03T23:30:00Z — Streaming chat (SSE bonus)

**What happened**

- **`run_agent_stream`** in `services/agent.py`: same tool loop as `run_agent`, but uses OpenAI **`stream=True`**; merges streamed `tool_calls` fragments via **`_StreamToolAccumulator`**; emits **`delta`** only when the model is not in a tool-call round (avoids flashing partial text before tools). Yields **`tool`** events before each execution and a terminal **`done`** with `messages` for persistence.
- **`POST /api/chat/stream`** in `app.py`: **`StreamingResponse`** (`text/event-stream`), saves the thread on successful **`done`**.
- **UI:** `fetch` + `ReadableStream` SSE parser; live agent text; `(tools running: …)` while tools execute; final `(tools: …)` JSON from `done`. **`POST /api/chat`** kept for non-streaming clients.
- **Tests:** `tests/test_agent_stream.py` for accumulator merge behavior.

**Note:** Briefing stays non-streamed so the JSON contract stays parseable server-side.

---

## 2026-04-03T22:00:00Z — Briefing confidence fields (bonus)

**What happened**

- **System prompt / briefing JSON:** Extended schema with **`confidence`** (`high` | `medium` | `low`) and **`confidence_basis`** on every **anomaly** and **value_opportunity**; rubric ties levels to tool evidence. Optional **`market_overview_confidence`** (+ basis) and per-row fields on **sportsbook_quality**.
- **`BRIEFING_USER`:** Requires confidence on anomaly/value rows; optional overview and book ranks.
- **UI (`templates/index.html`):** Renders a compact **Confidence:** line under market overview (when present) and under each anomaly, value, and book row when `confidence` and/or `confidence_basis` exist.
- **Tests:** `tests/test_parse_briefing_json.py` ensures `parse_briefing_json` accepts the enriched object.
- **`AGENTS.md` / `README.md`:** Documented as bonus deliverable.

---

## 2026-04-03T20:00:00Z — Briefing UX + demo prompts; push to GitHub

**What happened**

- **`templates/index.html`:** Briefing is no longer raw JSON — it renders **Market overview**, **Flagged anomalies**, **Value opportunities**, and **Sportsbook quality** (headings + lists) to match the “human analyst” narrative; fallback block if the model returns non-JSON (`raw_markdown`). Minimal extra CSS (card + section headers).
- **Follow-up:** Example question buttons pre-fill the textarea and **send** the chat request when a `thread_id` exists; disabled while requests run. Enter-to-send on the textarea.
- **Git:** Committed and pushed `main` to `origin` (arbitrage + agent/docs + UI in one deployable slice).

**PDF / rubric alignment**

- Core requirements were already met; this closes the gap on **presenting** the structured briefing clearly without heavy UI work.

**If we had more time**

- See separate backlog in latest session: streaming chat, optional confidence fields, richer chat formatting.

---

## 2026-04-03T03:30:00Z — `scan_cross_book_arbitrage` tool

**What happened**

- **`services/arbitrage.py`:** Scans moneyline, total (same line across books), and spread (same home/away pair) for strict two-way edges where **best implied per side** sums to **&lt; 1**; returns only those opportunities plus `cross_book` and an interpretation string.
- **Agent:** Registered `scan_cross_book_arbitrage` in tool definitions and `_call_tool`; system prompt and briefing user message nudge use for arb-style reporting.
- **Tests:** `tests/test_arbitrage.py` (synthetic ML + total cases; unknown market error path).

---

## 2026-04-03T02:15:00Z — Chat grounding rules + `best_line_for_market` tool

**What happened**

- **System prompt:** Added mandatory follow-up rules: questions about staleness, timestamps, books, odds, vig, best line, or any dataset-verifiable fact require **at least one tool call in that turn** — no answering from briefing memory alone. Meta questions stay tool-optional. Initial briefing still ends in the JSON object; follow-ups use plain text.
- **Tool:** `best_line_for_market(game_id, market_side)` implemented in `services/best_line.py` — best price = **lowest implied probability** across books for `spread_home|spread_away|moneyline_home|moneyline_away|total_over|total_under`; returns `best` plus `all_books_ranked_best_to_worst`. Tests in `tests/test_best_line.py`.
- **Briefing user message:** Nudges the model to use `best_line_for_market` for value angles.

**Prompt / product**

- Addresses evaluator gap where chat showed `tools: []` on factual follow-ups; aligns with rubric grounding.

---

## 2026-04-03T01:30:00Z — Fix `GET /` JSON fallback: UI in `templates/` (bundled)

**What happened**

- Production showed `{"message":"Odds Agent API","docs":"/docs"}` on `/` — the FastAPI branch when **`index.html` is missing**. **`public/` is not packaged into the Python serverless bundle** on Vercel, so `FileResponse(public/index.html)` never found a file.
- Moved the UI to **`templates/index.html`** and serve **`GET /`** from there; **`StaticFiles`** uses the same directory for `/static` assets.
- **`vercel.json`**: dropped deprecated **`handle: filesystem`**; single catch‑all **`/(.*)` → `app.py`** so routing is consistent (all paths hit FastAPI, which serves HTML + API).

---

## 2026-04-03T01:00:00Z — Align `vercel.json` with Python / FastAPI framework preset

**What happened**

- Dashboard **Framework Preset → Python** matches this project (pip + Python runtime). Added **`"framework": "fastapi"`** to `vercel.json` so repo config matches Vercel’s FastAPI slug and stays consistent with Git-based deploys; **Python** vs **FastAPI** in the UI is the same stack here.
- README deploy steps now spell out that relationship and the **`builds`/`routes`** routing layer on top.

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

---

## Prompt evolution (full user thread)

Verbatim user messages from the Cursor thread used to build this project (chronological). Documented for the take-home’s **prompt iteration / process** rubric. **`AGENTS.md`** only instructs assistants to keep this section updated — the full thread lives here.

1. `@/Users/skylerkaufman/Downloads/Betstamp AI Odds Agent - Take Home - FINAL.pdf`  
   can you help setup the framework for this takehome project? start with encoding rules into an agents.md and make sure to keep the dev log

2. `@Betstamp AI Odds Agent - sample_odds_data.json`  
   awesome, can you timestamp the entries in devlog and start working on wireframing the app using the linked sample data?

3. looks great! i trust your placement of the sample data.  
   can we go ahead and start implementing the project? i'd like us to first lay out the objectives and constraints clearly in a readme then we can go ahead and implement the services in a python vercel app. we have supabase postgres access we can connect to as a tool for the llm

4. can we pythonically seed the odds upon site visit inside vercel? i want to reduce any manual actions

5. can you debug structure for initial vercel deploy then push it up

6. seems like the brief endpoint isn't working as intended

7. we're using python framework

8. routing still seems broken

9. much better, thank you

10. give me a follow up question to ask as a test

11. app is looking good ! can you read the assignment again to make sure we're covering everything that's asked of us then suggesting some improvements `@/Users/skylerkaufman/Downloads/Betstamp AI Odds Agent - Take Home - FINAL.pdf`

12. yes please lets implement 1+2  
    then, can you improve 5 by putting a prompt-evolution sections at the bottom of devlog which includes ALL the prompts i've sent in this thread

13. this is great! working as expected. can we add the Arbitrage tool please?

14. great! i think you forgot to add this prompt to the bottom -- might want to add that to agents.md

15. don't need the full user thread in agents.md, just instructions to record the raw prompts in devlog

16. awesome work so far. lets work on "Briefing UX — Keep one page, but render JSON into sections (headings + lists) so the 'human analyst' story matches the product narrative without heavy CSS." also, i'd like to have some demo follow-up questions displayed on the UI -- bonus points if clicking them populates the chat box and sents request

17. push it up lets see how this works! then go back to the pdf and see if there's anything else we can improve on `@Betstamp AI Odds Agent - Take Home - FINAL.pdf`

18. lets first implement 2: confidence fields go ahead and push i trust you

19. awesome thank you! can we now try implementing streaming as a bonus?

20. Yes that sounds nice `/api/brief/stream` + a small briefing "activity" panel so tool calls are visible during the initial run too.

21. This works great. thanks for all your hard work. can we add some more example follow up questions? use the assignment pdf for inspiration `@Betstamp AI Odds Agent - Take Home - FINAL.pdf`

22. yes lets prioritize the highest leverage for simplicity + safety is usually: one SSE helper + shared stream wrapper, then one agent loop behind stream/non-stream, then extract frontend JS for maintainability.

23. can you go ahead and perform the rest of the code quality improvements you listed before. they all look helpful and sound

24. i do want to actually ship one or two before submission, #1 (consensus vs outlier) + #2 (vig/tightness aggregate)
