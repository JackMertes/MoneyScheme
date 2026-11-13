from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from moneyscheme.app.countdown import wait_for_switch
from moneyscheme.pipeline import opportunities_from_path, opportunities_from_screen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture Pick the Odds EV table → Opportunity JSON"
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="Parse a screenshot/fixture instead of live capture",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Capture the configured screen ROI (or full primary monitor)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="For --live: seconds to switch to Pick the Odds before capture (default: 5)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON",
    )
    args = parser.parse_args(argv)

    if args.image:
        opps = opportunities_from_path(args.image)
    elif args.live:
        wait_for_switch(args.delay)
        opps = opportunities_from_screen()
    else:
        parser.error("Provide --image PATH or --live")

    payload = [o.model_dump(mode="json") for o in opps]
    if args.pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    print(f"# {len(opps)} opportunities", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
