from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from moneyscheme.app.countdown import wait_for_switch
from moneyscheme.config import get_settings
from moneyscheme.decision import Portfolio, decide_many
from moneyscheme.models import Decision, Opportunity
from moneyscheme.novig.bootstrap import trading_client
from moneyscheme.novig.client import NovigClient
from moneyscheme.novig.place import PlacePlan, build_place_plan, place_ioc
from moneyscheme.pipeline import opportunities_from_path, opportunities_from_screen


def _confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes"}


def _opp_report(o: Opportunity) -> dict:
    """Compact opportunity view for stdout."""
    row = {
        "league": o.league,
        "status": o.status,
        "ev": o.ev_percent,
        "event": o.event,
        "market": o.market or None,
        "selection": o.selection,
        "odds": o.odds_price,
        "max": o.max_stake,
        "wager": o.wager,
    }
    return {k: v for k, v in row.items() if v is not None and v != ""}


def _decision_report(d: Decision) -> dict:
    row = _opp_report(d.opportunity)
    row["action"] = d.action
    row["reason"] = d.reason
    if d.suggested_stake:
        row["stake"] = d.suggested_stake
    return row


def _plan_report(plan: PlacePlan, place_result=None) -> dict:
    o = plan.opportunity
    row = {
        "action": plan.action,
        "reason": plan.reason,
        "status": o.status or None,
        "event": o.event,
        "market": o.market or None,
        "selection": o.selection,
        "odds": o.odds_price,
        "ask": plan.odds.available_ask if plan.odds else None,
        "max": o.max_stake,
        "wager": o.wager,
        "outcomeId": plan.match.outcome_id if plan.match else None,
    }
    if plan.action == "ready" and plan.price and plan.price != o.odds_price:
        row["limit"] = plan.price
    if place_result is not None:
        row["place_result"] = place_result
    return {k: v for k, v in row.items() if v is not None and v != ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture Pick the Odds EV table → Opportunity → Decision → Paper"
    )
    parser.add_argument("--image", type=Path, help="Parse a screenshot/fixture")
    parser.add_argument("--live", action="store_true", help="Capture screen ROI")
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="For --live: seconds to switch windows (default: 5)",
    )
    parser.add_argument("--decide", action="store_true", help="Run Decision take/skip")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="With --decide: write takes into local portfolio DB",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="With --decide: build Novig Paper IOC plans (match + odds gate)",
    )
    parser.add_argument(
        "--place",
        action="store_true",
        help="With --paper: after confirm, place IOC orders on Paper",
    )
    parser.add_argument(
        "--allow-odds-moved",
        action="store_true",
        help="With --paper: if ask is worse than OCR, still place at the current ask",
    )
    parser.add_argument(
        "--place-one",
        action="store_true",
        help="With --place: only place the first ready plan",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="With --place: skip interactive confirm",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    saved_shot: Path | None = None
    if args.image:
        opps = opportunities_from_path(args.image)
    elif args.live:
        wait_for_switch(args.delay)
        opps, saved_shot = opportunities_from_screen()
        print(f"# saved screenshot: {saved_shot}", file=sys.stderr)
    else:
        parser.error("Provide --image PATH or --live")

    settings = get_settings()

    if not args.decide:
        payload = [_opp_report(o) for o in opps]
        print(f"# {len(opps)} opportunities", file=sys.stderr)
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 0

    portfolio = Portfolio(settings.portfolio_db)
    decisions = decide_many(opps, portfolio, settings, commit=args.commit)
    takes = sum(1 for d in decisions if d.action == "take")
    print(
        f"# {len(opps)} opportunities → {takes} take, {len(decisions) - takes} skip",
        file=sys.stderr,
    )

    if not args.paper:
        payload = [_decision_report(d) for d in decisions]
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 0

    # Paper path uses trading key if set, else management (catalog-only works with either)
    if settings.novig_trading_key_id and Path(settings.novig_trading_pem_path).exists():
        client = trading_client(
            host=settings.novig_host,
            trading_key_id=settings.novig_trading_key_id,
            trading_pem_path=settings.novig_trading_pem_path,
        )
    else:
        client = NovigClient.from_settings(settings)
        if args.place:
            print(
                "Missing trading key. Run: python -m moneyscheme.app.novig_bootstrap",
                file=sys.stderr,
            )
            return 2

    plans = [
        build_place_plan(
            client,
            d,
            bankroll=settings.bankroll,
            kelly_fraction=settings.kelly_fraction,
            allow_worse_odds=args.allow_odds_moved,
        )
        for d in decisions
    ]
    payload = []
    placed = 0
    for plan in plans:
        place_result = None
        can_place = args.place and plan.action == "ready"
        if can_place and args.place_one and placed >= 1:
            place_result = {"skipped": "place_one_limit"}
            payload.append(_plan_report(plan, place_result))
            continue
        if can_place:
            summary = (
                f"PLACE IOC {plan.opportunity.selection} @ {plan.price} "
                f"qty={plan.qty} (odds {plan.opportunity.odds_price}, "
                f"ask {plan.odds.available_ask if plan.odds else '?'}, "
                f"{plan.reason})"
            )
            print(summary, file=sys.stderr)
            confirmed = args.yes or _confirm("Confirm Paper IOC order?")
            if confirmed:
                place_result = place_ioc(client, plan)
                placed += 1
                if args.commit:
                    portfolio.mark_open(plan.opportunity.fingerprint())
            else:
                place_result = {"skipped": "user_declined"}
        payload.append(_plan_report(plan, place_result))

    ready = sum(1 for p in plans if p.action == "ready")
    print(f"# paper plans: {ready} ready, {len(plans) - ready} skip", file=sys.stderr)
    print(json.dumps(payload, indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
