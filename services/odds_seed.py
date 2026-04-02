"""Idempotent Postgres schema + odds seed (Vercel cold start / local)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import psycopg

from services.config import database_url

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "sample_odds_data.json"

# Stable key so concurrent serverless instances serialize seed work.
_ADVISORY_LOCK_KEY = 872_364_231

# Idempotent DDL (mirrors supabase/migrations/001_init.sql) — avoids manual SQL editor step.
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS odds_snapshots (
      id BIGSERIAL PRIMARY KEY,
      label TEXT NOT NULL DEFAULT 'default',
      loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (label)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS odds_lines (
      id BIGSERIAL PRIMARY KEY,
      snapshot_id BIGINT NOT NULL REFERENCES odds_snapshots (id) ON DELETE CASCADE,
      game_id TEXT NOT NULL,
      sport TEXT NOT NULL DEFAULT 'NBA',
      home_team TEXT NOT NULL,
      away_team TEXT NOT NULL,
      commence_time TIMESTAMPTZ NOT NULL,
      sportsbook TEXT NOT NULL,
      markets JSONB NOT NULL,
      last_updated TIMESTAMPTZ NOT NULL,
      UNIQUE (snapshot_id, game_id, sportsbook)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_odds_lines_game ON odds_lines (game_id)",
    "CREATE INDEX IF NOT EXISTS idx_odds_lines_book ON odds_lines (sportsbook)",
    "CREATE INDEX IF NOT EXISTS idx_odds_lines_last_updated ON odds_lines (last_updated)",
    """
    CREATE TABLE IF NOT EXISTS chat_threads (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now (),
      messages JSONB NOT NULL DEFAULT '[]'::jsonb
    )
    """,
)


def _read_odds_rows() -> list[dict]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload["odds"]


def _bootstrap_schema(cur: psycopg.Cursor) -> None:
    for stmt in _SCHEMA_STATEMENTS:
        cur.execute(stmt)


def _insert_all_lines(cur: psycopg.Cursor, snap_id: int, rows: list[dict]) -> None:
    cur.execute("DELETE FROM odds_lines WHERE snapshot_id = %s", (snap_id,))
    for r in rows:
        commence = datetime.fromisoformat(r["commence_time"].replace("Z", "+00:00"))
        lu = datetime.fromisoformat(r["last_updated"].replace("Z", "+00:00"))
        cur.execute(
            """
            INSERT INTO odds_lines (
              snapshot_id, game_id, sport, home_team, away_team,
              commence_time, sportsbook, markets, last_updated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                snap_id,
                r["game_id"],
                r.get("sport", "NBA"),
                r["home_team"],
                r["away_team"],
                commence,
                r["sportsbook"],
                json.dumps(r["markets"]),
                lu,
            ),
        )


def ensure_odds_seeded(*, force: bool = False) -> dict:
    """
    Ensure tables exist and `odds_lines` matches `data/sample_odds_data.json` for snapshot `default`.

    Uses a transaction-scoped advisory lock so parallel Vercel instances do not corrupt each other.

    Returns a small status dict for logs (never raises for expected failures like missing URL).
    """
    url = database_url()
    if not url:
        return {"status": "skipped", "reason": "no_database_url"}

    if not DATA_PATH.is_file():
        return {"status": "error", "error": f"missing data file: {DATA_PATH}"}

    try:
        rows = _read_odds_rows()
    except (json.JSONDecodeError, KeyError) as e:
        return {"status": "error", "error": f"invalid odds json: {e}"}

    expected = len(rows)

    try:
        with psycopg.connect(url) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    _bootstrap_schema(cur)
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(%s)", (_ADVISORY_LOCK_KEY,)
                    )
                    cur.execute(
                        """
                        INSERT INTO odds_snapshots (label, loaded_at)
                        VALUES ('default', now())
                        ON CONFLICT (label) DO UPDATE SET loaded_at = excluded.loaded_at
                        RETURNING id
                        """
                    )
                    snap_id = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM odds_lines WHERE snapshot_id = %s",
                        (snap_id,),
                    )
                    count = cur.fetchone()[0]

                    if not force and count == expected:
                        return {
                            "status": "already_seeded",
                            "rows": count,
                            "snapshot_id": snap_id,
                        }

                    _insert_all_lines(cur, snap_id, rows)
                    return {
                        "status": "seeded",
                        "rows": expected,
                        "snapshot_id": snap_id,
                        "force": force,
                    }
    except Exception as e:
        logger.exception("ensure_odds_seeded failed")
        return {"status": "error", "error": str(e)}
