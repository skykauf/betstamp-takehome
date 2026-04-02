"""Chat thread persistence: Postgres when DATABASE_URL is set, else in-process (single instance)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import psycopg
from psycopg.types.json import Json

from services.config import database_url

_memory_threads: dict[str, list[dict[str, Any]]] = {}


def create_thread() -> str:
    url = database_url()
    if not url:
        tid = str(uuid.uuid4())
        _memory_threads[tid] = []
        return tid
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_threads (messages) VALUES ('[]'::jsonb) RETURNING id::text"
            )
            tid = cur.fetchone()[0]
        conn.commit()
    return tid


def load_messages(thread_id: str) -> list[dict[str, Any]] | None:
    url = database_url()
    if not url:
        if thread_id not in _memory_threads:
            return None
        return list(_memory_threads[thread_id])
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT messages FROM chat_threads WHERE id = %s::uuid",
                (thread_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row[0], list) else json.loads(row[0])


def save_messages(thread_id: str, messages: list[dict[str, Any]]) -> None:
    url = database_url()
    if not url:
        if thread_id not in _memory_threads:
            _memory_threads[thread_id] = []
        _memory_threads[thread_id] = messages
        return
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_threads SET messages = %s WHERE id = %s::uuid",
                (Json(messages), thread_id),
            )
            if cur.rowcount == 0:
                raise ValueError("thread not found")
        conn.commit()
