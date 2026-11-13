from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA, EllipticCurvePrivateKey
from cryptography.hazmat.primitives import hashes, serialization


KeyPair = Tuple[str, Any]


def load_key(key_id: str, pem_path: Union[str, Path]) -> KeyPair:
    pem = Path(pem_path).read_bytes()
    private = serialization.load_pem_private_key(pem, password=None)
    return key_id, private


def canonical_query(raw: str) -> str:
    """Build NOVIG-V3 canonical query (line 5)."""
    if not raw:
        return ""
    pairs: list[tuple[str, str]] = []
    for part in raw.split("&"):
        if part == "":
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        pairs.append((_enc(_dec(k)), _enc(_dec(v))))
    pairs.sort()
    return "&".join(f"{k}={v}" for k, v in pairs)


def _dec(part: str) -> bytes:
    raw = part.encode("utf-8")
    out = bytearray()
    i = 0
    while i < len(raw):
        if raw[i] == ord("%") and i + 2 < len(raw):
            try:
                out.append(int(raw[i + 1 : i + 3].decode("ascii"), 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(raw[i])
        i += 1
    return bytes(out)


def _enc(raw: bytes) -> str:
    chars: list[str] = []
    for b in raw:
        if (
            (48 <= b <= 57)
            or (65 <= b <= 90)
            or (97 <= b <= 122)
            or b in (45, 46, 95, 126)  # - . _ ~
        ):
            chars.append(chr(b))
        else:
            chars.append(f"%{b:02X}")
    return "".join(chars)


def body_bytes(body: Optional[Any]) -> bytes:
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    # Match Novig quickstart: default json.dumps spacing
    return json.dumps(body).encode("utf-8")


def sign_headers(
    key: KeyPair,
    method: str,
    path: str,
    query: str = "",
    body: Optional[Any] = None,
    *,
    timestamp_ms: Optional[str] = None,
) -> tuple[dict[str, str], bytes]:
    """Return (headers, raw_body_bytes) for a signed request."""
    key_id, private = key
    data = body_bytes(body)
    ts = timestamp_ms or str(int(time.time() * 1000))
    digest = hashlib.sha256(data).hexdigest()
    q = canonical_query(query) if query else ""
    canon = "\n".join(["NOVIG-V3", ts, method.upper(), path, q, digest])
    signature = _sign(private, canon.encode("utf-8"))
    headers = {
        "Novig-Key-Id": key_id,
        "Novig-Timestamp": ts,
        "Novig-Signature": base64.b64encode(signature).decode("ascii"),
        "Content-Type": "application/json",
    }
    return headers, data


def _sign(private: Any, message: bytes) -> bytes:
    if isinstance(private, Ed25519PrivateKey):
        return private.sign(message)
    if isinstance(private, EllipticCurvePrivateKey):
        return private.sign(message, ECDSA(hashes.SHA256()))
    raise TypeError(f"Unsupported private key type: {type(private)!r}")
