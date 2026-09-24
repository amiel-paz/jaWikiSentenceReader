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
        "また、ただし、大抵の訴訟も裁くほどで、かなりの権力を持ち、同じ奉公人と話した。",
        {
            "ただし::接続詞": "but; however",
            "大抵::副詞": "mostly; usually",
            "かなり::形状詞": "considerably",
            "同じ::連体詞": "same",
        },
    )

    assert rows["また"]["canonical"] == "又::接続詞"
    assert rows["また"]["translation"] == "also; additionally; moreover; furthermore"
    assert rows["ただし"]["pos1"] == "接続詞"
    assert rows["大抵"]["pos1"] == "副詞"
    assert rows["同じ"]["pos1"] == "連体詞"
    assert rows["同じ"]["translation"] == "same"
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


def test_arabic_number_counter_spans_use_counter_readings():
    rows = rows_by_surface("全700話で、単行本は全72巻と外伝1巻、50号。")

    episode = rows["700話"]
    assert episode["canonical"] == "話::助数詞"
    assert episode["pos1"] == "助数詞"
    assert episode["hiragana"] == "ななひゃくわ"
    assert episode["romaji"] == "nanahyakuwa"
    assert episode["translation"] == "counter for stories, episodes, chapters, or talks"

    volumes = rows["72巻"]
    assert volumes["canonical"] == "巻::助数詞"
    assert volumes["hiragana"] == "ななじゅうにかん"
    assert volumes["translation"] == "counter for volumes, scrolls, or reels"

    extra = rows["1巻"]
    assert extra["canonical"] == "巻::助数詞"
    assert extra["hiragana"] == "いっかん"
    issue = rows["50号"]
    assert issue["canonical"] == "号::助数詞"
    assert issue["hiragana"] == "ごじゅうごう"
    assert issue["translation"] == "number; issue number; edition marker"
    assert "話" not in rows
    assert "巻" not in rows


def test_family_suffix_compound_gets_generic_translation_fallback():
    rows = rows_by_surface(
        "夏目家は没落した。",
        {
            "夏目::名詞": "Natsume",
            "没落::名詞": "ruin; fall",
            "する::動詞": "to do",
        },
    )

    token = rows["夏目家"]
    assert token["canonical"] == "夏目家::名詞"
    assert token["translation"] == "Natsume family; Natsume household"
    assert token["inherited_tokens"] == [
        {
            "surface": "夏目",
            "canonical": "夏目::名詞",
            "hiragana": "なつめ",
            "romaji": "natsume",
            "reading_status": "available",
            "translation": "Natsume",
        }
    ]
    assert "家" not in rows


def test_nominal_go_suffix_is_phrase_metadata_on_base_compound():
    rows = rows_by_surface(
        "明治維新後の混乱期であった。",
        {
            "明治維新::名詞": "Meiji Restoration",
            "明治::名詞": "Meiji era",
            "維新::名詞": "reformation",
            "混乱::名詞": "confusion",
            "期::名詞": "period",
        },
    )

    token = rows["明治維新"]
    assert token["canonical"] == "明治維新::名詞"
    assert token["hiragana"] == "めいじいしん"
    assert token["translation"] == "Meiji Restoration"
    assert token["phrases"] == [
        {
            "surface": "明治維新後",
            "canonical": "後::表現",
            "translation": "after; following; since",
        }
    ]
    assert "明治" not in rows
    assert "維新" not in rows
    assert "維新後" not in rows
    assert "明治維新後" not in rows


def test_nominal_go_suffix_does_not_create_single_noun_suffix_token():
    rows = rows_by_surface(
        "帰国後に働いた。",
        {
            "帰国::名詞": "returning to one's country",
            "働く::動詞": "to work",
        },
    )

    token = rows["帰国"]
    assert token["canonical"] == "帰国::名詞"
    assert token["phrases"] == [
        {
            "surface": "帰国後",
            "canonical": "後::表現",
            "translation": "after; following; since",
        }
    ]
    assert "帰国後" not in rows


def test_source_framing_account_phrases_are_hover_metadata():
    rows = rows_by_surface(
        "一説には八百屋で、通説では古道具屋だった。",
        {
            "一説::名詞": "one theory; one opinion; another theory",
            "八百屋::名詞": "greengrocer",
            "通説::名詞": "accepted theory; common view",
            "古道具屋::名詞": "secondhand-goods shop",
        },
    )

    assert rows["一説"]["phrases"] == [
        {
            "surface": "一説には",
            "canonical": "一説には::表現",
            "translation": "according to one account; one theory says; some say",
        }
    ]
    assert rows["通説"]["phrases"] == [
        {
            "surface": "通説では",
            "canonical": "通説には::表現",
            "translation": "according to the accepted/common view",
        }
    ]
    assert "には" not in rows
    assert "では" not in rows


def test_tsutsu_aru_chain_collapses_sahen_verb_with_aspect_phrase():
    rows = rows_by_surface(
        "没落しつつあった。",
        {"没落::名詞": "ruin; fall; collapse; downfall"},
    )

    token = rows["没落しつつあった"]
    assert token["canonical"] == "没落する::動詞"
    assert token["hiragana"] == "ぼつらくしつつあった"
    assert token["romaji"] == "botsurakushitsutsuatta"
    assert token["translation"] == "ruin; fall; collapse; downfall"
    assert token["phrases"][0]["canonical"] == "つつある::表現"
    assert token["phrases"][0]["translation"].startswith("to be in the process")
    assert token["inherited_tokens"] == [
        {
            "surface": "没落",
            "canonical": "没落::名詞",
            "hiragana": "ぼつらく",
            "romaji": "botsuraku",
            "reading_status": "available",
            "translation": "ruin; fall; collapse; downfall",
        }
    ]
    assert "し" not in rows
    assert "あっ" not in rows


def test_tsutsu_aru_chain_collapses_plain_verb_with_aspect_phrase():
    rows = rows_by_surface(
        "傾きつつある。",
        {"傾く::動詞": "to decline"},
    )

    token = rows["傾きつつある"]
    assert token["canonical"] == "傾く::動詞"
    assert token["translation"] == "to decline"
    assert token["phrases"][0]["canonical"] == "つつある::表現"
    assert "ある" not in rows
