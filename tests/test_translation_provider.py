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


def test_duplicate_kana_variants_do_not_outvote_common_dictionary_sense(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("忍", "JMdict", "1467400", "忍", "しのび", "stealth", 20, 1, "n"),
            ("忍", "JMdict", "1467400", "忍", "しのび", "ninja", 20, 4, "n"),
            (
                "忍",
                "JMdict",
                "2179930",
                "忍",
                "しのぶ",
                "squirrel's foot fern (Davallia mariesii)",
                20,
                1,
                "n",
            ),
            (
                "忍",
                "JMdict",
                "2179930",
                "忍",
                "シノブ",
                "squirrel's foot fern (Davallia mariesii)",
                20,
                1,
                "n",
            ),
            ("忍", "JMnedict", "5584589", "忍", "おし", "Oshi", 10),
        ],
    )
    provider = SqliteDictionaryProvider(dictionary_path)

    assert provider.lookup(
        {
            "surface": "忍",
            "canonical": "忍::名詞",
            "hiragana": "おし",
            "pos2": "固有名詞",
        }
    ) == "stealth"

    rows = {
        row["surface"]: row
        for row in analyze_sentence("忍同士が戦う。", provider)
    }
    token = rows["忍同士"]
    assert token["hiragana"] == "しのびどうし"
    assert token["romaji"] == "shinobidoushi"
    assert token["inherited_tokens"][0]["hiragana"] == "しのび"
    assert token["inherited_tokens"][0]["romaji"] == "shinobi"
    assert token["inherited_tokens"][0]["translation"] == "stealth"


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


def test_exact_jmdict_gloss_beats_romanized_jmnedict_echo(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "改革",
                "JMnedict",
                "name-1",
                "改革",
                "かいかく",
                "kaikaku",
                10,
            ),
            (
                "改革",
                "JMdict",
                "word-1",
                "改革",
                "かいかく",
                "reform; reformation",
                20,
                1,
                "n",
            ),
        ],
    )

    gloss = SqliteDictionaryProvider(dictionary_path).lookup(
        {
            "surface": "改革",
            "canonical": "改革::名詞",
            "hiragana": "かいかく",
            "pos2": "固有名詞",
        }
    )

    assert gloss == "reform; reformation"


def test_macron_romanized_jmnedict_echo_does_not_beat_jmdict_word(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "横町",
                "JMdict",
                "1605910",
                "横町",
                "よこちょう",
                "bystreet; side street; back street; alley",
                20,
                1,
                "n",
            ),
            (
                "横町",
                "JMnedict",
                "5148953",
                "横町",
                "よこちょう",
                "Yokochō",
                10,
            ),
            (
                "横町",
                "JMnedict",
                "5148954",
                "横町",
                "よこまち",
                "Yokomachi",
                10,
            ),
        ],
    )

    gloss = SqliteDictionaryProvider(dictionary_path).lookup(
        {
            "surface": "横町",
            "canonical": "横町::名詞",
            "hiragana": "よこちょう",
            "pos2": "固有名詞",
        }
    )

    assert gloss == "bystreet; side street; back street; alley"

    rows = {
        row["surface"]: row
        for row in analyze_sentence("馬場下横町出身。", SqliteDictionaryProvider(dictionary_path))
    }
    assert rows["横町"]["hiragana"] == "よこちょう"
    assert rows["横町"]["romaji"] == "yokochou"
    assert rows["横町"]["translation"] == "bystreet; side street; back street; alley"


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


def test_dictionary_expression_spans_toshite_without_short_particle_noise(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "として",
                "JMdict",
                "100",
                "として",
                "として",
                "as (i.e. in the role of); for (i.e. from the viewpoint of)",
                0,
                1,
                "exp",
            ),
            (
                "には",
                "JMdict",
                "101",
                "には",
                "には",
                "to; for; on; in",
                0,
                1,
                "exp",
            ),
            ("名主", "JMdict", "102", "名主", "なぬし", "village headman", 0, 1, "n"),
            ("没落", "JMdict", "103", "没落", "ぼつらく", "decline", 0, 1, "n"),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "名主として没落し、家には財産があった。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["として"]["canonical"] == "として::表現"
    assert rows["として"]["translation"] == "as (i.e. in the role of); for (i.e. from the viewpoint of)"
    assert "には" not in rows


def test_person_name_compound_prefers_exact_jmnedict_full_name_reading(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("岸本", "JMnedict", "1", "岸本", "きしもと", "Kishimoto", 10),
            ("斉史", "JMnedict", "2", "斉史", "せいじ", "Seiji", 10),
            (
                "岸本斉史",
                "JMnedict",
                "3",
                "岸本斉史",
                "きしもとまさし",
                "Kishimoto Masashi",
                10,
            ),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "岸本斉史。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["岸本斉史"]["canonical"] == "岸本斉史::名詞"
    assert rows["岸本斉史"]["hiragana"] == "きしもとまさし"
    assert rows["岸本斉史"]["romaji"] == "kishimotomasashi"
    assert rows["岸本斉史"]["reading_status"] == "dictionary"
    assert rows["岸本斉史"]["translation"] == "Kishimoto Masashi"
    assert rows["岸本斉史"]["inherited_tokens"] == []
    assert "岸本" not in rows
    assert "斉史" not in rows
