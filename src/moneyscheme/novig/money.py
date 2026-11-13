from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Optional


def american_to_probability(odds: int) -> Decimal:
    if odds == 0:
        raise ValueError("odds cannot be 0")
    if odds > 0:
        return Decimal(100) / (Decimal(odds) + Decimal(100))
    return Decimal(abs(odds)) / (Decimal(abs(odds)) + Decimal(100))


def probability_to_american(p: Decimal) -> int:
    if p <= 0 or p >= 1:
        raise ValueError("probability must be in (0,1)")
    if p < Decimal("0.5"):
        return int((Decimal(100) * (Decimal(1) - p) / p).to_integral_value(rounding=ROUND_HALF_UP))
    return int((-Decimal(100) * p / (Decimal(1) - p)).to_integral_value(rounding=ROUND_HALF_UP))


def snap_price_down(p: Decimal) -> str:
    """Snap probability down onto Novig's price grid; return 3-place string."""
    milli = int((p * Decimal(1000)).to_integral_value(rounding=ROUND_DOWN))
    snapped = _snap_milli_down(milli)
    if snapped is None:
        raise ValueError(f"price out of range: {p}")
    return f"{Decimal(snapped) / Decimal(1000):.3f}"


def _snap_milli_down(milli: int) -> Optional[int]:
    if 1 <= milli <= 50 or 950 <= milli <= 999:
        return milli
    if 51 <= milli <= 949:
        return milli - (milli % 5)
    return None


def american_to_novig_price(odds: int) -> str:
    return snap_price_down(american_to_probability(odds))


def stake_to_qty(stake_dollars: float, price: str) -> int:
    """
    cost = price * qty * $0.01
    => qty = stake / (price * 0.01)
    """
    p = Decimal(price)
    if p <= 0:
        raise ValueError("invalid price")
    stake = Decimal(str(stake_dollars))
    if stake <= 0:
        return 0
    qty = (stake / (p * Decimal("0.01"))).to_integral_value(rounding=ROUND_DOWN)
    return int(max(qty, 0))


def ask_from_other_bid(other_bid_price: str) -> Decimal:
    """Book only has bids; ask on this outcome is 1 - bid on the other."""
    return Decimal("1") - Decimal(other_bid_price)


def odds_as_good_as(target_american: int, available_ask: Decimal) -> bool:
    """True if available ask is same or better (lower probability cost) than target odds."""
    target = american_to_probability(target_american)
    # Allow tiny grid/float slack of half a milli
    return available_ask <= target + Decimal("0.0005")
