from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ANALYSIS_CACHE_VERSION = "2026-07-13-toponym-suffixes"


class AnalysisCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    cache_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def get(self, article: dict[str, Any]) -> dict[str, Any] | None:
        key = analysis_cache_key(article)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT payload
                FROM analysis_cache
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row[0]))

    def set(self, article: dict[str, Any], payload: dict[str, Any]) -> None:
        title = str(article.get("title", ""))
        revision_id = str(article.get("revision_id", ""))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO analysis_cache(
                    cache_key,
                    title,
                    revision_id,
                    analyzer_version,
                    payload
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    analysis_cache_key(article),
                    title,
                    revision_id,
                    ANALYSIS_CACHE_VERSION,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )


def analysis_cache_key(article: dict[str, Any]) -> str:
    title = str(article.get("title", ""))
    revision_id = str(article.get("revision_id", ""))
    if not title or not revision_id:
        raise ValueError("Analyzed article cache requires a title and revision_id.")
    return f"{ANALYSIS_CACHE_VERSION}:{revision_id}:{title}"
