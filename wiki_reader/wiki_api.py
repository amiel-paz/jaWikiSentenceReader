from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


API_URL = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = "wiki-sentence-reader/0.1 (local prototype)"
SENTENCE_RE = re.compile(r".+?[。！？]")
HEADING_RE = re.compile(r"^(=+)\s*(.*?)\s*\1$")


class ArticleRateLimitError(RuntimeError):
    pass


def fetch_article_from_input(value: str, *, cache_dir: Path | None = None) -> dict[str, Any]:
    title = title_from_input(value)
    cache = ArticleCache(cache_dir / "article_cache.sqlite") if cache_dir else None
    if cache is not None:
        cached = cache.get(title)
        if cached is not None:
            return cached
    payload = fetch_article(title)
    page = payload["query"]["pages"][0]
    text = str(page.get("extract", "")).strip()
    article = {
        "title": page.get("title", title),
        "canonicalurl": page.get("canonicalurl", ""),
        "revision_id": page.get("revisions", [{}])[0].get("revid"),
        "revision_timestamp": page.get("revisions", [{}])[0].get("timestamp"),
        "sentences": sentence_entries(text),
    }
    if cache is not None:
        cache.set(title, article)
        actual_title = str(article.get("title", ""))
        if actual_title and actual_title != title:
            cache.set(actual_title, article)
    return article


class ArticleCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS article_cache (
                    title TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def get(self, title: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload FROM article_cache WHERE title = ?", (title,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row[0]))

    def set(self, title: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO article_cache(title, payload)
                VALUES (?, ?)
                """,
                (title, json.dumps(payload, ensure_ascii=False)),
            )


def title_from_input(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a Japanese Wikipedia article URL or title.")
    parsed = urlparse(value)
    if parsed.netloc:
        if "wikipedia.org" not in parsed.netloc:
            raise ValueError("Only Wikipedia article URLs are supported right now.")
        if parsed.path.startswith("/wiki/"):
            return unquote(parsed.path.removeprefix("/wiki/")).replace("_", " ")
        query = parse_qs(parsed.query)
        if "title" in query and query["title"]:
            return query["title"][0].replace("_", " ")
        raise ValueError("Could not find a page title in that Wikipedia URL.")
    return value


def fetch_article(title: str) -> dict[str, Any]:
    query = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "titles": title,
        "prop": "extracts|info|revisions",
        "explaintext": "1",
        "exsectionformat": "wiki",
        "inprop": "url",
        "rvprop": "ids|timestamp",
    }
    request = Request(
        f"{API_URL}?{urlencode(query)}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            raise ArticleRateLimitError(
                "Wikipedia rate-limited this request. Try again shortly, or reload a cached article."
            ) from error
        raise
    pages = payload.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise ValueError(f"Wikipedia page not found: {title}")
    return payload


def first_sentences(text: str, *, limit: int) -> list[str]:
    return [entry["text"] for entry in first_sentence_entries(text, limit=limit)]


def first_sentence_entries(text: str, *, limit: int) -> list[dict[str, Any]]:
    return sentence_entries(text, limit=limit)


def sentence_entries(text: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    pending_headings: list[str] = []
    for block in text.splitlines():
        block = block.strip()
        if not block:
            continue
        heading = heading_match(block)
        if heading is not None:
            depth, title = heading
            heading_stack = heading_stack[:depth]
            heading_stack.append(title)
            pending_headings = list(heading_stack)
            continue
        for match in SENTENCE_RE.finditer(block):
            sentence = re.sub(r"\s+", " ", match.group(0)).strip()
            if sentence:
                sentences.append({"text": sentence, "headings": pending_headings})
                pending_headings = []
            if limit is not None and len(sentences) >= limit:
                return sentences
    return sentences


def heading_match(line: str) -> tuple[int, str] | None:
    match = HEADING_RE.fullmatch(line)
    if match is None:
        return None
    title = match.group(2).strip()
    if not title:
        return None
    depth = max(0, len(match.group(1)) - 2)
    return depth, title
