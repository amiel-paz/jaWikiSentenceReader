from __future__ import annotations

import csv
import html
import io
import re
from typing import Any


DEFAULT_DECK = "Japanese::Sentence Reader"
MAX_CARDS_PER_EXPORT = 2_000
REQUIRED_FIELDS = ("canonical", "expression", "hiragana", "romaji", "translation")


def build_anki_tsv(cards: list[dict[str, Any]], *, deck: str = DEFAULT_DECK) -> str:
    if not cards:
        raise ValueError("No Anki cards were selected for export.")
    if len(cards) > MAX_CARDS_PER_EXPORT:
        raise ValueError(f"Anki exports are limited to {MAX_CARDS_PER_EXPORT} cards.")

    output = io.StringIO(newline="")
    output.write("#separator:Tab\n")
    output.write("#html:true\n")
    output.write("#notetype:Basic\n")
    output.write(f"#deck:{single_line(deck)}\n")
    output.write("#columns:Front\tBack\tTags\n")
    output.write("#tags column:3\n")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    seen: set[str] = set()
    for card in cards:
        normalized = validated_card(card)
        canonical = normalized["canonical"]
        if canonical in seen:
            continue
        seen.add(canonical)
        writer.writerow(
            [
                card_front(normalized),
                card_back(normalized),
                card_tags(normalized),
            ]
        )
    return output.getvalue()


def validated_card(card: dict[str, Any]) -> dict[str, str]:
    if not isinstance(card, dict):
        raise ValueError("Each Anki card must be an object.")
    normalized = {
        str(key): single_line(value) if key != "sentence" else str(value).strip()
        for key, value in card.items()
        if value is not None
    }
    missing = [field for field in REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValueError(
            f"Anki card {normalized.get('canonical', '<unknown>')} is missing: "
            + ", ".join(missing)
        )
    for key, value in normalized.items():
        if len(value) > 10_000:
            raise ValueError(f"Anki card field {key} is too long.")
    return normalized


def card_front(card: dict[str, str]) -> str:
    expression = html.escape(card["expression"])
    canonical = html.escape(card["canonical"])
    return (
        '<div style="font-size:2rem;text-align:center;font-family:serif">'
        f"{expression}</div>"
        f'<span style="display:none">{canonical}</span>'
    )


def card_back(card: dict[str, str]) -> str:
    values = [
        '<div style="font-size:1.35rem;font-weight:700">'
        f"{html.escape(card['hiragana'])}</div>",
        '<div style="margin-top:.2rem;color:#666">'
        f"{html.escape(card['romaji'])}</div>",
        '<div style="margin-top:1rem;font-size:1.1rem">'
        f"{html.escape(card['translation'])}</div>",
    ]
    surface = card.get("surface", "")
    if surface and surface != card["expression"]:
        values.append(
            '<div style="margin-top:.8rem;color:#666">Seen as: '
            f"{html.escape(surface)}</div>"
        )
    sentence = card.get("sentence", "")
    if sentence:
        values.append(
            '<div style="margin-top:1rem;padding-top:.8rem;border-top:1px solid #aaa">'
            f"{html.escape(sentence).replace(chr(10), '<br>')}</div>"
        )
    title = card.get("article_title", "")
    source_url = card.get("source_url", "")
    if title and source_url:
        values.append(
            '<div style="margin-top:.8rem;font-size:.8rem">Source: '
            f'<a href="{html.escape(source_url, quote=True)}">{html.escape(title)}</a></div>'
        )
    elif title:
        values.append(
            '<div style="margin-top:.8rem;font-size:.8rem">Source: '
            f"{html.escape(title)}</div>"
        )
    dictionary_source = card.get("dictionary_source", "")
    vocabulary_id = card.get("vocabulary_id", "")
    if dictionary_source or vocabulary_id:
        label = " · ".join(item for item in (dictionary_source, vocabulary_id) if item)
        values.append(
            '<div style="margin-top:.5rem;font-size:.7rem;color:#777">'
            f"{html.escape(label)}</div>"
        )
    return "".join(values)


def card_tags(card: dict[str, str]) -> str:
    pos = card["canonical"].split("::", 1)[1] if "::" in card["canonical"] else ""
    tags = ["ja_sentence_reader"]
    if pos:
        tags.append(f"pos_{safe_tag(pos)}")
    return " ".join(tags)


def safe_tag(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_\u3040-\u30ff\u4e00-\u9fff-]+", "_", value)


def single_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()
