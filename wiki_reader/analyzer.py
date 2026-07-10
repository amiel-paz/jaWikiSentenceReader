from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .phrase_matcher import detect_phrase_matches, overlapping_phrases, tagged_nodes
from .token_utils import (
    NUMERIC_RE,
    base_kana,
    canonical_token,
    get_tagger,
    kana_to_romaji,
    katakana_to_hiragana,
    token_node_is_lexical,
)
from .translation_provider import TranslationProvider, default_translation_provider
from .wikidata_places import (
    WikidataPlaceProvider,
    default_place_provider,
    detect_place_matches,
    overlapping_places,
)
from .wikimedia_readings import WikimediaReadingProvider, default_reading_provider


TRACKED_POS = {"名詞", "動詞", "形容詞", "形状詞", "副詞", "接続詞", "接頭辞", "代名詞"}
GRAMMAR_TOKEN_TRANSLATIONS = {
    ("助詞", "ほど"): "to the extent that; so much that; degree/extent",
}


def analyze_article(
    article: dict[str, Any],
    *,
    base_dir: Path,
    translation_provider: TranslationProvider | None = None,
    place_provider: WikidataPlaceProvider | None = None,
    reading_provider: WikimediaReadingProvider | None = None,
) -> dict[str, Any]:
    provider = translation_provider or default_translation_provider(base_dir)
    gazetteer = place_provider or default_place_provider(base_dir)
    readings = reading_provider or default_reading_provider(base_dir)
    return {
        **{key: article.get(key) for key in ("title", "canonicalurl", "revision_id", "revision_timestamp")},
        "sentences": [
            {
                "id": f"sentence-{index}",
                **analyze_sentence_with_cache(
                    sentence_entry,
                    translation_provider=provider,
                    place_provider=gazetteer,
                    reading_provider=readings,
                ),
            }
            for index, sentence_entry in enumerate(article["sentences"], start=1)
        ],
    }


def analyze_sentence_with_cache(
    sentence_entry: str | dict[str, Any],
    *,
    translation_provider: TranslationProvider,
    place_provider: WikidataPlaceProvider | None = None,
    reading_provider: WikimediaReadingProvider | None = None,
) -> dict[str, Any]:
    sentence, headings, heading_ranges = sentence_display_fields(sentence_entry)
    analysis_text, suppressed_spans = suppress_parenthetical_readings(
        sentence, translation_provider
    )
    rows = analyze_sentence(
        analysis_text,
        translation_provider,
        place_provider,
        reading_provider,
    )
    return {
        "display_text": sentence,
        "analysis_text": analysis_text,
        "headings": headings,
        "heading_ranges": heading_ranges,
        "suppressed_spans": suppressed_spans,
        "tokens": rows,
        "unique_sentence_cache": build_sentence_token_cache(rows),
    }


def sentence_display_fields(sentence_entry: str | dict[str, Any]) -> tuple[str, list[str], list[dict[str, int]]]:
    if isinstance(sentence_entry, str):
        return sentence_entry, [], []
    text = str(sentence_entry.get("text", ""))
    headings = [
        str(heading).strip()
        for heading in sentence_entry.get("headings", [])
        if str(heading).strip()
    ]
    if not headings:
        return text, [], []
    parts = [*headings, text]
    ranges: list[dict[str, int]] = []
    cursor = 0
    for heading in headings:
        ranges.append({"start": cursor, "end": cursor + len(heading)})
        cursor += len(heading) + 1
    return "\n".join(parts), headings, ranges


def analyze_sentence(
    sentence: str,
    translation_provider: TranslationProvider,
    place_provider: WikidataPlaceProvider | None = None,
    reading_provider: WikimediaReadingProvider | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tagged = tagged_nodes(sentence, get_tagger())
    phrase_matches = detect_phrase_matches(tagged, sentence)
    place_matches = (
        detect_place_matches(tagged, sentence, place_provider)
        if place_provider is not None
        else []
    )
    reading_matches = (
        detect_wikimedia_reading_matches(tagged, sentence, reading_provider)
        if reading_provider is not None
        else []
    )
    place_by_start = {
        int(match["start_index"]): match
        for match in place_matches
        if int(match["end_index"]) - int(match["start_index"]) > 1
    }
    reading_by_start = {
        int(match["start_index"]): match
        for match in reading_matches
        if int(match["end_index"]) - int(match["start_index"]) > 1
    }
    index = 0
    while index < len(tagged):
        item = tagged[index]
        node = item.node
        if not token_node_is_lexical(node) or NUMERIC_RE.fullmatch(node.surface):
            index += 1
            continue
        if index in place_by_start:
            match = place_by_start[index]
            rows.append(
                place_token(
                    tagged[int(match["start_index"]) : int(match["end_index"])],
                    match,
                    translation_provider,
                    phrase_matches,
                    place_matches,
                )
            )
            index = int(match["end_index"])
            continue
        if index in reading_by_start:
            match = reading_by_start[index]
            rows.append(
                wikimedia_reading_token(
                    tagged[int(match["start_index"]) : int(match["end_index"])],
                    match,
                    translation_provider,
                    phrase_matches,
                    place_matches,
                )
            )
            index = int(match["end_index"])
            continue
        te_iru_end = te_iru_chain_end_index(tagged, index)
        if te_iru_end is not None:
            rows.append(
                verb_chain_token(
                    tagged[index:te_iru_end],
                    sentence,
                    translation_provider,
                    phrase_matches,
                    place_matches,
                )
            )
            index = te_iru_end
            continue
        dictionary_compound_items = dictionary_noun_compound_items(
            tagged, index, translation_provider
        )
        if dictionary_compound_items is not None:
            rows.append(
                compound_token(
                    dictionary_compound_items,
                    translation_provider,
                    phrase_matches,
                    place_matches,
                )
            )
            index += len(dictionary_compound_items)
            continue
        if node_is_noun(node):
            compound_items = [item]
            next_index = index + 1
            while next_index < len(tagged) and node_is_nominal_suffix(tagged[next_index].node):
                compound_items.append(tagged[next_index])
                next_index += 1
            if len(compound_items) > 1:
                rows.append(
                    compound_token(
                        compound_items,
                        translation_provider,
                        phrase_matches,
                        place_matches,
                    )
                )
                index = next_index
                continue
        if node_is_nominal_suffix(node) and previous_significant_node_is_numeric(tagged, index):
            rows.append(token_row(item, translation_provider, phrase_matches, place_matches))
            index += 1
            continue
        if grammar_token_node(node):
            rows.append(token_row(item, translation_provider, phrase_matches, place_matches))
            index += 1
            continue
        pos1 = getattr(node.feature, "pos1", "") or "*"
        if pos1 not in TRACKED_POS:
            index += 1
            continue
        rows.append(token_row(item, translation_provider, phrase_matches, place_matches))
        index += 1
    return rows


def suppress_parenthetical_readings(
    sentence: str, translation_provider: TranslationProvider
) -> tuple[str, list[dict[str, Any]]]:
    analysis_parts: list[str] = []
    suppressed_spans: list[dict[str, Any]] = []
    last_end = 0
    for match in re.finditer(r"（([ぁ-ゖァ-ヺー\s]+)([、）])", sentence):
        open_paren_start = match.start()
        reading_start = match.start(1)
        delimiter_end = match.end(2)
        delimiter = match.group(2)
        reading_text = match.group(1)
        preceding_tokens = analyze_sentence(sentence[:open_paren_start], translation_provider)
        applies_to = matching_preceding_tokens(preceding_tokens, reading_text)
        if not applies_to:
            continue
        analysis_parts.append(sentence[last_end:open_paren_start])
        if delimiter == "、":
            analysis_parts.append("（")
        last_end = delimiter_end
        suppressed_spans.append(
            {
                "text": sentence[reading_start:delimiter_end],
                "reading": reading_text.strip(),
                "start": reading_start,
                "end": delimiter_end,
                "reason": "parenthetical_reading_gloss",
                "applies_to": applies_to,
            }
        )
    if not suppressed_spans:
        return sentence, []
    analysis_parts.append(sentence[last_end:])
    return "".join(analysis_parts), suppressed_spans


def matching_preceding_tokens(
    preceding_tokens: list[dict[str, Any]], reading_text: str
) -> list[str]:
    reading = re.sub(r"\s+", "", katakana_to_hiragana(reading_text))
    suffix: list[dict[str, Any]] = []
    joined = ""
    for token in reversed(preceding_tokens):
        suffix.insert(0, token)
        joined = token["hiragana"] + joined
        if joined == reading:
            return [item["canonical"] for item in suffix]
        if not reading.endswith(joined):
            break
    return []


def grammar_token_node(node) -> bool:
    pos1 = getattr(node.feature, "pos1", "") or "*"
    surface = str(node.surface)
    return (pos1, surface) in GRAMMAR_TOKEN_TRANSLATIONS


def grammar_token_translation(row: dict[str, Any]) -> str:
    pos1 = str(row.get("pos1", ""))
    surface = str(row.get("surface", ""))
    return GRAMMAR_TOKEN_TRANSLATIONS.get((pos1, surface), "")


def analyzer_canonical_token(node) -> str:
    pos = getattr(node.feature, "pos1", "") or "*"
    lemma = getattr(node.feature, "lemma", "") or ""
    orth_base = getattr(node.feature, "orthBase", "") or ""
    if pos == "名詞" and lemma and orth_base and kana_only(orth_base) and has_kanji(lemma):
        return f"{lemma}::{pos}"
    return canonical_token(node, "lemma_pos")


def token_row(
    item,
    translation_provider: TranslationProvider,
    phrase_matches: list[dict[str, Any]],
    place_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    node = item.node
    reading = reading_fields([node])
    pos1 = getattr(node.feature, "pos1", "") or "*"
    pos2 = getattr(node.feature, "pos2", "") or "*"
    canonical = analyzer_canonical_token(node)
    row = {
        "surface": node.surface,
        "pos1": pos1,
        "pos2": pos2,
        "canonical": canonical,
        **reading,
        "start": item.start,
        "end": item.end,
        "phrases": overlapping_phrases(phrase_matches, item.start, item.end),
        "places": overlapping_places(place_matches, item.start, item.end),
    }
    row["translation"] = grammar_token_translation(row) or translation_provider.lookup(row)
    return row


def compound_token(
    items: list[object],
    translation_provider: TranslationProvider,
    phrase_matches: list[dict[str, Any]],
    place_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = [item.node for item in items]
    surface = "".join(node.surface for node in nodes)
    reading = reading_fields(nodes)
    canonical = f"{surface}::名詞"
    row = {
        "surface": surface,
        "pos1": "名詞",
        "pos2": compound_pos2(nodes),
        "canonical": canonical,
        **reading,
        "start": items[0].start,
        "end": items[-1].end,
        "phrases": overlapping_phrases(phrase_matches, items[0].start, items[-1].end),
        "places": overlapping_places(place_matches, items[0].start, items[-1].end),
        "inherited_tokens": inherited_compound_tokens(nodes, translation_provider),
    }
    row["translation"] = translation_provider.lookup(row)
    return row


def place_token(
    items: list[object],
    match: dict[str, Any],
    translation_provider: TranslationProvider,
    phrase_matches: list[dict[str, Any]],
    place_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    surface = str(match["surface"])
    reading = reading_fields([item.node for item in items])
    canonical = f"{surface}::名詞"
    places = overlapping_places(place_matches, int(match["start"]), int(match["end"]))
    row = {
        "surface": surface,
        "pos1": "名詞",
        "pos2": "固有名詞",
        "canonical": canonical,
        **reading,
        "start": int(match["start"]),
        "end": int(match["end"]),
        "phrases": overlapping_phrases(
            phrase_matches, int(match["start"]), int(match["end"])
        ),
        "places": places,
    }
    row["translation"] = translation_provider.lookup(row) or place_translation(places)
    return row


def wikimedia_reading_token(
    items: list[object],
    match: dict[str, Any],
    translation_provider: TranslationProvider,
    phrase_matches: list[dict[str, Any]],
    place_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    surface = str(match["surface"])
    hiragana = str(match["hiragana"])
    canonical = f"{surface}::名詞"
    row = {
        "surface": surface,
        "pos1": "名詞",
        "pos2": "普通名詞",
        "canonical": canonical,
        "hiragana": hiragana,
        "romaji": kana_to_romaji(hiragana),
        "reading_status": "wikimedia",
        "reading_source": {
            "source": str(match.get("source", "")),
            "title": str(match.get("source_title", "")),
            "url": str(match.get("source_url", "")),
            "id": str(match.get("source_id", "")),
        },
        "start": items[0].start,
        "end": items[-1].end,
        "phrases": overlapping_phrases(phrase_matches, items[0].start, items[-1].end),
        "places": overlapping_places(place_matches, items[0].start, items[-1].end),
    }
    row["translation"] = translation_provider.lookup(row)
    return row


def verb_chain_token(
    items: list[object],
    sentence: str,
    translation_provider: TranslationProvider,
    phrase_matches: list[dict[str, Any]],
    place_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    base = items[0].node
    surface = sentence[items[0].start : items[-1].end]
    reading = reading_fields_for_surface_or_nodes(surface, [item.node for item in items])
    row = {
        "surface": surface,
        "pos1": "動詞",
        "pos2": getattr(base.feature, "pos2", "") or "*",
        "canonical": verb_chain_canonical(base),
        **reading,
        "start": items[0].start,
        "end": items[-1].end,
        "phrases": overlapping_phrases(phrase_matches, items[0].start, items[-1].end),
        "places": overlapping_places(place_matches, items[0].start, items[-1].end),
    }
    row["translation"] = translation_provider.lookup(row)
    return row


def verb_chain_canonical(base) -> str:
    pos = getattr(base.feature, "pos1", "") or "*"
    lemma = getattr(base.feature, "lemma", "") or ""
    orth_base = getattr(base.feature, "orthBase", "") or ""
    if orth_base == "する":
        return f"する::{pos}"
    if lemma and orth_base and kana_only(orth_base) and has_kanji(lemma):
        return f"{lemma}::{pos}"
    return canonical_token(base, "lemma_pos")


def kana_only(text: str) -> bool:
    return bool(text) and re.fullmatch(r"[ぁ-ゖァ-ヺー]+", text) is not None


def has_kanji(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def place_translation(places: list[dict[str, str]]) -> str:
    if not places:
        return ""
    place = places[0]
    label = place.get("english_label", "") or place.get("label", "")
    description = place.get("english_description", "") or place.get("description", "")
    if label and description:
        return f"{label}: {description}"
    return label or description


def compound_pos2(nodes: list[object]) -> str:
    if any(getattr(node.feature, "pos2", "") == "固有名詞" for node in nodes):
        return "固有名詞"
    return "普通名詞"


def dictionary_noun_compound_items(
    tagged: list[object],
    start: int,
    translation_provider: TranslationProvider,
) -> list[object] | None:
    if not node_is_common_noun(tagged[start].node):
        return None
    candidates: list[list[object]] = []
    for end in range(start + 2, min(len(tagged), start + 5) + 1):
        items = tagged[start:end]
        if not all(node_is_common_noun(item.node) for item in items):
            break
        candidates.append(items)
    for items in reversed(candidates):
        if dictionary_confirmed_compound(items, translation_provider):
            return items
    return None


def dictionary_confirmed_compound(
    items: list[object], translation_provider: TranslationProvider
) -> bool:
    nodes = [item.node for item in items]
    surface = "".join(node.surface for node in nodes)
    row = {
        "surface": surface,
        "pos1": "名詞",
        "pos2": compound_pos2(nodes),
        "canonical": f"{surface}::名詞",
        **reading_fields(nodes),
    }
    if not translation_provider.lookup(row):
        return False
    return all(plain_token_row(node, translation_provider).get("translation") for node in nodes)


def detect_wikimedia_reading_matches(
    tagged: list[object], text: str, provider: WikimediaReadingProvider
) -> list[dict[str, Any]]:
    candidates = wikimedia_reading_candidates(tagged, text)
    hits: list[dict[str, Any]] = []
    for candidate in candidates:
        reading = provider.lookup(str(candidate["surface"]))
        if reading is None:
            continue
        hits.append({**candidate, **reading})
    return select_non_overlapping_reading_matches(hits)


def wikimedia_reading_candidates(
    tagged: list[object], text: str
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for start in range(len(tagged)):
        if not reading_candidate_node(tagged[start].node):
            continue
        for end in range(start + 1, min(len(tagged), start + 5) + 1):
            items = tagged[start:end]
            if not all(reading_candidate_node(item.node) for item in items):
                break
            if not any(missing_node_reading(item.node) for item in items):
                continue
            surface = text[items[0].start : items[-1].end]
            if len(surface) < 2 or len(surface) > 12:
                continue
            candidates.append(
                {
                    "surface": surface,
                    "start": items[0].start,
                    "end": items[-1].end,
                    "start_index": start,
                    "end_index": end,
                    "score": 100 + len(surface) + (20 if len(items) > 1 else 0),
                }
            )
    candidates.sort(key=lambda item: (item["start"], -item["score"], -len(item["surface"])))
    return candidates


def select_non_overlapping_reading_matches(
    hits: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for hit in sorted(hits, key=lambda item: (item["start"], -item["score"], -len(item["surface"]))):
        indexes = set(range(int(hit["start_index"]), int(hit["end_index"])))
        if indexes & occupied:
            continue
        selected.append(hit)
        occupied.update(indexes)
    return selected


def reading_candidate_node(node) -> bool:
    pos1 = getattr(node.feature, "pos1", "")
    if pos1 not in {"名詞", "接尾辞"}:
        return False
    return all("\u4e00" <= char <= "\u9fff" for char in node.surface)


def missing_node_reading(node) -> bool:
    return base_kana(node) == ""


def te_iru_chain_end_index(tagged: list[object], start: int) -> int | None:
    if not node_is_verb(tagged[start].node):
        return None
    index = start + 1
    while index < len(tagged) and getattr(tagged[index].node.feature, "pos1", "") == "助動詞":
        index += 1
    if index + 1 >= len(tagged):
        return None
    if tagged[index].node.surface != "て":
        return None
    iru = tagged[index + 1].node
    if iru.surface != "いる":
        return None
    if getattr(iru.feature, "pos1", "") != "動詞":
        return None
    if getattr(iru.feature, "pos2", "") != "非自立可能":
        return None
    return index + 2


def reading_fields(nodes: list[object]) -> dict[str, str]:
    parts = [katakana_to_hiragana(base_kana(node)) for node in nodes]
    known_count = sum(1 for part in parts if part)
    if known_count == 0:
        return {"hiragana": "", "romaji": "", "reading_status": "missing"}
    status = "available" if known_count == len(parts) else "partial"
    hiragana = "".join(part or "?" for part in parts)
    return {
        "hiragana": hiragana,
        "romaji": kana_to_romaji(hiragana),
        "reading_status": status,
    }


def reading_fields_for_surface_or_nodes(
    surface: str, nodes: list[object]
) -> dict[str, str]:
    if re.fullmatch(r"[ぁ-ゖァ-ヺー]+", surface):
        hiragana = katakana_to_hiragana(surface)
        return {
            "hiragana": hiragana,
            "romaji": kana_to_romaji(hiragana),
            "reading_status": "available",
        }
    return reading_fields(nodes)


def inherited_compound_tokens(
    nodes: list[object], translation_provider: TranslationProvider
) -> list[dict[str, str]]:
    inherited: list[dict[str, str]] = []
    noun_nodes = [node for node in nodes if node_is_noun(node)]
    suffix_nodes = [node for node in nodes if node_is_nominal_suffix(node)]
    for node in noun_nodes:
        row = plain_token_row(node, translation_provider)
        inherited.append(
            {
                "surface": str(row["surface"]),
                "canonical": str(row["canonical"]),
                "hiragana": str(row["hiragana"]),
                "romaji": str(row["romaji"]),
                "reading_status": str(row["reading_status"]),
                "translation": str(row.get("translation", "")),
            }
        )
    if len(suffix_nodes) >= 2:
        suffix_surface = "".join(node.surface for node in suffix_nodes)
        suffix_token = retokenized_single_noun(suffix_surface, translation_provider)
        if suffix_token is not None:
            inherited.append(suffix_token)
    return inherited


def retokenized_single_noun(
    text: str, translation_provider: TranslationProvider
) -> dict[str, str] | None:
    nodes = [
        node
        for node in get_tagger()(text)
        if token_node_is_lexical(node) and not NUMERIC_RE.fullmatch(node.surface)
    ]
    if len(nodes) != 1 or not node_is_noun(nodes[0]):
        return None
    row = plain_token_row(nodes[0], translation_provider)
    return {
        "surface": str(row["surface"]),
        "canonical": str(row["canonical"]),
        "hiragana": str(row["hiragana"]),
        "romaji": str(row["romaji"]),
        "reading_status": str(row["reading_status"]),
        "translation": str(row.get("translation", "")),
    }


def plain_token_row(node, translation_provider: TranslationProvider) -> dict[str, Any]:
    reading = reading_fields([node])
    pos1 = getattr(node.feature, "pos1", "") or "*"
    pos2 = getattr(node.feature, "pos2", "") or "*"
    canonical = analyzer_canonical_token(node)
    row = {
        "surface": node.surface,
        "pos1": pos1,
        "pos2": pos2,
        "canonical": canonical,
        **reading,
    }
    row["translation"] = translation_provider.lookup(row)
    return row


def node_is_noun(node) -> bool:
    return token_node_is_lexical(node) and getattr(node.feature, "pos1", "") == "名詞"


def node_is_common_noun(node) -> bool:
    return node_is_noun(node) and getattr(node.feature, "pos2", "") == "普通名詞"


def node_is_verb(node) -> bool:
    return token_node_is_lexical(node) and getattr(node.feature, "pos1", "") == "動詞"


def node_is_nominal_suffix(node) -> bool:
    if not token_node_is_lexical(node):
        return False
    return (
        getattr(node.feature, "pos1", "") == "接尾辞"
        and getattr(node.feature, "pos2", "") == "名詞的"
    )


def previous_significant_node_is_numeric(nodes: list[object], index: int) -> bool:
    for previous_item in reversed(nodes[:index]):
        previous = previous_item.node
        if not token_node_is_lexical(previous):
            continue
        return NUMERIC_RE.fullmatch(previous.surface) is not None
    return False


def build_sentence_token_cache(rows: list[dict[str, Any]]) -> dict[str, dict[str, object]]:
    cache: dict[str, dict[str, object]] = {}
    for row in rows:
        canonical = row["canonical"]
        entry = cache.setdefault(
            canonical,
            {
                "canonical": canonical,
                "pos1": row["pos1"],
                "pos2": row.get("pos2", ""),
                "hiragana": row["hiragana"],
                "romaji": row["romaji"],
                "reading_status": row.get("reading_status", ""),
                "translation": row.get("translation", ""),
                "sentence_hits": 1,
                "occurrences_in_sentence": 0,
                "surfaces": [],
            },
        )
        entry["occurrences_in_sentence"] = int(entry["occurrences_in_sentence"]) + 1
        surfaces = entry["surfaces"]
        if isinstance(surfaces, list) and row["surface"] not in surfaces:
            surfaces.append(row["surface"])
    return cache
