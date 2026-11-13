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

Parse live (same countdown). Every `--live` run also saves a PNG under `fixtures/screenshots/live-TIMESTAMP.png`:

```powershell
moneyscheme --live --pretty
```

Use `--delay 8` if you need more time, or `--delay 0` for instant capture.

Without ROI vars, the full primary monitor is captured.

## Opportunity fields

From your locked table (Novig-only): `league`, `status`, `ev_percent`, `event`, `market`, `odds_percent` (or American), `max_stake`, `selection`, `book=novig`.

## Decision (take / skip)

```powershell
moneyscheme --image fixtures\screenshots\pto-ev-final.png --decide --pretty
```

Your fixture rows are negative EV, so with `MIN_EV_PERCENT=0` they should all **skip** (`ev_below_min`). Same-game rows also collapse under one-bet-per-game when EV is positive.

Add `--commit` to write takes into `data/portfolio.db` (so the next run can dedupe).

## Novig Paper credentials

1. Put API key id in `.env` as `NOVIG_KEY_ID=...`
2. Put private key PEM in `secrets/novig-paper.pem`
3. Test:

```powershell
python -m moneyscheme.app.novig_echo
```

A successful echo means signing and Paper auth work.

### Trading subaccount (for placing)

```powershell
python -m moneyscheme.app.novig_bootstrap
```

That creates `secrets/novig-trading.pem`, funds $100 Paper, and prints `NOVIG_TRADING_*` lines for `.env`.

### Paper dry-run / place

```powershell
moneyscheme --image fixtures\screenshots\pto-ev-final.png --decide --paper --pretty
moneyscheme --image fixtures\screenshots\pto-ev-final.png --decide --paper --place --pretty
```

`--place` asks for confirm on each ready IOC. No `--place` means plan only.
