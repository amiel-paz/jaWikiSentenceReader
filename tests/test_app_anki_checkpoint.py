from typing import Any

import wiki_reader.app as app_module
from wiki_reader.anki_connect import AnkiConnectError


SESSION_ID = "session-12345678"


def sample_card(**values: Any) -> dict[str, Any]:
    card = {
        "canonical": "離れる::動詞",
        "review_state": "again",
        "recognized_count": 0,
        "unrecognized_count": 1,
    }
    card.update(values)
    return card


def install_memory_sync_log(monkeypatch):
    class MemorySyncLog:
        completed: dict[str, dict[str, Any]] = {}
        fingerprints: dict[str, dict[str, str]] = {}
        summaries: dict[str, dict[str, dict[str, Any]]] = {}

        def __init__(self, path):
            self.path = path

        def get(self, session_id):
            return self.completed.get(session_id)

        def save(self, session_id, result):
            self.completed[session_id] = result

        def pending_cards(self, session_id, cards):
            from wiki_reader.anki_sync_log import card_fingerprint

            synced = self.fingerprints.get(session_id, {})
            pending = []
            fingerprints = {}
            for card in cards:
                token_id = card["canonical"]
                fingerprint = card_fingerprint(card)
                if synced.get(token_id) == fingerprint:
                    continue
                pending.append(card)
                fingerprints[token_id] = fingerprint
            return pending, fingerprints

        def save_card_fingerprints(self, session_id, fingerprints):
            self.fingerprints.setdefault(session_id, {}).update(fingerprints)

        def save_summary_cards(self, session_id, cards):
            values = self.summaries.setdefault(session_id, {})
            for card in cards:
                values[card["canonical"]] = dict(card)

        def vocabulary_summary(
            self, *, current_session_id=None, current_cards=None
        ):
            from wiki_reader.anki_sync_log import (
                aggregate_vocabulary_summary,
                summary_card_record,
            )

            records = [
                summary_card_record(session_id, card)
                for session_id, cards in self.summaries.items()
                for card in cards.values()
            ]
            if current_session_id and current_cards is not None:
                records = [
                    record
                    for record in records
                    if record["session_id"] != current_session_id
                ]
                records.extend(
                    summary_card_record(current_session_id, card)
                    for card in current_cards
                )
            return aggregate_vocabulary_summary(records)

    monkeypatch.setattr(app_module, "AnkiSyncLog", MemorySyncLog)
    return MemorySyncLog


def test_checkpoint_syncs_only_new_or_changed_cards_and_keeps_session_open(
    monkeypatch,
):
    install_memory_sync_log(monkeypatch)
    calls = []

    def fake_sync(cards):
        calls.append(cards)
        return {
            "tokens": len(cards),
            "created": len(cards),
            "updated": 0,
            "scheduled": {"again": len(cards)},
        }

    monkeypatch.setattr(app_module, "sync_anki_cards", fake_sync)
    client = app_module.create_app().test_client()
    card = sample_card()

    first = client.post(
        "/api/anki-checkpoint",
        json={"session_id": SESSION_ID, "cards": [card]},
    )
    unchanged = client.post(
        "/api/anki-checkpoint",
        json={"session_id": SESSION_ID, "cards": [card]},
    )
    changed_card = sample_card(recognized_count=1, unrecognized_count=0)
    changed = client.post(
        "/api/anki-checkpoint",
        json={"session_id": SESSION_ID, "cards": [changed_card]},
    )

    assert first.status_code == 200
    assert first.get_json()["checkpoint"] is True
    assert first.get_json()["ended"] is False
    assert unchanged.get_json()["tokens"] == 0
    assert unchanged.get_json()["already_logged"] == 1
    assert changed.get_json()["tokens"] == 1
    assert calls == [[card], [changed_card]]


def test_final_sync_skips_unchanged_checkpoint_cards_and_is_retry_safe(monkeypatch):
    install_memory_sync_log(monkeypatch)
    calls = []

    def fake_sync(cards):
        calls.append(cards)
        return {
            "tokens": len(cards),
            "created": len(cards),
            "updated": 0,
            "scheduled": {"again": len(cards)},
        }

    monkeypatch.setattr(app_module, "sync_anki_cards", fake_sync)
    client = app_module.create_app().test_client()
    card = sample_card()

    client.post(
        "/api/anki-checkpoint",
        json={"session_id": SESSION_ID, "cards": [card]},
    )
    final = client.post(
        "/api/anki-sync",
        json={"session_id": SESSION_ID, "cards": [card]},
    )
    replay = client.post(
        "/api/anki-sync",
        json={"session_id": SESSION_ID, "cards": [card]},
    )

    assert final.status_code == 200
    assert final.get_json()["tokens"] == 0
    assert final.get_json()["already_logged"] == 1
    assert final.get_json()["ended"] is True
    assert replay.get_json()["replayed"] is True
    assert calls == [[card]]


def test_failed_checkpoint_does_not_mark_card_as_logged(monkeypatch):
    install_memory_sync_log(monkeypatch)
    attempts = 0

    def fake_sync(cards):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AnkiConnectError("Anki is unavailable")
        return {
            "tokens": len(cards),
            "created": len(cards),
            "updated": 0,
            "scheduled": {"again": len(cards)},
        }

    monkeypatch.setattr(app_module, "sync_anki_cards", fake_sync)
    client = app_module.create_app().test_client()
    payload = {"session_id": SESSION_ID, "cards": [sample_card()]}

    failed = client.post("/api/anki-checkpoint", json=payload)
    retried = client.post("/api/anki-checkpoint", json=payload)

    assert failed.status_code == 503
    assert retried.status_code == 200
    assert retried.get_json()["tokens"] == 1
    assert attempts == 2


def test_summary_includes_saved_cards_and_current_unsynced_state(monkeypatch):
    install_memory_sync_log(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "sync_anki_cards",
        lambda cards: {
            "tokens": len(cards),
            "created": len(cards),
            "updated": 0,
            "scheduled": {"again": len(cards)},
        },
    )
    client = app_module.create_app().test_client()
    saved = sample_card(
        expression="離れる",
        hiragana="はなれる",
        romaji="hanareru",
        translation="to leave",
        article_title="First article",
    )
    client.post(
        "/api/anki-checkpoint",
        json={"session_id": SESSION_ID, "cards": [saved]},
    )
    current = {
        **saved,
        "recognized_count": 2,
        "unrecognized_count": 0,
        "review_state": "good",
    }

    response = client.post(
        "/api/summary",
        json={"session_id": SESSION_ID, "cards": [current]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session_count"] == 1
    assert payload["token_count"] == 1
    assert payload["tokens"][0]["recognized_count"] == 2
    assert payload["tokens"][0]["unrecognized_count"] == 0
    assert payload["tokens"][0]["difference"] == 2
