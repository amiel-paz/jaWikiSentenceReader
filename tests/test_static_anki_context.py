from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_explicit_recognized_and_unrecognized_marks_supply_recent_card_context():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'occurrence.choice === "recognized"' in script
    assert 'occurrence.choice === "unrecognized"' in script
    assert 'if (state.alwaysRecognized.has(canonical))' in script
    assert "pairs.slice(-5)" in script
    assert "surface: context.surface" in script
    assert "sentence: context.sentence" in script
    assert "sentence_romaji: context.sentenceRomaji" in script
    assert "sentence_translation: context.sentenceTranslation" in script
    assert "meaning_key: vocabulary.dictionary_id" in script
    assert "sentenceRomaji: String(aid.romaji" in script
    assert "sentenceTranslation: String(aid.english" in script
    assert "function referenceContextFields(canonical)" in script


def test_card_front_can_prefer_matching_encountered_kana():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "function displayExpression(row)" in script
    assert 'vocabulary.source === "Local override"' in script
    assert "/^[ぁ-ゖァ-ヺー]+$/" in script
    assert 'test(canonical)) return canonical' in script


def test_log_session_checkpoints_without_ending_the_reader():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    markup = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="log-session"' in markup
    assert "Log Session" in markup
    assert 'syncAnkiSession({ checkpoint: true })' in script
    assert '"/api/anki-checkpoint"' in script
    assert "resetToLanding();" not in script[
        script.index('logSessionButton.addEventListener("click"') :
        script.index('endSessionButton.addEventListener("click"')
    ]


def test_persistent_vocabulary_summary_matches_roleplay_sorting_controls():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    markup = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="summary-button"' in markup
    assert 'id="summary-dialog"' in markup
    assert "Most recognized" in markup
    assert "Most unrecognized" in markup
    assert "Best difference" in markup
    assert 'fetch("/api/summary", options)' in script
    assert 'scope: "session"' in script
    assert "in this reading session" in script
    assert "right.difference - left.difference" in script


def test_saved_session_log_lists_and_opens_reading_lookbacks():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    markup = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="study-log-button"' in markup
    assert 'id="study-log-dialog"' in markup
    assert 'id="study-log-list"' in markup
    assert 'id="study-log-detail"' in markup
    assert "Reading sessions" in markup
    assert 'fetch("/api/session-history")' in script
    assert "fetch(`/api/session-history/${encodeURIComponent(sessionId)}`)" in script
    assert "Logged checkpoint" in script
    assert "Ended session" in script


def test_reader_uses_source_neutral_product_name():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    markup = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "Japanese Sentence Reader" in markup
    assert 'articleTitle.textContent = "Japanese Sentence Reader"' in script
    assert "Wikipedia Sentence Reader" not in markup
    assert "Wikipedia Sentence Reader" not in script


def test_sentence_romaji_and_english_are_spoiler_hidden_and_revealed_on_demand():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    markup = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="sentence-aids"' in markup
    assert 'id="sentence-romaji"' in markup
    assert 'id="sentence-english"' in markup
    assert "Reveal romaji + English" in markup
    assert 'fetch("/api/sentence-aid"' in script
    assert "revealedSentenceAids" in script
    assert "scrollSentenceAidsIntoView" in script
    assert ".sentence-aids:not(.revealed) .sentence-aids-content" in styles
    assert ".sentence-aids.revealed .sentence-aids-cover" in styles


def test_cached_private_article_skips_job_polling():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "if (startPayload.article)" in script
    assert "startSession(startPayload.article)" in script


def test_viewing_a_sentence_does_not_auto_track_its_tokens():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    start = script.index("function markSentenceViewed(sentence)")
    end = script.index("\nfunction increment", start)
    viewed_function = script[start:end]

    assert "viewedCounts" not in script
    assert "registerTokenCatalog" not in viewed_function
    assert "increment(" not in viewed_function
    assert "const encounters = counts.encounters;" in script


def test_always_recognized_is_persistent_and_suppressed_from_anki():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/always-recognized")' in script
    assert 'card.review_state !== "easy"' in script
    assert "summary_cards: plan.summaryCards" in script
    assert "Always recognized · suppressed from Anki" in script
    assert "logAlwaysRecognizedForSentence" not in script


def test_active_article_session_survives_reload_until_successful_end():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'ACTIVE_SESSION_STORAGE_PREFIX = "japaneseReaderActiveSession:v1:"' in script
    assert "function persistActiveSession()" in script
    assert "function restoreActiveSession(article)" in script
    assert "sentenceMarks: [...state.sentenceMarks.entries()]" in script
    assert "viewedSentenceIds: [...state.viewedSentenceIds]" in script
    assert 'window.addEventListener("pagehide", persistActiveSession)' in script
    assert "const restoredMarks = restoreActiveSession(article);" in script

    successful_end = script[
        script.index('confirmEndButton.addEventListener("click"') :
        script.index('popover.addEventListener("click"')
    ]
    assert "clearActiveSession();" in successful_end
    assert successful_end.index("await syncAnkiSession()") < successful_end.index(
        "clearActiveSession();"
    )


def test_end_session_confirmation_is_viewport_bounded_and_scrollable():
    styles = (PROJECT_ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    panel_styles = styles[
        styles.index(".confirm-panel {") : styles.index(".confirm-panel h2")
    ]

    assert "max-height: calc(100dvh - 40px);" in panel_styles
    assert "overflow-y: auto;" in panel_styles
    assert "overscroll-behavior: contain;" in panel_styles
    assert "-webkit-overflow-scrolling: touch;" in panel_styles
