from services.database import validate_readonly_select


def test_accepts_simple_select():
    assert validate_readonly_select("SELECT 1") is None


def test_rejects_delete():
    assert validate_readonly_select("DELETE FROM odds_lines") is not None


def test_rejects_double_statement():
    assert validate_readonly_select("SELECT 1; SELECT 2") is not None
