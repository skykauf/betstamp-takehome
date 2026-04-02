"""Supabase / Postgres: safe read-only SQL for the agent tool."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from services.config import database_url

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|COPY|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


def db_available() -> bool:
    return database_url() is not None


def validate_readonly_select(sql: str) -> str | None:
    """Return error message if invalid; None if OK."""
    q = sql.strip()
    if not q:
        return "Empty query"
    if ";" in q.rstrip(";"):
        return "Only a single statement is allowed; remove semicolons inside the query"
    q = q.rstrip().rstrip(";")
    if not re.match(r"^\s*SELECT\b", q, re.IGNORECASE):
        return "Only SELECT queries are allowed"
    if _FORBIDDEN.search(q):
        return "Query contains forbidden keywords"
    return None


def run_readonly_sql(sql: str) -> list[dict[str, Any]]:
    err = validate_readonly_select(sql)
    if err:
        raise ValueError(err)
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    q = sql.strip().rstrip(";")
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            rows = cur.fetchall()
    return [dict(r) for r in rows]
