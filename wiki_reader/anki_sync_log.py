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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS summary_card (
                    session_id TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    hiragana TEXT NOT NULL,
                    romaji TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    article_title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    review_state TEXT NOT NULL,
                    recognized_count INTEGER NOT NULL,
                    unrecognized_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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

    def save_summary_cards(
        self, session_id: str, cards: list[dict[str, Any]]
    ) -> None:
        session_id = validate_session_id(session_id)
        records = [summary_card_record(session_id, card) for card in cards]
        records = [record for record in records if record["token_id"]]
        if not records:
            return
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO summary_card(
                    session_id, token_id, expression, hiragana, romaji,
                    translation, article_title, source_url, review_state,
                    recognized_count, unrecognized_count
                ) VALUES (
                    :session_id, :token_id, :expression, :hiragana, :romaji,
                    :translation, :article_title, :source_url, :review_state,
                    :recognized_count, :unrecognized_count
                )
                ON CONFLICT(session_id, token_id) DO UPDATE SET
                    expression = excluded.expression,
                    hiragana = excluded.hiragana,
                    romaji = excluded.romaji,
                    translation = excluded.translation,
                    article_title = excluded.article_title,
                    source_url = excluded.source_url,
                    review_state = excluded.review_state,
                    recognized_count = excluded.recognized_count,
                    unrecognized_count = excluded.unrecognized_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                records,
            )

    def vocabulary_summary(
        self,
        *,
        current_session_id: str | None = None,
        current_cards: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT session_id, token_id, expression, hiragana, romaji,
                       translation, article_title, source_url, review_state,
                       recognized_count, unrecognized_count
                FROM summary_card
                ORDER BY updated_at, session_id, token_id
                """
            ).fetchall()
        records = {
            (str(row[0]), str(row[1])): {
                "session_id": str(row[0]),
                "token_id": str(row[1]),
                "expression": str(row[2]),
                "hiragana": str(row[3]),
                "romaji": str(row[4]),
                "translation": str(row[5]),
                "article_title": str(row[6]),
                "source_url": str(row[7]),
                "review_state": str(row[8]),
                "recognized_count": int(row[9]),
                "unrecognized_count": int(row[10]),
            }
            for row in rows
        }
        if current_session_id and current_cards is not None:
            session_id = validate_session_id(current_session_id)
            for card in current_cards:
                record = summary_card_record(session_id, card)
                if record["token_id"]:
                    records[(session_id, record["token_id"])] = record
        return aggregate_vocabulary_summary(list(records.values()))


def card_fingerprint(card: Mapping[str, Any]) -> str:
    """Return a stable identity for the exact note fields and review answer."""
    payload = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_card_record(
    session_id: str, card: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "token_id": str(card.get("canonical", "")).strip(),
        "expression": str(card.get("expression", "")).strip(),
        "hiragana": str(card.get("hiragana", "")).strip(),
        "romaji": str(card.get("romaji", "")).strip(),
        "translation": str(card.get("translation", "")).strip(),
        "article_title": str(card.get("article_title", "")).strip(),
        "source_url": str(card.get("source_url", "")).strip(),
        "review_state": str(card.get("review_state", "")).strip(),
        "recognized_count": nonnegative_int(card.get("recognized_count", 0)),
        "unrecognized_count": nonnegative_int(card.get("unrecognized_count", 0)),
    }


def aggregate_vocabulary_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    tokens: dict[str, dict[str, Any]] = {}
    sessions: set[str] = set()
    for record in records:
        session_id = str(record["session_id"])
        token_id = str(record["token_id"])
        if not session_id or not token_id:
            continue
        sessions.add(session_id)
        summary = tokens.setdefault(
            token_id,
            {
                "token_id": token_id,
                "expression": str(record.get("expression", "")),
                "hiragana": str(record.get("hiragana", "")),
                "romaji": str(record.get("romaji", "")),
                "translation": str(record.get("translation", "")),
                "recognized_count": 0,
                "unrecognized_count": 0,
                "always_count": 0,
                "sessions": [],
            },
        )
        for field in ("expression", "hiragana", "romaji", "translation"):
            if record.get(field):
                summary[field] = str(record[field])
        summary["sessions"].append(
            {
                "session_id": session_id,
                "article_title": str(record.get("article_title") or "Untitled article"),
                "source_url": str(record.get("source_url", "")),
            }
        )
        if record.get("review_state") == "easy":
            summary["always_count"] += 1
        else:
            summary["recognized_count"] += int(record.get("recognized_count", 0))
            summary["unrecognized_count"] += int(
                record.get("unrecognized_count", 0)
            )

    values = []
    for summary in tokens.values():
        summary["difference"] = (
            summary["recognized_count"] - summary["unrecognized_count"]
        )
        summary["session_count"] = len(summary["sessions"])
        values.append(summary)
    return {
        "tokens": values,
        "token_count": len(values),
        "session_count": len(sessions),
    }


def nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def validate_session_id(value: str) -> str:
    session_id = value.strip()
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("A valid session_id is required for retry-safe Anki sync.")
    return session_id
