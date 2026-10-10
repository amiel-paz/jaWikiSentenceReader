import sqlite3

from wiki_reader.analysis_cache import AnalysisCache, analyzer_version
from wiki_reader.app import (
    get_cached_private_analysis,
    get_job,
    run_article_job,
    set_job,
)
from wiki_reader.private_articles import load_private_article
from wiki_reader.sentence_aids import SentenceAidCache


def article_payload(revision_id=1):
    return {
        "title": "NARUTO -ナルト-",
        "canonicalurl": "https://ja.wikipedia.org/wiki/NARUTO_-ナルト-",
        "revision_id": revision_id,
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "sentences": [{"text": "文。", "headings": []}],
    }


def analyzed_payload():
    return {
        "title": "NARUTO -ナルト-",
        "canonicalurl": "https://ja.wikipedia.org/wiki/NARUTO_-ナルト-",
        "revision_id": 1,
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "sentences": [
            {
                "id": "sentence-1",
                "display_text": "文。",
                "analysis_text": "文。",
                "tokens": [],
                "unique_sentence_cache": {},
            }
        ],
    }


def test_analysis_cache_round_trips_by_revision(tmp_path):
    cache = AnalysisCache(tmp_path / "analysis_cache.sqlite")
    article = article_payload()
    analyzed = analyzed_payload()

    cache.set(article, analyzed)

    assert cache.get(article) == analyzed
    assert cache.get(article_payload(revision_id=2)) is None


def test_article_job_uses_persistent_analysis_cache(monkeypatch, tmp_path):
    article = article_payload()
    analyzed = analyzed_payload()
    AnalysisCache(tmp_path / "data" / "analysis_cache.sqlite").set(article, analyzed)

    def fetch_from_cache(value, *, cache_dir):
        return article

    monkeypatch.setattr("wiki_reader.app.fetch_article_from_input", fetch_from_cache)
    SentenceAidCache(tmp_path / "data" / "sentence_aids.sqlite").set(
        "文。",
        {"romaji": "Bun.", "english": "A sentence."},
    )
    job_id = "cached-job"
    set_job(job_id, {"id": job_id, "status": "queued"})

    run_article_job(job_id, "NARUTO -ナルト-", tmp_path)

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "complete"
    assert job["message"] == "Article and sentence aids ready from cache."
    assert job["processed"] == 1
    assert job["total"] == 1
    assert job["article"]["sentences"][0]["sentence_aid"] == {
        "romaji": "Bun.",
        "english": "A sentence.",
    }


def test_private_article_analysis_can_take_direct_cache_path(tmp_path):
    private_dir = tmp_path / "data" / "private" / "articles"
    private_dir.mkdir(parents=True)
    (private_dir / "sample.json").write_text(
        '{"title":"Sample","text":"文。","canonicalurl":""}',
        encoding="utf-8",
    )
    article = load_private_article("private:sample", base_dir=tmp_path)
    analyzed = {**article, "sentences": []}
    AnalysisCache(tmp_path / "data" / "analysis_cache.sqlite").set(article, analyzed)

    assert get_cached_private_analysis("private:sample", tmp_path) == analyzed
    assert get_cached_private_analysis("Sample", tmp_path) is None


def test_analyzer_version_tracks_dictionary_release_and_private_overrides(tmp_path):
    dictionary = tmp_path / "dictionary.sqlite"
    with sqlite3.connect(dictionary) as connection:
        connection.execute("CREATE TABLE dictionary_metadata(key TEXT, value TEXT)")
        connection.execute(
            "INSERT INTO dictionary_metadata VALUES ('release_tag', 'test-release')"
        )
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    overrides = private_dir / "vocabulary_overrides.json"
    overrides.write_text("{}", encoding="utf-8")

    before = analyzer_version(dictionary)
    overrides.write_text('{"語": {"translation": "word"}}', encoding="utf-8")
    after = analyzer_version(dictionary)

    assert "test-release" in before
    assert before != after
