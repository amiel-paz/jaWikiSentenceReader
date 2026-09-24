from wiki_reader import wiki_api
from wiki_reader.wiki_api import (
    ArticleCache,
    fetch_article_from_input,
    first_sentence_entries,
    first_sentences,
    sentence_entries,
)


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


def test_article_cache_round_trips_payload(tmp_path):
    cache = ArticleCache(tmp_path / "article_cache.sqlite")
    payload = {
        "title": "夏目漱石",
        "canonicalurl": "https://ja.wikipedia.org/wiki/夏目漱石",
        "revision_id": 1,
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "sentences": [{"text": "文。", "headings": []}],
    }

    cache.set("夏目漱石", payload)

    assert cache.get("夏目漱石") == payload


def test_fetch_article_uses_cache_before_network(monkeypatch, tmp_path):
    cache = ArticleCache(tmp_path / "article_cache.sqlite")
    payload = {
        "title": "夏目漱石",
        "canonicalurl": "https://ja.wikipedia.org/wiki/夏目漱石",
        "revision_id": 1,
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "sentences": [{"text": "文。", "headings": []}],
    }
    cache.set("夏目漱石", payload)

    def fail_fetch(title):
        raise AssertionError(f"network fetch should not run for cached title: {title}")

    monkeypatch.setattr(wiki_api, "fetch_article", fail_fetch)

    assert fetch_article_from_input("夏目漱石", cache_dir=tmp_path) == payload
