#!/usr/bin/env python3
"""DraftKings NBA odds pull smoke test (DraftKings endpoint only).

Usage examples:
  python3 scripts/test_draftkings_nba_odds.py
  DK_COOKIE='ak_bmsc=...; bm_sz=...' python3 scripts/test_draftkings_nba_odds.py
  python3 scripts/test_draftkings_nba_odds.py --out /tmp/dk_nba_raw.json
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/"
    "controldata/league/leagueSubcategory/v1/markets"
)

# NBA (leagueId=42648), game lines subcategory in your working request.
DEFAULT_PARAMS = {
    "isBatchable": "false",
    "templateVars": "42648",
    "eventsQuery": "$filter=leagueId eq '42648' AND clientMetadata/Subcategories/any(s: s/Id eq '4511')",
    "marketsQuery": "$filter=clientMetadata/subCategoryId eq '4511' AND tags/all(t: t ne 'SportcastBetBuilder')",
    "include": "Events",
    "entity": "events",
}


def _build_url() -> str:
    return f"{BASE_URL}?{urllib.parse.urlencode(DEFAULT_PARAMS)}"


def _headers() -> dict[str, str]:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": "https://sportsbook.draftkings.com",
        "referer": "https://sportsbook.draftkings.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "x-client-feature": "leagueSubcategory",
        "x-client-name": "web",
        "x-client-page": "league",
        "x-client-version": os.getenv("DK_CLIENT_VERSION", "2615.2.1.13"),
        "x-client-widget-name": "cms",
        "x-client-widget-version": os.getenv("DK_WIDGET_VERSION", "2.9.9"),
    }
    cookie = os.getenv("DK_COOKIE", "").strip()
    if cookie:
        headers["cookie"] = cookie
    return headers


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("events"), list):
        return payload["events"]
    if isinstance(payload.get("Events"), list):
        return payload["Events"]
    if isinstance(payload.get("eventGroup"), dict):
        events = payload["eventGroup"].get("events")
        if isinstance(events, list):
            return events
    return []


def _event_name(event: dict[str, Any]) -> str:
    away = event.get("awayTeam") or event.get("awayTeamName") or event.get("away")
    home = event.get("homeTeam") or event.get("homeTeamName") or event.get("home")
    participants = event.get("participants")
    if (not away or not home) and isinstance(participants, list):
        for p in participants:
            if not isinstance(p, dict):
                continue
            role = (p.get("venueRole") or "").lower()
            if role == "away":
                away = away or p.get("name")
            elif role == "home":
                home = home or p.get("name")
    if away and home:
        return f"{away} @ {home}"
    return (
        event.get("name")
        or event.get("eventName")
        or event.get("slug")
        or str(event.get("id", "unknown_event"))
    )


def _moneyline_by_event(payload: dict[str, Any]) -> dict[str, list[str]]:
    markets = payload.get("markets")
    selections = payload.get("selections")
    if not isinstance(markets, list) or not isinstance(selections, list):
        return {}

    moneyline_market_ids: dict[str, str] = {}
    for m in markets:
        if not isinstance(m, dict):
            continue
        mkt = m.get("marketType")
        mkt_name = mkt.get("name") if isinstance(mkt, dict) else None
        if (mkt_name or "").lower() != "moneyline":
            continue
        event_id = str(m.get("eventId", ""))
        market_id = str(m.get("id", ""))
        if event_id and market_id and event_id not in moneyline_market_ids:
            moneyline_market_ids[event_id] = market_id

    selection_rows: dict[str, list[str]] = {}
    for s in selections:
        if not isinstance(s, dict):
            continue
        market_id = str(s.get("marketId", ""))
        if not market_id:
            continue
        event_id = next(
            (eid for eid, mid in moneyline_market_ids.items() if mid == market_id),
            None,
        )
        if event_id is None:
            continue
        label = s.get("label") or s.get("outcomeType") or "Unknown"
        american = None
        display_odds = s.get("displayOdds")
        if isinstance(display_odds, dict):
            american = display_odds.get("american")
        line = f"{label}: {american}" if american else str(label)
        selection_rows.setdefault(event_id, []).append(line)

    return selection_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test DraftKings NBA odds endpoint.")
    parser.add_argument(
        "--out",
        default="data/draftkings_nba_raw.json",
        help="Path to write raw JSON response (default: data/draftkings_nba_raw.json)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout seconds (default: 20)",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print full JSON payload to stdout",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS cert verification (for local debugging only)",
    )
    args = parser.parse_args()

    url = _build_url()
    req = urllib.request.Request(url=url, method="GET", headers=_headers())
    started = time.time()

    try:
        ssl_context = None
        if args.insecure:
            ssl_context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=args.timeout, context=ssl_context) as resp:
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        snippet = exc.read(400).decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} from DraftKings endpoint", file=sys.stderr)
        print(snippet, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = int((time.time() - started) * 1000)
    text = body.decode("utf-8", errors="replace")
    try:
        payload: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        print("Response was not JSON.", file=sys.stderr)
        print(text[:600], file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    events = _extract_rows(payload)
    moneyline = _moneyline_by_event(payload)
    markets = payload.get("markets") if isinstance(payload.get("markets"), list) else []
    selections = (
        payload.get("selections") if isinstance(payload.get("selections"), list) else []
    )
    print(f"status={status} content_type={content_type} elapsed_ms={elapsed_ms}")
    print(f"saved_raw={args.out}")
    print(f"event_count={len(events)}")
    print(f"market_count={len(markets)} selection_count={len(selections)}")

    for idx, event in enumerate(events[:10], start=1):
        event_id = event.get("id") or event.get("eventId")
        start_time = (
            event.get("startEventDate")
            or event.get("startDate")
            or event.get("startTime")
            or "unknown_start"
        )
        print(f"{idx:02d}. {_event_name(event)} | id={event_id} | start={start_time}")
        if event_id is not None:
            for line in moneyline.get(str(event_id), [])[:2]:
                print(f"    ML {line}")

    if args.print_json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
