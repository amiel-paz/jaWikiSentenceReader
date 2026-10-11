from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from flask import Flask, Response, jsonify, request, send_from_directory

from .always_recognized import (
    AlwaysRecognizedStore,
    merge_always_recognized_summary,
)
from .analysis_cache import AnalysisCache
from .analyzer import analyze_article, analyze_sentence_with_cache
from .anki_cards import build_anki_tsv
from .anki_connect import AnkiConnectError, anki_status, sync_anki_cards
from .anki_sync_log import (
    AnkiSyncLog,
    aggregate_vocabulary_summary,
    summary_card_record,
    validate_session_id,
)
from .private_articles import is_private_article_input, load_private_article
from .sentence_aids import (
    SentenceAidError,
    get_or_generate_sentence_aid,
    hydrate_article_sentence_aids,
)
from .translation_provider import default_translation_provider
from .wiki_api import ArticleRateLimitError, fetch_article_from_input
from .wikidata_places import default_place_provider
from .wikimedia_readings import default_reading_provider


JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = Lock()
ANKI_SYNC_LOCK = Lock()
SENTENCE_AID_LOCK = Lock()
ALWAYS_RECOGNIZED_LOCK = Lock()


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
            if not hydrate_article_sentence_aids(
                analyzed,
                base_dir=base_dir,
                generate_missing=False,
            ):
                with SENTENCE_AID_LOCK:
                    hydrate_article_sentence_aids(analyzed, base_dir=base_dir)
        except ArticleRateLimitError as error:
            return jsonify({"error": str(error)}), 429
        except SentenceAidError as error:
            return jsonify({"error": str(error), "retryable": True}), 503
        except Exception as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(analyzed)

    @app.post("/api/article-jobs")
    def article_jobs():
        payload = request.get_json(silent=True) or {}
        value = str(payload.get("url") or payload.get("title") or "")
        try:
            cached_analysis = get_cached_private_analysis(value, base_dir)
        except Exception as error:
            return jsonify({"error": str(error)}), 400
        if cached_analysis is not None and hydrate_article_sentence_aids(
            cached_analysis,
            base_dir=base_dir,
            generate_missing=False,
        ):
            return jsonify(
                {
                    "status": "complete",
                    "message": "Article ready from cache.",
                    "cached": True,
                    "article": cached_analysis,
                }
            )
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

    @app.post("/api/sentence-aid")
    def sentence_aid():
        payload = request.get_json(silent=True) or {}
        try:
            with SENTENCE_AID_LOCK:
                aid = get_or_generate_sentence_aid(
                    japanese=str(payload.get("japanese", "")),
                    previous=str(payload.get("previous", "")),
                    following=str(payload.get("following", "")),
                    base_dir=base_dir,
                )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except SentenceAidError as error:
            return jsonify({"error": str(error), "retryable": True}), 503
        return jsonify(aid)

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

    @app.get("/api/always-recognized")
    def always_recognized():
        try:
            with ALWAYS_RECOGNIZED_LOCK:
                result = AlwaysRecognizedStore(
                    base_dir / "data" / "always_recognized.json"
                ).payload()
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(result)

    @app.post("/api/always-recognized")
    def update_always_recognized():
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        cards = payload.get("cards")
        token_ids = payload.get("token_ids")
        if not isinstance(enabled, bool):
            return jsonify({"error": "enabled must be a boolean"}), 400
        if cards is not None and not isinstance(cards, list):
            return jsonify({"error": "cards must be a list"}), 400
        if cards is not None and any(not isinstance(card, dict) for card in cards):
            return jsonify({"error": "cards must contain objects"}), 400
        if token_ids is not None and not isinstance(token_ids, list):
            return jsonify({"error": "token_ids must be a list"}), 400
        if cards is None and token_ids is None:
            return jsonify({"error": "cards or token_ids must be provided"}), 400
        try:
            with ALWAYS_RECOGNIZED_LOCK:
                store = AlwaysRecognizedStore(
                    base_dir / "data" / "always_recognized.json"
                )
                result = (
                    store.set_cards(cards, enabled=enabled)
                    if cards is not None
                    else store.set_token_ids(token_ids, enabled=enabled)
                )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(result)

    def sync_anki_request(*, checkpoint: bool):
        payload = request.get_json(silent=True) or {}
        requested_cards = payload.get("cards") if isinstance(payload, dict) else None
        summary_cards = (
            payload.get("summary_cards") if isinstance(payload, dict) else None
        )
        if not isinstance(requested_cards, list):
            return jsonify({"error": "cards must be a list"}), 400
        if any(not isinstance(card, dict) for card in requested_cards):
            return jsonify({"error": "cards must contain objects"}), 400
        if summary_cards is not None and not isinstance(summary_cards, list):
            return jsonify({"error": "summary_cards must be a list"}), 400
        if summary_cards is not None and any(
            not isinstance(card, dict) for card in summary_cards
        ):
            return jsonify({"error": "summary_cards must contain objects"}), 400
        summary_cards = requested_cards if summary_cards is None else summary_cards
        # Always-recognized is a suppression state, never an Anki Easy answer.
        cards = [
            card
            for card in requested_cards
            if str(card.get("review_state", "")).strip() != "easy"
        ]
        try:
            session_id = validate_session_id(str(payload.get("session_id", "")))
            with ANKI_SYNC_LOCK:
                sync_log = AnkiSyncLog(base_dir / "data" / "anki_sync.sqlite")
                previous = None if checkpoint else sync_log.get(session_id)
                if previous is not None:
                    sync_log.save_summary_cards(session_id, summary_cards)
                    return jsonify({**previous, "replayed": True})
                pending, fingerprints = sync_log.pending_cards(session_id, cards)
                if pending:
                    result = sync_anki_cards(pending)
                else:
                    result = {
                        "tokens": 0,
                        "created": 0,
                        "updated": 0,
                        "scheduled": {},
                    }
                result = {
                    **result,
                    "already_logged": len(cards) - len(pending),
                    "checkpoint": checkpoint,
                    "ended": not checkpoint,
                }
                if not checkpoint:
                    sync_log.save(session_id, result)
                sync_log.save_card_fingerprints(session_id, fingerprints)
                sync_log.save_summary_cards(session_id, summary_cards)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except AnkiConnectError as error:
            return jsonify({"error": str(error)}), 503
        return jsonify(result)

    @app.post("/api/anki-checkpoint")
    def anki_checkpoint():
        return sync_anki_request(checkpoint=True)

    @app.post("/api/anki-sync")
    def anki_sync():
        return sync_anki_request(checkpoint=False)

    @app.route("/api/summary", methods=["GET", "POST"])
    def vocabulary_summary():
        payload = request.get_json(silent=True) or {}
        cards = payload.get("cards") if isinstance(payload, dict) else None
        scope = str(payload.get("scope", "history")) if isinstance(payload, dict) else "history"
        session_id = str(payload.get("session_id", "")) if cards is not None else ""
        if scope not in {"history", "session"}:
            return jsonify({"error": "scope must be history or session"}), 400
        if cards is not None and not isinstance(cards, list):
            return jsonify({"error": "cards must be a list"}), 400
        if cards is not None and any(not isinstance(card, dict) for card in cards):
            return jsonify({"error": "cards must contain objects"}), 400
        try:
            if scope == "session":
                current_session_id = validate_session_id(session_id)
                current_cards = cards or []
                summary = aggregate_vocabulary_summary(
                    [
                        summary_card_record(current_session_id, card)
                        for card in current_cards
                    ]
                )
            else:
                sync_log = AnkiSyncLog(base_dir / "data" / "anki_sync.sqlite")
                summary = sync_log.vocabulary_summary(
                    current_session_id=session_id or None,
                    current_cards=cards,
                )
            with ALWAYS_RECOGNIZED_LOCK:
                always_tokens = AlwaysRecognizedStore(
                    base_dir / "data" / "always_recognized.json"
                ).tokens()
            if scope == "session":
                current_ids = {
                    str(card.get("canonical", "")).strip()
                    for card in (cards or [])
                }
                always_tokens = [
                    token
                    for token in always_tokens
                    if str(token.get("canonical", "")).strip() in current_ids
                ]
            summary = merge_always_recognized_summary(summary, always_tokens)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(summary)

    return app


def run_article_job(job_id: str, value: str, base_dir: Path) -> None:
    try:
        update_job(job_id, status="fetching", message="Fetching article...", progress=0.02)
        article_payload = fetch_article_payload(value, base_dir)
        analysis_cache = AnalysisCache(base_dir / "data" / "analysis_cache.sqlite")
        cached_analysis = analysis_cache.get(article_payload)
        if cached_analysis is not None:
            prepare_article_sentence_aids(job_id, cached_analysis, base_dir)
            update_job(
                job_id,
                status="complete",
                message="Article and sentence aids ready from cache.",
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
                progress=(index / total) * 0.7 if total else 0.7,
            )
        analysis_cache.set(article_payload, result)
        prepare_article_sentence_aids(job_id, result, base_dir)
        update_job(
            job_id,
            status="complete",
            message="Article and sentence aids ready.",
            processed=total,
            total=total,
            progress=1,
            article=result,
        )
    except ArticleRateLimitError as error:
        update_job(job_id, status="error", message=str(error), error=str(error), progress=0)
    except Exception as error:
        update_job(job_id, status="error", message=str(error), error=str(error), progress=0)


def fetch_article_payload(value: str, base_dir: Path) -> dict[str, Any]:
    if is_private_article_input(value):
        return load_private_article(value, base_dir=base_dir)
    return fetch_article_from_input(value, cache_dir=base_dir / "data")


def prepare_article_sentence_aids(
    job_id: str,
    article: dict[str, Any],
    base_dir: Path,
) -> None:
    def report(completed: int, total: int) -> None:
        update_job(
            job_id,
            status="generating_aids",
            message=f"Preparing romaji and English {completed} of {total}...",
            processed=completed,
            total=total,
            progress=0.7 + (0.3 * completed / total if total else 0.3),
        )

    if hydrate_article_sentence_aids(
        article,
        base_dir=base_dir,
        generate_missing=False,
        progress=report,
    ):
        return
    with SENTENCE_AID_LOCK:
        hydrate_article_sentence_aids(
            article,
            base_dir=base_dir,
            progress=report,
        )


def get_cached_private_analysis(
    value: str, base_dir: Path
) -> dict[str, Any] | None:
    """Return a private article immediately when its analyzed revision is cached."""
    if not is_private_article_input(value):
        return None
    article_payload = load_private_article(value, base_dir=base_dir)
    analysis_cache = AnalysisCache(base_dir / "data" / "analysis_cache.sqlite")
    return analysis_cache.get(article_payload)


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
