from pathlib import Path

import wiki_reader.app as app_module
from wiki_reader.sentence_aids import (
    CodexSentenceAidGenerator,
    SentenceAidCache,
    hydrate_article_sentence_aids,
)


def test_sentence_aid_cache_round_trip(tmp_path: Path):
    cache = SentenceAidCache(tmp_path / "sentence-aids.sqlite")

    assert cache.get("猫がいる。") is None
    cache.set(
        "猫がいる。",
        {"romaji": "Neko ga iru.", "english": "There is a cat."},
    )

    assert cache.get("猫がいる。") == {
        "romaji": "Neko ga iru.",
        "english": "There is a cat.",
        "cached": True,
    }


def test_article_sentence_aids_are_batch_generated_cached_and_attached(tmp_path: Path):
    class FakeGenerator:
        def __init__(self):
            self.calls = []

        def generate_batch(self, items):
            self.calls.append(items)
            return {
                item["index"]: {
                    "romaji": f"reading {item['index']}",
                    "english": f"translation {item['index']}",
                    "cached": False,
                }
                for item in items
            }

    article = {
        "sentences": [
            {"display_text": "一文目。"},
            {"display_text": "二文目。"},
        ]
    }
    generator = FakeGenerator()

    assert hydrate_article_sentence_aids(
        article,
        base_dir=tmp_path,
        generator=generator,
    )
    assert len(generator.calls) == 1
    assert generator.calls[0][0]["following"] == "二文目。"
    assert article["sentences"][1]["sentence_aid"] == {
        "romaji": "reading 1",
        "english": "translation 1",
    }

    cached_article = {
        "sentences": [
            {"display_text": "一文目。"},
            {"display_text": "二文目。"},
        ]
    }
    assert hydrate_article_sentence_aids(
        cached_article,
        base_dir=tmp_path,
        generate_missing=False,
    )
    assert cached_article["sentences"][0]["sentence_aid"]["romaji"] == "reading 0"


def test_article_sentence_aids_report_incomplete_cache_without_generating(tmp_path: Path):
    article = {"sentences": [{"display_text": "未生成。"}]}

    assert not hydrate_article_sentence_aids(
        article,
        base_dir=tmp_path,
        generate_missing=False,
    )
    assert "sentence_aid" not in article["sentences"][0]


def test_batch_generator_retries_romaji_that_contains_japanese_script(
    monkeypatch, tmp_path: Path
):
    generator = CodexSentenceAidGenerator(project_root=tmp_path)
    responses = iter(
        [
            {
                "aids": [
                    {
                        "index": 0,
                        "romaji": "waraiaって iru.",
                        "english": "They are laughing together.",
                    }
                ]
            },
            {
                "romaji": "waraiatte iru.",
                "english": "They are laughing together.",
            },
        ]
    )
    monkeypatch.setattr(generator, "_execute", lambda *args, **kwargs: next(responses))

    aids = generator.generate_batch(
        [
            {
                "index": 0,
                "japanese": "笑い合っている。",
                "previous": "",
                "following": "",
            }
        ]
    )

    assert aids[0]["romaji"] == "waraiatte iru."


def test_sentence_aid_endpoint_returns_generated_values(monkeypatch):
    calls = []

    def fake_generate(**values):
        calls.append(values)
        return {
            "romaji": "Waga kuni no oujo denka wa hoshigari oujo da.",
            "english": "Our princess is a princess who always wants things.",
            "cached": False,
        }

    monkeypatch.setattr(app_module, "get_or_generate_sentence_aid", fake_generate)
    client = app_module.create_app().test_client()
    response = client.post(
        "/api/sentence-aid",
        json={
            "japanese": "我が国の王女殿下は欲しがり王女だ。",
            "previous": "",
            "following": "次の文。",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["english"].startswith("Our princess")
    assert calls[0]["japanese"] == "我が国の王女殿下は欲しがり王女だ。"


def test_sentence_aid_endpoint_rejects_empty_text():
    client = app_module.create_app().test_client()
    response = client.post("/api/sentence-aid", json={"japanese": ""})

    assert response.status_code == 400
    assert "non-empty" in response.get_json()["error"]
