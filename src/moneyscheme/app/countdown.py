from __future__ import annotations

import sys
import time


def wait_for_switch(seconds: float) -> None:
    """Give the user time to focus Pick the Odds before we capture."""
    if seconds <= 0:
        return
    total = int(seconds)
    print(
        f"Switch to Pick the Odds now. Capturing in {seconds:g}s...",
        file=sys.stderr,
        flush=True,
    )
    for left in range(total, 0, -1):
        print(f"  {left}...", file=sys.stderr, flush=True)
        time.sleep(1)
    leftover = seconds - total
    if leftover > 0:
        time.sleep(leftover)
    print("Capturing.", file=sys.stderr, flush=True)
