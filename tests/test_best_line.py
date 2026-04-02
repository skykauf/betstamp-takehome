from services.best_line import best_line_for_side


def test_best_line_moneyline_home_known_game():
    r = best_line_for_side("nba_20260320_lal_bos", "moneyline_home")
    assert "error" not in r
    assert r["best"]["sportsbook"]
    assert isinstance(r["best"]["american"], int)
    assert 0 < r["best"]["implied_probability"] < 1
    assert len(r["all_books_ranked_best_to_worst"]) >= 1


def test_best_line_unknown_game():
    r = best_line_for_side("nba_invalid", "moneyline_home")
    assert "error" in r


def test_best_line_invalid_side():
    r = best_line_for_side("nba_20260320_lal_bos", "not_a_side")
    assert "error" in r
