from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_only_explicit_unrecognized_marks_supply_card_context():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'choice !== "unrecognized"' in script
    assert "surface: context.surface" in script
    assert "sentence: context.sentence" in script
    assert "function failedContextFields(canonical)" in script


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
    assert "right.difference - left.difference" in script
