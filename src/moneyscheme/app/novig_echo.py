"""Prove Novig Paper credentials with POST /v3/echo."""

from __future__ import annotations

import json
import sys

from moneyscheme.novig.client import NovigApiError, NovigClient


def main() -> int:
    try:
        client = NovigClient.from_settings()
        print(f"Host: {client.host}", file=sys.stderr)
        print("Calling POST /v3/echo ...", file=sys.stderr)
        result = client.echo({"hello": "moneyscheme", "ok": True})
        print(json.dumps(result, indent=2))
        print("Echo OK. Credentials and signing work.", file=sys.stderr)
        return 0
    except NovigApiError as e:
        print(f"Echo FAILED ({e.status_code})", file=sys.stderr)
        print(json.dumps(e.payload, indent=2, default=str))
        return 1
    except Exception as e:
        print(f"Echo FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
