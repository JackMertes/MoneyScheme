from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kelly_fraction: float = 0.33
    bankroll: float = 1000.0

    # Decision rules
    min_ev_percent: float = 0.0
    one_bet_per_game: bool = True
    max_open_bets: int = 20
    # Comma-separated substrings matched against selection (empty = allow all)
    market_allowlist: str = ""
    portfolio_db: str = "data/portfolio.db"

    # Novig Paper / live API (management key for account; trading key for orders)
    novig_host: str = "https://api.paper.novig.com"
    novig_key_id: str = ""
    novig_pem_path: str = "secrets/novig-paper.pem"
    novig_trading_key_id: str = ""
    novig_trading_pem_path: str = "secrets/novig-trading.pem"

    # CAPTURE_USE_ROI=true → crop with the four values below; false → full monitor.
    capture_use_roi: bool = Field(default=False, validation_alias="CAPTURE_USE_ROI")
    roi_left: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_LEFT")
    roi_top: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_TOP")
    roi_width: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_WIDTH")
    roi_height: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_HEIGHT")

    def capture_region(self) -> Optional[dict[str, int]]:
        if not self.capture_use_roi:
            return None
        missing = [
            name
            for name, val in (
                ("CAPTURE_ROI_LEFT", self.roi_left),
                ("CAPTURE_ROI_TOP", self.roi_top),
                ("CAPTURE_ROI_WIDTH", self.roi_width),
                ("CAPTURE_ROI_HEIGHT", self.roi_height),
            )
            if val is None
        ]
        if missing:
            raise ValueError(
                "CAPTURE_USE_ROI=true but ROI box is incomplete. "
                f"Missing: {', '.join(missing)}."
            )
        return {
            "left": int(self.roi_left),  # type: ignore[arg-type]
            "top": int(self.roi_top),  # type: ignore[arg-type]
            "width": int(self.roi_width),  # type: ignore[arg-type]
            "height": int(self.roi_height),  # type: ignore[arg-type]
        }

    def market_allowlist_set(self) -> set[str]:
        if not self.market_allowlist.strip():
            return set()
        return {p.strip().lower() for p in self.market_allowlist.split(",") if p.strip()}


def get_settings() -> Settings:
    return Settings()
