from __future__ import annotations

import html
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from .anki_cards import DEFAULT_DECK, MAX_CARDS_PER_EXPORT, validated_card


ANKI_CONNECT_URL = "http://127.0.0.1:8765"
ANKI_CONNECT_VERSION = 6
MODEL_NAME = "Japanese Sentence Reader"
MODEL_FIELDS = [
    "TokenId",
    "Expression",
    "Reading",
    "Romaji",
    "Meaning",
    "Surface",
    "Sentence",
    "Article",
    "SourceUrl",
    "Dictionary",
    "SessionStatus",
]
REVIEW_EASE = {"again": 1, "good": 3, "easy": 4}


class AnkiConnectError(RuntimeError):
    pass


class AnkiClient(Protocol):
    def invoke(self, action: str, **params: Any) -> Any: ...


@dataclass
class AnkiConnectClient:
    endpoint: str = ANKI_CONNECT_URL
    timeout: float = 10
    api_key: str | None = None

    def invoke(self, action: str, **params: Any) -> Any:
        payload: dict[str, Any] = {
            "action": action,
            "version": ANKI_CONNECT_VERSION,
        }
        if params:
            payload["params"] = params
        key = self.api_key or os.environ.get("ANKI_CONNECT_KEY")
        if key:
            payload["key"] = key
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError) as error:
            raise AnkiConnectError(
                "Cannot reach AnkiConnect. Keep Anki open and install/enable "
                "AnkiConnect add-on 2055492159."
            ) from error
        if not isinstance(result, dict) or "error" not in result or "result" not in result:
            raise AnkiConnectError("AnkiConnect returned an invalid response.")
        if result["error"]:
            raise AnkiConnectError(f"AnkiConnect {action} failed: {result['error']}")
        return result["result"]


def anki_status(client: AnkiClient | None = None) -> dict[str, Any]:
    connector = client or AnkiConnectClient()
    try:
        version = connector.invoke("version")
        _require_supported_version(version)
    except AnkiConnectError as error:
        return {"connected": False, "error": str(error)}
    return {
        "connected": True,
        "version": version,
        "deck": DEFAULT_DECK,
        "model": MODEL_NAME,
    }


def sync_anki_cards(
    cards: list[dict[str, Any]],
    *,
    client: AnkiClient | None = None,
    deck: str = DEFAULT_DECK,
) -> dict[str, Any]:
    if not cards:
        raise ValueError("No session tokens were supplied for Anki sync.")
    if len(cards) > MAX_CARDS_PER_EXPORT:
        raise ValueError(f"Anki sync is limited to {MAX_CARDS_PER_EXPORT} tokens.")

    normalized = [_validated_sync_card(card) for card in cards]
    by_token: dict[str, dict[str, str]] = {}
    for card in normalized:
        token_id = card["canonical"]
        if token_id in by_token:
            raise ValueError(f"Duplicate token in Anki sync: {token_id}")
        by_token[token_id] = card

    connector = client or AnkiConnectClient()
    _require_supported_version(connector.invoke("version"))
    connector.invoke("createDeck", deck=deck)
    _ensure_model(connector)

    note_ids = connector.invoke("findNotes", query=f'note:"{_query_escape(MODEL_NAME)}"')
    existing_info = connector.invoke("notesInfo", notes=note_ids) if note_ids else []
    existing = _notes_by_token(existing_info)

    created_ids: list[int] = []
    target_note_ids: dict[str, int] = {}
    missing_notes: list[dict[str, Any]] = []
    missing_tokens: list[str] = []
    update_actions: list[dict[str, Any]] = []
    for token_id, card in by_token.items():
        fields = _note_fields(card)
        note_id = existing.get(token_id)
        if note_id is None:
            missing_tokens.append(token_id)
            missing_notes.append(_new_note(fields, deck))
            continue
        target_note_ids[token_id] = note_id
        update_actions.append(
            {
                "action": "updateNoteFields",
                "params": {"note": {"id": note_id, "fields": fields}},
            }
        )

    if update_actions:
        results = connector.invoke("multi", actions=update_actions)
        _check_multi_results(results, "update existing notes")
    if missing_notes:
        results = connector.invoke("addNotes", notes=missing_notes)
        if not isinstance(results, list) or len(results) != len(missing_notes):
            raise AnkiConnectError("AnkiConnect returned incomplete addNotes results.")
        for token_id, note_id in zip(missing_tokens, results, strict=True):
            if note_id is None:
                raise AnkiConnectError(f"Anki refused to add token {token_id}.")
            numeric_id = int(note_id)
            target_note_ids[token_id] = numeric_id
            created_ids.append(numeric_id)

    target_info = connector.invoke(
        "notesInfo", notes=list(target_note_ids.values())
    )
    cards_by_note = {
        int(note["noteId"]): [int(card_id) for card_id in note.get("cards", [])]
        for note in target_info
    }
    card_ids = [
        card_id
        for note_id in target_note_ids.values()
        for card_id in cards_by_note.get(note_id, [])
    ]
    if not card_ids:
        raise AnkiConnectError("No Anki cards were generated for the session notes.")
    existing_card_ids = [
        int(card_id)
        for note in existing_info
        for card_id in note.get("cards", [])
    ]
    model_card_ids = list(dict.fromkeys([*existing_card_ids, *card_ids]))
    connector.invoke("changeDeck", cards=model_card_ids, deck=deck)

    card_info = connector.invoke("cardsInfo", cards=card_ids)
    target_non_review = [
        int(card["cardId"])
        for card in card_info
        if int(card.get("type", 0)) != 2
    ]
    model_new = connector.invoke(
        "findCards", query=f'note:"{_query_escape(MODEL_NAME)}" is:new'
    )
    promote_to_review = list(
        dict.fromkeys([*target_non_review, *(int(card_id) for card_id in model_new)])
    )
    if promote_to_review:
        connector.invoke("setDueDate", cards=promote_to_review, days="0")
        promoted_info = connector.invoke("cardsInfo", cards=promote_to_review)
        still_not_review = [
            int(card["cardId"])
            for card in promoted_info
            if int(card.get("type", 0)) != 2
        ]
        if still_not_review:
            raise AnkiConnectError(
                "Anki did not move card(s) into Review: "
                + ", ".join(str(card_id) for card_id in still_not_review)
            )

    answers = []
    scheduled = Counter()
    for token_id, note_id in target_note_ids.items():
        review_state = by_token[token_id]["review_state"]
        note_card_ids = cards_by_note.get(note_id, [])
        if not note_card_ids:
            raise AnkiConnectError(f"Anki note for {token_id} has no cards.")
        for card_id in note_card_ids:
            answers.append({"cardId": card_id, "ease": REVIEW_EASE[review_state]})
            scheduled[review_state] += 1

    answer_results = connector.invoke("answerCards", answers=answers)
    if not isinstance(answer_results, list) or len(answer_results) != len(answers):
        raise AnkiConnectError("AnkiConnect returned incomplete scheduling results.")
    failed = [answer["cardId"] for answer, ok in zip(answers, answer_results, strict=True) if not ok]
    if failed:
        raise AnkiConnectError(
            "Anki could not apply the review answer to card(s): "
            + ", ".join(str(card_id) for card_id in failed)
        )

    priority_cards: dict[int, list[int]] = defaultdict(list)
    for token_id, note_id in target_note_ids.items():
        card = by_token[token_id]
        if card["review_state"] != "good":
            continue
        priority_days = int(card["priority_days"])
        priority_cards[priority_days].extend(cards_by_note.get(note_id, []))
    if priority_cards:
        priority_results = connector.invoke(
            "multi",
            actions=[
                {
                    "action": "setDueDate",
                    "params": {"cards": cards, "days": str(days)},
                }
                for days, cards in sorted(priority_cards.items())
            ],
        )
        _check_multi_results(priority_results, "apply recognition priority")

    return {
        "tokens": len(by_token),
        "created": len(created_ids),
        "updated": len(by_token) - len(created_ids),
        "scheduled": dict(scheduled),
        "priority_due_days": {
            str(days): len(cards) for days, cards in sorted(priority_cards.items())
        },
        "promoted_to_review": len(promote_to_review),
        "deck": deck,
        "model": MODEL_NAME,
    }


def _validated_sync_card(card: dict[str, Any]) -> dict[str, str]:
    normalized = validated_card(card)
    review_state = str(card.get("review_state", "")).strip().lower()
    if review_state not in REVIEW_EASE:
        raise ValueError("Each Anki token needs review_state: again, good, or easy.")
    try:
        recognized = int(card.get("recognized_count", 0))
        unrecognized = int(card.get("unrecognized_count", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("Recognition counts must be non-negative integers.") from error
    if recognized < 0 or unrecognized < 0:
        raise ValueError("Recognition counts must be non-negative integers.")
    normalized["recognized_count"] = str(recognized)
    normalized["unrecognized_count"] = str(unrecognized)
    normalized["review_state"] = review_state
    if review_state == "good":
        expected_priority = recognized - unrecognized
        try:
            priority_days = int(card.get("priority_days", 0))
        except (TypeError, ValueError) as error:
            raise ValueError("Good cards require a positive integer priority_days.") from error
        if expected_priority <= 0 or priority_days != expected_priority:
            raise ValueError(
                "Good cards require recognized_count > unrecognized_count and "
                "priority_days equal to their difference."
            )
        normalized["priority_days"] = str(priority_days)
    else:
        normalized["priority_days"] = ""
    return normalized


def _require_supported_version(value: Any) -> None:
    try:
        version = int(value)
    except (TypeError, ValueError) as error:
        raise AnkiConnectError("AnkiConnect did not report a valid API version.") from error
    if version < ANKI_CONNECT_VERSION:
        raise AnkiConnectError(
            f"AnkiConnect API {version} is too old; API {ANKI_CONNECT_VERSION} is required."
        )


def _ensure_model(client: AnkiClient) -> None:
    names = client.invoke("modelNames")
    if MODEL_NAME not in names:
        client.invoke(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=MODEL_FIELDS,
            css=_model_css(),
            cardTemplates=[
                {
                    "Name": "Recognition",
                    "Front": '<div class="expression">{{Expression}}</div>',
                    "Back": (
                        "{{FrontSide}}<hr id=answer>"
                        '<div class="reading">{{Reading}}</div>'
                        '<div class="romaji">{{Romaji}}</div>'
                        '<div class="meaning">{{Meaning}}</div>'
                        '<div class="surface">Seen as: {{Surface}}</div>'
                        '<div class="sentence">{{Sentence}}</div>'
                        '<div class="source"><a href="{{SourceUrl}}">{{Article}}</a></div>'
                        '<div class="dictionary">{{Dictionary}}</div>'
                    ),
                }
            ],
        )
        return
    fields = client.invoke("modelFieldNames", modelName=MODEL_NAME)
    missing = [field for field in MODEL_FIELDS if field not in fields]
    if missing:
        raise AnkiConnectError(
            f"Existing Anki model {MODEL_NAME!r} is missing fields: "
            + ", ".join(missing)
        )


def _notes_by_token(notes: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for note in notes or []:
        fields = note.get("fields", {})
        token_id = html.unescape(
            str(fields.get("TokenId", {}).get("value", ""))
        ).strip()
        if not token_id:
            continue
        if token_id in result:
            raise AnkiConnectError(f"Duplicate Anki notes exist for token {token_id}.")
        result[token_id] = int(note["noteId"])
    return result


def _note_fields(card: dict[str, str]) -> dict[str, str]:
    dictionary = " · ".join(
        value
        for value in (card.get("dictionary_source", ""), card.get("vocabulary_id", ""))
        if value
    )
    return {
        "TokenId": html.escape(card["canonical"]),
        "Expression": html.escape(card["expression"]),
        "Reading": html.escape(card["hiragana"]),
        "Romaji": html.escape(card["romaji"]),
        "Meaning": html.escape(card["translation"]),
        "Surface": html.escape(card.get("surface", "")),
        "Sentence": html.escape(card.get("sentence", "")).replace("\n", "<br>"),
        "Article": html.escape(card.get("article_title", "")),
        "SourceUrl": html.escape(card.get("source_url", ""), quote=True),
        "Dictionary": html.escape(dictionary),
        "SessionStatus": _session_status(card),
    }


def _new_note(fields: dict[str, str], deck: str) -> dict[str, Any]:
    return {
        "deckName": deck,
        "modelName": MODEL_NAME,
        "fields": fields,
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        "tags": ["ja_sentence_reader"],
    }


def _session_status(card: dict[str, str]) -> str:
    score = (
        f"recognized={card['recognized_count']}; "
        f"unrecognized={card['unrecognized_count']}"
    )
    priority = (
        f"; priority_days={card['priority_days']}" if card["priority_days"] else ""
    )
    return f"{card['review_state']}; {score}{priority}"


def _check_multi_results(results: Any, operation: str) -> None:
    if not isinstance(results, list):
        raise AnkiConnectError(f"AnkiConnect could not {operation}.")
    errors = [item.get("error") for item in results if isinstance(item, dict) and item.get("error")]
    if errors:
        raise AnkiConnectError(f"AnkiConnect could not {operation}: {errors[0]}")


def _query_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _model_css() -> str:
    return """
.card { font-family: -apple-system, BlinkMacSystemFont, sans-serif; text-align: center; }
.expression { font-family: serif; font-size: 2rem; }
.reading { font-size: 1.35rem; font-weight: 700; }
.romaji, .surface, .source, .dictionary { color: #666; margin-top: .35rem; }
.meaning { font-size: 1.1rem; margin-top: 1rem; }
.sentence { border-top: 1px solid #aaa; margin-top: 1rem; padding-top: .8rem; }
.source, .dictionary { font-size: .8rem; }
""".strip()
