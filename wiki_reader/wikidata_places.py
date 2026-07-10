from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://ja.wikipedia.org/w/api.php"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "wiki-sentence-reader/0.1 (local prototype)"
ADMIN_SUFFIXES = {"国", "都", "道", "府", "県", "市", "区", "町", "村"}
PLACE_SURFACE_RE = re.compile(r"^[一-龯ァ-ヺー]+$")
KANJI_SURFACE_RE = re.compile(r"^[一-龯]+$")
KATAKANA_SURFACE_RE = re.compile(r"^[ァ-ヺー]+$")


@dataclass
class WikidataPlaceProvider:
    cache_path: Path
    disabled: bool = False
    persist_lookups: bool = False
    transient_cache: dict[str, dict[str, str] | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS wikidata_place_cache (
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
            cached = self.cached(term)
            if cached is not None and needs_english_enrichment(cached) and not self.disabled:
                enriched = self.english_entities([str(cached.get("id", ""))])
                cached.update(enriched.get(str(cached.get("id", "")), {}))
                self.cache_result(term, cached)
            return cached
        if self.disabled:
            return None
        return self.fetch(term)

    def prefetch(self, terms: list[str]) -> None:
        if self.disabled:
            return
        missing = [
            term
            for term in dict.fromkeys(term.strip() for term in terms if len(term.strip()) >= 2)
            if self.cache_has(term) is False
        ]
        for chunk in chunks(missing, 50):
            self.fetch_many(chunk)

    def cached(self, term: str) -> dict[str, str] | None:
        if term in self.transient_cache:
            return self.transient_cache[term]
        with sqlite3.connect(self.cache_path) as connection:
            row = connection.execute(
                "SELECT payload FROM wikidata_place_cache WHERE term = ?", (term,)
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        return payload or None

    def cache_has(self, term: str) -> bool:
        if term in self.transient_cache:
            return True
        with sqlite3.connect(self.cache_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM wikidata_place_cache WHERE term = ?", (term,)
            ).fetchone()
        return row is not None

    def store(self, term: str, payload: dict[str, str] | None) -> None:
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO wikidata_place_cache(term, payload)
                VALUES (?, ?)
                """,
                (term, json.dumps(payload or {}, ensure_ascii=False)),
            )

    def cache_result(self, term: str, payload: dict[str, str] | None) -> None:
        if self.persist_lookups:
            self.store(term, payload)
        else:
            self.transient_cache[term] = payload

    def persist_places(self, places: list[dict[str, Any]]) -> int:
        count = 0
        for place in places:
            surface = str(place.get("surface") or place.get("label") or "").strip()
            qid = str(place.get("id") or "").strip()
            if len(surface) < 2 or not qid:
                continue
            self.store(
                surface,
                {
                    "id": qid,
                    "label": str(place.get("label") or surface),
                    "description": str(place.get("description") or ""),
                    "english_label": str(place.get("english_label") or ""),
                    "english_description": str(place.get("english_description") or ""),
                    "url": str(place.get("url") or ""),
                },
            )
            count += 1
        return count

    def fetch(self, term: str) -> dict[str, str] | None:
        self.fetch_many([term])
        return self.cached(term)

    def fetch_many(self, terms: list[str]) -> None:
        if not terms:
            return
        query = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "titles": "|".join(terms),
            "prop": "pageprops|info|description",
            "inprop": "url",
            "ppprop": "wikibase_item",
        }
        request = Request(
            f"{API_URL}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError):
            self.disabled = True
            return
        pages = payload.get("query", {}).get("pages", [])
        by_title = {str(page.get("title", "")): page for page in pages}
        qids = [
            str(page.get("pageprops", {}).get("wikibase_item", ""))
            for page in pages
            if not page.get("missing")
        ]
        english_by_qid = self.english_entities(qids)
        for term in terms:
            page = by_title.get(term)
            if page is None or page.get("missing"):
                self.cache_result(term, None)
                continue
            qid = str(page.get("pageprops", {}).get("wikibase_item", ""))
            if not qid:
                self.cache_result(term, None)
                continue
            self.cache_result(
                term,
                {
                    "id": qid,
                    "label": str(page.get("title", "")),
                    "description": str(page.get("description", "")),
                    "url": str(page.get("canonicalurl", "")),
                    **english_by_qid.get(qid, {}),
                },
            )

    def english_entities(self, qids: list[str]) -> dict[str, dict[str, str]]:
        ids = [qid for qid in dict.fromkeys(qids) if qid]
        if not ids:
            return {}
        query = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(ids),
            "props": "labels|descriptions",
            "languages": "en",
            "languagefallback": "1",
        }
        request = Request(
            f"{WIKIDATA_API_URL}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError):
            return {}
        results: dict[str, dict[str, str]] = {}
        for qid, entity in payload.get("entities", {}).items():
            label = entity.get("labels", {}).get("en", {}).get("value", "")
            description = entity.get("descriptions", {}).get("en", {}).get("value", "")
            values = {}
            if label:
                values["english_label"] = str(label)
            if description:
                values["english_description"] = str(description)
            if values:
                results[str(qid)] = values
        return results


def default_place_provider(base_dir: Path) -> WikidataPlaceProvider:
    return WikidataPlaceProvider(base_dir / "data" / "wikidata_place_cache.sqlite")


def detect_place_matches(
    tagged: list[Any], text: str, provider: WikidataPlaceProvider
) -> list[dict[str, Any]]:
    candidates = place_candidates(tagged, text)
    provider.prefetch([str(candidate["surface"]) for candidate in candidates])
    hits: list[dict[str, Any]] = []
    for candidate in candidates:
        entity = provider.lookup(str(candidate["surface"]))
        if entity is None:
            continue
        hits.append({**candidate, "entity": entity})
    return select_non_overlapping_place_matches(hits)


def place_candidates(tagged: list[Any], text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for start in range(len(tagged)):
        if not candidate_node(tagged[start].node):
            continue
        for end in range(start + 1, min(len(tagged), start + 6) + 1):
            items = tagged[start:end]
            if not all(candidate_node(item.node) for item in items):
                break
            surface = text[items[0].start : items[-1].end]
            if not valid_place_surface(surface, items):
                continue
            candidates.append(
                {
                    "surface": surface,
                    "start": items[0].start,
                    "end": items[-1].end,
                    "start_index": start,
                    "end_index": end,
                    "score": place_candidate_score(surface, items),
                }
            )
    candidates.sort(key=lambda item: (item["start"], -item["score"], -len(item["surface"])))
    return candidates


def select_non_overlapping_place_matches(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for hit in sorted(hits, key=lambda item: (item["start"], -item["score"], -len(item["surface"]))):
        indexes = set(range(int(hit["start_index"]), int(hit["end_index"])))
        if indexes & occupied:
            continue
        selected.append(hit)
        occupied.update(indexes)
    return selected


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def needs_english_enrichment(payload: dict[str, str]) -> bool:
    return bool(payload.get("id")) and not bool(payload.get("english_label"))


def candidate_node(node) -> bool:
    pos1 = getattr(node.feature, "pos1", "")
    if pos1 not in {"名詞", "接尾辞", "接頭辞", "副詞"}:
        return False
    if node.surface in ADMIN_SUFFIXES:
        return True
    return bool(KANJI_SURFACE_RE.fullmatch(node.surface) or KATAKANA_SURFACE_RE.fullmatch(node.surface))


def valid_place_surface(surface: str, items: list[Any]) -> bool:
    if len(surface) < 2 or len(surface) > 12:
        return False
    if not PLACE_SURFACE_RE.fullmatch(surface):
        return False
    if surface.endswith(tuple(ADMIN_SUFFIXES)):
        return True
    return any(getattr(item.node.feature, "pos3", "") == "地名" for item in items)


def place_candidate_score(surface: str, items: list[Any]) -> int:
    suffix_count = sum(1 for item in items if item.node.surface in ADMIN_SUFFIXES)
    score = 100
    if surface.endswith(tuple(ADMIN_SUFFIXES)):
        score += 30
    if any(getattr(item.node.feature, "pos3", "") == "地名" for item in items):
        score += 20
    if suffix_count > 1:
        score -= 35 * (suffix_count - 1)
    return score


def overlapping_places(
    matches: list[dict[str, Any]], start: int, end: int
) -> list[dict[str, str]]:
    places: list[dict[str, str]] = []
    for match in matches:
        if start < int(match["end"]) and end > int(match["start"]):
            entity = match["entity"]
            places.append(
                {
                    "surface": str(match["surface"]),
                    "id": str(entity.get("id", "")),
                    "label": str(entity.get("label", "")),
                    "description": str(entity.get("description", "")),
                    "english_label": str(entity.get("english_label", "")),
                    "english_description": str(entity.get("english_description", "")),
                    "url": str(entity.get("url", "")),
                }
            )
    return places
