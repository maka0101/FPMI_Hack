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
    identity = {"profile_id": engine.ml.profile_id, "index_version": "v1", "profile_sha256": "a" * 64}
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
    with closing(Engine(FIXTURES, "bm25")) as engine, TestClient(create_app(engine)) as client:
        assert client.get("/").headers["content-type"].startswith("text/html")
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


def test_default_search_returns_top_ten_and_preserves_inbox(tmp_path):
    rows = (FIXTURES / "documents.jsonl").read_text().splitlines()
    receipt = json.loads(rows[0])
    for i in range(8):
        rows.append(json.dumps({**receipt, "doc_id": f"extra-receipt-{i}"}))
    (tmp_path / "documents.jsonl").write_text("\n".join(rows))
    with closing(Engine(tmp_path)) as engine, TestClient(create_app(engine)) as client:
        assert engine.mode == "hybrid" and engine.ml.profile_id == "harrier270"
        mock_ml(engine, [])
        params = {"mailbox": "box-a", "q": "чек"}
        ranked = client.get("/api/search", params={**params, "limit": 20}).json()
        assert len(ranked) == 12
        assert client.get("/api/search", params=params).json() == ranked[:10]
        assert len(client.get("/api/search", params={"mailbox": "box-a"}).json()) == 13


@pytest.mark.parametrize("fields", [
    {"mailbox": "missing"}, {"as_of": "???"}, {"q": "чек 2028-02-31"},
    {"q": "я" * 1001}, {"limit": "many"}, {"limit": 0}, {"limit": 1001},
    {"q": "вчера", "as_of": "0001-01-01"},
])
def test_input_errors(fields):
    with closing(Engine(FIXTURES, "bm25")) as engine, TestClient(create_app(engine)) as client:
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
        ready = {"profile_id": engine.ml.profile_id, "index_version": "v1", "corpus_sha256": "f" * 64}
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


def test_harrier_fusion_prefers_lexical_order_on_conflicting_ranks():
    a, b = ({"doc_id": key} for key in "ab")
    assert fuse([b, a], [a, b], 2, 0.85) == [b, a]
    assert fuse([b, a], [a, b], 2, 0.5) == [a, b]


@pytest.mark.parametrize("expression", [
    "вчерашние", "за вчерашний день", "за 1 октября 2028 года",
    "с 01.10.2028 по 01.10.2028",
])
def test_yesterday_and_single_day_ranges(expression):
    with closing(Engine(FIXTURES, "bm25")) as engine, TestClient(create_app(engine)) as client:
        response = client.get("/api/search", params={**SEARCH, "q": expression})
        assert response.headers["x-search-mode"] == "browse"
        assert response.headers["x-target-day"] == "2028-10-01"
        assert [r["doc_id"] for r in response.json()] == ["receipt-a", "receipt-b"]


@pytest.mark.parametrize("expression,start,end", [
    ("с 30 сентября по 1 октября 2028 года", "2028-09-30", "2028-10-01"),
    ("с 2028-09-30 по 2028-10-01", "2028-09-30", "2028-10-01"),
    ("с 30.09 по 01.10.2028", "2028-09-30", "2028-10-01"),
    ("с 1 по 3 октября", "2028-10-01", "2028-10-03"),
    ("с 31 декабря по 2 января 2028", "2027-12-31", "2028-01-02"),
    ("со вчерашнего дня по сегодня", "2028-10-01", "2028-10-02"),
])
def test_range_filters_and_encoder_text(expression, start, end):
    from mail_search.search import DATE_IN_QUERY, parse_query

    text = f"Чек {expression} из магазина"
    words, period = parse_query(text, DAY)
    assert words == ["чек", "магазина"]
    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)
    assert " ".join(DATE_IN_QUERY.sub(" ", text, count=1).split()) == "Чек из магазина"


@pytest.mark.parametrize("mode", ["bm25", "encoder", "hybrid"])
def test_multiday_api_excludes_invisible_candidates(mode):
    with closing(Engine(FIXTURES, mode)) as engine, TestClient(create_app(engine)) as client:
        if engine.ml:
            ids = ["other-user", "future", "undated", "travel", "receipt-b", "receipt-a"]
            requests = mock_ml(engine, [{"doc_id": i, "score": -n} for n, i in enumerate(ids)])
        response = client.get("/api/search", params={
            **SEARCH, "q": "рейс чек с 30.09.2028 по 03.10.2028", "limit": 10,
        })
        assert response.headers["x-target-from"] == "2028-09-30"
        assert response.headers["x-target-to"] == "2028-10-03"
        assert "x-target-day" not in response.headers
        assert {r["doc_id"] for r in response.json()} == {"travel", "receipt-a", "receipt-b"}
        if engine.ml:
            assert requests[0]["target_range"] == {"start": "2028-09-30", "end": "2028-10-03"}


@pytest.mark.parametrize("expression", ["с 02.10.2028 по 01.10.2028", "с 31 по 32 октября"])
def test_invalid_range(expression):
    with closing(Engine(FIXTURES, "bm25")) as engine, TestClient(create_app(engine)) as client:
        assert client.get("/api/search", params={**SEARCH, "q": expression}).status_code == 400


AROUND = {"mailbox": "box-a", "as_of": "2028-10-02", "anchor_doc_id": "travel", "direction": "around"}


def test_anchors_filter_before_limit_and_read_full_headers(tmp_path):
    rows = (FIXTURES / "documents.jsonl").read_text().splitlines()
    rows.append(json.dumps({
        "doc_id": "header", "synthetic_user": "box-a", "doc_dt": "2028-10-01",
        "doc": "От: " + "А" * 300 + "\nТема: Покупка\nсмета",
    }))
    (tmp_path / "documents.jsonl").write_text("\n".join(rows))
    with closing(Engine(tmp_path, "encoder")) as engine, TestClient(create_app(engine)) as client:
        requests = mock_ml(engine, [{"doc_id": doc_id, "score": -i}
                                    for i, doc_id in enumerate(["header", "travel", "receipt-b"])])
        response = client.get("/api/search/anchors", params={**AROUND, "q": "покупка"})
        assert response.status_code == 200
        assert requests[0]["target_range"] == {"start": "0001-01-01", "end": "2028-10-02"}
        assert requests[0]["limit"] == 3
        assert response.json()[0] == {"doc_id": "header", "subject": "Покупка",
                                      "sender": "А" * 300, "day": "2028-10-01"}
        assert response.json()[1]["sender"] is None
    with closing(Engine(tmp_path, "bm25")) as engine, TestClient(create_app(engine)) as client:
        response = client.get("/api/search/anchors", params={**AROUND, "q": "чек"})
        assert {row["doc_id"] for row in response.json()} == {"receipt-a", "receipt-b"}
        assert client.get("/api/search/anchors", params={**AROUND, "q": " "}).status_code == 400


@pytest.mark.parametrize(("changes", "window", "ids"), [
    ({"direction": "after"}, ("2028-10-01", "2028-10-02"), ["receipt-a", "receipt-b"]),
    ({"direction": "before"}, ("2028-09-27", "2028-09-29"), []),
    ({"days": 7}, ("2028-09-23", "2028-10-02"), ["receipt-a", "receipt-b"]),
    ({"q": "01.10.2028"}, ("2028-10-01", "2028-10-01"), ["receipt-a", "receipt-b"]),
    ({"q": "01.01.2027"}, None, []),
    ({"anchor_doc_id": "receipt-a"}, ("2028-09-28", "2028-10-02"), ["receipt-b", "travel"]),
])
def test_anchor_windows_and_browse(changes, window, ids):
    with closing(Engine(FIXTURES)) as engine, TestClient(create_app(engine)) as client:
        requests = mock_ml(engine, httpx.ConnectError("refused"))
        response = client.get("/api/search/around", params={**AROUND, **changes})
        assert response.status_code == 200
        assert response.headers["X-Search-Mode"] == "browse"
        data = response.json()
        assert data["window"] == ({"start": window[0], "end": window[1]} if window else None)
        assert [row["doc_id"] for row in data["results"]] == ids
        for row in data["results"]:
            assert row["offset_days"] == (date.fromisoformat(row["day"]) -
                                          date.fromisoformat(data["anchor"]["day"])).days
        assert requests == []


def test_invalid_anchor_requests():
    with closing(Engine(FIXTURES, "bm25")) as engine, TestClient(create_app(engine)) as client:
        for doc_id in ("missing", "undated", "future", "other-user"):
            response = client.get("/api/search/around", params={**AROUND, "anchor_doc_id": doc_id})
            assert response.status_code == 404
            assert response.json() == {"error": "Письмо-ориентир недоступно"}
        for invalid in ({"days": 4}, {"direction": "next"}):
            assert client.get("/api/search/around", params={**AROUND, **invalid}).status_code == 400


def test_hybrid_anchor_range_and_fallback(tmp_path):
    rows = (FIXTURES / "documents.jsonl").read_text().splitlines()
    rows.extend(json.dumps({"doc_id": f"competing-{i:02}", "synthetic_user": "box-a",
                            "doc_dt": "2028-09-25", "doc": "Тема: Чек\nЧек чек чек"})
                for i in range(12))
    (tmp_path / "documents.jsonl").write_text("\n".join(rows))
    with closing(Engine(tmp_path)) as engine, TestClient(create_app(engine, True)) as client:
        mock_ml(engine, [])
        params = {**AROUND, "q": "чек"}
        baseline = client.get("/api/search", params=params).json()
        assert len(baseline) == 10
        assert not ({row["doc_id"] for row in baseline} & {"receipt-a", "receipt-b"})
        ids = ["travel", "undated", "other-user", "competing-00", "receipt-b", "receipt-a"]
        requests = mock_ml(engine, [{"doc_id": doc_id, "score": -i} for i, doc_id in enumerate(ids)])
        response = client.get("/api/search/around", params=params)
        assert requests[0]["target_range"] == {"start": "2028-09-27", "end": "2028-10-02"}
        assert requests[0]["limit"] == 51
        assert {row["doc_id"] for row in response.json()["results"]} == {"receipt-a", "receipt-b"}
        mock_ml(engine, httpx.ReadTimeout("test timeout"))
        response = client.get("/api/search/around", params=params)
        assert response.headers["X-Search-Mode"] == "bm25-fallback"
        assert {row["doc_id"] for row in response.json()["results"]} == {"receipt-a", "receipt-b"}
        mock_ml(engine, httpx.ConnectError("refused"))
        assert client.get("/api/search/around", params=params).status_code == 503


def test_fusion_resolves_equal_scores_by_distance():
    far = {"doc_id": "a", "day": "2028-10-06"}
    near = {"doc_id": "b", "day": "2028-10-02"}
    assert fuse([far], [near], 2) == [far, near]
    assert fuse([far], [near], 2, near_day=DAY) == [near, far]
