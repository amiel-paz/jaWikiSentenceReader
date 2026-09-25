import json

import pytest

from wiki_reader.private_articles import load_private_article


def write_private_article(tmp_path, key, payload):
    article_dir = tmp_path / "data" / "private" / "articles"
    article_dir.mkdir(parents=True)
    (article_dir / f"{key}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_load_private_article_builds_sentences_and_content_revision(tmp_path):
    write_private_article(
        tmp_path,
        "sample",
        {
            "title": "私的な記事",
            "canonicalurl": "https://example.test/article",
            "revision_timestamp": "2026-09-24",
            "text": "最初の文。次の文！",
        },
    )

    article = load_private_article("private:sample", base_dir=tmp_path)

    assert article["title"] == "私的な記事"
    assert article["canonicalurl"] == "https://example.test/article"
    assert article["revision_id"].startswith("private-")
    assert article["sentences"] == [
        {"text": "最初の文。", "headings": []},
        {"text": "次の文！", "headings": []},
    ]


@pytest.mark.parametrize("value", ["private:", "private:../secret", "private:UPPER CASE"])
def test_load_private_article_rejects_invalid_keys(tmp_path, value):
    with pytest.raises(ValueError):
        load_private_article(value, base_dir=tmp_path)
