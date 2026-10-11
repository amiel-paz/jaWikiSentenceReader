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

        def session_history(self):
            sessions = []
            for session_id, cards in self.summaries.items():
                values = list(cards.values())
                recognized = sum(
                    int(card.get("recognized_count", 0))
                    for card in values
                    if card.get("review_state") != "easy"
                )
                unrecognized = sum(
                    int(card.get("unrecognized_count", 0))
                    for card in values
                    if card.get("review_state") != "easy"
                )
                sessions.append(
                    {
                        "session_id": session_id,
                        "article_title": values[0].get("article_title") or "Untitled article",
                        "source_url": values[0].get("source_url", ""),
                        "token_count": len(values),
                        "recognized_count": recognized,
                        "unrecognized_count": unrecognized,
                        "always_count": sum(
                            card.get("review_state") == "easy" for card in values
                        ),
                        "difference": recognized - unrecognized,
                        "first_saved_at": "2026-10-10 20:00:00",
                        "last_saved_at": "2026-10-10 21:00:00",
                        "completed_at": (
                            "2026-10-10 21:00:00"
                            if session_id in self.completed
                            else None
                        ),
                        "status": (
                            "completed" if session_id in self.completed else "logged"
                        ),
                    }
                )
            return sessions

        def session_detail(self, session_id):
            from wiki_reader.anki_sync_log import (
                aggregate_vocabulary_summary,
                summary_card_record,
                validate_session_id,
            )

            validate_session_id(session_id)
            cards = self.summaries.get(session_id)
            if cards is None:
                return None
            session = next(
                item
                for item in self.session_history()
                if item["session_id"] == session_id
            )
            return {
                **session,
                "summary": aggregate_vocabulary_summary(
                    [summary_card_record(session_id, card) for card in cards.values()]
                ),
            }

    monkeypatch.setattr(app_module, "AnkiSyncLog", MemorySyncLog)

    class EmptyAlwaysRecognizedStore:
        def __init__(self, path):
            self.path = path

        def tokens(self):
            return []

        def payload(self):
            return {"token_ids": [], "tokens": []}

    monkeypatch.setattr(
        app_module, "AlwaysRecognizedStore", EmptyAlwaysRecognizedStore
    )
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


def test_session_summary_excludes_counts_from_other_saved_sessions(monkeypatch):
    memory_log = install_memory_sync_log(monkeypatch)
    older_session = "session-older-1234"
    current_session = "session-current-12"
    older = sample_card(
        expression="ギリギリ",
        canonical="ギリギリ::副詞",
        recognized_count=0,
        unrecognized_count=2,
    )
    memory_log.summaries[older_session] = {older["canonical"]: older}
    current = {
        **older,
        "unrecognized_count": 1,
        "article_title": "今日も彼女たちがご機嫌な理由",
    }
    client = app_module.create_app().test_client()

    response = client.post(
        "/api/summary",
        json={
            "session_id": current_session,
            "cards": [current],
            "scope": "session",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session_count"] == 1
    assert payload["tokens"][0]["recognized_count"] == 0
    assert payload["tokens"][0]["unrecognized_count"] == 1
    assert payload["tokens"][0]["sessions"] == [
        {
            "session_id": current_session,
            "article_title": "今日も彼女たちがご機嫌な理由",
            "source_url": "",
        }
    ]


def test_saved_session_history_lists_and_opens_individual_session(monkeypatch):
    memory_log = install_memory_sync_log(monkeypatch)
    card = sample_card(
        expression="ギリギリ",
        canonical="ギリギリ::副詞",
        hiragana="ぎりぎり",
        romaji="girigiri",
        translation="just barely",
        article_title="今日も彼女たちがご機嫌な理由",
        source_url="https://ncode.syosetu.com/n1122lc/",
        recognized_count=1,
        unrecognized_count=3,
    )
    memory_log.summaries[SESSION_ID] = {card["canonical"]: card}
    memory_log.completed[SESSION_ID] = {"ended": True}
    client = app_module.create_app().test_client()

    history = client.get("/api/session-history")
    detail = client.get(f"/api/session-history/{SESSION_ID}")
    missing = client.get("/api/session-history/session-missing-12")

    assert history.status_code == 200
    assert history.get_json()["sessions"][0]["article_title"] == (
        "今日も彼女たちがご機嫌な理由"
    )
    assert history.get_json()["sessions"][0]["status"] == "completed"
    assert detail.status_code == 200
    assert detail.get_json()["summary"]["token_count"] == 1
    assert detail.get_json()["summary"]["tokens"][0]["unrecognized_count"] == 3
    assert missing.status_code == 404


def test_easy_card_is_saved_for_summary_but_never_sent_to_anki(monkeypatch):
    memory_log = install_memory_sync_log(monkeypatch)
    calls = []

    monkeypatch.setattr(app_module, "sync_anki_cards", lambda cards: calls.append(cards))
    client = app_module.create_app().test_client()
    easy = sample_card(
        expression="予約",
        canonical="予約::名詞",
        review_state="easy",
        recognized_count=0,
        unrecognized_count=0,
    )

    response = client.post(
        "/api/anki-checkpoint",
        json={
            "session_id": SESSION_ID,
            "cards": [easy],
            "summary_cards": [easy],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["tokens"] == 0
    assert calls == []
    assert memory_log.summaries[SESSION_ID]["予約::名詞"]["review_state"] == "easy"


def test_sync_cards_and_summary_cards_are_kept_separate(monkeypatch):
    memory_log = install_memory_sync_log(monkeypatch)
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
    again = sample_card()
    easy = sample_card(canonical="予約::名詞", review_state="easy")

    response = client.post(
        "/api/anki-checkpoint",
        json={
            "session_id": SESSION_ID,
            "cards": [again],
            "summary_cards": [again, easy],
        },
    )

    assert response.status_code == 200
    assert calls == [[again]]
    assert set(memory_log.summaries[SESSION_ID]) == {
        "離れる::動詞",
        "予約::名詞",
    }
