from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


ANALYSIS_CACHE_VERSION = "2026-09-25-vocabulary-mapping"


class AnalysisCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.analyzer_version = analyzer_version(self.path.parent / "dictionary.sqlite")
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
        key = analysis_cache_key(article, self.analyzer_version)
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
                    analysis_cache_key(article, self.analyzer_version),
                    title,
                    revision_id,
                    self.analyzer_version,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )


def analysis_cache_key(
    article: dict[str, Any], analyzer_version_value: str = ANALYSIS_CACHE_VERSION
) -> str:
    title = str(article.get("title", ""))
    revision_id = str(article.get("revision_id", ""))
    if not title or not revision_id:
        raise ValueError("Analyzed article cache requires a title and revision_id.")
    return f"{analyzer_version_value}:{revision_id}:{title}"


def analyzer_version(dictionary_path: Path) -> str:
    release_tag = "no-dictionary"
    if dictionary_path.is_file():
        try:
            with sqlite3.connect(dictionary_path) as connection:
                row = connection.execute(
                    "SELECT value FROM dictionary_metadata WHERE key = 'release_tag'"
                ).fetchone()
            release_tag = str(row[0]) if row else "legacy-dictionary"
        except sqlite3.Error:
            release_tag = "legacy-dictionary"
    overrides_path = dictionary_path.parent / "private" / "vocabulary_overrides.json"
    overrides_version = "no-overrides"
    if overrides_path.is_file():
        overrides_version = hashlib.sha256(overrides_path.read_bytes()).hexdigest()[:12]
    return f"{ANALYSIS_CACHE_VERSION}:{release_tag}:{overrides_version}"
