from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, List, Optional, Sequence

from moneyscheme.models import Opportunity
from moneyscheme.novig.client import NovigClient


LEAGUE_MAP = {
    "tennis": ["ATP", "WTA"],
    "nba": ["NBA"],
    "nfl": ["NFL"],
    "mlb": ["MLB"],
    "nhl": ["NHL"],
    "ncaab": ["NCAAB"],
    "ncaaf": ["NCAAF"],
    "soccer": ["EPL", "MLS", "Bundesliga", "Serie A", "La Liga", "Ligue 1"],
    "ufc": ["UFC"],
    "mma": ["UFC"],
}


@dataclass
class CatalogMatch:
    market: dict[str, Any]
    outcome: dict[str, Any]
    event_id: str
    market_id: str
    outcome_id: str
    reason: str = "exact_match"


def _norm(s: str) -> str:
    s = s.casefold().replace("−", "-")
    s = re.sub(r"[^\w\s.+-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _surname(name: str) -> str:
    parts = [p for p in _norm(name).split() if p]
    return parts[-1] if parts else ""


def _initial(name: str) -> str:
    parts = [p for p in _norm(name).replace(".", " ").split() if p]
    if len(parts) >= 2:
        return parts[0][0]
    return ""


def _event_players(event: str) -> List[str]:
    if "/" in event:
        return [p.strip() for p in event.split("/") if p.strip()]
    parts = re.split(r"\s+vs\.?\s+", event, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def _parse_selection(selection: str) -> dict[str, Any]:
    sel = selection.strip()
    m = re.match(r"^(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)\s*$", sel, re.I)
    if m:
        return {
            "kind": "total",
            "side": m.group(1).title(),
            "strike": m.group(2),
            "outcome_name": f"{m.group(1).title()} {m.group(2)}",
        }
    m = re.match(r"^([+-][0-9]+(?:\.[0-9]+)?)\s*$", sel.replace("−", "-"))
    if m:
        return {"kind": "spread", "line": m.group(1), "outcome_name": sel}
    return {"kind": "money", "outcome_name": sel, "player": sel}


def _name_exact(ocr_name: str, novig_name: str) -> bool:
    """
    Exact identity check tolerant only of Novig abbreviation:
    'Michele Ribecai' == 'M. Ribecai' / 'Michele Ribecai'
    """
    a, b = _norm(ocr_name), _norm(novig_name)
    if a == b:
        return True
    if _surname(a) != _surname(b):
        return False
    ia, ib = _initial(a), _initial(b)
    # If either side has an initial/first token, they must agree when both present
    if ia and ib and ia != ib:
        return False
    return True


def _event_matches(
    opp_event: str,
    market_description: str,
    event_description: str = "",
    outcome_names: Sequence[str] = (),
) -> bool:
    players = _event_players(opp_event)
    if len(players) < 2:
        return False
    hay = _norm(
        " ".join(
            [market_description, event_description, *list(outcome_names)]
        )
    )
    # Both surnames must appear as whole tokens across market/event/outcomes
    for p in players:
        sur = _surname(p)
        if not sur or not re.search(rf"\b{re.escape(sur)}\b", hay):
            return False
    return True


def _outcome_matches(parsed: dict[str, Any], outcome_name: str) -> bool:
    want = _norm(parsed["outcome_name"])
    got = _norm(outcome_name)
    if want == got:
        return True
    if parsed["kind"] == "money":
        return _name_exact(parsed["outcome_name"], outcome_name)
    return False


def leagues_for_opportunity(opp: Opportunity) -> List[str]:
    key = opp.league.strip().casefold()
    return LEAGUE_MAP.get(key, [opp.league.upper()] if opp.league else [])


def iter_catalog_markets(
    client: NovigClient,
    *,
    leagues: Sequence[str],
    market_types: Sequence[str],
    pages: int = 20,
) -> Iterable[dict[str, Any]]:
    for league in leagues:
        for market_type in market_types:
            after: Optional[str] = None
            for _ in range(pages):
                query = f"league={league}&marketType={market_type}&limit=200"
                if after:
                    query += f"&after={after}"
                page = client.request("GET", "/v3/catalog/markets", query=query)
                for item in page.get("items", []):
                    yield item
                after = page.get("next")
                if not after:
                    break


def match_opportunity(
    client: NovigClient,
    opp: Opportunity,
    *,
    pages: int = 15,
) -> Optional[CatalogMatch]:
    parsed = _parse_selection(opp.selection)
    if parsed["kind"] == "total":
        market_types = ["TOTAL", "TOTAL_SETS", "TEAM_TOTAL"]
    elif parsed["kind"] == "spread":
        market_types = ["SPREAD", "SET_SPREAD"]
    else:
        # Plain moneyline from PTO is full-match MONEY, not first-set
        sel_l = opp.selection.casefold()
        if "set" in sel_l:
            market_types = ["FIRST_SET_MONEYLINE", "MONEY"]
        else:
            market_types = ["MONEY"]

    leagues = leagues_for_opportunity(opp) or ["ATP", "WTA"]
    hits: List[CatalogMatch] = []

    for market in iter_catalog_markets(
        client, leagues=leagues, market_types=market_types, pages=pages
    ):
        if market.get("status") and market.get("status") != "OPEN":
            continue
        if parsed["kind"] == "total":
            try:
                if Decimal(str(market.get("strike"))) != Decimal(parsed["strike"]):
                    continue
            except Exception:
                continue
        outcome_names = [str(o.get("name") or "") for o in (market.get("outcomes") or [])]
        if not _event_matches(
            opp.event,
            market.get("description") or "",
            outcome_names=outcome_names,
        ):
            continue
        for outcome in market.get("outcomes") or []:
            if _outcome_matches(parsed, outcome.get("name") or ""):
                hits.append(
                    CatalogMatch(
                        market=market,
                        outcome=outcome,
                        event_id=str(market.get("eventId")),
                        market_id=str(market.get("marketId")),
                        outcome_id=str(outcome.get("outcomeId")),
                    )
                )

    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Prefer full-match MONEY when still ambiguous
        money_hits = [h for h in hits if h.market.get("marketType") == "MONEY"]
        if len(money_hits) == 1:
            return money_hits[0]
        return None
    return None
