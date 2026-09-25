import json

import pytest

from wiki_reader.private_import import (
    finalize_article,
    parse_page_spec,
    stage_article,
)


def test_stage_and_finalize_private_text_article(tmp_path):
    source = tmp_path / "download.txt"
    source.write_text("navigation\nSTART\n第一文です。\n第二文です。\nEND\nfooter", encoding="utf-8")

    draft = stage_article(
        source=source,
        key="sample-article",
        title="サンプル",
        url="https://example.test/article",
        base_dir=tmp_path,
        start_marker="START",
        end_marker="END",
    )

    assert draft.read_text(encoding="utf-8").strip() == "第一文です。\n第二文です。"
    destination = finalize_article("sample-article", base_dir=tmp_path)
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["title"] == "サンプル"
    assert payload["canonicalurl"] == "https://example.test/article"
    assert payload["text"] == "第一文です。\n第二文です。"


def test_stage_refuses_to_overwrite_reviewed_draft(tmp_path):
    source = tmp_path / "download.txt"
    source.write_text("本文です。", encoding="utf-8")
    values = dict(
        source=source,
        key="sample",
        title="Sample",
        url="https://example.test",
        base_dir=tmp_path,
    )
    stage_article(**values)

    with pytest.raises(ValueError, match="already exists"):
        stage_article(**values)


def test_pdf_page_spec_is_one_based_and_deduplicated():
    assert parse_page_spec("1-3,3,5", 5) == [0, 1, 2, 4]

    with pytest.raises(ValueError, match="file has 5"):
        parse_page_spec("6", 5)
