from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    """Normalized +EV row from Pick the Odds (Novig-only)."""

    league: str
    status: str = ""
    ev_percent: float
    event: str
    odds_american: int
    max_stake: Optional[float] = None
    selection: str
    book: str = "novig"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_text: str = ""
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def fingerprint(self) -> str:
        """Stable key for dedupe: event + selection + odds."""
        return "|".join(
            [
                self.event.strip().lower(),
                self.selection.strip().lower(),
                str(self.odds_american),
            ]
        )


class Decision(BaseModel):
    """Result of looking at an Opportunity against portfolio rules."""

    action: Literal["take", "skip"]
    reason: str
    opportunity: Opportunity
    suggested_stake: float = 0.0
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
