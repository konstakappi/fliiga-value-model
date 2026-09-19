from fliiga_model.quick_input import parse_bookmaker_odds


def test_parse_bookmaker_odds_accepts_decimal_commas_and_extra_line():
    text = """
    Coolbet 9,5 1,75 1,96
    Unibet | Over 1.82 | Under 1.91
    jotain muuta
    """
    parsed = parse_bookmaker_odds(text, ["Coolbet", "Unibet", "Veikkaus"])
    assert parsed == {"Coolbet": (1.75, 1.96), "Unibet": (1.82, 1.91)}


def test_parse_bookmaker_odds_ignores_incomplete_rows():
    parsed = parse_bookmaker_odds("Veikkaus 1,90", ["Veikkaus"])
    assert parsed == {}
