from pathlib import Path

from wiki_reader.anki_connect import MODEL_EXPRESSION_SIZE


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_reader_and_card_preview_match_native_anki_expression_size():
    styles = (PROJECT_ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    variable = f"--native-anki-expression-size: {MODEL_EXPRESSION_SIZE};"
    use = "font-size: var(--native-anki-expression-size);"

    assert variable in styles
    assert styles.count(use) >= 3
