from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Opportunity(BaseModel):
    """Normalized +EV row from Pick the Odds (Novig-only)."""

    league: str
    status: str = ""
    ev_percent: float
    event: str
    market: str = ""
    # Pick the Odds ODDS column is implied probability percent (e.g. 46.1).
    odds_percent: float = 0.0
    # American form kept for Kelly helper; derived when missing.
    odds_american: int = 0
    max_stake: Optional[float] = None
    # PTO WAGER column (Kelly suggestion). Display only; we size ourselves.
    wager: Optional[float] = None
    selection: str
    book: str = "novig"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_text: str = ""
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def odds_price(self) -> Optional[str]:
        """OCR odds as Novig-style probability, e.g. '0.470'."""
        if self.odds_percent <= 0:
            return None
        return f"{self.odds_percent / 100.0:.3f}"

    @model_validator(mode="after")
    def _sync_odds_fields(self) -> "Opportunity":
        from moneyscheme.novig.money import (
            american_to_probability,
            percent_to_american,
        )

        if self.odds_percent > 0 and self.odds_american == 0:
            self.odds_american = percent_to_american(self.odds_percent)
        elif self.odds_american != 0 and self.odds_percent == 0:
            p = american_to_probability(self.odds_american)
            self.odds_percent = float((p * Decimal(100)).quantize(Decimal("0.001")))
        return self

    def fingerprint(self) -> str:
        """Stable key for dedupe: event + selection + odds percent."""
        odds_key = (
            f"{self.odds_percent:.3f}"
            if self.odds_percent > 0
            else str(self.odds_american)
        )
        return "|".join(
            [
                self.event.strip().lower(),
                self.market.strip().lower(),
                self.selection.strip().lower(),
                odds_key,
            ]
        )


class Decision(BaseModel):
    """Result of looking at an Opportunity against portfolio rules."""

    action: Literal["take", "skip"]
    reason: str
    opportunity: Opportunity
    suggested_stake: float = 0.0
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
