from moneyscheme.config import get_settings
from moneyscheme.models import Opportunity
from moneyscheme.novig.bootstrap import trading_client
from moneyscheme.novig.catalog import (
    _event_matches,
    _outcome_matches,
    _parse_selection,
    iter_catalog_markets,
    match_opportunity,
)
from moneyscheme.novig.money import ask_from_other_bid, probability_to_american


def main() -> None:
    s = get_settings()
    c = trading_client(
        host=s.novig_host,
        trading_key_id=s.novig_trading_key_id,
        trading_pem_path=s.novig_trading_pem_path,
    )
    r = c.request("GET", "/v3/catalog/markets", query="league=ATP&marketType=MONEY&limit=30")
    m = next(
        item
        for item in r["items"]
        if all((o.get("bid") or {}).get("price") for o in item.get("outcomes", []))
    )
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
    print("opp", opp.event, opp.selection, opp.odds_american)
    print("marketType", m.get("marketType"), "status", m.get("status"), "id", m.get("marketId"))
    parsed = _parse_selection(opp.selection)
    print("parsed", parsed)
    print(
        "event_matches",
        _event_matches(
            opp.event,
            m.get("description") or "",
            outcome_names=[o0["name"], o1["name"]],
        ),
    )
    print("outcome_matches", _outcome_matches(parsed, o0["name"]))

    # See if iterator yields this market
    found = False
    for i, market in enumerate(
        iter_catalog_markets(c, leagues=["ATP"], market_types=["MONEY"], pages=3)
    ):
        if market.get("marketId") == m["marketId"]:
            found = True
            print("iterator_found_at", i)
            break
    print("iterator_found", found)
    matched = match_opportunity(c, opp, pages=5)
    print("matched", matched)


if __name__ == "__main__":
    main()
