from moneyscheme.novig.catalog import (
    _event_matches,
    _name_exact,
    _parse_prop_player,
    _parse_selection,
    _prop_player_matches,
    _teams_in_event_description,
)


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


def test_teams_in_event_description():
    assert _teams_in_event_description(
        "Warriors / Spurs",
        "Golden State Warriors @ San Antonio Spurs",
    )
    assert _teams_in_event_description(
        "Central Arkansas / Arkansas",
        "Central Arkansas @ Arkansas",
    )
    assert not _teams_in_event_description(
        "Central Arkansas / Arkansas",
        "Arkansas Pine Bluff @ California Baptist",
    )


def test_prop_player_initial_disambiguates():
    prop = _parse_prop_player("Rebounds (Green, D)")
    assert prop == {"last": "green", "initial": "d"}
    assert _prop_player_matches(prop, "Draymond Green 5.5 REBOUNDS")
    assert not _prop_player_matches(prop, "Josh Green 5.5 REBOUNDS")
