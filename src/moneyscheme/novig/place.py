from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from moneyscheme.decision.sizing import kelly_stake
from moneyscheme.models import Decision, Opportunity
from moneyscheme.novig.catalog import CatalogMatch, match_opportunity
from moneyscheme.novig.client import NovigClient
from moneyscheme.novig.money import american_to_novig_price, stake_to_qty
from moneyscheme.novig.odds_gate import OddsCheck, check_odds


@dataclass
class PlacePlan:
    opportunity: Opportunity
    match: Optional[CatalogMatch]
    odds: Optional[OddsCheck]
    price: Optional[str]
    qty: int
    tif: str = "IOC"
    action: str = "skip"  # skip | ready
    reason: str = ""
    order_body: Optional[dict[str, Any]] = None


def build_place_plan(
    trading: NovigClient,
    decision: Decision,
    *,
    bankroll: float,
    kelly_fraction: float,
) -> PlacePlan:
    opp = decision.opportunity
    if decision.action != "take":
        return PlacePlan(
            opportunity=opp,
            match=None,
            odds=None,
            price=None,
            qty=0,
            action="skip",
            reason=f"decision_{decision.action}:{decision.reason}",
        )

    matched = match_opportunity(trading, opp)
    if matched is None:
        return PlacePlan(
            opportunity=opp,
            match=None,
            odds=None,
            price=None,
            qty=0,
            action="skip",
            reason="no_exact_match",
        )

    odds = check_odds(trading, opp, matched)
    if not odds.ok:
        return PlacePlan(
            opportunity=opp,
            match=matched,
            odds=odds,
            price=odds.target_price,
            qty=0,
            action="skip",
            reason=odds.reason,
        )

    price = odds.target_price  # limit at OCR'd +EV odds (snapped)
    stake = decision.suggested_stake
    if stake <= 0:
        stake = kelly_stake(
            odds_american=opp.odds_american,
            ev_percent=opp.ev_percent,
            bankroll=bankroll,
            kelly_fraction=kelly_fraction,
            max_stake=opp.max_stake,
        )
    qty = stake_to_qty(stake, price)
    if qty < 1:
        return PlacePlan(
            opportunity=opp,
            match=matched,
            odds=odds,
            price=price,
            qty=0,
            action="skip",
            reason="qty_zero",
        )

    body = {
        "outcomeId": matched.outcome_id,
        "price": price,
        "qty": qty,
        "tif": "IOC",
        "clientId": str(uuid.uuid4()),
    }
    return PlacePlan(
        opportunity=opp,
        match=matched,
        odds=odds,
        price=price,
        qty=qty,
        action="ready",
        reason="ready_to_place",
        order_body=body,
    )


def place_ioc(trading: NovigClient, plan: PlacePlan) -> Any:
    if plan.action != "ready" or not plan.order_body:
        raise ValueError(f"cannot place: {plan.reason}")
    return trading.request("POST", "/v3/orders", body=plan.order_body)
