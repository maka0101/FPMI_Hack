from contextlib import closing
from datetime import date
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from mail_search.api import create_app
from mail_search.engine import Engine, MLTimeout, fuse


FIXTURES = Path(__file__).with_name("fixtures")
DAY = date(2028, 10, 2)
SEARCH = {"mailbox": "box-a", "q": "чек вчера", "as_of": DAY.isoformat(), "limit": 2}


def mock_ml(engine, candidates, *, ready=None):
    identity = {"profile_id": "encoder-a", "index_version": "v1", "profile_sha256": "a" * 64}
    meta = {**identity, "corpus_sha256": engine.corpus_sha256}
    requests = []

    def handle(request):
        if request.url.path == "/readyz":
            return httpx.Response(200, json=ready if ready is not None else meta)
        assert request.url.path == "/v1/candidates"
        requests.append(json.loads(request.content))
        if isinstance(candidates, Exception):
            raise candidates
        if isinstance(candidates, dict):
            return httpx.Response(200, json={**identity, **candidates})
        return httpx.Response(200, json={**identity, "candidates": candidates})

    engine.ml.http.close()
    engine.ml.http = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://ml.test")
    return requests


def test_public_routes_and_search_parity():
    with closing(Engine(FIXTURES)) as engine, TestClient(create_app(engine)) as client:
        assert client.get("/api/mailboxes").json() == {"box-a": "2028-10-03", "box-b": "2028-10-01"}
        assert client.get("/healthz").status_code == client.get("/readyz").status_code == 200
        response = client.get("/api/search", params=SEARCH)
        assert response.status_code == 200
        assert response.json() == engine.search("box-a", "чек вчера", DAY, 2)
        assert response.headers["x-search-mode"] == "bm25"
        assert response.headers["x-target-day"] == "2028-10-01"
        assert float(response.headers["server-timing"].removeprefix("search;dur=")) >= 0
        for row in response.json():
            assert set(row) == {"doc_id", "subject", "day", "preview"}
            result = client.get("/api/message", params={**SEARCH, "doc_id": row["doc_id"]})
            assert result.json()["body"].startswith("Тема:")
        for inaccessible in ("missing", "future", "other-user"):
            result = client.get("/api/message", params={**SEARCH, "doc_id": inaccessible})
            assert result.status_code == 404
            assert "error" in result.json()
        assert client.get("/missing").json() == {"error": "Страница не найдена"}


@pytest.mark.parametrize("fields", [
    {"mailbox": "missing"}, {"as_of": "???"}, {"q": "чек 2028-02-31"},
    {"q": "я" * 1001}, {"limit": "many"}, {"limit": 0}, {"limit": 1001},
    {"q": "вчера", "as_of": "0001-01-01"},
])
def test_input_errors(fields):
    with closing(Engine(FIXTURES)) as engine, TestClient(create_app(engine)) as client:
        response = client.get("/api/search", params={**SEARCH, **fields})
        assert response.status_code == 400
        assert set(response.json()) == {"error"}


@pytest.mark.parametrize("mode", ["encoder", "hybrid"])
def test_semantic_search_filters_and_browse(mode):
    with closing(Engine(FIXTURES, mode)) as engine, TestClient(create_app(engine)) as client:
        ids = ["other-user", "future", "undated", "travel", "nonexistent", "receipt-a", "receipt-b"]
        requests = mock_ml(engine, [
            {"doc_id": doc_id, "score": -float(i)} for i, doc_id in enumerate(ids)
        ])
        assert client.get("/readyz").json()["index_version"] == "v1"
        params = {**SEARCH, "limit": 10}
        rows = client.get("/api/search", params=params).json()
        assert rows == engine.search("box-a", "чек вчера", DAY, 10)
        assert {r["doc_id"] for r in rows} == {"receipt-a", "receipt-b"}
        assert requests[0] == {
            "synthetic_user": "box-a", "query": "чек вчера", "query_date": "2028-10-02",
            "target_day": "2028-10-01", "limit": 50 if mode == "hybrid" else 10,
            "corpus_sha256": engine.corpus_sha256,
        }
        assert {r["doc_id"] for r in engine.search("box-a", "чек", DAY, 10)} >= {"undated"}
        consulted = len(requests)
        assert [r["doc_id"] for r in engine.search("box-a", "вчера", DAY)] == ["receipt-a", "receipt-b"]
        assert engine.search("box-a", "чек 2028-10-03", DAY) == []
        assert [r["doc_id"] for r in engine.search("box-a", "", DAY)][-1] == "undated"
        assert len(requests) == consulted


@pytest.mark.parametrize("bad", [
    {"index_version": "another", "candidates": []},
    {"profile_id": "another", "candidates": []},
    {"profile_sha256": "b" * 64, "candidates": []},
    {"candidates": [{"doc_id": "repeat", "score": 1}] * 2},
    {"candidates": [{"doc_id": "a", "score": "no"}]},
    {"candidates": [{"doc_id": "z", "score": 0}, {"doc_id": "a", "score": 0}]},
])
def test_incompatible_ml_is_never_substituted(bad):
    with closing(Engine(FIXTURES, "hybrid")) as engine, TestClient(create_app(engine, True)) as client:
        mock_ml(engine, bad)
        assert client.get("/api/search", params=SEARCH).status_code == 503


def test_readiness_pins_corpus_and_profile():
    with closing(Engine(FIXTURES, "encoder")) as engine, TestClient(create_app(engine)) as client:
        ready = {"profile_id": "encoder-a", "index_version": "v1", "corpus_sha256": "f" * 64}
        mock_ml(engine, [], ready=ready)
        assert client.get("/readyz").status_code == 503
        ready.update(corpus_sha256=engine.corpus_sha256, profile_sha256="a" * 64)
        assert client.get("/readyz").status_code == 200
        ready["profile_sha256"] = "b" * 64
        assert client.get("/readyz").status_code == 503


def test_fallback_only_for_hybrid_demo_timeout(caplog):
    with closing(Engine(FIXTURES, "hybrid")) as engine, TestClient(create_app(engine, True)) as client:
        mock_ml(engine, httpx.ReadTimeout("test timeout"))
        response = client.get("/api/search", params=SEARCH)
        assert response.status_code == 200
        assert response.headers["x-search-mode"] == "bm25-fallback"
        assert response.json() == engine.index.search("box-a", "чек вчера", DAY, 2)
        assert "timeout" in caplog.text
        with pytest.raises(MLTimeout):
            engine.search("box-a", "чек вчера", DAY, 2)
        mock_ml(engine, httpx.ConnectError("refused"))
        assert client.get("/api/search", params=SEARCH).status_code == 503


def test_rrf_agreement_and_tie_break():
    a, b, c = ({"doc_id": key} for key in "abc")
    assert fuse([b, a], [c, a], 3) == [a, b, c]


def test_frontend_versions_are_separate_and_demo_is_opt_in(monkeypatch):
    monkeypatch.delenv("MAIL_SEARCH_FRONTEND_V1", raising=False)
    monkeypatch.delenv("MAIL_SEARCH_FRONTEND_V2", raising=False)
    with closing(Engine(FIXTURES)) as engine:
        with TestClient(create_app(engine)) as client:
            assert client.get("/").status_code == 404
            assert client.get("/v1").status_code == 404
            assert client.get("/v2").status_code == 404
            assert client.get("/v2/search.js").status_code == 404
        monkeypatch.setenv("MAIL_SEARCH_FRONTEND_V2", "1")
        with TestClient(create_app(engine)) as client:
            new_page = client.get("/v2")
            assert client.get("/").content == new_page.content
            assert client.get("/v1").status_code == 404
            assert new_page.status_code == 200
            assert 'href="/v1"' not in new_page.text
            script_url = new_page.text.split('<script src="', 1)[1].split('"', 1)[0]
            assert script_url.startswith("/v2/search.js?rev=")
            assert client.get(script_url).status_code == 200
        monkeypatch.setenv("MAIL_SEARCH_FRONTEND_V1", "1")
        with TestClient(create_app(engine)) as client:
            assert client.get("/v1").status_code == 200
            assert client.get("/").content == client.get("/v2").content
