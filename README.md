# MoneyScheme

Pick the Odds screen capture → Opportunity → Decision → Novig.

## Setup

```powershell
cd MoneyScheme
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Parse a fixture screenshot

```powershell
moneyscheme --image fixtures\screenshots\pto-ev-final.png --pretty
```

## Live capture

Copy `.env.example` → `.env` and set a tight ROI around the table (pixels):

```
CAPTURE_ROI_LEFT=...
CAPTURE_ROI_TOP=...
CAPTURE_ROI_WIDTH=...
CAPTURE_ROI_HEIGHT=...
```

Save a calibration shot (5s countdown so you can switch to Pick the Odds):

```powershell
python -m moneyscheme.app.save_capture
```

Parse live (same countdown):

```powershell
moneyscheme --live --pretty
```

Use `--delay 8` if you need more time, or `--delay 0` for instant capture.

Without ROI vars, the full primary monitor is captured.

## Opportunity fields

From your locked table (Novig-only): `league`, `status`, `ev_percent`, `event`, `odds_american`, `max_stake`, `selection`, `book=novig`.
