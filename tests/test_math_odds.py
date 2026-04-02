from services.math_odds import american_to_implied_probability, two_sided_market


def test_negative_american_implied():
    p = american_to_implied_probability(-150)
    assert abs(p - 0.6) < 1e-6


def test_positive_american_implied():
    p = american_to_implied_probability(200)
    assert abs(p - 1 / 3) < 1e-6


def test_even_vig_standard():
    m = two_sided_market(-110, -110)
    expected = 2 * (110 / 210) - 1
    assert abs(m["vig_decimal"] - expected) < 1e-4
