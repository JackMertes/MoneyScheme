from __future__ import annotations

import re
from typing import List, Optional, Sequence

from moneyscheme.config import Settings, get_settings
from moneyscheme.decision.portfolio import Portfolio
from moneyscheme.decision.sizing import kelly_stake
from moneyscheme.models import Decision, Opportunity


_TIP_RE = re.compile(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", re.I)


def _tip_token(status: str) -> str:
    """Pull tip time from PTO STATUS (e.g. '6:10 PM In 4 hours' → '6:10 pm')."""
    if not status:
        return ""
    m = _TIP_RE.search(status)
    return m.group(1).casefold() if m else ""


def event_key(event: str, status: str = "") -> str:
    """
    Normalize a game so team order does not matter.

    Includes tip time from STATUS when present so a rematch next week
    (same teams, different tip) is a different event.
    """
    parts = [p.strip().lower() for p in event.split("/") if p.strip()]
    if len(parts) < 2:
        parts = [
            p.strip().lower()
            for p in re.split(r"\s+vs\.?\s+", event, flags=re.I)
            if p.strip()
        ]
    if not parts:
        base = event.strip().lower()
    else:
        base = " / ".join(sorted(parts))
    tip = _tip_token(status)
    return f"{base}|{tip}" if tip else base


def decide(
    opportunity: Opportunity,
    portfolio: Portfolio,
    settings: Optional[Settings] = None,
    *,
    commit: bool = False,
) -> Decision:
    """Decide take/skip for one opportunity against portfolio state."""
    settings = settings or get_settings()
    fp = opportunity.fingerprint()
    ek = event_key(opportunity.event, opportunity.status)
    suggested = kelly_stake(
        odds_american=opportunity.odds_american,
        ev_percent=opportunity.ev_percent,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        max_stake=opportunity.max_stake,
    )

    if opportunity.ev_percent < settings.min_ev_percent:
        return Decision(
            action="skip",
            reason=f"ev_below_min ({opportunity.ev_percent}% < {settings.min_ev_percent}%)",
            opportunity=opportunity,
            suggested_stake=suggested,
        )

    allow = settings.market_allowlist_set()
    if allow:
        sel = opportunity.selection.strip().lower()
        if not any(a in sel for a in allow):
            return Decision(
                action="skip",
                reason=f"selection_not_in_allowlist ({opportunity.selection})",
                opportunity=opportunity,
                suggested_stake=suggested,
            )

    if fp in portfolio.fingerprints_active():
        return Decision(
            action="skip",
            reason="already_taken",
            opportunity=opportunity,
            suggested_stake=suggested,
        )

    if settings.one_bet_per_game and ek in portfolio.event_keys_active():
        return Decision(
            action="skip",
            reason="same_event_already_active",
            opportunity=opportunity,
            suggested_stake=suggested,
        )

    if portfolio.count_active() >= settings.max_open_bets:
        return Decision(
            action="skip",
            reason=f"max_open_bets ({settings.max_open_bets})",
            opportunity=opportunity,
            suggested_stake=suggested,
        )

    if suggested <= 0 and opportunity.ev_percent > 0:
        # Still allow take with stake 0 logged; sizing can be refined later
        pass

    if commit:
        portfolio.add_pending(
            fingerprint=fp,
            event_key=ek,
            selection=opportunity.selection,
            odds_american=opportunity.odds_american,
            opportunity_json=opportunity.model_dump_json(),
        )

    return Decision(
        action="take",
        reason="passed_rules",
        opportunity=opportunity,
        suggested_stake=suggested,
    )


def decide_many(
    opportunities: Sequence[Opportunity],
    portfolio: Portfolio,
    settings: Optional[Settings] = None,
    *,
    commit: bool = False,
) -> List[Decision]:
    """
    Decide on a batch (e.g. one screenshot).

    Highest EV first so the best line on a game wins under one-bet-per-game.
    Within the batch we also track provisional takes so later rows see them.
    """
    settings = settings or get_settings()
    ordered = sorted(opportunities, key=lambda o: o.ev_percent, reverse=True)
    decisions: List[Decision] = []

    # Provisional state for this batch (does not hit DB unless commit=True on take)
    provisional_fps = set(portfolio.fingerprints_active())
    provisional_events = set(portfolio.event_keys_active())
    provisional_count = portfolio.count_active()

    for opp in ordered:
        # Temporarily shadow portfolio checks via a thin wrapper path:
        # reuse decide() only when not needing provisional; for batch we inline.
        fp = opp.fingerprint()
        ek = event_key(opp.event, opp.status)
        suggested = kelly_stake(
            odds_american=opp.odds_american,
            ev_percent=opp.ev_percent,
            bankroll=settings.bankroll,
            kelly_fraction=settings.kelly_fraction,
            max_stake=opp.max_stake,
        )

        if opp.ev_percent < settings.min_ev_percent:
            decisions.append(
                Decision(
                    action="skip",
                    reason=f"ev_below_min ({opp.ev_percent}% < {settings.min_ev_percent}%)",
                    opportunity=opp,
                    suggested_stake=suggested,
                )
            )
            continue

        allow = settings.market_allowlist_set()
        if allow and not any(a in opp.selection.strip().lower() for a in allow):
            decisions.append(
                Decision(
                    action="skip",
                    reason=f"selection_not_in_allowlist ({opp.selection})",
                    opportunity=opp,
                    suggested_stake=suggested,
                )
            )
            continue

        if fp in provisional_fps:
            decisions.append(
                Decision(
                    action="skip",
                    reason="already_taken",
                    opportunity=opp,
                    suggested_stake=suggested,
                )
            )
            continue

        if settings.one_bet_per_game and ek in provisional_events:
            decisions.append(
                Decision(
                    action="skip",
                    reason="same_event_already_active",
                    opportunity=opp,
                    suggested_stake=suggested,
                )
            )
            continue

        if provisional_count >= settings.max_open_bets:
            decisions.append(
                Decision(
                    action="skip",
                    reason=f"max_open_bets ({settings.max_open_bets})",
                    opportunity=opp,
                    suggested_stake=suggested,
                )
            )
            continue

        if commit:
            portfolio.add_pending(
                fingerprint=fp,
                event_key=ek,
                selection=opp.selection,
                odds_american=opp.odds_american,
                opportunity_json=opp.model_dump_json(),
            )

        provisional_fps.add(fp)
        provisional_events.add(ek)
        provisional_count += 1
        decisions.append(
            Decision(
                action="take",
                reason="passed_rules",
                opportunity=opp,
                suggested_stake=suggested,
            )
        )

    return decisions
