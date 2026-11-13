from __future__ import annotations

from typing import Any, Optional

import requests

from moneyscheme.config import Settings, get_settings
from moneyscheme.novig.signing import KeyPair, load_key, sign_headers


class NovigClient:
    """Signed REST client for Novig Paper/Production."""

    def __init__(
        self,
        *,
        host: str,
        key: KeyPair,
        timeout: float = 30.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.session = requests.Session()

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "NovigClient":
        settings = settings or get_settings()
        if not settings.novig_key_id:
            raise ValueError("NOVIG_KEY_ID is not set in .env")
        if not settings.novig_pem_path:
            raise ValueError("NOVIG_PEM_PATH is not set in .env")
        key = load_key(settings.novig_key_id, settings.novig_pem_path)
        return cls(host=settings.novig_host, key=key)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: str = "",
        body: Any = None,
    ) -> Any:
        headers, data = sign_headers(self.key, method, path, query=query, body=body)
        url = self.host + path
        if query:
            url = f"{url}?{query}"
        resp = self.session.request(
            method.upper(),
            url,
            data=data if data else None,
            headers=headers,
            timeout=self.timeout,
        )
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}
        if resp.status_code >= 400:
            raise NovigApiError(resp.status_code, payload)
        return payload

    def echo(self, body: Optional[dict] = None) -> Any:
        return self.request("POST", "/v3/echo", body=body or {"hello": "world"})

    def time(self) -> Any:
        return self.request("GET", "/v3/time")


class NovigApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Novig API {status_code}: {payload}")
