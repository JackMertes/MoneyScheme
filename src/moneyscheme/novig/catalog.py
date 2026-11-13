from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, List, Optional, Sequence, Set

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

_OPEN_EVENT_STATUSES = {
    "OPEN",
    "OPEN_PREGAME",
    "OPEN_INGAME",
    "PREGAME",
    "INGAME",
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
    """Tennis-style fallback: both surnames appear in market/event/outcomes text."""
    players = _event_players(opp_event)
    if len(players) < 2:
        return False
    hay = _norm(
        " ".join([market_description, event_description, *list(outcome_names)])
    )
    for p in players:
        sur = _surname(p)
        if not sur or not re.search(rf"\b{re.escape(sur)}\b", hay):
            return False
    return True


def _teams_in_event_description(opp_event: str, event_description: str) -> bool:
    """
    Team sports: each OCR side must appear as a phrase in the Novig event
    description (e.g. Warriors + Spurs in 'Golden State Warriors @ San Antonio Spurs').
    Uses full phrases so Central Arkansas / Arkansas does not collapse to one token.
    """
    teams = _event_players(opp_event)
    if len(teams) < 2:
        return False
    hay = _norm(event_description)
    if not hay:
        return False
    for team in teams:
        phrase = _norm(team)
        if not phrase or phrase not in hay:
            return False
    return True


def _parse_prop_player(market_text: str) -> Optional[dict[str, str]]:
    """Parse 'Rebounds (Green, D)' → {last: green, initial: d}."""
    m = re.search(r"\(([a-zA-Z.'\-]+)\s*,\s*([a-zA-Z0])\.?\)", market_text or "")
    if not m:
        return None
    initial = m.group(2)
    if initial == "0":
        initial = "O"
    return {"last": _norm(m.group(1)), "initial": initial.casefold()}


def _prop_player_matches(prop: dict[str, str], market_description: str) -> bool:
    """Match Novig 'Draymond Green 5.5 REBOUNDS' to PTO (Green, D)."""
    desc = _norm(market_description)
    last = prop["last"]
    if not last or not re.search(rf"\b{re.escape(last)}\b", desc):
        return False
    initial = prop.get("initial") or ""
    if not initial:
        return True
    # Tokens before the surname should start with the given initial (Draymond → d)
    before = desc.split(last, 1)[0].strip()
    tokens = [t for t in before.replace(".", " ").split() if t and not t[0].isdigit()]
    if not tokens:
        # Surname-only description: cannot verify initial → reject when initial known
        return False
    return tokens[-1][0] == initial


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
    if key.startswith("ncaab"):
        return ["NCAAB"]
    if key.startswith("ncaaf"):
        return ["NCAAF"]
    return LEAGUE_MAP.get(key, [opp.league.upper()] if opp.league else [])


def market_types_for_opportunity(opp: Opportunity) -> List[str]:
    """Map Pick the Odds MARKET text → Novig catalog marketType values."""
    m = (opp.market or "").casefold()
    sel = (opp.selection or "").casefold()

    if "total points 1h" in m or ("1h" in m and "total" in m):
        return ["TOTAL_1H"]
    if "team total" in m:
        return ["TEAM_TOTAL"]
    if "total" in m:
        return ["TOTAL"]
    if "spread" in m:
        return ["SPREAD", "SPREAD_1H"]
    if "rebound" in m:
        return ["REBOUNDS"]
    if "assist" in m:
        return ["ASSISTS"]
    if "3pt" in m or "three" in m:
        return ["THREE_POINTERS_MADE"]
    if "point" in m and "total" not in m:
        return ["POINTS"]
    if "money" in m:
        return ["MONEY"]

    # Fall back from selection shape if MARKET OCR missed
    parsed = _parse_selection(opp.selection)
    if parsed["kind"] == "total":
        return ["TOTAL", "TOTAL_1H", "TEAM_TOTAL"]
    if parsed["kind"] == "spread":
        return ["SPREAD"]
    if "set" in sel:
        return ["FIRST_SET_MONEYLINE", "MONEY"]
    return ["MONEY"]


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


def iter_catalog_events(
    client: NovigClient,
    *,
    leagues: Sequence[str],
    pages: int = 15,
) -> Iterable[dict[str, Any]]:
    for league in leagues:
        after: Optional[str] = None
        for _ in range(pages):
            query = f"league={league}&limit=200"
            if after:
                query += f"&after={after}"
            page = client.request("GET", "/v3/catalog/events", query=query)
            for item in page.get("items", []):
                yield item
            after = page.get("next")
            if not after:
                break


def resolve_event_ids(
    client: NovigClient,
    opp: Opportunity,
    *,
    pages: int = 15,
) -> Set[str]:
    """Find open Novig eventIds whose description contains both OCR teams."""
    leagues = leagues_for_opportunity(opp)
    if not leagues:
        return set()
    open_hits: Set[str] = set()
    any_hits: Set[str] = set()
    for event in iter_catalog_events(client, leagues=leagues, pages=pages):
        desc = str(event.get("description") or "")
        if not _teams_in_event_description(opp.event, desc):
            continue
        eid = str(event.get("eventId") or "")
        if not eid:
            continue
        any_hits.add(eid)
        status = str(event.get("status") or "").upper()
        if status in _OPEN_EVENT_STATUSES or status.startswith("OPEN"):
            open_hits.add(eid)
    return open_hits or any_hits


def match_opportunity(
    client: NovigClient,
    opp: Opportunity,
    *,
    pages: int = 20,
) -> Optional[CatalogMatch]:
    parsed = _parse_selection(opp.selection)
    market_types = market_types_for_opportunity(opp)
    leagues = leagues_for_opportunity(opp) or ["ATP", "WTA"]
    prop = _parse_prop_player(opp.market or "")
    event_ids = resolve_event_ids(client, opp, pages=min(pages, 15))
    hits: List[CatalogMatch] = []

    for market in iter_catalog_markets(
        client, leagues=leagues, market_types=market_types, pages=pages
    ):
        if market.get("status") and market.get("status") != "OPEN":
            continue
        mid_event = str(market.get("eventId") or "")
        if event_ids:
            if mid_event not in event_ids:
                continue
        elif prop:
            # Player props without a resolved game: still require player identity
            if not _prop_player_matches(prop, market.get("description") or ""):
                continue
        else:
            # Tennis / no event resolve: fall back to surname haystack
            outcome_names = [
                str(o.get("name") or "") for o in (market.get("outcomes") or [])
            ]
            if not _event_matches(
                opp.event,
                market.get("description") or "",
                outcome_names=outcome_names,
            ):
                continue

        if prop and not _prop_player_matches(prop, market.get("description") or ""):
            continue
        if opp.market and not prop and not _market_text_compatible(opp.market, market):
            continue

        if parsed["kind"] == "total":
            try:
                if Decimal(str(market.get("strike"))) != Decimal(parsed["strike"]):
                    continue
            except Exception:
                continue

        for outcome in market.get("outcomes") or []:
            if _outcome_matches(parsed, outcome.get("name") or ""):
                hits.append(
                    CatalogMatch(
                        market=market,
                        outcome=outcome,
                        event_id=mid_event,
                        market_id=str(market.get("marketId")),
                        outcome_id=str(outcome.get("outcomeId")),
                    )
                )

    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Prefer markets tied to a resolved open event; then MONEY if ambiguous types
        if event_ids:
            scoped = [h for h in hits if h.event_id in event_ids]
            if len(scoped) == 1:
                return scoped[0]
            hits = scoped or hits
        money_hits = [h for h in hits if h.market.get("marketType") == "MONEY"]
        if len(money_hits) == 1:
            return money_hits[0]
        # Identical outcome across duplicate catalog rows → still ambiguous
        return None
    return None


def _market_text_compatible(pto_market: str, novig_market: dict[str, Any]) -> bool:
    """Non-prop MARKET checks (e.g. 1H totals)."""
    m = pto_market.casefold()
    desc = _norm(str(novig_market.get("description") or ""))
    if "1h" in m:
        mt = str(novig_market.get("marketType") or "")
        return "1H" in mt or "1h" in desc
    return True
