"""Read odds from data/sample_odds_data.json (and optionally mirror DB later)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "sample_odds_data.json"


@lru_cache
def _payload() -> dict:
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Missing odds file: {DATA_PATH}")
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def dataset_meta() -> dict:
    p = _payload()
    return {
        "description": p.get("description"),
        "generated": p.get("generated"),
        "notes": p.get("notes", []),
        "record_count": len(p.get("odds", [])),
    }


def list_games() -> list[dict]:
    seen: dict[str, dict] = {}
    for row in _payload()["odds"]:
        gid = row["game_id"]
        if gid not in seen:
            seen[gid] = {
                "game_id": gid,
                "sport": row.get("sport"),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "commence_time": row["commence_time"],
            }
    return sorted(seen.values(), key=lambda g: g["commence_time"])


def get_odds_for_game(game_id: str) -> list[dict]:
    return [r for r in _payload()["odds"] if r["game_id"] == game_id]


def all_last_updated_times() -> list[tuple[str, str, str]]:
    """(game_id, sportsbook, last_updated iso) for staleness scans."""
    out = []
    for r in _payload()["odds"]:
        out.append((r["game_id"], r["sportsbook"], r["last_updated"]))
    return out
