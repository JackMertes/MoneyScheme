from moneyscheme.config import get_settings
from moneyscheme.models import Decision, Opportunity
from moneyscheme.novig.bootstrap import trading_client
from moneyscheme.novig.money import ask_from_other_bid, probability_to_american
from moneyscheme.novig.place import build_place_plan


def main() -> None:
    s = get_settings()
    c = trading_client(
        host=s.novig_host,
        trading_key_id=s.novig_trading_key_id,
        trading_pem_path=s.novig_trading_pem_path,
    )
    r = c.request("GET", "/v3/catalog/markets", query="league=ATP&marketType=MONEY&limit=30")
    m = None
    for item in r["items"]:
        if all((o.get("bid") or {}).get("price") for o in item.get("outcomes", [])):
            m = item
            break
    print("market", None if m is None else m.get("description"))
    if not m:
        return
    o0, o1 = m["outcomes"][0], m["outcomes"][1]
    ask = ask_from_other_bid(o1["bid"]["price"])
    amer = int(probability_to_american(ask))
    event = f"{o0['name']} / {o1['name']}"
    opp = Opportunity(
        league="Tennis",
        ev_percent=2.0,
        event=event,
        odds_american=amer,
        max_stake=50,
        selection=o0["name"],
        confidence=1,
    )
    d = Decision(action="take", reason="test", opportunity=opp, suggested_stake=1.0)
    plan = build_place_plan(c, d, bankroll=100, kelly_fraction=0.33)
    print(
        "plan",
        plan.action,
        plan.reason,
        plan.price,
        plan.qty,
        plan.match.outcome_id if plan.match else None,
    )


if __name__ == "__main__":
    main()
