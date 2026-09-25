from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from flask import Flask, Response, jsonify, request, send_from_directory

from .analysis_cache import AnalysisCache
from .analyzer import analyze_article, analyze_sentence_with_cache
from .anki_cards import build_anki_tsv
from .anki_connect import AnkiConnectError, anki_status, sync_anki_cards
from .anki_sync_log import AnkiSyncLog, validate_session_id
from .private_articles import is_private_article_input, load_private_article
from .translation_provider import default_translation_provider
from .wiki_api import ArticleRateLimitError, fetch_article_from_input
from .wikidata_places import default_place_provider
from .wikimedia_readings import default_reading_provider


JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = Lock()
ANKI_SYNC_LOCK = Lock()


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    static_dir = base_dir / "static"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="")

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.post("/api/article")
    def article():
        payload = request.get_json(silent=True) or {}
        value = str(payload.get("url") or payload.get("title") or "")
        try:
            article_payload = fetch_article_payload(value, base_dir)
            analysis_cache = AnalysisCache(base_dir / "data" / "analysis_cache.sqlite")
            analyzed = analysis_cache.get(article_payload)
            if analyzed is None:
                analyzed = analyze_article(article_payload, base_dir=base_dir)
                analysis_cache.set(article_payload, analyzed)
        except ArticleRateLimitError as error:
            return jsonify({"error": str(error)}), 429
        except Exception as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(analyzed)

    @app.post("/api/article-jobs")
    def article_jobs():
        payload = request.get_json(silent=True) or {}
        value = str(payload.get("url") or payload.get("title") or "")
        job_id = uuid4().hex
        set_job(
            job_id,
            {
                "id": job_id,
                "status": "queued",
                "message": "Queued",
                "processed": 0,
                "total": 0,
                "progress": 0,
            },
        )
        Thread(
            target=run_article_job,
            args=(job_id, value, base_dir),
            daemon=True,
        ).start()
        return jsonify({"job_id": job_id})

    @app.get("/api/article-jobs/<job_id>")
    def article_job(job_id: str):
        job = get_job(job_id)
        if job is None:
            return jsonify({"error": "Article job not found."}), 404
        return jsonify(job)

    @app.post("/api/place-cache")
    def place_cache():
        payload = request.get_json(silent=True) or {}
        places = payload.get("places") if isinstance(payload, dict) else None
        if not isinstance(places, list):
            return jsonify({"error": "places must be a list"}), 400
        provider = default_place_provider(base_dir)
        return jsonify({"cached": provider.persist_places(places)})

    @app.post("/api/anki-export")
    def anki_export():
        payload = request.get_json(silent=True) or {}
        cards = payload.get("cards") if isinstance(payload, dict) else None
        if not isinstance(cards, list):
            return jsonify({"error": "cards must be a list"}), 400
        try:
            body = build_anki_tsv(cards)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return Response(
            body,
            content_type="text/tab-separated-values; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="japanese-reader-cards.tsv"'
            },
        )

    @app.get("/api/anki/status")
    def anki_connection_status():
        status = anki_status()
        return jsonify(status), 200 if status["connected"] else 503

    @app.post("/api/anki-sync")
    def anki_sync():
        payload = request.get_json(silent=True) or {}
        cards = payload.get("cards") if isinstance(payload, dict) else None
        if not isinstance(cards, list):
            return jsonify({"error": "cards must be a list"}), 400
        try:
            session_id = validate_session_id(str(payload.get("session_id", "")))
            with ANKI_SYNC_LOCK:
                sync_log = AnkiSyncLog(base_dir / "data" / "anki_sync.sqlite")
                previous = sync_log.get(session_id)
                if previous is not None:
                    return jsonify({**previous, "replayed": True})
                result = sync_anki_cards(cards)
                sync_log.save(session_id, result)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except AnkiConnectError as error:
            return jsonify({"error": str(error)}), 503
        return jsonify(result)

    return app


def run_article_job(job_id: str, value: str, base_dir: Path) -> None:
    try:
        update_job(job_id, status="fetching", message="Fetching article...", progress=0.02)
        article_payload = fetch_article_payload(value, base_dir)
        analysis_cache = AnalysisCache(base_dir / "data" / "analysis_cache.sqlite")
        cached_analysis = analysis_cache.get(article_payload)
        if cached_analysis is not None:
            update_job(
                job_id,
                status="complete",
                message="Article ready from cache.",
                processed=len(cached_analysis.get("sentences", [])),
                total=len(cached_analysis.get("sentences", [])),
                progress=1,
                article=cached_analysis,
            )
            return
        sentence_entries = list(article_payload.get("sentences", []))
        total = len(sentence_entries)
        result = {
            **{
                key: article_payload.get(key)
                for key in ("title", "canonicalurl", "revision_id", "revision_timestamp")
            },
            "sentences": [],
        }
        update_job(
            job_id,
            status="analyzing",
            message=f"Analyzing sentence 0 of {total}...",
            processed=0,
            total=total,
            progress=0 if total else 1,
        )
        provider = default_translation_provider(base_dir)
        gazetteer = default_place_provider(base_dir)
        readings = default_reading_provider(base_dir)
        for index, sentence_entry in enumerate(sentence_entries, start=1):
            result["sentences"].append(
                {
                    "id": f"sentence-{index}",
                    **analyze_sentence_with_cache(
                        sentence_entry,
                        translation_provider=provider,
                        place_provider=gazetteer,
                        reading_provider=readings,
                    ),
                }
            )
            update_job(
                job_id,
                message=f"Analyzing sentence {index} of {total}...",
                processed=index,
                total=total,
                progress=index / total if total else 1,
            )
        update_job(
            job_id,
            status="complete",
            message="Article ready.",
            processed=total,
            total=total,
            progress=1,
            article=result,
        )
        analysis_cache.set(article_payload, result)
    except ArticleRateLimitError as error:
        update_job(job_id, status="error", message=str(error), error=str(error), progress=0)
    except Exception as error:
        update_job(job_id, status="error", message=str(error), error=str(error), progress=0)


def fetch_article_payload(value: str, base_dir: Path) -> dict[str, Any]:
    if is_private_article_input(value):
        return load_private_article(value, base_dir=base_dir)
    return fetch_article_from_input(value, cache_dir=base_dir / "data")


def set_job(job_id: str, values: dict[str, Any]) -> None:
    with JOBS_LOCK:
        JOBS[job_id] = dict(values)


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job is not None else None


def update_job(job_id: str, **values: Any) -> None:
    with JOBS_LOCK:
        if job_id not in JOBS:
            return
        JOBS[job_id].update(values)


if __name__ == "__main__":
    create_app().run(debug=False, port=5001)
