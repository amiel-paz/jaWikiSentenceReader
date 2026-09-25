import pytest

from wiki_reader.anki_connect import (
    MODEL_FIELDS,
    MODEL_NAME,
    AnkiConnectError,
    anki_status,
    sync_anki_cards,
)


def sample_card(canonical="離れる::動詞", review_state="again"):
    return {
        "canonical": canonical,
        "expression": canonical.split("::", 1)[0],
        "surface": "離れ",
        "hiragana": "はなれる",
        "romaji": "hanareru",
        "translation": "to leave",
        "sentence": "地元を離れた。",
        "article_title": "記事",
        "source_url": "https://example.test/article",
        "vocabulary_id": "JMdict:123",
        "dictionary_source": "JMdict",
        "review_state": review_state,
    }


class FakeClient:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls = []

    def invoke(self, action, **params):
        self.calls.append((action, params))
        values = self.responses.get(action)
        if not values:
            raise AssertionError(f"Unexpected AnkiConnect action: {action}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_new_note_is_promoted_out_of_new_queue_then_answered_again():
    client = FakeClient(
        {
            "version": [6],
            "createDeck": [1],
            "modelNames": [[]],
            "createModel": [{"id": 2}],
            "findNotes": [[]],
            "addNotes": [[101]],
            "notesInfo": [[{"noteId": 101, "cards": [201]}]],
            "changeDeck": [None],
            "cardsInfo": [
                [{"cardId": 201, "type": 0}],
                [{"cardId": 201, "type": 2}],
            ],
            "findCards": [[201]],
            "setDueDate": [True],
            "answerCards": [[True]],
        }
    )

    result = sync_anki_cards([sample_card()], client=client)

    assert result["created"] == 1
    assert result["promoted_to_review"] == 1
    assert result["scheduled"] == {"again": 1}
    assert ("setDueDate", {"cards": [201], "days": "0"}) in client.calls
    assert ("answerCards", {"answers": [{"cardId": 201, "ease": 1}]}) in client.calls


def test_existing_review_notes_are_updated_and_use_good_and_easy():
    note_info = [
        {
            "noteId": 101,
            "cards": [201],
            "fields": {"TokenId": {"value": "離れる::動詞"}},
        },
        {
            "noteId": 102,
            "cards": [202],
            "fields": {"TokenId": {"value": "南国::名詞"}},
        },
    ]
    client = FakeClient(
        {
            "version": [6],
            "createDeck": [1],
            "modelNames": [[MODEL_NAME]],
            "modelFieldNames": [MODEL_FIELDS],
            "findNotes": [[101, 102]],
            "notesInfo": [note_info, note_info],
            "multi": [[{"result": None, "error": None}, {"result": None, "error": None}]],
            "changeDeck": [None],
            "cardsInfo": [[{"cardId": 201, "type": 2}, {"cardId": 202, "type": 2}]],
            "findCards": [[]],
            "answerCards": [[True, True]],
        }
    )
    cards = [
        sample_card(review_state="good"),
        sample_card(canonical="南国::名詞", review_state="easy"),
    ]

    result = sync_anki_cards(cards, client=client)

    assert result["created"] == 0
    assert result["updated"] == 2
    assert result["promoted_to_review"] == 0
    assert result["scheduled"] == {"good": 1, "easy": 1}
    assert not any(action == "setDueDate" for action, _ in client.calls)
    assert (
        "answerCards",
        {
            "answers": [
                {"cardId": 201, "ease": 3},
                {"cardId": 202, "ease": 4},
            ]
        },
    ) in client.calls


def test_sync_rejects_missing_review_state():
    card = sample_card()
    del card["review_state"]

    with pytest.raises(ValueError, match="review_state"):
        sync_anki_cards([card], client=FakeClient({}))


def test_status_reports_unavailable_connector():
    client = FakeClient({"version": [AnkiConnectError("not running")]})

    assert anki_status(client) == {"connected": False, "error": "not running"}


def test_status_rejects_old_connector_api():
    client = FakeClient({"version": [5]})

    assert anki_status(client) == {
        "connected": False,
        "error": "AnkiConnect API 5 is too old; API 6 is required.",
    }
