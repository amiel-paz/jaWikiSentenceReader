from wiki_reader.anki_sync_log import AnkiSyncLog, card_fingerprint


def test_completed_anki_sync_round_trips_by_session_id(tmp_path):
    log = AnkiSyncLog(tmp_path / "anki_sync.sqlite")
    result = {"tokens": 3, "scheduled": {"again": 2, "good": 1}}

    assert log.get("session-12345678") is None
    log.save("session-12345678", result)

    assert log.get("session-12345678") == result


def test_checkpoint_tracks_exact_card_state_and_returns_only_changes(tmp_path):
    log = AnkiSyncLog(tmp_path / "anki_sync.sqlite")
    session_id = "session-12345678"
    card = {
        "canonical": "離れる::動詞",
        "review_state": "again",
        "recognized_count": 0,
        "unrecognized_count": 1,
    }

    pending, fingerprints = log.pending_cards(session_id, [card])
    assert pending == [card]
    assert fingerprints == {"離れる::動詞": card_fingerprint(card)}

    log.save_card_fingerprints(session_id, fingerprints)
    pending, fingerprints = log.pending_cards(session_id, [card])
    assert pending == []
    assert fingerprints == {}

    changed = {**card, "recognized_count": 1, "unrecognized_count": 0}
    pending, fingerprints = log.pending_cards(session_id, [changed])
    assert pending == [changed]
    assert fingerprints == {"離れる::動詞": card_fingerprint(changed)}


def test_card_fingerprint_is_stable_across_mapping_key_order():
    first = {"canonical": "南国::名詞", "review_state": "good"}
    second = {"review_state": "good", "canonical": "南国::名詞"}

    assert card_fingerprint(first) == card_fingerprint(second)


def test_vocabulary_summary_aggregates_sessions_and_current_state(tmp_path):
    log = AnkiSyncLog(tmp_path / "anki_sync.sqlite")
    first_session = "session-12345678"
    second_session = "session-87654321"
    base = {
        "canonical": "離れる::動詞",
        "expression": "離れる",
        "hiragana": "はなれる",
        "romaji": "hanareru",
        "translation": "to leave",
        "source_url": "",
    }
    log.save_summary_cards(
        first_session,
        [
            {
                **base,
                "article_title": "First article",
                "review_state": "again",
                "recognized_count": 1,
                "unrecognized_count": 2,
            }
        ],
    )
    log.save_summary_cards(
        second_session,
        [
            {
                **base,
                "article_title": "Second article",
                "review_state": "easy",
                "recognized_count": 4,
                "unrecognized_count": 0,
            }
        ],
    )

    summary = log.vocabulary_summary(
        current_session_id=first_session,
        current_cards=[
            {
                **base,
                "article_title": "First article",
                "review_state": "good",
                "recognized_count": 3,
                "unrecognized_count": 1,
            }
        ],
    )

    assert summary["session_count"] == 2
    assert summary["token_count"] == 1
    token = summary["tokens"][0]
    assert token["recognized_count"] == 3
    assert token["unrecognized_count"] == 1
    assert token["always_count"] == 1
    assert token["always_recognized"] is False
    assert token["difference"] == 2
    assert token["session_count"] == 2
    assert {item["article_title"] for item in token["sessions"]} == {
        "First article",
        "Second article",
    }


def test_session_history_and_detail_preserve_each_reading_session(tmp_path):
    log = AnkiSyncLog(tmp_path / "anki_sync.sqlite")
    first_session = "session-12345678"
    second_session = "session-87654321"
    log.save_summary_cards(
        first_session,
        [
            {
                "canonical": "離れる::動詞",
                "expression": "離れる",
                "hiragana": "はなれる",
                "romaji": "hanareru",
                "translation": "to leave",
                "article_title": "First article",
                "source_url": "https://example.com/first",
                "review_state": "again",
                "recognized_count": 1,
                "unrecognized_count": 2,
            },
            {
                "canonical": "予約::名詞",
                "expression": "予約",
                "hiragana": "よやく",
                "romaji": "yoyaku",
                "translation": "reservation",
                "article_title": "First article",
                "source_url": "https://example.com/first",
                "review_state": "easy",
                "recognized_count": 0,
                "unrecognized_count": 0,
            },
        ],
    )
    log.save_summary_cards(
        second_session,
        [
            {
                "canonical": "離れる::動詞",
                "expression": "離れる",
                "hiragana": "はなれる",
                "romaji": "hanareru",
                "translation": "to leave",
                "article_title": "Second article",
                "source_url": "https://example.com/second",
                "review_state": "good",
                "recognized_count": 3,
                "unrecognized_count": 0,
            }
        ],
    )
    log.save(first_session, {"tokens": 1})

    sessions = {item["session_id"]: item for item in log.session_history()}
    assert set(sessions) == {first_session, second_session}
    assert sessions[first_session]["article_title"] == "First article"
    assert sessions[first_session]["token_count"] == 2
    assert sessions[first_session]["recognized_count"] == 1
    assert sessions[first_session]["unrecognized_count"] == 2
    assert sessions[first_session]["always_count"] == 1
    assert sessions[first_session]["difference"] == -1
    assert sessions[first_session]["status"] == "completed"
    assert sessions[second_session]["status"] == "logged"

    detail = log.session_detail(first_session)
    assert detail is not None
    assert detail["summary"]["session_count"] == 1
    assert detail["summary"]["token_count"] == 2
    by_token = {
        token["token_id"]: token for token in detail["summary"]["tokens"]
    }
    assert by_token["離れる::動詞"]["recognized_count"] == 1
    assert by_token["離れる::動詞"]["unrecognized_count"] == 2
    assert by_token["予約::名詞"]["always_count"] == 1
    assert log.session_detail("session-missing-12") is None
