from wiki_reader.analysis_cache import AnalysisCache
from wiki_reader.app import get_job, run_article_job, set_job


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
    job_id = "cached-job"
    set_job(job_id, {"id": job_id, "status": "queued"})

    run_article_job(job_id, "NARUTO -ナルト-", tmp_path)

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "complete"
    assert job["message"] == "Article ready from cache."
    assert job["processed"] == 1
    assert job["total"] == 1
    assert job["article"] == analyzed
