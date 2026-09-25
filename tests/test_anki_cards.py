import pytest

from wiki_reader.anki_cards import build_anki_tsv


def sample_card(**values):
    card = {
        "canonical": "離れる::動詞",
        "expression": "離れる",
        "surface": "離れ",
        "hiragana": "はなれる",
        "romaji": "hanareru",
        "translation": "to leave; to be separated",
        "sentence": "地元を離れた。",
        "article_title": "記事",
        "source_url": "https://example.test/article",
        "vocabulary_id": "JMdict:123",
        "dictionary_source": "JMdict",
    }
    card.update(values)
    return card


def test_build_anki_tsv_has_import_headers_and_reveal_fields():
    result = build_anki_tsv([sample_card()])

    assert result.startswith(
        "#separator:Tab\n#html:true\n#notetype:Basic\n"
        "#deck:Japanese::Sentence Reader\n"
    )
    assert "離れる::動詞" in result
    assert "はなれる" in result
    assert "hanareru" in result
    assert "to leave; to be separated" in result
    assert "地元を離れた。" in result
    assert "ja_sentence_reader pos_動詞" in result


def test_build_anki_tsv_deduplicates_by_canonical_token():
    result = build_anki_tsv(
        [sample_card(), sample_card(surface="離れて", sentence="家を離れて暮らす。")]
    )

    assert result.count("離れる::動詞") == 1


def test_build_anki_tsv_requires_reveal_fields():
    with pytest.raises(ValueError, match="translation"):
        build_anki_tsv([sample_card(translation="")])


def test_build_anki_tsv_escapes_html_from_content():
    result = build_anki_tsv([sample_card(translation="<script>bad()</script>")])

    assert "<script>" not in result
    assert "&lt;script&gt;bad()&lt;/script&gt;" in result
