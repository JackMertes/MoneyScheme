from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneyscheme.app.countdown import wait_for_switch
from moneyscheme.config import Settings, get_settings
from moneyscheme.decision import Portfolio, decide_many
from moneyscheme.decision.engine import event_key
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


def _append_bet_log(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _record_placed(
    portfolio: Portfolio,
    plan: PlacePlan,
    place_result: Any,
    bet_log: Path,
) -> None:
    o = plan.opportunity
    ek = event_key(o.event, o.status)
    portfolio.record_open(
        fingerprint=o.fingerprint(),
        event_key=ek,
        selection=o.selection,
        odds_american=o.odds_american,
        opportunity_json=o.model_dump_json(),
    )
    _append_bet_log(
        bet_log,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": o.event,
            "event_key": ek,
            "market": o.market,
            "selection": o.selection,
            "odds": o.odds_price,
            "ask": plan.odds.available_ask if plan.odds else None,
            "limit": plan.price,
            "qty": plan.qty,
            "stake": plan.qty * float(plan.price or 0) * 0.01 if plan.price else None,
            "outcomeId": plan.match.outcome_id if plan.match else None,
            "place_result": place_result,
        },
    )


def _run_cycle(args: argparse.Namespace, settings: Settings, *, cycle: int) -> int:
    saved_shot: Path | None = None
    if args.image:
        opps = opportunities_from_path(args.image)
    elif args.live:
        # Only countdown on the first cycle so watch mode can sit on PTO.
        delay = args.delay if cycle == 1 else 0.0
        if delay > 0:
            wait_for_switch(delay)
        opps, saved_shot = opportunities_from_screen()
        print(f"# saved screenshot: {saved_shot}", file=sys.stderr)
    else:
        raise SystemExit("Provide --image PATH or --live")

    if not args.decide:
        payload = [_opp_report(o) for o in opps]
        print(f"# {len(opps)} opportunities", file=sys.stderr)
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 0

    portfolio = Portfolio(settings.portfolio_db)
    decisions = decide_many(opps, portfolio, settings, commit=args.commit)
    takes = sum(1 for d in decisions if d.action == "take")
    print(
        f"# {len(opps)} opportunities → {takes} take, {len(decisions) - takes} skip "
        f"(portfolio active={portfolio.count_active()})",
        file=sys.stderr,
    )

    if not args.paper:
        payload = [_decision_report(d) for d in decisions]
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 0

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
    bet_log = Path(args.bet_log)
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
                # Always persist placed bets so later cycles skip the same event.
                _record_placed(portfolio, plan, place_result, bet_log)
            else:
                place_result = {"skipped": "user_declined"}
        payload.append(_plan_report(plan, place_result))

    ready = sum(1 for p in plans if p.action == "ready")
    print(
        f"# paper plans: {ready} ready, {len(plans) - ready} skip, placed={placed}",
        file=sys.stderr,
    )
    print(json.dumps(payload, indent=2 if args.pretty else None, default=str))
    return 0


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
        help="For --live: seconds to switch windows on first cycle (default: 5)",
    )
    parser.add_argument("--decide", action="store_true", help="Run Decision take/skip")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="With --decide: write Decision takes into portfolio DB before place",
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
        help="With --place: only place the first ready plan per cycle",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="With --place: skip interactive confirm",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="Seconds between live cycles (0 = run once). Ctrl+C to stop.",
    )
    parser.add_argument(
        "--bet-log",
        type=Path,
        default=Path("data/bet_log.jsonl"),
        help="Append placed bets here (default: data/bet_log.jsonl)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    if args.interval and not args.live:
        parser.error("--interval requires --live")
    if args.interval and args.image:
        parser.error("--interval cannot be used with --image")

    settings = get_settings()
    cycle = 0
    try:
        while True:
            cycle += 1
            if args.interval:
                print(
                    f"\n# --- cycle {cycle} @ {datetime.now().isoformat(timespec='seconds')} ---",
                    file=sys.stderr,
                )
            code = _run_cycle(args, settings, cycle=cycle)
            if code != 0:
                return code
            if not args.interval:
                return 0
            print(f"# sleeping {args.interval:.0f}s …", file=sys.stderr)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n# stopped", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
