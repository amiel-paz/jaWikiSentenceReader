from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence

from .private_articles import PRIVATE_ARTICLE_KEY_RE, load_private_article


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def main(argv: Sequence[str] | None = None) -> int:
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Stage and finalize a downloaded article for private local reading."
    )
    parser.add_argument("--base-dir", type=Path, default=repo_dir, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    stage = commands.add_parser("stage", help="extract a private draft for manual review")
    stage.add_argument("source", type=Path)
    stage.add_argument("--key", required=True)
    stage.add_argument("--title", required=True)
    stage.add_argument("--url", required=True)
    stage.add_argument(
        "--pages",
        help="1-based PDF pages such as 1-4,7 (all pages by default)",
    )
    stage.add_argument("--start-marker", help="discard text through this exact marker")
    stage.add_argument("--end-marker", help="discard this marker and everything after it")
    stage.add_argument("--force", action="store_true")

    finalize = commands.add_parser(
        "finalize", help="validate a reviewed draft and make it reader-ready"
    )
    finalize.add_argument("key")
    finalize.add_argument(
        "--reviewed",
        action="store_true",
        help="confirm article.txt contains only the intended article body",
    )
    finalize.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "stage":
        draft = stage_article(
            source=args.source,
            key=args.key,
            title=args.title,
            url=args.url,
            base_dir=args.base_dir,
            pages=args.pages,
            start_marker=args.start_marker,
            end_marker=args.end_marker,
            force=args.force,
        )
        print(f"Review and trim the private draft: {draft}")
        print(f"Then run: ja-reader-import finalize {args.key} --reviewed")
        return 0
    if not args.reviewed:
        parser.error("finalize requires --reviewed after article.txt has been checked")
    article = finalize_article(args.key, base_dir=args.base_dir, force=args.force)
    print(f"Private article ready: {article}")
    print(f"Open: http://127.0.0.1:5001/?article=private%3A{args.key}")
    return 0


def stage_article(
    *,
    source: Path,
    key: str,
    title: str,
    url: str,
    base_dir: Path,
    pages: str | None = None,
    start_marker: str | None = None,
    end_marker: str | None = None,
    force: bool = False,
) -> Path:
    key = validate_key(key)
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Downloaded article file not found: {source}")
    if not title.strip() or not url.strip():
        raise ValueError("A non-empty article title and source URL are required.")

    text = extract_source_text(source, pages=pages)
    text = select_marked_body(text, start_marker=start_marker, end_marker=end_marker)
    text = normalize_article_text(text)
    if not text:
        raise ValueError("The selected source produced no article text.")

    stage_dir = base_dir / "data" / "private" / "imports" / key
    draft_path = stage_dir / "article.txt"
    metadata_path = stage_dir / "metadata.json"
    if (draft_path.exists() or metadata_path.exists()) and not force:
        raise ValueError(f"A staged import already exists for {key}; use --force to replace it.")
    stage_dir.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(text + "\n", encoding="utf-8")
    metadata = {
        "key": key,
        "title": title.strip(),
        "canonicalurl": url.strip(),
        "source_name": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_modified": datetime.fromtimestamp(
            source.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
        "pages": pages or "all",
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return draft_path


def finalize_article(key: str, *, base_dir: Path, force: bool = False) -> Path:
    key = validate_key(key)
    stage_dir = base_dir / "data" / "private" / "imports" / key
    draft_path = stage_dir / "article.txt"
    metadata_path = stage_dir / "metadata.json"
    if not draft_path.is_file() or not metadata_path.is_file():
        raise ValueError(f"No staged import exists for {key}.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    text = normalize_article_text(draft_path.read_text(encoding="utf-8"))
    if not text:
        raise ValueError("The reviewed article draft is empty.")

    destination = base_dir / "data" / "private" / "articles" / f"{key}.json"
    if destination.exists() and not force:
        raise ValueError(f"Private article {key} already exists; use --force to replace it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": str(metadata.get("title", "")).strip(),
        "canonicalurl": str(metadata.get("canonicalurl", "")).strip(),
        "revision_timestamp": str(metadata.get("source_modified", "")).strip(),
        "text": text,
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        load_private_article(f"private:{key}", base_dir=base_dir)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def extract_source_text(source: Path, *, pages: str | None = None) -> str:
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:  # pragma: no cover - dependency is declared
            raise RuntimeError("PDF import requires the pypdf package.") from error
        reader = PdfReader(str(source))
        indexes = parse_page_spec(pages, len(reader.pages)) if pages else range(len(reader.pages))
        return "\n\n".join(reader.pages[index].extract_text() or "" for index in indexes)
    if pages:
        raise ValueError("--pages can only be used with a PDF source.")
    raw = source.read_text(encoding="utf-8")
    if suffix in {".html", ".htm"}:
        parser = _VisibleTextParser()
        parser.feed(raw)
        return parser.text()
    return raw


def parse_page_spec(value: str, page_count: int) -> list[int]:
    selected: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"Invalid PDF page range {part!r}; file has {page_count} page(s).")
        selected.extend(range(start - 1, end))
    if not selected:
        raise ValueError("The PDF page selection is empty.")
    return list(dict.fromkeys(selected))


def select_marked_body(
    text: str, *, start_marker: str | None, end_marker: str | None
) -> str:
    if start_marker:
        position = text.find(start_marker)
        if position < 0:
            raise ValueError(f"Start marker was not found: {start_marker}")
        text = text[position + len(start_marker) :]
    if end_marker:
        position = text.find(end_marker)
        if position < 0:
            raise ValueError(f"End marker was not found: {end_marker}")
        text = text[:position]
    return text


def normalize_article_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.replace("\u00a0", " ").split()) for line in text.split("\n")]
    normalized: list[str] = []
    for line in lines:
        if not line and normalized and not normalized[-1]:
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def validate_key(value: str) -> str:
    key = value.strip().lower()
    if not PRIVATE_ARTICLE_KEY_RE.fullmatch(key):
        raise ValueError(
            "Private article keys may contain lowercase letters, numbers, hyphens, and underscores."
        )
    return key


if __name__ == "__main__":
    raise SystemExit(main())
