from wiki_reader.analyzer import analyze_sentence_with_cache
from wiki_reader.translation_provider import (
    NullTranslationProvider,
    OverrideTranslationProvider,
)


class EntryProvider:
    def lookup(self, token):
        return "cat"

    def lookup_entry(self, token):
        return {
            "source": "JMdict",
            "entry_id": "1467640",
            "headword": "猫",
            "hiragana": "ねこ",
            "romaji": "neko",
            "translation": "cat",
        }


def test_analyzed_token_has_stable_dictionary_vocabulary_mapping():
    result = analyze_sentence_with_cache("猫がいる。", translation_provider=EntryProvider())
    token = result["tokens"][0]

    assert token["vocabulary"] == {
        "token_id": "猫::名詞",
        "dictionary_id": "JMdict:1467640",
        "source": "JMdict",
        "headword": "猫",
        "hiragana": "ねこ",
        "romaji": "neko",
        "translation": "cat",
        "mapping_status": "dictionary",
    }


def test_local_override_supplies_missing_translation_and_reading():
    provider = OverrideTranslationProvider(
        NullTranslationProvider(),
        {
            "汁かけ飯::名詞": {
                "hiragana": "しるかけめし",
                "translation": "rice topped with broth or soup",
            }
        },
    )
    token = {
        "surface": "汁かけ飯",
        "canonical": "汁かけ飯::名詞",
        "hiragana": "しるかけはん",
    }

    assert provider.lookup(token) == "rice topped with broth or soup"
    assert provider.lookup_reading(token) == "しるかけめし"
    assert provider.lookup_entry(token)["source"] == "Local override"
