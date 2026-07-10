from pathlib import Path
from typing import Any

from wiki_reader.analyzer import analyze_article, analyze_sentence


class StaticTranslations:
    def __init__(self, glosses: dict[str, str] | None = None):
        self.glosses = glosses or {}

    def lookup(self, token: dict[str, Any]) -> str:
        keys = [
            str(token.get("canonical", "")),
            str(token.get("surface", "")),
            str(token.get("hiragana", "")),
        ]
        return next((self.glosses[key] for key in keys if key in self.glosses), "")


def rows_by_surface(sentence: str, glosses: dict[str, str] | None = None):
    return {
        row["surface"]: row
        for row in analyze_sentence(sentence, StaticTranslations(glosses))
    }


def test_heading_text_is_analyzed_and_marked_with_ranges():
    article = {
        "title": "test",
        "sentences": [
            {
                "text": "夏目金之助は、幕末の江戸にて出生した。",
                "headings": ["生涯", "生い立ち"],
            }
        ],
    }

    result = analyze_article(
        article,
        base_dir=Path.cwd(),
        translation_provider=StaticTranslations(),
        place_provider=None,
        reading_provider=None,
    )
    sentence = result["sentences"][0]

    assert sentence["display_text"].startswith("生涯\n生い立ち\n")
    assert sentence["heading_ranges"] == [{"start": 0, "end": 2}, {"start": 3, "end": 7}]
    assert ["生涯", "生い立ち"] == [row["surface"] for row in sentence["tokens"][:2]]


def test_load_bearing_pos_and_grammar_tokens_are_mapped_without_all_particles():
    rows = rows_by_surface(
        "また、ただし、大抵の訴訟も裁くほどで、かなりの権力を持った。",
        {
            "ただし::接続詞": "but; however",
            "大抵::副詞": "mostly; usually",
            "かなり::形状詞": "considerably",
        },
    )

    assert rows["また"]["canonical"] == "又::接続詞"
    assert rows["また"]["translation"] == "also; additionally; moreover; furthermore"
    assert rows["ただし"]["pos1"] == "接続詞"
    assert rows["大抵"]["pos1"] == "副詞"
    assert rows["ほど"]["canonical"] == "ほど::助詞"
    assert rows["ほど"]["translation"].startswith("to the extent that")
    assert "の" not in rows
    assert "で" not in rows


def test_te_iru_passive_chain_uses_semantic_base_verb():
    rows = rows_by_surface(
        "「面目ない」と恥じたといわれている。",
        {"言う::動詞": "to say; to utter; to declare"},
    )

    token = rows["いわれている"]
    assert token["canonical"] == "言う::動詞"
    assert token["hiragana"] == "いわれている"
    assert token["translation"] == "to say; to utter; to declare"


def test_kana_written_tokens_use_kanji_lemma_to_avoid_homophone_gloss():
    rows = rows_by_surface(
        "高齢で出産したことからいう。",
        {"事::名詞": "thing; matter", "言う::動詞": "to say"},
    )

    assert rows["こと"]["canonical"] == "事::名詞"
    assert rows["こと"]["translation"] == "thing; matter"
    assert rows["いう"]["canonical"] == "言う::動詞"
    assert rows["いう"]["translation"] == "to say"


def test_sareteiru_chain_still_maps_to_suru():
    rows = rows_by_surface("評価されている。", {"する::動詞": "to do"})

    token = rows["されている"]
    assert token["canonical"] == "する::動詞"
    assert token["hiragana"] == "されている"


def test_phrase_annotations_are_hover_metadata_not_canonical_tokens():
    rows = rows_by_surface(
        "作品を通して、明治末期から大正初期にかけて活躍し、子沢山の上に高齢であり、入れられたものである。",
        {
            "作品::名詞": "work",
            "通す::動詞": "to pass through",
            "明治::名詞": "Meiji era",
            "沢山::形状詞": "many",
        },
    )

    assert rows["作品"]["phrases"][0]["canonical"] == "を通して::表現"
    assert rows["通し"]["phrases"][0]["translation"].startswith("through")
    assert rows["明治"]["phrases"][0]["canonical"] == "から…にかけて::表現"
    assert rows["子"]["phrases"][0]["canonical"] == "の上に::表現"
    assert rows["沢山"]["phrases"][0]["canonical"] == "の上に::表現"
    assert rows["上"]["phrases"][0]["translation"].startswith("on top of")
    assert rows["もの"]["phrases"][0]["canonical"] == "ものである::表現"
    assert rows["ある"]["phrases"][0]["translation"].startswith("it is/was the case")
    assert "の" not in rows
    assert "で" not in rows


def test_dictionary_confirmed_compound_inherits_constituent_tokens():
    rows = rows_by_surface(
        "個人主義。",
        {
            "個人主義::名詞": "individualism",
            "個人::名詞": "individual",
            "主義::名詞": "principle",
        },
    )

    token = rows["個人主義"]
    inherited = {item["canonical"] for item in token["inherited_tokens"]}
    assert token["translation"] == "individualism"
    assert {"個人::名詞", "主義::名詞"} <= inherited


def test_dictionary_confirmed_numeric_compound_is_single_token_without_inheritance():
    rows = rows_by_surface(
        "3歳頃には一代で傾いた。",
        {
            "歳::接尾辞": "... years old; age (of) ...",
            "頃::名詞": "around; about",
            "一代::名詞": "generation; lifetime; age",
            "一::名詞": "one",
            "代::名詞": "world; society; public",
            "傾く::動詞": "to decline",
        },
    )

    assert "3" not in rows
    assert rows["一代"]["canonical"] == "一代::名詞"
    assert rows["一代"]["hiragana"] == "いちだい"
    assert rows["一代"]["translation"] == "generation; lifetime; age"
    assert rows["一代"].get("inherited_tokens") == []
    assert "一" not in rows
    assert "代" not in rows
