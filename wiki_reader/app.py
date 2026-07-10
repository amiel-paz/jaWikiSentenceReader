from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .analyzer import analyze_article
from .wiki_api import fetch_article_from_input
from .wikidata_places import default_place_provider


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
            article_payload = fetch_article_from_input(value)
            analyzed = analyze_article(article_payload, base_dir=base_dir)
        except Exception as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(analyzed)

    @app.post("/api/place-cache")
    def place_cache():
        payload = request.get_json(silent=True) or {}
        places = payload.get("places") if isinstance(payload, dict) else None
        if not isinstance(places, list):
            return jsonify({"error": "places must be a list"}), 400
        provider = default_place_provider(base_dir)
        return jsonify({"cached": provider.persist_places(places)})

    return app


if __name__ == "__main__":
    create_app().run(debug=False, port=5001)
