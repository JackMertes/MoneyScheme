"""Create Paper trading subaccount + fund it; print .env lines to add."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from moneyscheme.config import get_settings
from moneyscheme.novig.bootstrap import ensure_trading_subaccount
from moneyscheme.novig.client import NovigClient


def main() -> int:
    settings = get_settings()
    management = NovigClient.from_settings(settings)
    pem_path = Path("secrets/novig-trading.pem")
    result = ensure_trading_subaccount(
        management,
        trading_pem_path=pem_path,
        label="moneyscheme",
        fund_amount="100.00000",
    )
    print(json.dumps(result, indent=2, default=str))
    print(
        "\nAdd these to .env:\n"
        f"NOVIG_TRADING_KEY_ID={result['keyId']}\n"
        f"NOVIG_TRADING_PEM_PATH={result['pem_path']}\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
