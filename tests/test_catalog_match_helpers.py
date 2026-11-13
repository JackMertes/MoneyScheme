from moneyscheme.novig.catalog import _event_matches, _name_exact, _parse_selection


def test_parse_under():
    p = _parse_selection("Under 21.5")
    assert p["kind"] == "total"
    assert p["side"] == "Under"
    assert p["strike"] == "21.5"


def test_name_abbreviation_exact():
    assert _name_exact("Michele Ribecai", "M. Ribecai")
    assert _name_exact("Adrian Andreev", "Adrian Andreev")
    assert not _name_exact("Adrian Andreev", "M. Ribecai")


def test_event_both_surnames():
    assert _event_matches(
        "Adrian Andreev / Michele Ribecai",
        "A. Andreev @ M. Ribecai t21.5",
    )
    assert _event_matches(
        "J. Forejtek / M. Moeller",
        "J. Forejtek",
        outcome_names=["J. Forejtek", "M. Moeller"],
    )
    assert not _event_matches(
        "Adrian Andreev / Michele Ribecai",
        "J. Forejtek @ M. Moeller",
    )
