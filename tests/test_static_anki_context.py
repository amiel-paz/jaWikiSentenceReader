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
