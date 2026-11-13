from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

from moneyscheme.models import Opportunity
from moneyscheme.ocr.engine import OcrToken

# Header labels we expect in the locked UI (left → right).
HEADER_LABELS = (
    "LEAGUE",
    "STATUS",
    "EV",
    "EVENT",
    "MARKET",
    "ODDS",
    "MAX",
    "WAGER",
    "BOOK",
    "SELECTION",
)

ODDS_RE = re.compile(r"^[+\-−]?\d{2,4}$")
EV_RE = re.compile(r"^[+\-−]?\d+(?:\.\d+)?\s*%?$")
MONEY_RE = re.compile(r"^\$?\s*[\d,]+(?:\.\d+)?$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)?$", re.I)


def parse_opportunities(
    tokens: Sequence[OcrToken],
    image_width: Optional[int] = None,
) -> List[Opportunity]:
    """Turn OCR tokens from the PTO EV table into Opportunity rows."""
    if not tokens:
        return []

    headers = _find_headers(tokens)
    body = _tokens_below_headers(tokens, headers)
    if not body:
        body = list(tokens)

    rows = _cluster_rows(body)
    opportunities: List[Opportunity] = []
    for row in rows:
        opp = _parse_row(row, headers, image_width)
        if opp is not None:
            opportunities.append(opp)
    return opportunities


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).upper()


def _find_headers(tokens: Sequence[OcrToken]) -> dict[str, float]:
    """Map column name → center x from header row tokens."""
    found: dict[str, float] = {}
    for t in tokens:
        n = _norm(t.text)
        if n in ("LEAGUE", "STATUS", "EV", "EVENT", "MARKET", "ODDS", "MAX", "WAGER"):
            found[n] = t.cx
        elif "BOOK" in n and "SELECTION" in n:
            found["BOOK"] = t.cx
        elif n == "BOOK":
            found["BOOK"] = t.cx
        elif n == "SELECTION":
            found["SELECTION"] = t.cx
    # Infer WAGER between MAX and BOOK when the header glyph is missed
    if "WAGER" not in found and "MAX" in found and "BOOK" in found:
        found["WAGER"] = (found["MAX"] + found["BOOK"]) / 2.0
    return found


def _tokens_below_headers(
    tokens: Sequence[OcrToken], headers: dict[str, float]
) -> List[OcrToken]:
    if not headers:
        return list(tokens)
    # Approximate header band: tokens whose text matched headers are near the top.
    header_ys = []
    for t in tokens:
        n = _norm(t.text)
        if n in HEADER_LABELS or ("BOOK" in n and "SELECTION" in n):
            header_ys.append(t.y1)
    if not header_ys:
        return list(tokens)
    cutoff = max(header_ys) + 8
    return [t for t in tokens if t.cy > cutoff]


def _cluster_rows(tokens: Sequence[OcrToken], y_tol: float = 55.0) -> List[List[OcrToken]]:
    """Group tokens into horizontal rows by y center.

    Event cells are often two stacked names, so tolerance is wider than a single line.
    """
    ordered = sorted(tokens, key=lambda t: (t.cy, t.cx))
    rows: List[List[OcrToken]] = []
    for tok in ordered:
        if not rows:
            rows.append([tok])
            continue
        # Compare against the running mean y of the current cluster
        mean_y = sum(t.cy for t in rows[-1]) / len(rows[-1])
        if abs(tok.cy - mean_y) <= y_tol:
            rows[-1].append(tok)
        else:
            rows.append([tok])
    return _merge_event_split_rows(rows, y_tol=120.0)


def _parse_percent_token(text: str) -> Optional[float]:
    m = re.search(r"([+\-−]?\d+(?:\.\d+)?)\s*%", text.replace("−", "-"))
    if not m:
        return None
    return float(m.group(1))


def _row_has_signed_odds(row: Sequence[OcrToken]) -> bool:
    """True if row has American odds or an implied-probability ODDS percent."""
    for t in row:
        raw = t.text.replace("−", "-").replace(" ", "")
        if ODDS_RE.match(raw) and (raw.startswith("+") or raw.startswith("-")):
            return True
        pct = _parse_percent_token(t.text)
        # Implied odds percents are typically in a wider band than tiny EV labels.
        if pct is not None and 5.0 <= abs(pct) <= 95.0:
            return True
    return False


def _row_has_ev(row: Sequence[OcrToken]) -> bool:
    for t in row:
        pct = _parse_percent_token(t.text)
        if pct is not None and abs(pct) < 20.0:
            return True
    return False


def _merge_event_split_rows(
    rows: List[List[OcrToken]], y_tol: float
) -> List[List[OcrToken]]:
    """Attach stacked event-name lines to the odds/EV anchor row."""
    if not rows:
        return rows

    # First pass: merge name-only lines into nearby anchor rows (odds+ev)
    anchors = []
    for i, row in enumerate(rows):
        if _row_has_signed_odds(row) and _row_has_ev(row):
            anchors.append(i)

    if not anchors:
        return rows

    used = set()
    bundles: List[List[OcrToken]] = []
    for ai in anchors:
        anchor_y = sum(t.cy for t in rows[ai]) / len(rows[ai])
        bundle = list(rows[ai])
        used.add(ai)
        for j, row in enumerate(rows):
            if j in used:
                continue
            if _row_has_signed_odds(row) or _row_has_ev(row):
                continue
            row_y = sum(t.cy for t in row) / len(row)
            # Ignore IDE/chrome overlay tokens when sizing a candidate fragment
            useful = [t for t in row if not _looks_like_chrome(t.text)]
            if abs(row_y - anchor_y) <= y_tol and 0 < len(useful) <= 6:
                bundle.extend(useful)
                used.add(j)
        bundles.append(bundle)

    # Keep non-consumed rows in order (filters/chrome); parser will discard junk
    leftovers = [rows[i] for i in range(len(rows)) if i not in used]
    return bundles + leftovers


def _parse_row(
    row: Sequence[OcrToken],
    headers: dict[str, float],
    image_width: Optional[int],
) -> Optional[Opportunity]:
    # Drop IDE/browser overlay tokens so they don't poison MARKET/EVENT or kill the row
    clean = [t for t in row if not _looks_like_chrome(t.text)]
    if not clean:
        return None
    texts = [t.text for t in clean]
    joined = " | ".join(texts)

    odds_percent = _extract_odds_percent(clean, headers)
    odds_american = None if odds_percent is not None else _extract_odds_american(clean)
    ev = _extract_ev(clean, headers)
    max_stake = _extract_max(clean, headers)
    wager = _extract_wager(clean, headers)
    if (odds_percent is None and odds_american is None) or ev is None:
        return None

    # Skip pure chrome / filter junk rows (after overlay strip)
    if _looks_like_chrome(joined):
        return None

    league = _extract_league(clean)
    status = _extract_status(clean, headers)
    market = _extract_market(clean, headers)
    event = _extract_event(clean, headers, image_width)
    selection = _extract_selection(clean, headers, image_width, event)

    if not event or not selection:
        return None

    confs = [t.conf for t in clean]
    confidence = sum(confs) / len(confs) if confs else 0.0

    return Opportunity(
        league=league or "UNKNOWN",
        status=status,
        ev_percent=ev,
        event=event,
        market=market,
        odds_percent=odds_percent or 0.0,
        odds_american=odds_american or 0,
        max_stake=max_stake,
        wager=wager,
        selection=selection,
        book="novig",
        confidence=float(confidence),
        raw_text=joined,
    )


def _looks_like_chrome(text: str) -> bool:
    u = text.upper()
    junk = (
        "EXPECTED VALUES",
        "FIND GAMES",
        "ALL FILTERS",
        "APPROVAL REQUIRED",
        "GET-CHILDITEM",
        "SORT-OBJECT",
        "SELECT-OBJECT",
        "LASTWRITETIME",
        "FIXTURES",
        "SCREENSHOTS",
        "ACCEPT",
        "REJECT",
        "CURSOR",
        "IMPORTANT STUFF",
        "KELLY",
        "FORMULA",
        "GITHUB",
        "CHATGPT",
    )
    return any(j in u for j in junk)


def _extract_odds_percent(
    row: Sequence[OcrToken], headers: dict[str, float]
) -> Optional[float]:
    """Read implied probability from ODDS column (e.g. 46.1%)."""
    x_odds = headers.get("ODDS")
    x_ev = headers.get("EV")
    candidates: list[tuple[float, float]] = []
    for t in row:
        pct = _parse_percent_token(t.text)
        if pct is None:
            continue
        # Odds percents are market prices, typically well above tiny EV labels.
        if abs(pct) < 5.0 or abs(pct) > 95.0:
            continue
        score = 0.0
        if x_odds is not None:
            score -= abs(t.cx - x_odds)
        if x_ev is not None:
            # Prefer farther from EV header when both percents exist
            score += abs(t.cx - x_ev) * 0.25
        candidates.append((score, pct))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _extract_odds_american(row: Sequence[OcrToken]) -> Optional[int]:
    """Legacy American odds parser (+120 / -150)."""
    signed: list[tuple[float, int]] = []
    unsigned: list[tuple[float, int]] = []
    for t in row:
        raw = t.text.replace("−", "-").replace(" ", "")
        if not ODDS_RE.match(raw):
            continue
        val = int(raw)
        if not (100 <= abs(val) <= 10000):
            continue
        if raw.startswith("+") or raw.startswith("-"):
            signed.append((t.cx, val))
        else:
            unsigned.append((t.cx, val))
    pool = signed or unsigned
    if not pool:
        return None
    pool.sort(key=lambda x: x[0])
    return pool[0][1] if len(pool) == 1 else pool[len(pool) // 2][1]


def _extract_ev(
    row: Sequence[OcrToken], headers: Optional[dict[str, float]] = None
) -> Optional[float]:
    headers = headers or {}
    x_ev = headers.get("EV")
    x_odds = headers.get("ODDS")
    scored: list[tuple[float, float]] = []
    for t in row:
        pct = _parse_percent_token(t.text)
        if pct is None:
            continue
        # EV labels are usually small; still allow larger if clearly in EV column
        score = 0.0
        if x_ev is not None:
            score -= abs(t.cx - x_ev)
        if x_odds is not None:
            score += abs(t.cx - x_odds) * 0.25
        if abs(pct) <= 20.0:
            score += 50.0
        scored.append((score, pct))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # Split number + % fallback
    for i, t in enumerate(row):
        raw = t.text.replace("−", "-")
        if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", raw):
            nxt = row[i + 1].text if i + 1 < len(row) else ""
            if nxt.strip() == "%":
                val = float(raw)
                if abs(val) < 100:
                    return val
    return None


def _parse_money_token(text: str) -> Optional[float]:
    raw = text.replace(",", "").replace(" ", "").replace("−", "-")
    if raw.startswith("+") or raw.startswith("-") or "%" in raw:
        return None
    km = re.fullmatch(r"[\$Ss]?(\d+(?:\.\d+)?)\s*[kK]", raw)
    if km:
        return float(km.group(1)) * 1000.0
    m = re.fullmatch(r"[\$Ss]?(\d+(?:\.\d+)?)", raw)
    if not m:
        return None
    digits = m.group(1)
    val = float(digits)
    dollarish = raw.startswith(("$", "S", "s"))
    if not dollarish and digits.startswith("3") and len(digits) == 4:
        val = float(digits[1:])
        dollarish = True
    if not dollarish and "." not in digits:
        # Bare integers without $ are ambiguous; only keep with $ / S prefix
        return None
    if not (0.01 <= val <= 1_000_000):
        return None
    return val


def _extract_money_in_band(
    row: Sequence[OcrToken],
    x_left: Optional[float],
    x_right: Optional[float],
) -> Optional[float]:
    hits: list[tuple[float, float]] = []
    for t in row:
        val = _parse_money_token(t.text)
        if val is None:
            continue
        if x_left is not None and t.cx < x_left - 40:
            continue
        if x_right is not None and t.cx > x_right - 20:
            continue
        hits.append((t.cx, val))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0])
    return hits[0][1]


def _extract_max(
    row: Sequence[OcrToken], headers: Optional[dict[str, float]] = None
) -> Optional[float]:
    """Parse MAX stake (not WAGER). Prefer the MAX column band."""
    headers = headers or {}
    x_max = headers.get("MAX")
    x_right = headers.get("WAGER") or headers.get("BOOK") or headers.get("SELECTION")
    if x_max is not None:
        banded = _extract_money_in_band(row, x_max - 80, x_right)
        if banded is not None:
            return banded
    # Fallback: first dollar token left of WAGER/BOOK
    return _extract_money_in_band(
        row,
        headers.get("ODDS"),
        headers.get("WAGER") or headers.get("BOOK"),
    )


def _extract_wager(
    row: Sequence[OcrToken], headers: Optional[dict[str, float]] = None
) -> Optional[float]:
    """Parse PTO WAGER column (display only)."""
    headers = headers or {}
    x_left = headers.get("WAGER") or headers.get("MAX")
    x_right = headers.get("BOOK") or headers.get("SELECTION")
    if x_left is None:
        return None
    # When WAGER header was inferred, prefer the rightmost $ between MAX and BOOK
    hits: list[tuple[float, float]] = []
    for t in row:
        val = _parse_money_token(t.text)
        if val is None:
            continue
        if t.cx < x_left - 40:
            continue
        if x_right is not None and t.cx > x_right - 20:
            continue
        # Skip the MAX cell itself when scanning from MAX
        if headers.get("MAX") is not None and abs(t.cx - headers["MAX"]) < 60:
            continue
        hits.append((t.cx, val))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0])
    return hits[-1][1]


def _extract_league(row: Sequence[OcrToken]) -> str:
    for t in row:
        n = _norm(t.text)
        # OCR often drops a letter: TENIS
        if n in {"TENNIS", "TENIS"} or "TENNIS" in n or n.startswith("TENI"):
            return "Tennis"
        if "NCAAB" in n:
            return "NCAAB"
        if "NCAAF" in n:
            return "NCAAF"
        if n in {"NBA", "NFL", "MLB", "NHL", "SOCCER", "UFC", "MMA", "WNBA"}:
            return n.split()[0] if " " in n else n
    return ""


def _looks_like_status(text: str) -> bool:
    t = text.strip()
    if TIME_RE.match(t):
        return True
    if re.search(r"\bIn\s+\d+\s+hour", t, re.I):
        return True
    if re.search(r"\b(AM|PM)\b", t) and re.search(r"\d", t):
        return True
    return False


def _extract_status(
    row: Sequence[OcrToken],
    headers: Optional[dict[str, float]] = None,
) -> str:
    headers = headers or {}
    x_left = headers.get("STATUS") or headers.get("LEAGUE")
    x_right = headers.get("EV") or headers.get("EVENT")
    parts: list[tuple[float, str]] = []
    for t in row:
        if not _looks_like_status(t.text):
            continue
        if x_left is not None and t.cx < x_left - 80:
            continue
        if x_right is not None and t.cx > x_right - 20:
            continue
        parts.append((t.cy, t.text.strip()))
    parts.sort(key=lambda x: x[0])
    # Prefer "6:10 PM In 4 hours" order
    return " ".join(p for _, p in parts)


def _is_team_abbrev(text: str) -> bool:
    t = text.strip()
    return bool(re.fullmatch(r"[A-Za-z]{2,4}", t)) and t.upper() == t


def _normalize_prop_initial(initial: str) -> str:
    """OCR often reads initial O as 0."""
    ch = initial.strip().rstrip(".")[:1]
    if ch == "0":
        return "O"
    return ch.upper() if ch.isalpha() else ch


def _is_prop_player_tag(text: str) -> bool:
    """PTO market player tags look like '(Green, D)' or 'Green, D' / 'Toppin, 0'."""
    t = text.strip().strip("()")
    return bool(re.fullmatch(r"[A-Za-z.'\-]+\s*,\s*[A-Za-z0]\.?", t))


def _format_prop_player_tag(text: str) -> str:
    t = text.strip().strip("()")
    m = re.fullmatch(r"([A-Za-z.'\-]+)\s*,\s*([A-Za-z0])\.?", t)
    if not m:
        return t
    return f"{m.group(1)}, {_normalize_prop_initial(m.group(2))}"


def _normalize_market_blob(text: str) -> str:
    """Normalize OCR variants like 'Assists - Allen, J' → 'Assists (Allen, J)'."""
    t = text.strip()
    m = re.match(
        r"^(Assists|Rebounds|Points|3PT|Threes)\s*[-–—:]\s*(.+)$",
        t,
        re.IGNORECASE,
    )
    if m and _is_prop_player_tag(m.group(2)):
        return f"{m.group(1)} ({_format_prop_player_tag(m.group(2))})"
    m2 = re.match(
        r"^(Assists|Rebounds|Points|3PT|Threes)\s*\((.+)\)$",
        t,
        re.IGNORECASE,
    )
    if m2 and _is_prop_player_tag(m2.group(2)):
        return f"{m2.group(1)} ({_format_prop_player_tag(m2.group(2))})"
    return t


def _extract_market(row: Sequence[OcrToken], headers: dict[str, float]) -> str:
    """Read MARKET column text (e.g. Total Points 1H, Rebounds (Green, D))."""
    x_left = headers.get("MARKET")
    x_right = headers.get("ODDS")
    parts: list[tuple[float, float, str]] = []
    for t in row:
        text = t.text.strip()
        if _is_numeric_ish(text) or _is_selection_phrase(text):
            continue
        if _looks_like_status(text) or _looks_like_chrome(text):
            continue
        if len(text) <= 1:
            continue
        # MARKET labels often sit slightly left of the header glyph
        if x_left is not None and x_right is not None:
            if not (x_left - 100 <= t.cx <= x_right - 20):
                continue
        elif x_left is not None and abs(t.cx - x_left) > 260:
            continue
        else:
            continue
        parts.append((t.cy, t.cx, _normalize_market_blob(text)))
    if not parts:
        return ""
    parts.sort(key=lambda x: (x[0], x[1]))
    # Prefer a single already-normalized "Assists (Allen, J)" blob if present
    for _, _, blob in parts:
        if re.match(
            r"^(Assists|Rebounds|Points|3PT|Threes)\s*\(",
            blob,
            re.IGNORECASE,
        ):
            return blob
    # Normalize player tag formatting: Rebounds + Green, D → Rebounds (Green, D)
    texts = [p for _, _, p in parts]
    if len(texts) >= 2 and _is_prop_player_tag(texts[-1]) and not texts[-1].startswith("("):
        tag = _format_prop_player_tag(texts[-1])
        head = " ".join(texts[:-1])
        if head:
            return f"{head} ({tag})"
        return f"({tag})"
    # If we only captured a player tag, try to find the market kind token in-band
    if len(texts) == 1 and _is_prop_player_tag(texts[0]):
        tag = _format_prop_player_tag(texts[0])
        kinds = []
        for t in row:
            n = _norm(t.text)
            if n in {"REBOUNDS", "ASSISTS", "POINTS", "3PT", "THREES"} or n.startswith("TOTAL"):
                if x_left is None or abs(t.cx - x_left) < 280:
                    kinds.append(t.text.strip())
        if kinds:
            return f"{kinds[0]} ({tag})"
        return f"({tag})"
    return " ".join(texts)


def _extract_event(
    row: Sequence[OcrToken],
    headers: dict[str, float],
    image_width: Optional[int],
) -> str:
    """Collect team/player names in the EVENT column (between EV and MARKET/ODDS)."""
    x_left = headers.get("EV")
    x_right = headers.get("MARKET") or headers.get("ODDS")
    x_event = headers.get("EVENT")
    league_like = {
        "TENNIS",
        "TENIS",
        "NBA",
        "NFL",
        "MLB",
        "NHL",
        "UNDER",
        "OVER",
        "NCAAB",
        "NCAAF",
        "WNBA",
    }
    market_words = {
        "TOTAL",
        "POINTS",
        "REBOUNDS",
        "ASSISTS",
        "SPREAD",
        "MONEYLINE",
        "3PT",
        "THREES",
        "1H",
        "2H",
    }
    name_tokens: List[OcrToken] = []
    for t in row:
        text = t.text.strip()
        if len(text) <= 1:
            continue
        n = _norm(text)
        if _is_numeric_ish(text) or n in league_like or n.startswith("TENI"):
            continue
        if n.startswith("NCAAB") or n.startswith("NCAAF"):
            continue
        if _is_selection_phrase(text) or _looks_like_status(text):
            continue
        if _is_prop_player_tag(text):
            continue
        if any(w in n.split() for w in market_words) and "(" not in text:
            # bare market labels belong in MARKET, not EVENT
            if n in market_words or n.startswith("TOTAL") or n.startswith("REBOUND") or n == "3PT":
                continue
        if not _looks_like_name(text) and not _is_team_abbrev(text):
            continue
        in_band = False
        # Stay left of MARKET column so prop labels don't leak into EVENT
        right_limit = x_right - 60 if x_right is not None else None
        if x_left is not None and right_limit is not None and x_left < t.cx < right_limit:
            in_band = True
        elif x_event is not None and abs(t.cx - x_event) < 220:
            if right_limit is None or t.cx < right_limit:
                in_band = True
        if in_band:
            name_tokens.append(t)

    # Prefer full names over abbreviations when both appear
    full = [
        t
        for t in name_tokens
        if not _is_team_abbrev(t.text) and len(t.text.strip()) >= 4
    ]
    use = full if len(full) >= 2 else name_tokens
    names = [t.text.strip() for t in sorted(use, key=lambda t: (t.cy, t.cx))]
    seen = set()
    uniq = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(n)
    if len(uniq) >= 2:
        return f"{uniq[0]} / {uniq[1]}"
    return uniq[0] if uniq else ""


def _extract_selection(
    row: Sequence[OcrToken],
    headers: dict[str, float],
    image_width: Optional[int],
    event: str,
) -> str:
    x_book = headers.get("BOOK") or headers.get("SELECTION")
    x_max = headers.get("MAX")
    event_parts = {p.strip().lower() for p in re.split(r"/", event) if p.strip()}

    candidates: List[OcrToken] = []
    for t in row:
        if _is_numeric_ish(t.text):
            continue
        if _norm(t.text) in {"TENNIS", "NBA", "NFL", "MLB", "NHL"}:
            continue
        if TIME_RE.match(t.text.strip()):
            continue
        if x_book is not None and t.cx < x_book - 40:
            # Still allow if clearly Under/Over and right of MAX
            if x_max is not None and t.cx > x_max and _is_selection_phrase(t.text):
                candidates.append(t)
            continue
        if _is_selection_phrase(t.text) or _looks_like_name(t.text):
            candidates.append(t)

    # Prefer Under/Over line or a name that matches one side
    for t in sorted(candidates, key=lambda t: t.cx, reverse=True):
        if _is_selection_phrase(t.text):
            return _clean_selection(t.text)
    for t in sorted(candidates, key=lambda t: t.cx, reverse=True):
        if t.text.strip().lower() in event_parts or _looks_like_name(t.text):
            # Avoid using both players as selection; pick rightmost name-like
            return t.text.strip()

    # Last resort: rightmost non-numeric token
    non_num = [t for t in row if not _is_numeric_ish(t.text) and _looks_like_name(t.text)]
    if non_num:
        return sorted(non_num, key=lambda t: t.cx)[-1].text.strip()
    return ""


def _is_numeric_ish(text: str) -> bool:
    raw = text.replace("−", "-").replace(",", "").replace(" ", "")
    if ODDS_RE.match(raw) or MONEY_RE.match(raw) or EV_RE.match(raw):
        return True
    if raw in {"%", "$"}:
        return True
    return bool(re.fullmatch(r"[+\-]?\d+(?:\.\d+)?%?", raw))


def _looks_like_name(text: str) -> bool:
    t = text.strip()
    if len(t) < 3:
        return False
    if _is_numeric_ish(t):
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    # Reject pure UI words
    if _norm(t) in HEADER_LABELS or _norm(t) in {"WIDTH", "DEMO", "BOOKS"}:
        return False
    return True


def _is_selection_phrase(text: str) -> bool:
    u = text.strip().upper()
    if re.match(r"^(OVER|UNDER)\s+\d", u):
        return True
    if re.match(r"^[+-]\d+\.?\d*$", u.replace("−", "-")):
        return True
    return False


def _clean_selection(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    t = re.sub(r"^(OVER|UNDER)\s+", lambda m: m.group(1).title() + " ", t, flags=re.I)
    return t
