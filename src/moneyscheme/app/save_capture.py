"""Save a live screen (or ROI) to disk for ROI calibration."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from moneyscheme.app.countdown import wait_for_switch
from moneyscheme.capture.screen import capture_region
from moneyscheme.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save a screenshot for ROI calibration")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: fixtures/screenshots/live-TIMESTAMP.png)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Seconds to wait so you can switch to Pick the Odds (default: 5)",
    )
    args = parser.parse_args(argv)

    wait_for_switch(args.delay)
    settings = get_settings()
    img = capture_region(settings.capture_region())
    out = args.out
    if out is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path("fixtures/screenshots") / f"live-{ts}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"Saved {out} ({img.size[0]}x{img.size[1]})")
    region = settings.capture_region()
    if region:
        print(f"ROI used: {region}")
    else:
        print("ROI: full primary monitor (set CAPTURE_ROI_* in .env to crop)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
