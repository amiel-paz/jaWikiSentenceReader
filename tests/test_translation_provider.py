import sqlite3

from wiki_reader.analyzer import analyze_sentence
from wiki_reader.translation_provider import SqliteDictionaryProvider


def write_dictionary(path, rows):
    with sqlite3.connect(path) as connection:
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
        normalized = [(*row, 0, "") if len(row) == 7 else row for row in rows]
        connection.executemany("INSERT INTO dictionary_lookup VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", normalized)


def test_exact_kanji_headword_consensus_can_beat_contextual_reading(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("痘痕", "JMdict", "1649560", "痘痕", "あばた", "pockmark", 20),
            ("痘痕", "JMdict", "2212940", "痘痕", "いも", "smallpox", 20),
            ("痘痕", "JMdict", "2857864", "痘痕", "とうこん", "pockmark", 20),
        ],
    )

    token = {
        "surface": "痘痕",
        "canonical": "痘痕::名詞",
        "hiragana": "いも",
        "pos2": "普通名詞",
    }
    provider = SqliteDictionaryProvider(dictionary_path)

    assert provider.lookup(token) == "pockmark"
    assert provider.lookup_reading(token) == "あばた"


def test_exact_reading_still_breaks_ties_without_consensus(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("例", "JMdict", "1", "例", "れい", "example", 20),
            ("例", "JMdict", "2", "例", "ためし", "trial", 20),
        ],
    )

    token = {
        "surface": "例",
        "canonical": "例::名詞",
        "hiragana": "ためし",
        "pos2": "普通名詞",
    }
    provider = SqliteDictionaryProvider(dictionary_path)

    assert provider.lookup(token) == "trial"
    assert provider.lookup_reading(token) == ""


def test_analyzer_can_use_dictionary_consensus_reading_override(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("痘痕", "JMdict", "1649560", "痘痕", "あばた", "pockmark", 20),
            ("痘痕", "JMdict", "2212940", "痘痕", "いも", "smallpox", 20),
            ("痘痕", "JMdict", "2857864", "痘痕", "とうこん", "pockmark", 20),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "このときできた痘痕は目立つほどに残ることとなった。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["痘痕"]["hiragana"] == "あばた"
    assert rows["痘痕"]["romaji"] == "abata"
    assert rows["痘痕"]["reading_status"] == "dictionary"
    assert rows["痘痕"]["translation"] == "pockmark"


def test_no_modifier_context_prefers_adnominal_dictionary_senses(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "相当",
                "JMdict",
                "1401240",
                "相当",
                "そうとう",
                "corresponding to (in meaning, function, etc.); being equivalent to",
                0,
                1,
                "n,vs,vi,adj-no",
            ),
            (
                "相当",
                "JMdict",
                "1401240",
                "相当",
                "そうとう",
                "appropriate; suitable; befitting; proportionate",
                0,
                2,
                "adj-na,adj-no",
            ),
            (
                "相当",
                "JMdict",
                "1401240",
                "相当",
                "そうとう",
                "considerable; substantial",
                0,
                4,
                "adj-na,adj-no",
            ),
        ],
    )

    gloss = SqliteDictionaryProvider(dictionary_path).lookup(
        {
            "surface": "相当",
            "canonical": "相当::名詞",
            "hiragana": "そうとう",
            "pos2": "普通名詞",
            "next_surface": "の",
        }
    )

    assert gloss == "appropriate; suitable; befitting; proportionate; considerable; substantial"


def test_dictionary_conjunction_expression_spans_particle_and_verb_tokens(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "とはいえ",
                "JMdict",
                "2576510",
                "とは言え",
                "とはいえ",
                "though; although; be that as it may; nonetheless",
                20,
                1,
                "conj",
            ),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "とはいえ、当時は混乱期であった。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["とはいえ"]["canonical"] == "とはいえ::表現"
    assert rows["とはいえ"]["hiragana"] == "とはいえ"
    assert rows["とはいえ"]["translation"] == "though; although; be that as it may; nonetheless"
    assert "いえ" not in rows
