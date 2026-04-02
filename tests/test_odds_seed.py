import pytest


@pytest.fixture
def no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_ensure_skipped_without_database_url(no_database_url):
    from services.odds_seed import ensure_odds_seeded

    r = ensure_odds_seeded()
    assert r["status"] == "skipped"
    assert r["reason"] == "no_database_url"


def test_force_true_still_skipped_without_url(no_database_url):
    from services.odds_seed import ensure_odds_seeded

    r = ensure_odds_seeded(force=True)
    assert r["status"] == "skipped"
