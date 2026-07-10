import sqlite3

from wiki_reader.phrase_matcher import tagged_nodes
from wiki_reader.token_utils import get_tagger
from wiki_reader.wikidata_places import WikidataPlaceProvider, place_candidates


def cache_count(path) -> int:
    with sqlite3.connect(path) as connection:
        return int(
            connection.execute("SELECT COUNT(*) FROM wikidata_place_cache").fetchone()[0]
        )


def test_katakana_admin_suffix_place_candidates_are_generated():
    text = "大ロンドンのカムデン区、ランベス区などに居住した。"
    tagged = tagged_nodes(text, get_tagger())

    surfaces = {candidate["surface"] for candidate in place_candidates(tagged, text)}

    assert "カムデン区" in surfaces
    assert "ランベス区" in surfaces


def test_place_results_are_transient_until_explicitly_persisted(tmp_path):
    cache_path = tmp_path / "places.sqlite"
    provider = WikidataPlaceProvider(cache_path)
    payload = {
        "id": "Q202088",
        "label": "カムデン区",
        "description": "ロンドンの区",
        "english_label": "London Borough of Camden",
        "english_description": "borough in the London Region in England",
        "url": "https://ja.wikipedia.org/wiki/カムデン区",
    }

    provider.cache_result("カムデン区", payload)

    assert provider.cached("カムデン区") == payload
    assert cache_count(cache_path) == 0

    persisted = provider.persist_places([{"surface": "カムデン区", **payload}])

    assert persisted == 1
    assert cache_count(cache_path) == 1
    assert WikidataPlaceProvider(cache_path).cached("カムデン区") == payload
