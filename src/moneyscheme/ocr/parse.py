from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

from moneyscheme.models import Opportunity
from moneyscheme.ocr.engine import OcrToken

# Header labels we expect in the locked UI (left → right).
HEADER_LABELS = ("LEAGUE", "STATUS", "EV", "EVENT", "ODDS", "MAX", "BOOK", "SELECTION")

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
        if n in ("LEAGUE", "STATUS", "EV", "EVENT", "ODDS", "MAX"):
            found[n] = t.cx
        elif "BOOK" in n and "SELECTION" in n:
            found["BOOK"] = t.cx
        elif n == "BOOK":
            found["BOOK"] = t.cx
        elif n == "SELECTION":
            found["SELECTION"] = t.cx
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


def _cluster_rows(tokens: Sequence[OcrToken], y_tol: float = 18.0) -> List[List[OcrToken]]:
    """Group tokens into horizontal rows by y center."""
    ordered = sorted(tokens, key=lambda t: (t.cy, t.cx))
    rows: List[List[OcrToken]] = []
    for tok in ordered:
        if not rows:
            rows.append([tok])
            continue
        if abs(tok.cy - rows[-1][0].cy) <= y_tol:
            rows[-1].append(tok)
        else:
            rows.append([tok])
    # Merge very close consecutive rows (player name on two lines, etc.)
    return _merge_event_split_rows(rows, y_tol=28.0)


def _merge_event_split_rows(
    rows: List[List[OcrToken]], y_tol: float
) -> List[List[OcrToken]]:
    """Merge a short follow-up line (second player name) into the previous row."""
    if not rows:
        return rows
    merged: List[List[OcrToken]] = [rows[0]]
    for row in rows[1:]:
        prev = merged[-1]
        prev_y = sum(t.cy for t in prev) / len(prev)
        row_y = sum(t.cy for t in row) / len(row)
        prev_has_odds = any(ODDS_RE.match(t.text.replace("−", "-")) for t in prev)
        row_has_odds = any(ODDS_RE.match(t.text.replace("−", "-")) for t in row)
        # Second player line: close in y, no odds of its own, previous already has odds/ev.
        if (
            abs(row_y - prev_y) <= y_tol
            and not row_has_odds
            and prev_has_odds
            and len(row) <= 3
        ):
            prev.extend(row)
        else:
            merged.append(row)
    return merged


def _parse_row(
    row: Sequence[OcrToken],
    headers: dict[str, float],
    image_width: Optional[int],
) -> Optional[Opportunity]:
    texts = [t.text for t in row]
    joined = " | ".join(texts)

    odds = _extract_odds(row)
    ev = _extract_ev(row)
    max_stake = _extract_max(row)
    if odds is None or ev is None:
        return None

    # Skip chrome / filter junk rows
    if _looks_like_chrome(joined):
        return None

    league = _extract_league(row)
    status = _extract_status(row)
    event = _extract_event(row, headers, image_width)
    selection = _extract_selection(row, headers, image_width, event)

    if not event or not selection:
        return None

    confs = [t.conf for t in row]
    confidence = sum(confs) / len(confs) if confs else 0.0

    return Opportunity(
        league=league or "UNKNOWN",
        status=status,
        ev_percent=ev,
        event=event,
        odds_american=odds,
        max_stake=max_stake,
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
        "IMPORTANT STUFF",
        "KELLY",
        "FORMULA",
        "GITHUB",
        "CHATGPT",
    )
    return any(j in u for j in junk)


def _extract_odds(row: Sequence[OcrToken]) -> Optional[int]:
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
    # Prefer the odds token (usually mid-right), not a random large number
    pool.sort(key=lambda x: x[0])
    return pool[0][1] if len(pool) == 1 else pool[len(pool) // 2][1]


def _extract_ev(row: Sequence[OcrToken]) -> Optional[float]:
    for t in row:
        raw = t.text.replace("−", "-").replace(" ", "")
        if "%" in t.text:
            m = re.search(r"([+\-]?\d+(?:\.\d+)?)\s*%", t.text.replace("−", "-"))
            if m:
                return float(m.group(1))
        if EV_RE.match(raw) and raw.endswith("%"):
            return float(raw.rstrip("%"))
    # Sometimes OCR splits number and %
    for i, t in enumerate(row):
        raw = t.text.replace("−", "-")
        if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", raw):
            nxt = row[i + 1].text if i + 1 < len(row) else ""
            if nxt.strip() == "%":
                val = float(raw)
                # EV is usually small magnitude vs american odds
                if abs(val) < 100:
                    return val
    return None


def _extract_max(row: Sequence[OcrToken]) -> Optional[float]:
    """Parse MAX stake. OCR often turns '$620' into 'S620' or '$801' into '3801'."""
    # Prefer explicitly dollar-like tokens over bare digits (OCR splits "$801" → "$801","3").
    preferred: list[float] = []
    fallback: list[tuple[float, float]] = []
    for t in row:
        raw = t.text.replace(",", "").replace(" ", "").replace("−", "-")
        if raw.startswith("+") or raw.startswith("-") or "%" in raw:
            continue
        m = re.fullmatch(r"[\$Ss]?(\d+(?:\.\d+)?)", raw)
        if not m:
            continue
        digits = m.group(1)
        val = float(digits)
        dollarish = raw.startswith(("$", "S", "s"))
        if not dollarish and digits.startswith("3") and len(digits) == 4:
            val = float(digits[1:])
            dollarish = True
        if not (1 <= val <= 1_000_000):
            continue
        if dollarish:
            preferred.append(val)
        elif len(digits) >= 2:
            fallback.append((t.cx, val))
    if preferred:
        return preferred[-1]
    if fallback:
        fallback.sort(key=lambda x: x[0])
        return fallback[-1][1]
    return None


def _extract_league(row: Sequence[OcrToken]) -> str:
    for t in row:
        n = _norm(t.text)
        # OCR often drops a letter: TENIS
        if n in {"TENNIS", "TENIS"} or "TENNIS" in n or n.startswith("TENI"):
            return "Tennis"
        if n in {"NBA", "NFL", "MLB", "NHL", "NCAAB", "NCAAF", "SOCCER", "UFC", "MMA"}:
            return n
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


def _extract_status(row: Sequence[OcrToken]) -> str:
    parts = []
    for t in row:
        if _looks_like_status(t.text):
            parts.append(t.text.strip())
    return " ".join(parts)


def _extract_event(
    row: Sequence[OcrToken],
    headers: dict[str, float],
    image_width: Optional[int],
) -> str:
    """Collect player/team name tokens between EV and ODDS columns when possible."""
    x_ev = headers.get("EV")
    x_odds = headers.get("ODDS")
    league_like = {"TENNIS", "TENIS", "NBA", "NFL", "MLB", "NHL", "UNDER", "OVER"}
    name_tokens: List[OcrToken] = []
    for t in row:
        if _is_numeric_ish(t.text) or _norm(t.text) in league_like:
            continue
        if _is_selection_phrase(t.text):
            continue
        if TIME_RE.match(t.text.strip()):
            continue
        if re.search(r"\bIn\s+\d+\s+hour", t.text, re.I):
            continue
        if _norm(t.text).startswith("TENI"):
            continue
        if _looks_like_status(t.text):
            continue
        if x_ev is not None and x_odds is not None:
            if x_ev < t.cx < x_odds:
                name_tokens.append(t)
        elif _looks_like_name(t.text):
            name_tokens.append(t)

    if not name_tokens:
        # Fallback: any name-like tokens
        name_tokens = [t for t in row if _looks_like_name(t.text)]

    names = [t.text.strip() for t in sorted(name_tokens, key=lambda t: (t.cy, t.cx))]
    # Deduplicate while preserving order
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
