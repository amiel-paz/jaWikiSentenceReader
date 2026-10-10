import pytest

from wiki_reader.anki_connect import (
    MODEL_EXPRESSION_SIZE,
    MODEL_FIELDS,
    MODEL_NAME,
    AnkiConnectError,
    _ensure_model,
    anki_status,
    merge_context_examples,
    merge_context_fields,
    merge_meaning_fields,
    sync_anki_cards,
)


def sample_card(canonical="離れる::動詞", review_state="again", **values):
    scores = {
        "again": {"recognized_count": 0, "unrecognized_count": 1},
        "good": {
            "recognized_count": 3,
            "unrecognized_count": 1,
            "priority_days": 2,
        },
        "easy": {"recognized_count": 1, "unrecognized_count": 0},
    }[review_state]
    card = {
        "canonical": canonical,
        "expression": canonical.split("::", 1)[0],
        "surface": "離れ",
        "hiragana": "はなれる",
        "romaji": "hanareru",
        "translation": "to leave",
        "meaning_key": "JMdict:123",
        "sentence": "地元を離れた。",
        "sentence_romaji": "Jimoto o hanareta.",
        "sentence_translation": "I left my hometown.",
        "article_title": "記事",
        "source_url": "https://example.test/article",
        "vocabulary_id": "JMdict:123",
        "dictionary_source": "JMdict",
        "review_state": review_state,
        **scores,
    }
    card.update(values)
    return card


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


def test_existing_model_migrates_sentence_aid_fields_without_reviewing_cards():
    old_fields = [
        field
        for field in MODEL_FIELDS
        if field not in {"MeaningKeys", "SentenceRomaji", "SentenceTranslation"}
    ]
    client = FakeClient(
        {
            "modelNames": [[MODEL_NAME]],
            "modelFieldNames": [old_fields],
            "modelFieldAdd": [None, None, None],
            "updateModelTemplates": [None],
            "updateModelStyling": [None],
        }
    )

    _ensure_model(client)

    assert (
        "modelFieldAdd",
        {"modelName": MODEL_NAME, "fieldName": "MeaningKeys"},
    ) in client.calls
    assert (
        "modelFieldAdd",
        {"modelName": MODEL_NAME, "fieldName": "SentenceRomaji"},
    ) in client.calls
    assert (
        "modelFieldAdd",
        {"modelName": MODEL_NAME, "fieldName": "SentenceTranslation"},
    ) in client.calls
    assert any(action == "updateModelTemplates" for action, _ in client.calls)
    assert any(action == "updateModelStyling" for action, _ in client.calls)
    assert not any(action in {"answerCards", "setDueDate"} for action, _ in client.calls)


def test_meaning_merge_uses_stable_keys_and_normalized_text_without_duplicates():
    meaning, keys = merge_meaning_fields(
        "to stuff into; to jam; to cram; to pack",
        "JMdict:1226510",
        "  To stuff into; to jam; to cram; to pack. ",
        "Local:equivalent-pack-sense",
    )

    assert meaning == "To stuff into; to jam; to cram; to pack."
    assert keys == "JMdict:1226510|Local:equivalent-pack-sense"

    meaning, keys = merge_meaning_fields(
        meaning,
        keys,
        "to grill or press for answers; to call to account",
        "Local:詰める::動詞:press",
    )

    assert meaning == (
        "To stuff into; to jam; to cram; to pack.<br>"
        "to grill or press for answers; to call to account"
    )
    assert keys == (
        "JMdict:1226510|Local:equivalent-pack-sense<br>"
        "Local:詰める::動詞:press"
    )


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
    create_model = next(params for action, params in client.calls if action == "createModel")
    assert create_model["modelName"] == MODEL_NAME
    assert create_model["inOrderFields"] == MODEL_FIELDS
    assert f"font-size: {MODEL_EXPRESSION_SIZE};" in create_model["css"]
    assert create_model["cardTemplates"][0]["Front"] == (
        '<div class="expression">{{Expression}}</div>'
    )


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
            "multi": [
                [{"result": None, "error": None}, {"result": None, "error": None}],
                [True],
            ],
            "changeDeck": [None],
            "cardsInfo": [[{"cardId": 201, "type": 2}, {"cardId": 202, "type": 2}]],
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
    assert result["priority_due_days"] == {"2": 1}
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
    assert (
        "multi",
        {
            "actions": [
                {
                    "action": "setDueDate",
                    "params": {"cards": [201], "days": "2"},
                }
            ]
        },
    ) in client.calls


def test_context_merge_keeps_five_recent_pairs_and_moves_repeat_to_newest():
    surface, sentence = merge_context_fields(
        "一<br>二<br>三<br>四<br>五",
        "例一。<br>例二。<br>例三。<br>例四。<br>例五。",
        "三\n六",
        "例三。\n例六。",
    )

    assert surface == "二<br>四<br>五<br>三<br>六"
    assert sentence == "例二。<br>例四。<br>例五。<br>例三。<br>例六。"


def test_context_merge_keeps_original_romaji_and_translation_aligned():
    surface, sentence, romaji, translation = merge_context_examples(
        "一<br>二<br>三<br>四<br>五",
        "例一。<br>例二。<br>例三。<br>例四。<br>例五。",
        "rei ichi<br>rei ni<br>rei san<br>rei yon<br>rei go",
        "one<br>two<br>three<br>four<br>five",
        "三\n六",
        "例三。\n例六。",
        "rei san\nrei roku",
        "three updated\nsix",
    )

    assert surface == "二<br>四<br>五<br>三<br>六"
    assert sentence == "例二。<br>例四。<br>例五。<br>例三。<br>例六。"
    assert romaji == "rei ni<br>rei yon<br>rei go<br>rei san<br>rei roku"
    assert translation == "two<br>four<br>five<br>three updated<br>six"


def test_sync_appends_new_context_to_existing_note():
    note_info = {
        "noteId": 101,
        "cards": [201],
        "fields": {
            "TokenId": {"value": "離れる::動詞"},
            "Surface": {"value": "離れ"},
            "Sentence": {"value": "前の失敗。"},
        },
    }
    client = FakeClient(
        {
            "version": [6],
            "createDeck": [1],
            "modelNames": [[MODEL_NAME]],
            "modelFieldNames": [MODEL_FIELDS],
            "findNotes": [[101]],
            "notesInfo": [[note_info], [note_info]],
            "multi": [[{"result": None, "error": None}]],
            "changeDeck": [None],
            "cardsInfo": [[{"cardId": 201, "type": 2}]],
            "answerCards": [[True]],
        }
    )

    sync_anki_cards(
        [sample_card(surface="離れて", sentence="次の失敗。")],
        client=client,
    )

    update = next(params for action, params in client.calls if action == "multi")
    fields = update["actions"][0]["params"]["note"]["fields"]
    assert fields["Surface"] == "離れ<br>離れて"
    assert fields["Sentence"] == "前の失敗。<br>次の失敗。"
    assert fields["SentenceRomaji"] == "<br>Jimoto o hanareta."
    assert fields["SentenceTranslation"] == "<br>I left my hometown."


def test_sync_does_not_erase_context_when_incoming_card_has_no_example():
    surface, sentence = merge_context_fields(
        "離れ",
        "以前わからなかった文。",
        "",
        "",
    )

    assert surface == "離れ"
    assert sentence == "以前わからなかった文。"


def test_sync_only_moves_and_promotes_cards_in_the_current_batch():
    existing_info = [
        {
            "noteId": 101,
            "cards": [201],
            "fields": {"TokenId": {"value": "離れる::動詞"}},
        },
        {
            "noteId": 999,
            "cards": [299],
            "fields": {"TokenId": {"value": "役割::名詞"}},
        },
    ]
    target_info = [existing_info[0]]
    client = FakeClient(
        {
            "version": [6],
            "createDeck": [1],
            "modelNames": [[MODEL_NAME]],
            "modelFieldNames": [MODEL_FIELDS],
            "findNotes": [[101, 999]],
            "notesInfo": [existing_info, target_info],
            "multi": [[{"result": None, "error": None}]],
            "changeDeck": [None],
            "cardsInfo": [
                [{"cardId": 201, "type": 0}],
                [{"cardId": 201, "type": 2}],
            ],
            "setDueDate": [True],
            "answerCards": [[True]],
        }
    )

    sync_anki_cards([sample_card()], client=client)

    assert ("changeDeck", {"cards": [201], "deck": "Japanese::Sentence Reader"}) in client.calls
    assert ("setDueDate", {"cards": [201], "days": "0"}) in client.calls
    assert not any(action == "findCards" for action, _ in client.calls)
    assert all(299 not in params.get("cards", []) for _, params in client.calls)


def test_sync_rejects_missing_review_state():
    card = sample_card()
    del card["review_state"]

    with pytest.raises(ValueError, match="review_state"):
        sync_anki_cards([card], client=FakeClient({}))


def test_good_requires_recognition_majority_and_matching_margin():
    card = sample_card(
        review_state="good",
        recognized_count=2,
        unrecognized_count=2,
        priority_days=1,
    )

    with pytest.raises(ValueError, match="recognized_count > unrecognized_count"):
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
