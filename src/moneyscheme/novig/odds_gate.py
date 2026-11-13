from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from moneyscheme.models import Opportunity
from moneyscheme.novig.catalog import CatalogMatch
from moneyscheme.novig.client import NovigClient
from moneyscheme.novig.money import (
    ask_as_good_as,
    ask_from_other_bid,
    opportunity_to_novig_price,
    percent_to_probability,
    probability_to_american,
)


@dataclass
class OddsCheck:
    ok: bool
    reason: str
    target_price: str
    available_ask: Optional[str] = None
    available_american: Optional[int] = None
    book: Optional[dict[str, Any]] = None


def check_odds(
    client: NovigClient,
    opp: Opportunity,
    match: CatalogMatch,
) -> OddsCheck:
    target_price = opportunity_to_novig_price(
        odds_percent=opp.odds_percent or None,
        odds_american=opp.odds_american or None,
    )
    target_prob = (
        percent_to_probability(opp.odds_percent)
        if opp.odds_percent > 0
        else None
    )
    market_id = match.market_id
    book = client.request("GET", f"/v3/catalog/markets/{market_id}/book")
    orders = book.get("orders") or {}

    # Find the other outcome in this market
    other_ids = [
        o["outcomeId"]
        for o in (match.market.get("outcomes") or [])
        if o.get("outcomeId") != match.outcome_id
    ]
    if len(other_ids) != 1:
        return OddsCheck(
            ok=False,
            reason="book_shape_unexpected",
            target_price=target_price,
            book=book,
        )
    other_id = other_ids[0]
    other_orders = orders.get(other_id) or []
    if not other_orders:
        # Fall back to catalog ticker bid if present
        other_outcome = next(
            (o for o in match.market.get("outcomes") or [] if o.get("outcomeId") == other_id),
            None,
        )
        bid = (other_outcome or {}).get("bid") or {}
        if not bid.get("price"):
            return OddsCheck(
                ok=False,
                reason="no_ask_available",
                target_price=target_price,
                book=book,
            )
        other_bid = str(bid["price"])
    else:
        # Best bid = highest price on that outcome
        other_bid = max(other_orders, key=lambda o: Decimal(str(o["price"])))["price"]

    ask = ask_from_other_bid(str(other_bid))
    ask_s = f"{ask:.3f}"
    avail_amer = probability_to_american(ask)
    if target_prob is None:
        from moneyscheme.novig.money import american_to_probability, odds_as_good_as

        ok = odds_as_good_as(opp.odds_american, ask)
    else:
        ok = ask_as_good_as(target_prob, ask)
    if ok:
        return OddsCheck(
            ok=True,
            reason="odds_ok",
            target_price=target_price,
            available_ask=ask_s,
            available_american=avail_amer,
            book=book,
        )
    return OddsCheck(
        ok=False,
        reason="odds_moved",
        target_price=target_price,
        available_ask=ask_s,
        available_american=avail_amer,
        book=book,
    )
