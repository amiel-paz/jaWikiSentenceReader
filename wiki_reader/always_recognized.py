from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping


SUMMARY_FIELDS = (
    "canonical",
    "expression",
    "hiragana",
    "romaji",
    "translation",
    "article_title",
    "source_url",
)


class AlwaysRecognizedStore:
    """Persist the project-wide set of tokens suppressed from Anki."""

    def __init__(self, path: Path):
        self.path = path

    def payload(self) -> dict[str, Any]:
        tokens = self._load_tokens()
        return {
            "token_ids": sorted(tokens),
            "tokens": [tokens[token_id] for token_id in sorted(tokens)],
        }

    def token_ids(self) -> set[str]:
        return set(self._load_tokens())

    def tokens(self) -> list[dict[str, str]]:
        payload = self.payload()
        return list(payload["tokens"])

    def set_cards(
        self,
        cards: Iterable[Mapping[str, Any]],
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        tokens = self._load_tokens()
        for card in cards:
            token_id = str(card.get("canonical", "")).strip()
            if not token_id:
                raise ValueError("Each always-recognized token requires a canonical ID.")
            if enabled:
                tokens[token_id] = summary_token(card)
            else:
                tokens.pop(token_id, None)
        self._write_tokens(tokens)
        return self.payload()

    def set_token_ids(
        self, token_ids: Iterable[Any], *, enabled: bool
    ) -> dict[str, Any]:
        tokens = self._load_tokens()
        for value in token_ids:
            token_id = str(value).strip()
            if not token_id:
                raise ValueError("Each always-recognized token requires a canonical ID.")
            if enabled:
                tokens.setdefault(token_id, summary_token({"canonical": token_id}))
            else:
                tokens.pop(token_id, None)
        self._write_tokens(tokens)
        return self.payload()

    def _load_tokens(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("The always-recognized vocabulary file is invalid.") from error

        raw_tokens = payload.get("tokens", {}) if isinstance(payload, dict) else {}
        if isinstance(raw_tokens, list):
            raw_tokens = {
                str(item.get("canonical", "")): item
                for item in raw_tokens
                if isinstance(item, dict)
            }
        if not isinstance(raw_tokens, dict):
            raw_tokens = {}

        tokens: dict[str, dict[str, str]] = {}
        for token_id, card in raw_tokens.items():
            canonical = str(token_id).strip()
            if not canonical or not isinstance(card, dict):
                continue
            tokens[canonical] = summary_token({**card, "canonical": canonical})

        # Accept the roleplay app's token_ids-only shape as a simple migration path.
        raw_ids = payload.get("token_ids", []) if isinstance(payload, dict) else []
        if isinstance(raw_ids, list):
            for value in raw_ids:
                token_id = str(value).strip()
                if token_id:
                    tokens.setdefault(token_id, summary_token({"canonical": token_id}))
        return tokens

    def _write_tokens(self, tokens: Mapping[str, Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "token_ids": sorted(tokens),
            "tokens": {
                token_id: summary_token(card)
                for token_id, card in sorted(tokens.items())
            },
        }
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, self.path)


def summary_token(card: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(card.get(field, "")).strip() for field in SUMMARY_FIELDS}


def merge_always_recognized_summary(
    summary: dict[str, Any],
    always_tokens: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    by_token = {
        str(token.get("token_id", "")): token
        for token in summary.get("tokens", [])
        if str(token.get("token_id", ""))
    }
    active_ids: set[str] = set()
    for card in always_tokens:
        token_id = str(card.get("canonical", "")).strip()
        if not token_id:
            continue
        active_ids.add(token_id)
        token = by_token.get(token_id)
        if token is None:
            token = {
                "token_id": token_id,
                "expression": str(card.get("expression", ""))
                or token_id.split("::", 1)[0],
                "hiragana": str(card.get("hiragana", "")),
                "romaji": str(card.get("romaji", "")),
                "translation": str(card.get("translation", "")),
                "recognized_count": 0,
                "unrecognized_count": 0,
                "always_count": 0,
                "difference": 0,
                "sessions": [],
                "session_count": 0,
            }
            summary.setdefault("tokens", []).append(token)
            by_token[token_id] = token
        for field in ("expression", "hiragana", "romaji", "translation"):
            if card.get(field):
                token[field] = str(card[field])
        token["always_recognized"] = True
        token["always_count"] = max(1, int(token.get("always_count", 0)))

    for token_id, token in by_token.items():
        token.setdefault("always_recognized", token_id in active_ids)
        if token_id not in active_ids:
            token["always_recognized"] = False
    summary["token_count"] = len(by_token)
    return summary
