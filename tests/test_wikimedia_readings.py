from wiki_reader.wikimedia_readings import extract_reading_for_term, parenthetical_pairs


def test_spaced_person_name_is_normalized_before_matching():
    extract = "菅田 将暉（すだ まさき、1993年2月21日 - ）は、日本の俳優。"

    assert parenthetical_pairs(extract) == [("菅田将暉", "すだまさき")]
    assert extract_reading_for_term(
        "菅田将暉",
        {
            "title": "菅田将暉",
            "extract": extract,
            "canonicalurl": "https://ja.wikipedia.org/wiki/菅田将暉",
            "pageprops": {"wikibase_item": "Q1322323"},
        },
    ) == {
        "hiragana": "すだまさき",
        "source": "jawiki",
        "source_title": "菅田将暉",
        "source_url": "https://ja.wikipedia.org/wiki/菅田将暉",
        "source_id": "Q1322323",
        "romaji": "suda masaki",
    }
