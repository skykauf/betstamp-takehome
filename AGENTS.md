# Agent instructions — Betstamp AI Odds Agent (take-home)

This file encodes the official take-home requirements and how assistants should work in this repo. Treat it as source of truth alongside the evaluator’s brief.

## Product goal

Automate the morning odds review workflow: **Detect** anomalies, **Analyze** lines (vig, best price, value), **Brief** with a daily market summary a human can act on. A user opens a URL, runs the agent, reads the briefing, then asks **follow-up questions in chat** (e.g. why a game was flagged, which books to avoid).

## Deliverables (must ship)

- GitHub repo (invite **jbetstamp** if private).
- **Deployed URL** (Vercel, Railway, Fly.io, or equivalent) — live at submission.
- **README**: setup instructions and architecture decisions.
- **DEVLOG.md**: required; weighted heavily — maintain it throughout development (see `DEVLOG.md` template sections).

## Data

- Repo file: `data/sample_odds_data.json` — top-level keys `description`, `generated`, `notes`, `odds` (array of per-book rows). With `DATABASE_URL`, Postgres is bootstrapped and `odds_lines` is seeded automatically on serverless cold start (`services/odds_seed.py`) for the SQL tool.
- Baseline: sample JSON — **10 NBA games × 8 sportsbooks** (80 records): spreads, moneylines, totals in **American odds**.
- Seeded anomalies to find: **2–3 stale lines** (`last_updated` much older), **1–2 outlier prices**, **≥1 arbitrage-style opportunity** across books.
- Extending the dataset or using a live odds API is optional; provided data is sufficient.

## AI agent — non‑negotiables

1. **Tool use / function calling** to query and analyze odds — do **not** rely on stuffing the full dataset into the model context as the primary approach.
2. **Real calculations** with **visible math**: implied probability, vig, no-vig fair odds, best line per side. No hand-waving.
3. **Structured daily briefing** including: market overview, flagged anomalies, top value opportunities, **sportsbook quality rankings**.
4. **Follow-up chat** grounded in data; data-grounded questions (books, times, odds, best line, vig) require **tool calls** in that turn — see `services/agent.py` system prompt.
5. **Epistemic honesty**: if data is missing or the question is out of scope, say so — **do not guess**.
6. **`best_line_for_market`:** cross-book best price for one side = lowest implied probability (`services/best_line.py`).
7. **`scan_cross_book_arbitrage`:** scan slate or one game for strict two-way arbs — best implied per side across books; totals/spreads only when line/pair matches (`services/arbitrage.py`).
8. **Briefing JSON — confidence (bonus):** each **anomaly** and **value_opportunity** includes `confidence` (`high` | `medium` | `low`) and `confidence_basis` tied to tool evidence; optional fields on market overview and sportsbook rows (`services/briefing_schema.py` + UI in `templates/index.html`).
9. **Prompts:** agent system + briefing user messages are **`services/prompts/system_prompt.md`** and **`briefing_user.md`** (not hard-coded in Python).

## UI expectations (simple is fine)

- Trigger the agent and show the generated briefing.
- Chat for follow-ups about the briefing.
- Some visibility into **reasoning**: tool calls made, data sources used.
- Single-page app or CLI is acceptable; **depth of the agent matters more than polish**.

## Odds math (verify correctness)

- **American → implied probability**
  - Negative: `|odds| / (|odds| + 100)` (e.g. -150 → 60%).
  - Positive: `100 / (odds + 100)` (e.g. +200 → 33.3%).
- **Vig / margin**: sum implied probabilities of both sides of a market; subtract 1 (e.g. -110 / -110 → ~4.76% vig).
- **No-vig fair odds**: normalize implied probabilities so they sum to 100%.
- **Best line**: across books, highest payout (lowest implied probability) for the side in question.

## Technical freedom

- Any LLM provider (bring your own API key).
- Any language, framework, or stack.
- Prefer **depth over breadth**: a smaller feature set done well beats shallow box-checking.

## Bonus (optional)

- **Streaming** — **`POST /api/chat/stream`** and **`POST /api/brief/stream`** (SSE); initial briefing shows live tool calls, then **`brief_done`** with parsed JSON (`run_agent_stream` in `services/agent.py`, `templates/index.html`).
- Arbitrage detection — `scan_cross_book_arbitrage` (`services/arbitrage.py`).
- Confidence scoring — briefing JSON + UI (`confidence` / `confidence_basis`).

## Evaluation rubric (what reviewers weight)

| Area | Weight | Focus |
|------|--------|--------|
| AI agent design | 35% | Tool schemas, prompts, grounding, reasoning |
| Process thinking | 25% | Real workflow automation, useful briefing |
| Development log | 20% | AI-assisted dev, iteration, judgment |
| Code & craft | 15% | Clean code, errors, deploy, meaningful tests |
| Bonus / creativity | 5% | Product instinct, extra depth |

## Assistant behavior in this repo

- Keep changes **focused** on the task; avoid unrelated refactors.
- **Update DEVLOG.md** when making meaningful decisions, prompt changes, or AI-tool usage worth recording.
- **Verbatim prompts:** Append **raw user messages** (chronological, numbered) to the **Prompt evolution** section at the bottom of `DEVLOG.md` — reviewers weight prompt iteration; that section is the single place for the full thread, not `AGENTS.md`.
- Do not commit secrets; use `.env` / env vars for API keys.
- Prefer implementations that make **tool traces and calculations inspectable** (logs, UI panel, or test assertions).

## Submission reminder

- Reply with repo link + deployed URL; ensure the deploy works at submission time.
- Questions: spencer@betstamp.app
