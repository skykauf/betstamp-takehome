from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

DK_MARKETS_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/"
    "controldata/league/leagueSubcategory/v1/markets"
)

DK_DEFAULT_PARAMS = {
    "isBatchable": "false",
    "templateVars": "42648",
    "eventsQuery": "$filter=leagueId eq '42648' AND clientMetadata/Subcategories/any(s: s/Id eq '4511')",
    "marketsQuery": "$filter=clientMetadata/subCategoryId eq '4511' AND tags/all(t: t ne 'SportcastBetBuilder')",
    "include": "Events",
    "entity": "events",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_american(raw: Any) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # DraftKings often uses Unicode minus in displayOdds.
    s = s.replace("−", "-").replace("–", "-")
    if s.startswith("+"):
        s = s[1:]
    try:
        return int(s)
    except ValueError:
        return None


def _event_teams(event: dict[str, Any]) -> tuple[str | None, str | None]:
    home, away = None, None
    participants = event.get("participants")
    if isinstance(participants, list):
        for p in participants:
            if not isinstance(p, dict):
                continue
            role = str(p.get("venueRole", "")).lower()
            name = p.get("name")
            if role == "home":
                home = home or name
            elif role == "away":
                away = away or name
    return home, away


def _build_url() -> str:
    return f"{DK_MARKETS_URL}?{urllib.parse.urlencode(DK_DEFAULT_PARAMS)}"


def _build_headers() -> dict[str, str]:
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


def fetch_raw_draftkings_nba(timeout_seconds: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(_build_url(), headers=_build_headers(), method="GET")
    insecure_tls = os.getenv("DK_INSECURE_TLS", "").strip().lower() in {"1", "true", "yes"}
    ssl_context = ssl._create_unverified_context() if insecure_tls else None
    with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("DraftKings response was not a JSON object")
    return payload


def normalize_draftkings_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = payload.get("events")
    markets = payload.get("markets")
    selections = payload.get("selections")
    if not isinstance(events, list) or not isinstance(markets, list) or not isinstance(
        selections, list
    ):
        raise ValueError("DraftKings payload missing events/markets/selections arrays")

    markets_by_event: dict[str, dict[str, str]] = {}
    for m in markets:
        if not isinstance(m, dict):
            continue
        event_id = str(m.get("eventId", ""))
        market_id = str(m.get("id", ""))
        market_type = m.get("marketType")
        market_name = ""
        if isinstance(market_type, dict):
            market_name = str(market_type.get("name", "")).lower()
        if not event_id or not market_id or market_name not in {"moneyline", "spread", "total"}:
            continue
        markets_by_event.setdefault(event_id, {})[market_name] = market_id

    selections_by_market: dict[str, list[dict[str, Any]]] = {}
    for s in selections:
        if not isinstance(s, dict):
            continue
        mid = str(s.get("marketId", ""))
        if not mid:
            continue
        selections_by_market.setdefault(mid, []).append(s)

    rows: list[dict[str, Any]] = []
    fetched_at = _iso_now()
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id", ""))
        if not event_id:
            continue
        home, away = _event_teams(event)
        if not home or not away:
            continue

        game_markets = markets_by_event.get(event_id, {})
        row_markets: dict[str, Any] = {}

        # Moneyline
        ml_market_id = game_markets.get("moneyline")
        if ml_market_id:
            home_odds, away_odds = None, None
            for s in selections_by_market.get(ml_market_id, []):
                outcome = str(s.get("outcomeType", "")).lower()
                display = s.get("displayOdds")
                american = (
                    _to_american(display.get("american"))
                    if isinstance(display, dict)
                    else None
                )
                if outcome == "home":
                    home_odds = american
                elif outcome == "away":
                    away_odds = american
            if home_odds is not None and away_odds is not None:
                row_markets["moneyline"] = {
                    "home_odds": home_odds,
                    "away_odds": away_odds,
                }

        # Spread
        spread_market_id = game_markets.get("spread")
        if spread_market_id:
            home_line, away_line = None, None
            home_odds, away_odds = None, None
            for s in selections_by_market.get(spread_market_id, []):
                outcome = str(s.get("outcomeType", "")).lower()
                display = s.get("displayOdds")
                american = (
                    _to_american(display.get("american"))
                    if isinstance(display, dict)
                    else None
                )
                points = s.get("points")
                try:
                    line = float(points) if points is not None else None
                except (TypeError, ValueError):
                    line = None
                if outcome == "home":
                    home_line = line
                    home_odds = american
                elif outcome == "away":
                    away_line = line
                    away_odds = american
            if None not in (home_line, away_line, home_odds, away_odds):
                row_markets["spread"] = {
                    "home_line": float(home_line),
                    "home_odds": int(home_odds),
                    "away_line": float(away_line),
                    "away_odds": int(away_odds),
                }

        # Total
        total_market_id = game_markets.get("total")
        if total_market_id:
            line, over_odds, under_odds = None, None, None
            for s in selections_by_market.get(total_market_id, []):
                outcome = str(s.get("outcomeType", "")).lower()
                display = s.get("displayOdds")
                american = (
                    _to_american(display.get("american"))
                    if isinstance(display, dict)
                    else None
                )
                points = s.get("points")
                try:
                    sel_line = float(points) if points is not None else None
                except (TypeError, ValueError):
                    sel_line = None
                if sel_line is not None:
                    line = sel_line
                if outcome == "over":
                    over_odds = american
                elif outcome == "under":
                    under_odds = american
            if None not in (line, over_odds, under_odds):
                row_markets["total"] = {
                    "line": float(line),
                    "over_odds": int(over_odds),
                    "under_odds": int(under_odds),
                }

        if not row_markets:
            continue

        rows.append(
            {
                "game_id": f"nba_dk_{event_id}",
                "sport": "NBA",
                "home_team": home,
                "away_team": away,
                "commence_time": event.get("startEventDate") or fetched_at,
                "sportsbook": "DraftKings",
                "markets": row_markets,
                "last_updated": fetched_at,
            }
        )
    return rows


def fetch_and_normalize_draftkings_nba(timeout_seconds: float = 20.0) -> dict[str, Any]:
    payload = fetch_raw_draftkings_nba(timeout_seconds=timeout_seconds)
    rows = normalize_draftkings_payload(payload)
    return {
        "description": "Live DraftKings NBA odds snapshot",
        "generated": _iso_now(),
        "notes": [
            "Source: DraftKings sportsbook API endpoint (sportsbook-nash)",
            "Rows contain DraftKings only (one sportsbook)",
        ],
        "source": "draftkings_live",
        "odds": rows,
        "raw_counts": {
            "events": len(payload.get("events", [])) if isinstance(payload.get("events"), list) else 0,
            "markets": len(payload.get("markets", [])) if isinstance(payload.get("markets"), list) else 0,
            "selections": len(payload.get("selections", []))
            if isinstance(payload.get("selections"), list)
            else 0,
        },
    }
