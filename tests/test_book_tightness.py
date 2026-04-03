"""slate_book_tightness."""

from __future__ import annotations

from services import book_tightness


def test_slate_book_tightness_returns_ranked_books():
    out = book_tightness.slate_book_tightness()
    assert "error" not in out
    assert out["book_count"] >= 1
    books = out["books_ranked_tightest_first"]
    assert len(books) == out["book_count"]
    # ascending by avg vig
    vigs = [b["avg_vig_percent"] for b in books]
    assert vigs == sorted(vigs)
    assert all("sportsbook" in b for b in books)
