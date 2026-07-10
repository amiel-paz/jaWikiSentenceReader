from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .token_utils import base_kana, get_tagger, katakana_to_hiragana, token_node_is_lexical


API_URL = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = "wiki-sentence-reader/0.1 (local prototype)"
KANA_RE = re.compile(r"^[ぁ-ゖァ-ヺー・\s]+$")
PAREN_RE = re.compile(r"([一-龯々〆ヵヶぁ-ゖァ-ヺー・]+)（([ぁ-ゖァ-ヺー・\s]+)[、）]")


@dataclass
class WikimediaReadingProvider:
    cache_path: Path
    disabled: bool = False

    def __post_init__(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS wikimedia_reading_cache (
                    term TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def lookup(self, term: str) -> dict[str, str] | None:
        term = term.strip()
        if len(term) < 2:
            return None
        if self.cache_has(term):
            return self.cached(term)
        if self.disabled:
            return None
        result = self.fetch(term)
        self.store(term, result)
        return result

    def cached(self, term: str) -> dict[str, str] | None:
        with sqlite3.connect(self.cache_path) as connection:
            row = connection.execute(
                "SELECT payload FROM wikimedia_reading_cache WHERE term = ?", (term,)
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        return payload or None

    def cache_has(self, term: str) -> bool:
        with sqlite3.connect(self.cache_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM wikimedia_reading_cache WHERE term = ?", (term,)
            ).fetchone()
        return row is not None

    def store(self, term: str, payload: dict[str, str] | None) -> None:
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO wikimedia_reading_cache(term, payload)
                VALUES (?, ?)
                """,
                (term, json.dumps(payload or {}, ensure_ascii=False)),
            )

    def fetch(self, term: str) -> dict[str, str] | None:
        dictionary_path = self.cache_path.parent / "dictionary.sqlite"
        for page in self.fetch_exact(term):
            reading = extract_reading_for_term(term, page, dictionary_path)
            if reading is not None:
                return reading
        for page in self.fetch_prefix(term):
            reading = extract_reading_for_term(term, page, dictionary_path)
            if reading is not None:
                return reading
        return None

    def fetch_exact(self, term: str) -> list[dict[str, Any]]:
        return self.fetch_query(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "redirects": "1",
                "titles": term,
                "prop": "extracts|info|pageprops",
                "exintro": "1",
                "explaintext": "1",
                "exchars": "700",
                "inprop": "url",
                "ppprop": "wikibase_item",
            }
        )

    def fetch_prefix(self, term: str) -> list[dict[str, Any]]:
        return self.fetch_query(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "prefixsearch",
                "gpssearch": term,
                "gpsnamespace": "0",
                "gpslimit": "5",
                "prop": "extracts|info|pageprops",
                "exintro": "1",
                "explaintext": "1",
                "exchars": "700",
                "inprop": "url",
                "ppprop": "wikibase_item",
            }
        )

    def fetch_query(self, query: dict[str, str]) -> list[dict[str, Any]]:
        request = Request(
            f"{API_URL}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError):
            self.disabled = True
            return []
        return [
            page
            for page in payload.get("query", {}).get("pages", [])
            if not page.get("missing")
        ]


def default_reading_provider(base_dir: Path) -> WikimediaReadingProvider:
    return WikimediaReadingProvider(base_dir / "data" / "wikimedia_reading_cache.sqlite")


def extract_reading_for_term(
    term: str, page: dict[str, Any], dictionary_path: Path | None = None
) -> dict[str, str] | None:
    title = str(page.get("title", ""))
    extract = str(page.get("extract", ""))
    for written, reading in parenthetical_pairs(extract):
        resolved = reading_for_written_prefix(term, written, reading, dictionary_path)
        if resolved is None:
            continue
        return {
            "hiragana": resolved,
            "source": "jawiki",
            "source_title": title,
            "source_url": str(page.get("canonicalurl", "")),
            "source_id": str(page.get("pageprops", {}).get("wikibase_item", "")),
        }
    return None


def parenthetical_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in PAREN_RE.finditer(text):
        written = match.group(1).strip()
        reading = re.sub(r"[\s・]", "", katakana_to_hiragana(match.group(2)))
        if written and reading and KANA_RE.fullmatch(match.group(2)):
            pairs.append((written, reading))
    return pairs


def reading_for_written_prefix(
    term: str, written: str, reading: str, dictionary_path: Path | None = None
) -> str | None:
    if written == term:
        return reading
    if not written.startswith(term):
        return None
    suffix = written[len(term) :]
    for suffix_reading in possible_readings_for_surface(suffix, dictionary_path):
        if suffix_reading and reading.endswith(suffix_reading):
            return reading[: -len(suffix_reading)]
    return None


def possible_readings_for_surface(
    surface: str, dictionary_path: Path | None = None
) -> list[str]:
    readings: list[str] = []
    if dictionary_path is not None and dictionary_path.exists():
        with sqlite3.connect(dictionary_path) as connection:
            rows = connection.execute(
                """
                SELECT reading
                FROM dictionary_lookup
                WHERE lookup_key = ? OR headword = ?
                ORDER BY priority ASC, source ASC, entry_id ASC
                LIMIT 20
                """,
                (surface, surface),
            ).fetchall()
        for row in rows:
            reading = re.sub(r"[\s・]", "", katakana_to_hiragana(str(row[0])))
            if reading and KANA_RE.fullmatch(reading):
                readings.append(reading)
    fallback = reading_for_surface(surface)
    if fallback:
        readings.append(fallback)
    return sorted(set(readings), key=len, reverse=True)


def reading_for_surface(surface: str) -> str:
    if not surface:
        return ""
    parts: list[str] = []
    for node in get_tagger()(surface):
        if not token_node_is_lexical(node):
            continue
        kana = katakana_to_hiragana(base_kana(node))
        if not kana:
            return ""
        parts.append(kana)
    return "".join(parts)
