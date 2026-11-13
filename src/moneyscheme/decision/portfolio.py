from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PortfolioEntry:
    fingerprint: str
    event_key: str
    selection: str
    odds_american: int
    status: str  # pending | open | recent
    created_at: str
    opportunity_json: str = ""


class Portfolio:
    """SQLite-backed open/pending/recent bets for Decision."""

    def __init__(self, path: Path | str = "data/portfolio.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    odds_american INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    opportunity_json TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_fp ON entries(fingerprint)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_event ON entries(event_key)"
            )

    def active(self) -> List[PortfolioEntry]:
        return self._fetch("SELECT * FROM entries WHERE status IN ('pending','open') ORDER BY id")

    def fingerprints_active(self) -> set[str]:
        return {e.fingerprint for e in self.active()}

    def event_keys_active(self) -> set[str]:
        return {e.event_key for e in self.active()}

    def count_active(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM entries WHERE status IN ('pending','open')"
            ).fetchone()
            return int(row["c"])

    def add_pending(
        self,
        *,
        fingerprint: str,
        event_key: str,
        selection: str,
        odds_american: int,
        opportunity_json: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO entries
                (fingerprint, event_key, selection, odds_american, status, created_at, opportunity_json)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    fingerprint,
                    event_key,
                    selection,
                    odds_american,
                    _utc_now(),
                    opportunity_json,
                ),
            )

    def mark_open(self, fingerprint: str) -> None:
        self._set_status(fingerprint, "open")

    def mark_recent(self, fingerprint: str) -> None:
        self._set_status(fingerprint, "recent")

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM entries")

    def _set_status(self, fingerprint: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE entries SET status = ? WHERE fingerprint = ? AND status IN ('pending','open')",
                (status, fingerprint),
            )

    def _fetch(self, sql: str, params: Iterable = ()) -> List[PortfolioEntry]:
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            PortfolioEntry(
                fingerprint=r["fingerprint"],
                event_key=r["event_key"],
                selection=r["selection"],
                odds_american=int(r["odds_american"]),
                status=r["status"],
                created_at=r["created_at"],
                opportunity_json=r["opportunity_json"] or "",
            )
            for r in rows
        ]

    def dump_json(self) -> str:
        return json.dumps([e.__dict__ for e in self.active()], indent=2)
