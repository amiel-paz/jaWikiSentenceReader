from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


API_URL = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = "wiki-sentence-reader/0.1 (local prototype)"
SENTENCE_RE = re.compile(r".+?[。！？](?=\s*|$)", re.S)


def fetch_article_from_input(value: str) -> dict[str, Any]:
    title = title_from_input(value)
    payload = fetch_article(title)
    page = payload["query"]["pages"][0]
    text = str(page.get("extract", "")).strip()
    return {
        "title": page.get("title", title),
        "canonicalurl": page.get("canonicalurl", ""),
        "revision_id": page.get("revisions", [{}])[0].get("revid"),
        "revision_timestamp": page.get("revisions", [{}])[0].get("timestamp"),
        "sentences": first_sentences(text, limit=80),
    }


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
        "exsectionformat": "plain",
        "inprop": "url",
        "rvprop": "ids|timestamp",
    }
    request = Request(
        f"{API_URL}?{urlencode(query)}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise ValueError(f"Wikipedia page not found: {title}")
    return payload


def first_sentences(text: str, *, limit: int) -> list[str]:
    sentences: list[str] = []
    for match in SENTENCE_RE.finditer(text.strip()):
        sentence = re.sub(r"\s+", " ", match.group(0)).strip()
        if sentence:
            sentences.append(sentence)
        if len(sentences) >= limit:
            break
    return sentences
