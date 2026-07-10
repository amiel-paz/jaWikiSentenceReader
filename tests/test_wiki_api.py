from wiki_reader.wiki_api import first_sentence_entries, first_sentences, sentence_entries


def test_heading_context_attaches_only_to_first_following_sentence():
    text = (
        "== 生涯 ==\n"
        "=== 生い立ち ===\n"
        "夏目金之助は、幕末の江戸にて出生した。次の文。\n"
        "=== 幼少期 ===\n"
        "別の文。さらに次。"
    )

    entries = sentence_entries(text)

    assert entries == [
        {"text": "夏目金之助は、幕末の江戸にて出生した。", "headings": ["生涯", "生い立ち"]},
        {"text": "次の文。", "headings": []},
        {"text": "別の文。", "headings": ["生涯", "幼少期"]},
        {"text": "さらに次。", "headings": []},
    ]


def test_first_sentence_helpers_still_apply_limit():
    text = "== A ==\n文一。文二。文三。"

    assert first_sentences(text, limit=2) == ["文一。", "文二。"]
    assert len(first_sentence_entries(text, limit=2)) == 2
