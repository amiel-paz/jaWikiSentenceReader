from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{7,127}")


class AnkiSyncLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS completed_sync (
                    session_id TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(self, session_id: str) -> dict[str, Any] | None:
        session_id = validate_session_id(session_id)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT result FROM completed_sync WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return json.loads(str(row[0])) if row else None

    def save(self, session_id: str, result: dict[str, Any]) -> None:
        session_id = validate_session_id(session_id)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO completed_sync(session_id, result) VALUES (?, ?)",
                (session_id, json.dumps(result, ensure_ascii=False)),
            )


def validate_session_id(value: str) -> str:
    session_id = value.strip()
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("A valid session_id is required for retry-safe Anki sync.")
    return session_id
