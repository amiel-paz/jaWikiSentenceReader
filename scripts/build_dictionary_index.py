from __future__ import annotations

import argparse
import json
import sqlite3
import zipfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://github.com/scriptin/jmdict-simplified/releases/download"
LATEST_RELEASE_API = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"


def main() -> int:
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build JMdict/JMnedict SQLite index.")
    parser.add_argument("--source-dir", type=Path, default=repo_dir / "data" / "dictionary_sources")
    parser.add_argument("--out", type=Path, default=repo_dir / "data" / "dictionary.sqlite")
    parser.add_argument(
        "--release-tag",
        default="latest",
        help="jmdict-simplified release tag, or 'latest' (default)",
    )
    args = parser.parse_args()

    release_tag = resolve_release_tag(args.release_tag)
    release_path = quote(release_tag, safe="")
    jmdict_url = f"{BASE_URL}/{release_path}/jmdict-eng-{release_tag}.json.zip"
    jmnedict_url = f"{BASE_URL}/{release_path}/jmnedict-all-{release_tag}.json.zip"
    args.source_dir.mkdir(parents=True, exist_ok=True)
    jmdict = ensure_download(
        args.source_dir / f"jmdict-eng-{release_tag}.zip", jmdict_url
    )
    jmnedict = ensure_download(
        args.source_dir / f"jmnedict-all-{release_tag}.zip", jmnedict_url
    )
    if args.out.exists():
        args.out.unlink()
    with sqlite3.connect(args.out) as connection:
        create_schema(connection)
        connection.executemany(
            "INSERT INTO dictionary_metadata(key, value) VALUES (?, ?)",
            [
                ("release_tag", release_tag),
                ("jmdict_url", jmdict_url),
                ("jmnedict_url", jmnedict_url),
            ],
        )
        insert_jmdict(connection, jmdict)
        insert_jmnedict(connection, jmnedict)
        connection.execute("CREATE INDEX dictionary_lookup_key_idx ON dictionary_lookup(lookup_key)")
        connection.commit()
    print(f"Wrote {args.out} from {release_tag}")
    return 0


def resolve_release_tag(value: str) -> str:
    if value != "latest":
        return value
    request = Request(
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "wiki-sentence-reader/0.1"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name", "")).strip()
    if not tag:
        raise RuntimeError("Could not determine the latest JMdict release tag.")
    return tag


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
        CREATE TABLE dictionary_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE dictionary_lookup (
            lookup_key TEXT NOT NULL,
            source TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            headword TEXT NOT NULL,
            reading TEXT NOT NULL,
            gloss TEXT NOT NULL,
            priority INTEGER NOT NULL,
            sense_index INTEGER NOT NULL,
            sense_pos TEXT NOT NULL
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
        for sense_index, sense in enumerate(entry.get("sense", []), start=1):
            gloss = jmdict_sense_gloss(sense)
            if not gloss:
                continue
            rows.extend(
                lookup_rows(
                    source="JMdict",
                    entry_id=str(entry["id"]),
                    headwords=headwords,
                    readings=readings,
                    gloss=gloss,
                    priority=0 if entry_is_common(entry) else 20,
                    sense_index=sense_index,
                    sense_pos=",".join(sense.get("partOfSpeech", [])),
                )
            )
    connection.executemany("INSERT INTO dictionary_lookup VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


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
                    sense_index=0,
                    sense_pos="",
                )
            )
    connection.executemany("INSERT INTO dictionary_lookup VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def load_zipped_json(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".json")]
        return json.loads(archive.read(names[0]).decode("utf-8"))


def lookup_rows(
    *,
    source: str,
    entry_id: str,
    headwords: list[str],
    readings: list[str],
    gloss: str,
    priority: int,
    sense_index: int,
    sense_pos: str,
) -> Iterable[tuple[str, str, str, str, str, str, int, int, str]]:
    for headword in headwords:
        for reading in readings or [""]:
            for key in lookup_keys(headword, reading):
                yield (key, source, entry_id, headword, reading, gloss, priority, sense_index, sense_pos)


def lookup_keys(headword: str, reading: str) -> list[str]:
    keys = [headword, reading, katakana_to_hiragana(reading)]
    return list(dict.fromkeys(key for key in keys if key))


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if 0x30A1 <= ord(char) <= 0x30F6 else char
        for char in text
    )


def jmdict_sense_gloss(sense: dict) -> str:
    glosses = []
    for gloss in sense.get("gloss", []):
        if gloss.get("lang") == "eng" and gloss.get("text"):
            glosses.append(str(gloss["text"]))
    return "; ".join(dict.fromkeys(glosses[:4]))


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
