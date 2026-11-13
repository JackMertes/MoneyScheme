from pathlib import Path

from moneyscheme.config import Settings
from moneyscheme.decision.engine import decide_many, event_key
from moneyscheme.decision.portfolio import Portfolio
from moneyscheme.decision.sizing import kelly_stake
from moneyscheme.models import Opportunity


def _opp(**kwargs) -> Opportunity:
    base = dict(
        league="Tennis",
        status="2:00 AM",
        ev_percent=2.5,
        event="Adrian Andreev / Michele Ribecai",
        odds_american=102,
        max_stake=198.0,
        selection="Under 21.5",
        book="novig",
        confidence=0.9,
    )
    base.update(kwargs)
    return Opportunity(**base)


def test_event_key_order_invariant():
    a = event_key("Adrian Andreev / Michele Ribecai")
    b = event_key("Michele Ribecai / Adrian Andreev")
    assert a == b


def test_one_bet_per_game_keeps_best_ev(tmp_path: Path):
    settings = Settings(
        min_ev_percent=0.0,
        one_bet_per_game=True,
        max_open_bets=20,
        bankroll=1000,
        kelly_fraction=0.33,
    )
    portfolio = Portfolio(tmp_path / "p.db")
    opps = [
        _opp(ev_percent=1.0, selection="Under 21.5", odds_american=102),
        _opp(ev_percent=3.0, selection="Adrian Andreev", odds_american=141),
        _opp(ev_percent=2.0, selection="Michele Ribecai", odds_american=-150),
    ]
    decisions = decide_many(opps, portfolio, settings, commit=True)
    takes = [d for d in decisions if d.action == "take"]
    skips = [d for d in decisions if d.action == "skip"]
    assert len(takes) == 1
    assert takes[0].opportunity.selection == "Adrian Andreev"
    assert len(skips) == 2
    assert all(d.reason == "same_event_already_active" for d in skips)
    assert portfolio.count_active() == 1


def test_dedupe_same_fingerprint(tmp_path: Path):
    settings = Settings(min_ev_percent=0.0, one_bet_per_game=False)
    portfolio = Portfolio(tmp_path / "p.db")
    opp = _opp()
    first = decide_many([opp], portfolio, settings, commit=True)
    second = decide_many([opp], portfolio, settings, commit=True)
    assert first[0].action == "take"
    assert second[0].action == "skip"
    assert second[0].reason == "already_taken"


def test_min_ev_skips_negative_file(tmp_path: Path):
    settings = Settings(min_ev_percent=0.0)
    portfolio = Portfolio(tmp_path / "p.db")
    decisions = decide_many(
        [_opp(ev_percent=-1.6)], portfolio, settings, commit=False
    )
    assert decisions[0].action == "skip"
    assert "ev_below_min" in decisions[0].reason


def test_kelly_positive_for_plus_ev():
    stake = kelly_stake(
        odds_american=100,
        ev_percent=5.0,
        bankroll=1000,
        kelly_fraction=0.33,
        max_stake=200,
    )
    assert stake > 0
    assert stake <= 200
