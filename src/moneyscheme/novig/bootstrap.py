from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from moneyscheme.novig.client import NovigClient
from moneyscheme.novig.signing import load_key


def generate_ed25519_pem_pair(private_path: Path) -> str:
    """Write private PEM to disk; return public SPKI PEM string (with newlines)."""
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    priv_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_path.write_bytes(priv_pem)
    pub_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pub_pem.decode("ascii")


def ensure_trading_subaccount(
    management: NovigClient,
    *,
    trading_pem_path: Path,
    label: str = "moneyscheme",
    fund_amount: str = "100.00000",
) -> dict[str, Any]:
    """
    Ensure a trading subaccount exists for this app.

    If trading_pem_path already exists and NOVIG_TRADING_KEY_ID is usable, reuse it.
    Otherwise create a new keypair + subaccount and fund it.
    """
    subs = management.request("GET", "/v3/account/subaccounts")
    existing = [s for s in subs if s.get("label") == label]
    if existing and trading_pem_path.exists():
        key_id = existing[0]["keyId"]
        return {
            "keyId": key_id,
            "label": label,
            "balance": existing[0].get("balance"),
            "created": False,
            "pem_path": str(trading_pem_path),
        }

    public_pem = generate_ed25519_pem_pair(trading_pem_path)
    created = management.request(
        "POST",
        "/v3/account/subaccounts",
        body={
            "label": label,
            "publicKey": public_pem,
            "algorithm": "Ed25519",
        },
    )
    key_id = created["keyId"]
    transfer = management.request(
        "POST",
        f"/v3/account/subaccounts/{key_id}/transfer",
        body={
            "direction": "fund",
            "amount": fund_amount,
            "clientTransferId": f"moneyscheme-fund-{uuid.uuid4()}",
        },
    )
    # Wait briefly for Applied
    status = transfer
    for _ in range(10):
        if status.get("status") in {"Applied", "Rejected"}:
            break
        time.sleep(0.5)
        status = management.request(
            "GET",
            f"/v3/account/subaccounts/{key_id}/transfers/{transfer['transferId']}",
        )
    bal = management.request("GET", f"/v3/account/subaccounts/{key_id}/balance")
    return {
        "keyId": key_id,
        "label": label,
        "balance": bal if isinstance(bal, str) else bal,
        "transfer": status,
        "created": True,
        "pem_path": str(trading_pem_path),
    }


def trading_client(
    *,
    host: str,
    trading_key_id: str,
    trading_pem_path: str,
) -> NovigClient:
    key = load_key(trading_key_id, trading_pem_path)
    return NovigClient(host=host, key=key)
