from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .wiki_api import sentence_entries


PRIVATE_ARTICLE_PREFIX = "private:"
PRIVATE_ARTICLE_KEY_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def is_private_article_input(value: str) -> bool:
    return value.strip().lower().startswith(PRIVATE_ARTICLE_PREFIX)


def load_private_article(value: str, *, base_dir: Path) -> dict[str, Any]:
    key = value.strip()[len(PRIVATE_ARTICLE_PREFIX) :].strip().lower()
    if not PRIVATE_ARTICLE_KEY_RE.fullmatch(key):
        raise ValueError("Private article keys may contain lowercase letters, numbers, hyphens, and underscores.")

    private_dir = (base_dir / "data" / "private" / "articles").resolve()
    path = (private_dir / f"{key}.json").resolve()
    if path.parent != private_dir:
        raise ValueError("Invalid private article key.")
    if not path.is_file():
        raise ValueError(f"Private article not found: {key}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Private article file must contain a JSON object.")
    title = str(payload.get("title", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not title or not text:
        raise ValueError("Private article file requires non-empty title and text fields.")

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
    article = {
        "title": title,
        "canonicalurl": str(payload.get("canonicalurl", "")).strip(),
        "revision_id": f"private-{content_hash}",
        "revision_timestamp": payload.get("revision_timestamp"),
        "sentences": sentence_entries(text),
    }
    if not article["sentences"]:
        raise ValueError("Private article does not contain any complete Japanese sentences.")
    return article
