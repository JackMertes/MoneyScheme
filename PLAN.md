# Positive EV Bet Automation

The goal is to automate the loop from spotting a +EV bet on Pick the Odds to placing it on Novig, without blindly taking every line that appears.

## Pipeline

```
Screenshot → OCR → Opportunity → Decision → Novig match/place → fills back to Decision
```

- **Capture + OCR:** Capture a fixed region of the Pick the Odds window and OCR it into a structured Opportunity (event, market, side, line, odds, EV, confidence).
- **Decision:** Compare the Opportunity to our current portfolio (open, pending, recently placed). Handle dedupe, correlation, and take/skip. Nothing goes to Novig until Decision says take. Optional money safety later (max stake, kill switch) lives here too, not as a separate stage.
- **Novig:** Match accepted opportunities to a Novig outcome, place via their API, and feed fills/positions back into Decision.

## Build order

1. Get Capture → Opportunity working so we trust the parsed JSON from your real UI.
2. Build Decision with portfolio state and log take/skip reasons without placing anything.
3. Wire Novig Paper so only `take` decisions become orders.
4. Move to live, tighten rules, and add auto only when the selection logic is solid.

## Decision v1

- **Dedupe:** Skip if we already have the same event, market, side, and line open or pending.
- **Correlation:** Start strict: one bet per game. Loosen later (e.g. allow spread + total) once the loop is trustworthy.
- **Selection:** Min EV%, market allowlist, max open bets.

## UI assumptions (locked)

Table columns: LEAGUE, STATUS, EV, EVENT, ODDS, MAX, BOOK & SELECTION. No WAGER column; we compute Kelly ourselves and cap with MAX.

Book is always Novig (filter is Novig-only). We hardcode `book = novig` and OCR the selection text from that column, not the logo.

## Stack

- Local Python on Windows
- Secrets in `.env`
- Screenshot OCR (not a camera)
- Novig API for execution

## Status

- Stage 1 (Capture → Opportunity): done on fixture `pto-ev-final.png`
- Stage 2 (Decision): done (dedupe, one bet per game, min EV, Kelly sizing, portfolio DB)
- Next: Novig Paper match/place for `take` only

## Need from you

- Set `CAPTURE_ROI_*` in `.env` for a tight table crop (optional but better OCR)
- Novig Paper keys when we reach stage 3
