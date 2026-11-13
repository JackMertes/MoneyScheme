# Positive EV Bet Automation

The goal is to automate the loop from spotting a +EV bet on Pick the Odds to placing it on Novig, without blindly taking every line that appears.

## Pipeline

```
Screenshot → OCR → Opportunity → Decision → Novig match/place → fills back to Decision
```

- **Capture + OCR:** Pixels → Opportunity (done).
- **Decision:** Dedupe, one bet per game, min EV, Kelly size → take/skip (done).
- **Novig:** Match `take` to an outcome, place order, stream fills back into portfolio.

## Build order

1. Capture → Opportunity (done)
2. Decision (done)
3. **Novig Paper match/place** (planning now)
4. Live Novig later

## Decision v1 (locked)

- Dedupe same event + selection + odds
- One bet per game (best EV wins)
- Min EV%, max open bets, Kelly stake capped by MAX
- Book always Novig

## Stage 3: Novig Paper plan

Paper is Novig’s play-money API (`https://api.paper.novig.com`). Same endpoints as live. Keys are Paper-only.

### Flow for a `take`

```
Decision(take)
    → match Opportunity to Novig outcomeId
    → convert odds → price string on Novig grid
    → convert stake $ → contract qty
    → POST /v3/orders (Paper)
    → private WS open/fill/reject
    → update portfolio (pending → open / recent)
```

### What we will build

1. **Auth client**
   - Load Paper key id + PEM from `.env` (never commit)
   - Sign requests with NOVIG-V3 (Ed25519 or P-256)
   - Prove signing with `POST /v3/echo`

2. **Account bootstrap (once)**
   - Management key opens a subaccount + trading key
   - Fund subaccount from Paper wallet
   - Docs: [Quickstart](https://docs.novig.com/api/quickstart), [Environments](https://docs.novig.com/api/environments)

3. **Catalog match (exact, not fuzzy)**
   - Pick the Odds is Novig-only, so the row is the same bet that exists on Novig
   - Look up catalog by exact event + selection (and line where applicable) → `outcomeId`
   - Normalize only boring OCR noise (case, spacing, player order in event names)
   - If there is no exact catalog hit: **skip** (`no_exact_match`). Never guess a “close” market

4. **Odds gate (locked)**
   - Before place, check Novig’s book for that outcome
   - Only proceed if available price is **at least as good as** the Pick the Odds American odds we OCR’d (same or better for us)
   - If the line moved worse: skip (`odds_moved`)
   - Order limit price is set from the OCR’d odds (snapped to Novig’s grid), so IOC cannot pay a worse price than we intended

5. **Order builder**
   - American odds → probability price string on Novig grid
   - Stake dollars → integer contract `qty`
   - Cap qty from MAX / bankroll / Kelly
   - Time in force: **IOC only** (no GTC)

6. **Place + observe**
   - Confirm prompt, then `POST /v3/orders`
   - `201` means accepted/queued, not filled
   - Private stream for `open` / `fill` / `reject`
   - Update portfolio so Decision sees the bet

7. **CLI**
   - `--decide --paper` dry-run: show match + odds check + order, do not place
   - `--decide --paper --place`: confirm each take, then place IOC on Paper

### Money model (important)

| Field | Novig format | Example |
|---|---|---|
| price | probability string, 3 places, on grid | `"0.495"` |
| qty | whole contracts | `110` |
| cost | `price * qty * $0.01` | 110 @ 0.495 ≈ $0.54 |

Snap prices **down** to the grid before send. Docs: [Money](https://docs.novig.com/api/concepts/money).

### Hard rules for Paper stage

- Default host: Paper only (`NOVIG_HOST=https://api.paper.novig.com`)
- Only Decision `take` can place
- **IOC only**
- **Odds must still match (or beat) the +EV line we saw** or we skip
- No exact catalog match → skip (no fuzzy guesses)
- Confirm before every place
- No blind retries (Novig `clientId` is not idempotent)
- `--place` required so a normal run cannot fire orders by accident

### Your setup checklist

1. Account at https://paper.novig.com (start with $10k play money)
2. Profile → Settings → Novig API → create management key + PEM
3. Put in `.env`: `NOVIG_HOST`, `NOVIG_KEY_ID`, `NOVIG_PEM_PATH`
4. We run echo → subaccount → tiny test order on Paper

### Docs

- https://docs.novig.com/
- https://docs.novig.com/api/environments
- https://docs.novig.com/api/quickstart
- https://docs.novig.com/api/signing
- https://docs.novig.com/api/execution/orders
- https://docs.novig.com/api/catalog

## Choices (locked)

1. Confirm before each Paper place: **yes**
2. Order style: **IOC only**
3. Odds gate: only take if Novig price is **same or better** than the +EV odds from Pick the Odds
4. Catalog match: **exact only**; no match → skip

## Status

- Stages 1–2 done
- Stage 3 mostly done:
  - Paper echo OK
  - Trading subaccount bootstrap + $100 Paper fund
  - Exact catalog match, odds gate, IOC-only, confirm-before-place
- Try: `moneyscheme --image ... --decide --paper --pretty`
- Place: add `--place` (prompts y/N per order)
