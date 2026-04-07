from __future__ import annotations

from services import draftkings_odds, odds_repository


def _sample_payload() -> dict:
    return {
        "events": [
            {
                "id": "123",
                "startEventDate": "2026-04-08T00:10:00.0000000Z",
                "participants": [
                    {"name": "Away Team", "venueRole": "Away"},
                    {"name": "Home Team", "venueRole": "Home"},
                ],
            }
        ],
        "markets": [
            {
                "id": "m1",
                "eventId": "123",
                "marketType": {"name": "Moneyline"},
            },
            {
                "id": "m2",
                "eventId": "123",
                "marketType": {"name": "Spread"},
            },
            {
                "id": "m3",
                "eventId": "123",
                "marketType": {"name": "Total"},
            },
        ],
        "selections": [
            {"marketId": "m1", "outcomeType": "Away", "displayOdds": {"american": "+120"}},
            {"marketId": "m1", "outcomeType": "Home", "displayOdds": {"american": "-130"}},
            {
                "marketId": "m2",
                "outcomeType": "Away",
                "points": 3.5,
                "displayOdds": {"american": "-110"},
            },
            {
                "marketId": "m2",
                "outcomeType": "Home",
                "points": -3.5,
                "displayOdds": {"american": "-110"},
            },
            {
                "marketId": "m3",
                "outcomeType": "Over",
                "points": 221.5,
                "displayOdds": {"american": "-105"},
            },
            {
                "marketId": "m3",
                "outcomeType": "Under",
                "points": 221.5,
                "displayOdds": {"american": "-115"},
            },
        ],
    }


def test_normalize_draftkings_payload_to_internal_rows() -> None:
    rows = draftkings_odds.normalize_draftkings_payload(_sample_payload())
    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == "nba_dk_123"
    assert row["home_team"] == "Home Team"
    assert row["away_team"] == "Away Team"
    assert row["sportsbook"] == "DraftKings"
    assert row["markets"]["moneyline"]["home_odds"] == -130
    assert row["markets"]["moneyline"]["away_odds"] == 120
    assert row["markets"]["spread"]["home_line"] == -3.5
    assert row["markets"]["spread"]["away_line"] == 3.5
    assert row["markets"]["total"]["line"] == 221.5


def test_runtime_payload_switching() -> None:
    payload = {
        "description": "runtime",
        "generated": "2026-01-01T00:00:00Z",
        "notes": [],
        "source": "draftkings_live",
        "odds": [
            {
                "game_id": "nba_dk_1",
                "sport": "NBA",
                "home_team": "H",
                "away_team": "A",
                "commence_time": "2026-01-01T00:00:00Z",
                "sportsbook": "DraftKings",
                "markets": {"moneyline": {"home_odds": -110, "away_odds": -110}},
                "last_updated": "2026-01-01T00:00:00Z",
            }
        ],
    }
    odds_repository.use_runtime_payload(payload)
    try:
        meta = odds_repository.dataset_meta()
        assert meta["source"] == "draftkings_live"
        assert meta["record_count"] == 1
        assert odds_repository.list_games()[0]["game_id"] == "nba_dk_1"
    finally:
        odds_repository.clear_runtime_payload()
