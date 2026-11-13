from moneyscheme.ocr.engine import OcrToken
from moneyscheme.ocr.parse import parse_opportunities


def _tok(text: str, x: float, y: float, conf: float = 0.99) -> OcrToken:
    w = max(20.0, len(text) * 8.0)
    return OcrToken(text=text, conf=conf, x0=x, y0=y, x1=x + w, y1=y + 14)


def test_parse_three_table_rows():
    # Header row
    y0 = 10
    tokens = [
        _tok("LEAGUE", 40, y0),
        _tok("STATUS", 120, y0),
        _tok("EV", 220, y0),
        _tok("EVENT", 320, y0),
        _tok("ODDS", 480, y0),
        _tok("MAX", 560, y0),
        _tok("BOOK & SELECTION", 700, y0),
    ]
    # Data row 1
    y = 50
    tokens += [
        _tok("TENNIS", 40, y),
        _tok("2:00 AM", 100, y),
        _tok("In 2 hours", 100, y + 12),
        _tok("-1.6%", 220, y),
        _tok("Adrian Andreev", 300, y),
        _tok("Michele Ribecai", 300, y + 14),
        _tok("+102", 480, y),
        _tok("$198", 560, y),
        _tok("Under 21.5", 700, y),
    ]
    # Data row 2
    y = 110
    tokens += [
        _tok("TENIS", 40, y),
        _tok("2:00 AM", 100, y),
        _tok("In 2 hours", 100, y + 12),
        _tok("-1.9%", 220, y),
        _tok("Adrian Andreev", 300, y),
        _tok("Michele Ribecai", 300, y + 14),
        _tok("-150", 480, y),
        _tok("S620", 560, y),
        _tok("Michele Ribecai", 700, y),
    ]

    opps = parse_opportunities(tokens, image_width=900)
    assert len(opps) == 2
    assert opps[0].selection == "Under 21.5"
    assert opps[0].odds_american == 102
    assert opps[0].max_stake == 198.0
    assert opps[0].book == "novig"
    assert opps[0].league == "Tennis"
    assert "Adrian" in opps[0].event and "Michele" in opps[0].event
    assert opps[1].odds_american == -150
    assert opps[1].max_stake == 620.0
    assert opps[1].selection == "Michele Ribecai"
