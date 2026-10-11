import sqlite3

from wiki_reader.analyzer import analyze_sentence, analyze_sentence_with_cache
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


def test_mimetic_senses_follow_unidic_grammar_and_nearby_semantic_context(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "車内",
                "JMdict",
                "car-interior",
                "車内",
                "しゃない",
                "inside a car (train, bus, etc.)",
                0,
                1,
                "n",
            ),
            ("声", "JMdict", "voice", "声", "こえ", "voice", 0, 1, "n"),
            (
                "ガラガラ",
                "JMdict",
                "garagara",
                "ガラガラ",
                "がらがら",
                "with a clatter; with a rattle",
                20,
                1,
                "adv,adv-to",
            ),
            (
                "ガラガラ",
                "JMdict",
                "garagara",
                "ガラガラ",
                "がらがら",
                "(almost) empty; (mostly) vacant; bare; uninhabited",
                20,
                2,
                "adj-no,adj-na",
            ),
            (
                "ガラガラ",
                "JMdict",
                "garagara",
                "ガラガラ",
                "がらがら",
                "raspy (voice); gravelly; husky",
                20,
                3,
                "adj-no,adj-na",
            ),
        ],
    )
    provider = SqliteDictionaryProvider(dictionary_path)

    empty_rows = {
        row["surface"]: row for row in analyze_sentence("車内はガラガラだ。", provider)
    }
    voice_rows = {
        row["surface"]: row for row in analyze_sentence("声がガラガラだ。", provider)
    }
    sound_rows = {
        row["surface"]: row
        for row in analyze_sentence("ガラガラと音がした。", provider)
    }

    assert empty_rows["ガラガラ"]["translation"] == (
        "(almost) empty; (mostly) vacant; bare; uninhabited"
    )
    assert voice_rows["ガラガラ"]["translation"] == "raspy (voice); gravelly; husky"
    assert sound_rows["ガラガラ"]["translation"] == "with a clatter; with a rattle"


def test_following_noun_gloss_disambiguates_a_polysemous_noun(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "春雨",
                "JMdict",
                "1580180",
                "春雨",
                "はるさめ",
                "gentle spring rain",
                20,
                1,
                "n",
            ),
            (
                "春雨",
                "JMdict",
                "1580180",
                "春雨",
                "はるさめ",
                "glass noodles; cellophane noodles; thin noodles made from bean starch",
                20,
                2,
                "n",
            ),
            (
                "ヌードル",
                "JMdict",
                "noodle",
                "ヌードル",
                "ヌードル",
                "noodle",
                0,
                1,
                "n",
            ),
        ],
    )
    provider = SqliteDictionaryProvider(dictionary_path)

    food_rows = {
        row["surface"]: row
        for row in analyze_sentence("春雨ヌードルを食べる。", provider)
    }
    rain_rows = {
        row["surface"]: row
        for row in analyze_sentence("春雨が降る。", provider)
    }

    assert food_rows["春雨"]["translation"] == (
        "glass noodles; cellophane noodles; thin noodles made from bean starch"
    )
    assert rain_rows["春雨"]["translation"] == "gentle spring rain"


def test_dictionary_noun_in_a_comma_separated_list_beats_homophonous_verb(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            ("青梗菜", "JMdict", "greens", "青梗菜", "ちんげんさい", "bok choy", 0, 1, "n"),
            ("もやし", "JMdict", "1517810", "萌やし", "もやし", "bean sprouts", 20, 1, "n"),
            ("燃やす", "JMdict", "1582900", "燃やす", "もやす", "to burn", 0, 1, "v5s,vt"),
            ("れんこん", "JMdict", "lotus", "蓮根", "れんこん", "lotus root", 0, 1, "n"),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "具材は青梗菜、もやし、れんこん。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["もやし"]["canonical"] == "もやし::名詞"
    assert rows["もやし"]["hiragana"] == "もやし"
    assert rows["もやし"]["romaji"] == "moyashi"
    assert rows["もやし"]["translation"] == "bean sprouts"
    assert not any(row["canonical"] == "燃やす::動詞" for row in rows.values())


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


def test_inflected_dictionary_expression_uses_lemma_but_keeps_full_surface(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "我に返る",
                "JMdict",
                "2125250",
                "我に返る",
                "われにかえる",
                "to come to one's senses",
                20,
                1,
                "exp,v5r",
            ),
        ],
    )

    rows = analyze_sentence(
        "我に返ってふと前を見る。", SqliteDictionaryProvider(dictionary_path)
    )
    expression = next(row for row in rows if row["surface"] == "我に返って")

    assert expression["canonical"] == "我に返る::表現"
    assert expression["hiragana"] == "われにかえる"
    assert expression["romaji"] == "warenikaeru"
    assert expression["translation"] == "to come to one's senses"
    assert not any(row["surface"] in {"我", "返っ"} for row in rows)


def test_inflected_expression_prefers_kana_orthographic_base_for_lookup(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "気になる",
                "JMdict",
                "1221690",
                "気になる",
                "きになる",
                "to weigh on one's mind; to worry about; to be concerned about",
                20,
                1,
                "exp,v5r",
            ),
            (
                "気になる",
                "JMdict",
                "1221690",
                "気になる",
                "きになる",
                "to be interested (in); to be curious (about); to catch one's eye",
                20,
                2,
                "exp,v5r",
            ),
        ],
    )

    rows = analyze_sentence(
        "なんとなく気になって聞き耳を立てる。",
        SqliteDictionaryProvider(dictionary_path),
    )
    expression = next(row for row in rows if row["surface"] == "気になって")

    assert expression["canonical"] == "気になる::表現"
    assert expression["hiragana"] == "きになる"
    assert expression["romaji"] == "kininaru"
    assert expression["translation"] == (
        "to weigh on one's mind; to worry about; to be concerned about; "
        "to be interested (in); to be curious (about); to catch one's eye"
    )
    assert not any(row["surface"] in {"気", "なっ"} for row in rows)


def test_dictionary_multiword_adverb_repairs_unidic_adverb_particle_split(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "どうやら",
                "JMdict",
                "1009020",
                "どうやら",
                "どうやら",
                "possibly; apparently; (seem) likely; seemingly",
                0,
                1,
                "adv",
            ),
            (
                "どう",
                "JMdict",
                "wrong-sense",
                "どう",
                "どう",
                "whoa (command used to stop a horse, etc.)",
                20,
                1,
                "int",
            ),
        ],
    )

    rows = analyze_sentence(
        "どうやらしりとりをしているようだ。",
        SqliteDictionaryProvider(dictionary_path),
    )
    adverb = next(row for row in rows if row["surface"] == "どうやら")

    assert adverb["canonical"] == "どうやら::副詞"
    assert adverb["pos1"] == "副詞"
    assert adverb["hiragana"] == "どうやら"
    assert adverb["romaji"] == "douyara"
    assert adverb["translation"] == "possibly; apparently; (seem) likely; seemingly"
    assert not any(row["surface"] == "どう" for row in rows)
    assert "いえ" not in rows


def test_short_dictionary_adverb_spans_topic_particle_and_uses_spoken_romaji(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "要は",
                "JMdict",
                "1914670",
                "要は",
                "ようは",
                "in short; the point is; the important thing is; in a word",
                0,
                1,
                "adv",
            ),
            ("要", "JMdict", "wrong-sense", "要", "かなめ", "pivot", 0, 1, "n"),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "要は麻辣スープということだ。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["要は"]["canonical"] == "要は::副詞"
    assert rows["要は"]["hiragana"] == "ようは"
    assert rows["要は"]["romaji"] == "you wa"
    assert rows["要は"]["translation"] == (
        "in short; the point is; the important thing is; in a word"
    )
    assert "要" not in rows


def test_context_resolves_karada_and_dictionary_compound_verb(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "身体",
                "JMdict",
                "formal-body",
                "身体",
                "しんたい",
                "body; physical system; the person",
                0,
                1,
                "n",
            ),
            (
                "身体",
                "JMdict",
                "everyday-body",
                "身体",
                "からだ",
                "body; health; constitution",
                0,
                1,
                "n",
            ),
            (
                "心惹かれる",
                "JMdict",
                "2402830",
                "心惹かれる",
                "こころひかれる",
                "to feel attracted by; to be fascinated by",
                20,
                1,
                "v1",
            ),
        ],
    )
    provider = SqliteDictionaryProvider(dictionary_path)

    result = analyze_sentence_with_cache(
        "身体に良さそうで心惹かれる。",
        translation_provider=provider,
    )
    rows = {row["surface"]: row for row in result["tokens"]}

    body = rows["身体"]
    assert body["hiragana"] == "からだ"
    assert body["romaji"] == "karada"
    assert body["reading_status"] == "contextual"
    assert body["vocabulary"]["hiragana"] == "からだ"

    expression = rows["心惹かれる"]
    assert expression["canonical"] == "心惹かれる::動詞"
    assert expression["hiragana"] == "こころひかれる"
    assert expression["romaji"] == "kokorohikareru"
    assert expression["translation"] == "to feel attracted by; to be fascinated by"
    assert "心" not in rows
    assert "惹か" not in rows


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


def test_right_hand_expression_keeps_shared_connector_from_left_match(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "になると",
                "JMdict",
                "left",
                "になると",
                "になると",
                "when it becomes; when it comes to",
                0,
                1,
                "exp",
            ),
            (
                "とともに",
                "JMdict",
                "right",
                "と共に",
                "とともに",
                "together with; at the same time as",
                20,
                1,
                "exp",
            ),
            (
                "ともに",
                "JMdict",
                "short-right",
                "共に",
                "ともに",
                "together; jointly",
                0,
                1,
                "adv",
            ),
        ],
    )

    rows = {
        row["surface"]: row
        for row in analyze_sentence(
            "微笑ましい気持ちになるとともに笑った。",
            SqliteDictionaryProvider(dictionary_path),
        )
    }

    assert rows["とともに"]["canonical"] == "とともに::表現"
    assert rows["とともに"]["translation"] == "together with; at the same time as"
    assert "になると" not in rows
    assert "ともに" not in rows


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


def test_mixed_pos_kanji_food_name_uses_exact_dictionary_token(tmp_path):
    dictionary_path = tmp_path / "dictionary.sqlite"
    write_dictionary(
        dictionary_path,
        [
            (
                "麻辣湯",
                "JMdict",
                "1",
                "麻辣湯",
                "マーラータン",
                "malatang (Sichuan-style spicy street food)",
                10,
                1,
                "n",
            ),
        ],
    )

    rows = analyze_sentence(
        "マーラータン、つまり麻辣湯。",
        SqliteDictionaryProvider(dictionary_path),
    )
    katakana = next(row for row in rows if row["surface"] == "マーラータン")
    kanji = next(row for row in rows if row["surface"] == "麻辣湯")

    assert katakana["canonical"] == "マーラータン::名詞"
    assert kanji["canonical"] == katakana["canonical"]
    assert kanji["hiragana"] == "まーらーたん"
    assert kanji["romaji"] == "ma-ra-tan"
    assert kanji["translation"] == "malatang (Sichuan-style spicy street food)"
    assert kanji["inherited_tokens"] == []
    assert all(row["surface"] not in {"麻", "辣", "湯"} for row in rows)
