import json

from wiki_reader.always_recognized import (
    AlwaysRecognizedStore,
    merge_always_recognized_summary,
)


def test_always_recognized_store_persists_metadata_and_can_clear(tmp_path):
    path = tmp_path / "always_recognized.json"
    store = AlwaysRecognizedStore(path)
    card = {
        "canonical": "予約::名詞",
        "expression": "予約",
        "hiragana": "よやく",
        "romaji": "yoyaku",
        "translation": "reservation",
        "sentence": "これは保存しない。",
    }

    enabled = store.set_cards([card], enabled=True)

    assert enabled["token_ids"] == ["予約::名詞"]
    assert enabled["tokens"][0]["translation"] == "reservation"
    assert "sentence" not in enabled["tokens"][0]
    assert AlwaysRecognizedStore(path).token_ids() == {"予約::名詞"}

    disabled = store.set_token_ids(["予約::名詞"], enabled=False)
    assert disabled == {"token_ids": [], "tokens": []}


def test_store_accepts_roleplay_token_ids_only_shape(tmp_path):
    path = tmp_path / "always_recognized.json"
    path.write_text(
        json.dumps({"token_ids": ["予約::名詞"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = AlwaysRecognizedStore(path).payload()

    assert payload["token_ids"] == ["予約::名詞"]
    assert payload["tokens"][0]["canonical"] == "予約::名詞"


def test_merge_marks_active_suppression_without_counting_a_reading_session():
    summary = {"tokens": [], "token_count": 0, "session_count": 0}

    merged = merge_always_recognized_summary(
        summary,
        [
            {
                "canonical": "予約::名詞",
                "expression": "予約",
                "hiragana": "よやく",
                "romaji": "yoyaku",
                "translation": "reservation",
            }
        ],
    )

    assert merged["token_count"] == 1
    assert merged["session_count"] == 0
    assert merged["tokens"][0]["always_recognized"] is True
    assert merged["tokens"][0]["always_count"] == 1
