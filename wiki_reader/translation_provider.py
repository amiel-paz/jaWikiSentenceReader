from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .token_utils import hiragana_to_katakana


class TranslationProvider(Protocol):
    def lookup(self, token: dict[str, Any]) -> str:
        """Return a short gloss for a token, or an empty string when unknown."""


@dataclass(frozen=True)
class NullTranslationProvider:
    def lookup(self, token: dict[str, Any]) -> str:
        return ""


@dataclass(frozen=True)
class SqliteDictionaryProvider:
    path: Path

    def lookup(self, token: dict[str, Any]) -> str:
        with sqlite3.connect(self.path) as connection:
            for key in lookup_keys(token):
                row = connection.execute(
                    """
                    SELECT gloss
                    FROM dictionary_lookup
                    WHERE lookup_key = ?
                    ORDER BY
                        CASE
                            WHEN reading = ? THEN 0
                            WHEN reading = ? THEN 0
                            ELSE 1
                        END,
                        CASE
                            WHEN ? != '固有名詞' AND source = 'JMdict' THEN 0
                            ELSE 1
                        END,
                        priority ASC,
                        source ASC,
                        entry_id ASC
                    LIMIT 1
                    """,
                    (
                        key,
                        str(token.get("hiragana", "")),
                        hiragana_to_katakana(str(token.get("hiragana", ""))),
                        str(token.get("pos2", "")),
                    ),
                ).fetchone()
                if row:
                    return str(row[0])
        return ""


def default_translation_provider(base_dir: Path) -> TranslationProvider:
    dictionary_path = base_dir / "data" / "dictionary.sqlite"
    if dictionary_path.exists():
        return SqliteDictionaryProvider(dictionary_path)
    return NullTranslationProvider()


def lookup_keys(token: dict[str, Any]) -> list[str]:
    canonical = str(token.get("canonical", ""))
    surface = str(token.get("surface", ""))
    hiragana = str(token.get("hiragana", ""))
    lemma = canonical.split("::", 1)[0]
    keys = [canonical, lemma, hiragana, surface]
    return list(dict.fromkeys(key for key in keys if key))
