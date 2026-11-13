from decimal import Decimal

from moneyscheme.novig.money import (
    american_to_novig_price,
    american_to_probability,
    ask_from_other_bid,
    odds_as_good_as,
    snap_price_down,
    stake_to_qty,
)


def test_plus_odds_to_price():
    # +100 -> 0.500
    assert american_to_novig_price(100) == "0.500"
    # +102 -> ~0.495
    assert american_to_novig_price(102) == "0.495"


def test_snap_grid():
    assert snap_price_down(Decimal("0.667")) == "0.665"
    assert snap_price_down(Decimal("0.495")) == "0.495"


def test_stake_to_qty():
    # $0.495 cost per contract-cent unit: qty = stake/(price*0.01)
    qty = stake_to_qty(4.95, "0.495")
    assert qty == 1000


def test_odds_gate_same_or_better():
    ask = ask_from_other_bid("0.505")  # ask = 0.495
    assert odds_as_good_as(102, ask) is True
    worse = ask_from_other_bid("0.400")  # ask = 0.600 worse than ~0.495
    assert odds_as_good_as(102, worse) is False


def test_implied():
    assert abs(float(american_to_probability(-110)) - (110 / 210)) < 1e-9
