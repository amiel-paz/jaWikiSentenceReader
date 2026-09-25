from wiki_reader.anki_sync_log import AnkiSyncLog


def test_completed_anki_sync_round_trips_by_session_id(tmp_path):
    log = AnkiSyncLog(tmp_path / "anki_sync.sqlite")
    result = {"tokens": 3, "scheduled": {"again": 2, "good": 1}}

    assert log.get("session-12345678") is None
    log.save("session-12345678", result)

    assert log.get("session-12345678") == result
