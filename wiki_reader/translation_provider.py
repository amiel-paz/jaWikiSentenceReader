from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .token_utils import hiragana_to_katakana, katakana_to_hiragana


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
            columns = dictionary_columns(connection)
            select_columns = dictionary_select_columns(columns)
            for key in lookup_keys(token):
                rows = connection.execute(
                    f"""
                    SELECT {select_columns}
                    FROM dictionary_lookup
                    WHERE lookup_key = ?
                    """,
                    (key,),
                ).fetchall()
                gloss = select_gloss(rows, token)
                if gloss:
                    return gloss
        return ""

    def lookup_reading(self, token: dict[str, Any]) -> str:
        row, rows = self.lookup_row_with_candidates(token)
        if row is None or not should_override_reading(row, rows, token):
            return ""
        return katakana_to_hiragana(str(row[4]))

    def lookup_sense_pos(self, token: dict[str, Any]) -> set[str]:
        row = self.lookup_row(token)
        if row is None:
            return set()
        return sense_pos_set(row)

    def lookup_row(self, token: dict[str, Any]) -> sqlite3.Row | tuple | None:
        row, _ = self.lookup_row_with_candidates(token)
        return row

    def lookup_row_with_candidates(
        self, token: dict[str, Any]
    ) -> tuple[sqlite3.Row | tuple | None, list[sqlite3.Row | tuple]]:
        with sqlite3.connect(self.path) as connection:
            columns = dictionary_columns(connection)
            select_columns = dictionary_select_columns(columns)
            for key in lookup_keys(token):
                rows = connection.execute(
                    f"""
                    SELECT {select_columns}
                    FROM dictionary_lookup
                    WHERE lookup_key = ?
                    """,
                    (key,),
                ).fetchall()
                row = select_row(rows, token)
                if row:
                    return row, rows
        return None, []


def default_translation_provider(base_dir: Path) -> TranslationProvider:
    dictionary_path = base_dir / "data" / "dictionary.sqlite"
    if dictionary_path.exists():
        return SqliteDictionaryProvider(dictionary_path)
    return NullTranslationProvider()


def dictionary_columns(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(dictionary_lookup)").fetchall()
    }


def dictionary_select_columns(columns: set[str]) -> str:
    if {"sense_index", "sense_pos"} <= columns:
        return "gloss, source, entry_id, headword, reading, priority, sense_index, sense_pos"
    return "gloss, source, entry_id, headword, reading, priority, 0, ''"


def lookup_keys(token: dict[str, Any]) -> list[str]:
    canonical = str(token.get("canonical", ""))
    surface = str(token.get("surface", ""))
    hiragana = str(token.get("hiragana", ""))
    lemma = canonical.split("::", 1)[0]
    keys = [canonical, lemma, hiragana, surface]
    return list(dict.fromkeys(key for key in keys if key))


def select_gloss(rows: list[sqlite3.Row | tuple], token: dict[str, Any]) -> str:
    contextual = contextual_gloss(rows, token)
    if contextual:
        return contextual
    row = select_row(rows, token)
    return str(row[0]) if row else ""


def select_row(
    rows: list[sqlite3.Row | tuple], token: dict[str, Any]
) -> sqlite3.Row | tuple | None:
    if not rows:
        return None

    hiragana = str(token.get("hiragana", ""))
    katakana = hiragana_to_katakana(hiragana)
    pos2 = str(token.get("pos2", ""))
    token_headwords = exact_token_headwords(token)
    exact_headword_rows = [row for row in rows if str(row[3]) in token_headwords]
    exact_headword_gloss_counts = Counter(
        str(row[0]) for row in exact_headword_rows if has_kanji(str(row[3]))
    )

    def sort_key(row: sqlite3.Row | tuple) -> tuple[object, ...]:
        gloss = str(row[0])
        source = str(row[1])
        entry_id = str(row[2])
        headword = str(row[3])
        reading = str(row[4])
        priority = int(row[5])
        exact_headword = headword in token_headwords
        exact_reading = reading in {hiragana, katakana}
        return (
            0 if exact_headword else 1,
            0 if pos2 != "固有名詞" and source == "JMdict" else 1,
            priority,
            -exact_headword_gloss_counts[gloss] if exact_headword else 0,
            0 if exact_reading else 1,
            source,
            entry_id,
        )

    return sorted(rows, key=sort_key)[0]


def contextual_gloss(rows: list[sqlite3.Row | tuple], token: dict[str, Any]) -> str:
    compatible = context_sense_rows(rows, token)
    if not compatible:
        return ""
    selected = select_row(compatible, token)
    if selected is None:
        return ""
    selected_priority = int(selected[5])
    selected_source = str(selected[1])
    selected_headword = str(selected[3])
    selected_reading = str(selected[4])
    selected_pos = sense_pos_set(selected)
    merged = [
        row
        for row in compatible
        if int(row[5]) == selected_priority
        and str(row[1]) == selected_source
        and str(row[3]) == selected_headword
        and str(row[4]) == selected_reading
        and sense_pos_set(row) == selected_pos
    ]
    return merge_glosses(merged)


def context_sense_rows(
    rows: list[sqlite3.Row | tuple], token: dict[str, Any]
) -> list[sqlite3.Row | tuple]:
    if str(token.get("next_surface", "")) != "の":
        return []
    token_headwords = exact_token_headwords(token)
    pure_adnominal = [
        row
        for row in rows
        if str(row[3]) in token_headwords and sense_pos_is_pure_adnominal(row)
    ]
    if pure_adnominal:
        return pure_adnominal
    return [
        row
        for row in rows
        if str(row[3]) in token_headwords and "adj-no" in sense_pos_set(row)
    ]


def sense_pos_set(row: sqlite3.Row | tuple) -> set[str]:
    return {part for part in str(row[7]).split(",") if part}


def sense_pos_is_pure_adnominal(row: sqlite3.Row | tuple) -> bool:
    parts = sense_pos_set(row)
    return bool(parts) and "adj-no" in parts and parts <= {"adj-no", "adj-na"}


def merge_glosses(rows: list[sqlite3.Row | tuple]) -> str:
    glosses: list[str] = []
    for row in sorted(rows, key=lambda item: int(item[6])):
        for gloss in str(row[0]).split("; "):
            if gloss and gloss not in glosses:
                glosses.append(gloss)
    return "; ".join(glosses[:8])


def should_override_reading(
    row: sqlite3.Row | tuple, rows: list[sqlite3.Row | tuple], token: dict[str, Any]
) -> bool:
    selected_reading = katakana_to_hiragana(str(row[4]))
    current_reading = katakana_to_hiragana(str(token.get("hiragana", "")))
    headword = str(row[3])
    gloss = str(row[0])
    if not selected_reading or selected_reading == current_reading:
        return False
    if headword not in exact_token_headwords(token) or not has_kanji(headword):
        return False
    supporting_rows = [
        candidate
        for candidate in rows
        if str(candidate[3]) == headword and str(candidate[0]) == gloss
    ]
    supporting_readings = {
        katakana_to_hiragana(str(candidate[4]))
        for candidate in supporting_rows
        if str(candidate[4])
    }
    return len(supporting_readings) > 1


def exact_token_headwords(token: dict[str, Any]) -> set[str]:
    canonical = str(token.get("canonical", ""))
    surface = str(token.get("surface", ""))
    lemma = canonical.split("::", 1)[0]
    return {item for item in (surface, lemma) if item}


def has_kanji(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
