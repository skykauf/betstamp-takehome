#!/usr/bin/env python3
"""Force-reload data/sample_odds_data.json into Postgres (optional local / CI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.odds_seed import ensure_odds_seeded  # noqa: E402


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        print("Set DATABASE_URL to your Supabase Postgres connection string.", file=sys.stderr)
        sys.exit(1)
    result = ensure_odds_seeded(force=True)
    print(result)
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
