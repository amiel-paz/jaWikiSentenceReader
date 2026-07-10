from __future__ import annotations

import argparse
import json
import sqlite3
import zipfile
from collections.abc import Iterable
from pathlib import Path
from urllib.request import Request, urlopen


RELEASE_TAG = "3.6.2+20260706150322"
BASE_URL = "https://github.com/scriptin/jmdict-simplified/releases/download"
JMDICT_URL = f"{BASE_URL}/3.6.2%2B20260706150322/jmdict-eng-{RELEASE_TAG}.json.zip"
JMNEDICT_URL = f"{BASE_URL}/3.6.2%2B20260706150322/jmnedict-all-{RELEASE_TAG}.json.zip"


def main() -> int:
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build JMdict/JMnedict SQLite index.")
    parser.add_argument("--source-dir", type=Path, default=repo_dir / "data" / "dictionary_sources")
    parser.add_argument("--out", type=Path, default=repo_dir / "data" / "dictionary.sqlite")
    args = parser.parse_args()

    args.source_dir.mkdir(parents=True, exist_ok=True)
    jmdict = ensure_download(args.source_dir / "jmdict-eng.zip", JMDICT_URL)
    jmnedict = ensure_download(args.source_dir / "jmnedict-all.zip", JMNEDICT_URL)
    if args.out.exists():
        args.out.unlink()
    with sqlite3.connect(args.out) as connection:
        create_schema(connection)
        insert_jmdict(connection, jmdict)
        insert_jmnedict(connection, jmnedict)
        connection.execute("CREATE INDEX dictionary_lookup_key_idx ON dictionary_lookup(lookup_key)")
        connection.commit()
    print(f"Wrote {args.out}")
    return 0


def ensure_download(path: Path, url: str) -> Path:
    if path.exists():
        return path
    request = Request(url, headers={"User-Agent": "wiki-sentence-reader/0.1"})
    with urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    return path


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE dictionary_lookup (
            lookup_key TEXT NOT NULL,
            source TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            headword TEXT NOT NULL,
            reading TEXT NOT NULL,
            gloss TEXT NOT NULL,
            priority INTEGER NOT NULL
        )
        """
    )


def insert_jmdict(connection: sqlite3.Connection, archive_path: Path) -> None:
    payload = load_zipped_json(archive_path)
    rows = []
    for entry in payload["words"]:
        headwords = [item["text"] for item in entry.get("kanji", [])] or [
            item["text"] for item in entry.get("kana", [])
        ]
        readings = [item["text"] for item in entry.get("kana", [])]
        gloss = jmdict_gloss(entry)
        if gloss:
            rows.extend(
                lookup_rows(
                    source="JMdict",
                    entry_id=str(entry["id"]),
                    headwords=headwords,
                    readings=readings,
                    gloss=gloss,
                    priority=0 if entry_is_common(entry) else 20,
                )
            )
    connection.executemany("INSERT INTO dictionary_lookup VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def insert_jmnedict(connection: sqlite3.Connection, archive_path: Path) -> None:
    payload = load_zipped_json(archive_path)
    rows = []
    for entry in payload["words"]:
        headwords = [item["text"] for item in entry.get("kanji", [])] or [
            item["text"] for item in entry.get("kana", [])
        ]
        readings = [item["text"] for item in entry.get("kana", [])]
        gloss = jmnedict_gloss(entry)
        if gloss:
            rows.extend(
                lookup_rows(
                    source="JMnedict",
                    entry_id=str(entry["id"]),
                    headwords=headwords,
                    readings=readings,
                    gloss=gloss,
                    priority=10,
                )
            )
    connection.executemany("INSERT INTO dictionary_lookup VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def load_zipped_json(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".json")]
        return json.loads(archive.read(names[0]).decode("utf-8"))


def lookup_rows(
    *, source: str, entry_id: str, headwords: list[str], readings: list[str], gloss: str, priority: int
) -> Iterable[tuple[str, str, str, str, str, str, int]]:
    for headword in headwords:
        for reading in readings or [""]:
            for key in lookup_keys(headword, reading):
                yield (key, source, entry_id, headword, reading, gloss, priority)


def lookup_keys(headword: str, reading: str) -> list[str]:
    keys = [headword, reading, katakana_to_hiragana(reading)]
    return list(dict.fromkeys(key for key in keys if key))


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if 0x30A1 <= ord(char) <= 0x30F6 else char
        for char in text
    )


def jmdict_gloss(entry: dict) -> str:
    glosses = []
    for sense in entry.get("sense", []):
        for gloss in sense.get("gloss", []):
            if gloss.get("lang") == "eng" and gloss.get("text"):
                glosses.append(str(gloss["text"]))
        if glosses:
            break
    return "; ".join(dict.fromkeys(glosses[:3]))


def jmnedict_gloss(entry: dict) -> str:
    glosses = []
    for group in entry.get("translation", []):
        for item in group.get("translation", []):
            if item.get("lang") == "eng" and item.get("text"):
                glosses.append(str(item["text"]))
        if glosses:
            break
    return "; ".join(dict.fromkeys(glosses[:3]))


def entry_is_common(entry: dict) -> bool:
    return any(item.get("common") for item in entry.get("kanji", [])) or any(
        item.get("common") for item in entry.get("kana", [])
    )


if __name__ == "__main__":
    raise SystemExit(main())
