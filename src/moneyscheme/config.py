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

    # Absolute screen ROI for live capture (pixels). None = full primary monitor.
    roi_left: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_LEFT")
    roi_top: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_TOP")
    roi_width: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_WIDTH")
    roi_height: Optional[int] = Field(default=None, validation_alias="CAPTURE_ROI_HEIGHT")

    def capture_region(self) -> Optional[dict[str, int]]:
        if None in (self.roi_left, self.roi_top, self.roi_width, self.roi_height):
            return None
        assert self.roi_left is not None
        assert self.roi_top is not None
        assert self.roi_width is not None
        assert self.roi_height is not None
        return {
            "left": self.roi_left,
            "top": self.roi_top,
            "width": self.roi_width,
            "height": self.roi_height,
        }

    def market_allowlist_set(self) -> set[str]:
        if not self.market_allowlist.strip():
            return set()
        return {p.strip().lower() for p in self.market_allowlist.split(",") if p.strip()}


def get_settings() -> Settings:
    return Settings()
