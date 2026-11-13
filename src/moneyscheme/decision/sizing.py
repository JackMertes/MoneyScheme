from __future__ import annotations

from typing import Optional


def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1.0 + (odds / 100.0)
    return 1.0 + (100.0 / abs(odds))


def american_implied_prob(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def kelly_stake(
    *,
    odds_american: int,
    ev_percent: float,
    bankroll: float,
    kelly_fraction: float,
    max_stake: Optional[float] = None,
) -> float:
    """
    Size a stake from EV% and American odds.

    Pick the Odds EV% is (edge). Approximate true win probability as:
      p = implied_prob * (1 + ev_percent/100)
    then apply fractional Kelly and cap by max_stake / bankroll.
    """
    if bankroll <= 0 or kelly_fraction <= 0:
        return 0.0
    if odds_american == 0:
        return 0.0

    implied = american_implied_prob(odds_american)
    p = implied * (1.0 + ev_percent / 100.0)
    p = min(max(p, 0.0), 1.0)
    decimal = american_to_decimal(odds_american)
    b = decimal - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0

    stake = bankroll * full_kelly * kelly_fraction
    if max_stake is not None:
        stake = min(stake, max_stake)
    stake = min(stake, bankroll)
    return round(max(stake, 0.0), 2)
