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
