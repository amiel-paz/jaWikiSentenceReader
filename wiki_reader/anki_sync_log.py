from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS synced_card (
                    session_id TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(session_id, token_id)
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

    def card_fingerprints(self, session_id: str) -> dict[str, str]:
        session_id = validate_session_id(session_id)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT token_id, fingerprint
                FROM synced_card
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchall()
        return {str(token_id): str(fingerprint) for token_id, fingerprint in rows}

    def pending_cards(
        self, session_id: str, cards: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        synced = self.card_fingerprints(session_id)
        pending: list[dict[str, Any]] = []
        fingerprints: dict[str, str] = {}
        for card in cards:
            token_id = str(card.get("canonical", "")).strip()
            fingerprint = card_fingerprint(card)
            if token_id and synced.get(token_id) == fingerprint:
                continue
            pending.append(card)
            if token_id:
                fingerprints[token_id] = fingerprint
        return pending, fingerprints

    def save_card_fingerprints(
        self, session_id: str, fingerprints: Mapping[str, str]
    ) -> None:
        session_id = validate_session_id(session_id)
        if not fingerprints:
            return
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO synced_card(session_id, token_id, fingerprint)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, token_id) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    synced_at = CURRENT_TIMESTAMP
                """,
                [
                    (session_id, str(token_id), str(fingerprint))
                    for token_id, fingerprint in fingerprints.items()
                ],
            )


def card_fingerprint(card: Mapping[str, Any]) -> str:
    """Return a stable identity for the exact note fields and review answer."""
    payload = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_session_id(value: str) -> str:
    session_id = value.strip()
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("A valid session_id is required for retry-safe Anki sync.")
    return session_id
