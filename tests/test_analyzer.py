from pathlib import Path
from typing import Any

from wiki_reader.analyzer import (
    analyze_article,
    analyze_sentence,
    analyze_sentence_with_cache,
)


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


class DictionaryTranslations(StaticTranslations):
    def __init__(self, entries: dict[str, dict[str, str]]):
        super().__init__({key: value["translation"] for key, value in entries.items()})
        self.entries = entries

    def lookup_entry(self, token: dict[str, Any]) -> dict[str, str] | None:
        return self.entries.get(str(token.get("canonical", "")))

    def lookup_reading(self, token: dict[str, Any]) -> str:
        entry = self.lookup_entry(token)
        return str(entry.get("hiragana", "")) if entry else ""

    def lookup_sense_pos(self, token: dict[str, Any]) -> set[str]:
        entry = self.lookup_entry(token)
        return set(str(entry.get("sense_pos", "")).split(",")) if entry else set()


class StaticReadings:
    def __init__(self, readings: dict[str, dict[str, str]]):
        self.readings = readings
        self.lookups: list[str] = []

    def lookup(self, term: str) -> dict[str, str] | None:
        self.lookups.append(term)
        return self.readings.get(term)


def dictionary_entry(
    headword: str,
    hiragana: str,
    translation: str,
    *,
    source: str = "JMdict",
    sense_pos: str = "",
) -> dict[str, str]:
    return {
        "source": source,
        "entry_id": headword,
        "headword": headword,
        "hiragana": hiragana,
        "romaji": "",
        "translation": translation,
        "sense_pos": sense_pos,
    }


def rows_by_surface(sentence: str, glosses: dict[str, str] | None = None):
    return {
        row["surface"]: row
        for row in analyze_sentence(sentence, StaticTranslations(glosses))
    }


def cached_rows(sentence: str, provider: DictionaryTranslations):
    return {
        row["surface"]: row
        for row in analyze_sentence_with_cache(
            sentence, translation_provider=provider
        )["tokens"]
    }


def test_shared_mapping_recovers_inflected_dictionary_lemma():
    provider = DictionaryTranslations(
        {
            "過ごす::動詞": dictionary_entry("過ごす", "すごす", "to spend time"),
        }
    )

    token = cached_rows("大学で過ごせる。", provider)["過ごせる"]

    assert token["canonical"] == "過ごす::動詞"
    assert token["translation"] == "to spend time"
    assert token["vocabulary"]["token_id"] == "過ごす::動詞"


def test_shared_mapping_rejects_name_homophone_for_inflected_verb():
    provider = DictionaryTranslations(
        {
            "乗れる::動詞": dictionary_entry(
                "ノレル", "のれる", "Norell", source="JMnedict"
            ),
            "乗る::動詞": dictionary_entry("乗る", "のる", "to board"),
        }
    )

    token = cached_rows("電車に乗れる。", provider)["乗れる"]

    assert token["canonical"] == "乗る::動詞"
    assert token["translation"] == "to board"
    assert token["vocabulary"]["source"] == "JMdict"


def test_full_person_name_reading_overrides_isolated_name_guesses():
    readings = StaticReadings(
        {
            "菅田将暉": {
                "hiragana": "すだまさき",
                "source": "jawiki",
                "source_title": "菅田将暉",
                "source_url": "https://ja.wikipedia.org/wiki/菅田将暉",
                "source_id": "Q1322323",
                "romaji": "suda masaki",
            }
        }
    )

    rows = analyze_sentence(
        "菅田将暉って渋いの?",
        StaticTranslations(),
        reading_provider=readings,
    )
    name = next(row for row in rows if row["surface"] == "菅田将暉")

    assert readings.lookups == ["菅田将暉"]
    assert name["hiragana"] == "すだまさき"
    assert name["romaji"] == "suda masaki"
    assert name["translation"] == "Suda Masaki (person name)"
    assert name["reading_status"] == "wikimedia"
    assert all(row["surface"] not in {"菅田", "将", "暉"} for row in rows)


def test_adv_to_predicate_is_one_expression_instead_of_bare_to_suru():
    provider = DictionaryTranslations(
        {
            "どきり::副詞": dictionary_entry(
                "どきり",
                "どきり",
                "being startled; getting a shock",
                sense_pos="adv-to,adv,vs",
            ),
            "とする::表現": dictionary_entry(
                "とする",
                "とする",
                "to try to; to regard as",
                sense_pos="exp,vs-i",
            ),
        }
    )

    rows = analyze_sentence("俺は思わずどきりとした。", provider)
    expression = next(row for row in rows if row["surface"] == "どきりとした")

    assert expression["canonical"] == "どきりとする::表現"
    assert expression["hiragana"] == "どきりとする"
    assert expression["romaji"] == "dokiritosuru"
    assert expression["translation"] == "being startled; getting a shock"
    assert all(row["surface"] not in {"どきり", "とし"} for row in rows)


def test_shared_mapping_disambiguates_productive_te_miru():
    provider = DictionaryTranslations(
        {
            "のぞいて::表現": dictionary_entry(
                "除いて", "のぞいて", "except", sense_pos="exp"
            ),
            "覗く::動詞": dictionary_entry("覗く", "のぞく", "to peek"),
        }
    )

    token = cached_rows("のぞいてみる。", provider)["のぞいて"]

    assert token["canonical"] == "覗く::動詞"
    assert token["translation"] == "to peek"


def test_shared_mapping_exposes_dictionary_backed_nominal_suffix():
    provider = DictionaryTranslations(
        {
            "コーヒー::名詞": dictionary_entry("コーヒー", "こーひー", "coffee"),
            "派::名詞": dictionary_entry("派", "は", "group; faction"),
        }
    )

    token = cached_rows("コーヒー派。", provider)["コーヒー派"]
    inherited = {item["canonical"]: item for item in token["inherited_tokens"]}

    assert inherited["派::名詞"]["translation"] == "group; faction"
    assert inherited["派::名詞"]["vocabulary"]["token_id"] == "派::名詞"


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


def test_ni_chigai_nai_is_one_selectable_grammar_token():
    rows = rows_by_surface("彼女に違いない。")

    token = rows["に違いない"]
    assert token["canonical"] == "に違いない::表現"
    assert token["hiragana"] == "にちがいない"
    assert token["romaji"] == "ni chigai nai"
    assert token["translation"] == "must be; surely; there is no doubt that"
    assert "違い" not in rows
    assert "ない" not in rows


def test_ni_chigai_nai_has_a_stable_shared_vocabulary_mapping():
    token = analyze_sentence_with_cache(
        "彼女に違いない。",
        translation_provider=StaticTranslations(),
    )["tokens"][1]

    assert token["vocabulary"] == {
        "token_id": "に違いない::表現",
        "dictionary_id": "Grammar:に違いない::表現",
        "source": "Local grammar",
        "headword": "に違いない",
        "hiragana": "にちがいない",
        "romaji": "ni chigai nai",
        "translation": "must be; surely; there is no doubt that",
        "mapping_status": "grammar",
    }


def test_tsukiage_is_one_contextually_correct_noun_token():
    rows = rows_by_surface("工場からは突上げを食らう。")

    token = rows["突上げ"]
    assert token["canonical"] == "突き上げ::名詞"
    assert token["hiragana"] == "つきあげ"
    assert token["romaji"] == "tsukiage"
    assert token["translation"] == (
        "pressure or pushback from below or from subordinates"
    )
    assert "突" not in rows
    assert "上げ" not in rows


def test_tsukiage_has_a_stable_shared_vocabulary_mapping():
    tokens = analyze_sentence_with_cache(
        "工場からは突上げを食らう。",
        translation_provider=StaticTranslations(),
    )["tokens"]
    token = next(item for item in tokens if item["surface"] == "突上げ")

    assert token["vocabulary"] == {
        "token_id": "突き上げ::名詞",
        "dictionary_id": "Local:突き上げ::名詞",
        "source": "Local vocabulary",
        "headword": "突き上げ",
        "hiragana": "つきあげ",
        "romaji": "tsukiage",
        "translation": "pressure or pushback from below or from subordinates",
        "mapping_status": "local",
    }


def test_tsumeru_passive_is_one_contextual_grilling_token_after_boss():
    rows = rows_by_surface("上司に詰められ、言葉に詰められた。")

    token = rows["詰められ"]
    assert token["canonical"] == "詰める::動詞"
    assert token["hiragana"] == "つめる"
    assert token["romaji"] == "tsumeru"
    assert token["translation"] == (
        "to grill or press for answers; to call to account"
    )
    assert rows["詰め"]["canonical"] == "詰める::動詞"
    assert rows["詰め"]["translation"] == ""


def test_contextual_tsumeru_sense_has_a_stable_anki_mapping():
    tokens = analyze_sentence_with_cache(
        "上司に詰められた。",
        translation_provider=StaticTranslations(),
    )["tokens"]
    token = next(item for item in tokens if item["surface"] == "詰められ")

    assert token["vocabulary"] == {
        "token_id": "詰める::動詞",
        "dictionary_id": "Local:詰める::動詞:press",
        "source": "Local override",
        "headword": "詰める",
        "hiragana": "つめる",
        "romaji": "tsumeru",
        "translation": "to grill or press for answers; to call to account",
        "mapping_status": "local",
    }


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
