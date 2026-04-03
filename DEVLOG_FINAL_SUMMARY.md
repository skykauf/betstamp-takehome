# Development summary

Short companion to **`DEVLOG.md`**, which stays the **full** log (session notes + 25-message prompt thread for the process rubric). Use this file for a **fast read** of how the project came together.

## Timeline (compressed)

**Setup** — Encoded the PDF into `AGENTS.md`, wireframed against `data/sample_odds_data.json`, then shipped a **vertical slice**: FastAPI, OpenAI tool loop, structured briefing contract, minimal UI, pytest for odds math and SQL guardrails, optional Postgres + seed.

**Vercel** — Routing took a few iterations. The durable pattern is **one Python function** handling **`GET /`** and **`/api/*`**, with the UI under **`templates/`** and **`vercel.json`** `builds` + catch‑all route. Static-only hosting of `public/` without the function left **`/api/brief`** as 404.

**Agent depth** — `best_line_for_market`; **follow-up grounding** (data questions require a tool call that turn); `scan_cross_book_arbitrage`; briefing **rendered as sections** (not raw JSON) + **demo chat prompts**; **confidence** fields on anomalies/value rows; **SSE** for chat and briefing, then refactors (**`sse.py`**, shared tool loop, **`app.js`**).

**Quality** — Prompts moved to **`services/prompts/*.md`**; Pydantic **soft-validate** briefing; capped tool iterations; clearer errors when the API key is missing.

**Late additions** — `line_vs_consensus`, `slate_book_tightness`, `build_stake_weights` for consensus/outlier stories, book tightness ranking, and arb-style stake splits.

## Decisions that stuck

- **Slice, don’t dump** — Tools return game-sized (or aggregate) payloads, not the whole JSON in context.
- **Math in code** — `math_odds.py` and tool outputs; the model explains formulas in prose.
- **Honest scope** — No invented books or games; admit when the dataset cannot answer.

## With more time

Pre-built SQL views for common aggregates; stronger thread persistence tests across serverless instances; optional E2E with a real model key.
