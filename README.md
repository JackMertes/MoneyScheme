# MoneyScheme

Pick the Odds screenshot → OCR → Decision → Novig Paper IOC.

Paper is a **separate** play-money book. Odds often differ from live Novig / PTO. Use Paper to prove the loop; live comes later.

## Setup

```powershell
cd MoneyScheme
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
```

Fill `.env`:

1. Optional capture crop: `CAPTURE_USE_ROI=true` plus the `CAPTURE_ROI_*` box so only the EV table is grabbed
2. `BANKROLL`, `KELLY_FRACTION` for sizing
3. Novig Paper keys (below)

## Novig Paper keys

1. Management key: `NOVIG_KEY_ID` in `.env`, PEM in `secrets/novig-paper.pem`
2. Echo test:

```powershell
python -m moneyscheme.app.novig_echo
```

3. Trading subaccount (once):

```powershell
python -m moneyscheme.app.novig_bootstrap
```

Paste the printed `NOVIG_TRADING_*` lines into `.env`. That creates `secrets/novig-trading.pem` and funds Paper.

## Run

Activate the venv first. Every `--live` run saves `fixtures/screenshots/live-TIMESTAMP.png`.

**Capture + parse only**

```powershell
moneyscheme --live --pretty
```

**Capture + Decision (no Novig)**

```powershell
moneyscheme --live --decide --pretty
```

**Capture + match + odds gate (dry-run, no orders)**

```powershell
moneyscheme --live --decide --paper --pretty
```

**Capture + place Paper IOCs** (asks confirm per ready plan)

```powershell
moneyscheme --live --decide --paper --place --pretty
```

**Unsupervised Paper soak** (leave PTO visible; Ctrl+C to stop)

```powershell
moneyscheme --live --decide --paper --place --allow-odds-moved --yes --interval 180 --pretty
```

Every successful place is written to `data/portfolio.db` (blocks that **event** on later cycles) and appended to `data/bet_log.jsonl` for review. `--allow-odds-moved` is needed on Paper because its book usually differs from PTO/live.

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--delay 8` | Extra seconds before first capture (default 5) |
| `--delay 0` | Capture immediately |
| `--interval 180` | Re-run every N seconds (`--live` only) |
| `--place-one` | Place only the first ready plan per cycle |
| `--allow-odds-moved` | If Paper ask is worse than OCR, still place at the ask |
| `--yes` | Skip confirm (with `--place`) |
| `--bet-log PATH` | Where to append placed bets (default `data/bet_log.jsonl`) |
| `--commit` | Also write Decision *takes* to portfolio before place |
| `--image PATH` | Use a saved screenshot instead of `--live` |

Calibrate ROI (5s countdown):

```powershell
python -m moneyscheme.app.save_capture
```

## What we read from PTO

Keep these columns visible: **LEAGUE**, **STATUS**, **EV**, **EVENT**, **MARKET**, **ODDS**, **MAX**, **WAGER**, **BOOK & SELECTION**.

Report shape:

```json
{
  "league": "NBA",
  "status": "6:10 PM In 4 hours",
  "ev": 7.9,
  "event": "Bucks / Magic",
  "market": "3PT (Turner, M)",
  "selection": "Over 1.5",
  "odds": "0.455",
  "max": 345.0,
  "wager": 43.14
}
```

- `odds` is implied probability (`45.5%` → `0.455`)
- `wager` is display-only; we size with fractional Kelly × `BANKROLL`, capped by `max`
- `MARKET` is required for exact Novig prop matching

## Decision / place rules

- Dedupe + one bet per game (best EV)
- Book always Novig
- Exact catalog match only (event → market type → strike → player)
- Odds gate: Paper ask must be same or better than OCR odds, unless `--allow-odds-moved`
- Orders are **IOC** only, with confirm before place (or `--yes`)
- Placed bets persist in `data/portfolio.db`; the same **event** (teams + tip time from STATUS) is skipped on later screenshots even if that row is gone. A rematch next week is a new event.
