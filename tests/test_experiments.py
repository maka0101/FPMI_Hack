import json
from pathlib import Path
import sys

import httpx
import pytest

from mail_search.__main__ import main
from mail_search.experiments import compare_queries, evaluate, latency, read_queries, run_compare
from mail_search.loadtest import sample
from mail_search.search import read_jsonl


FIXTURE = Path(__file__).parent / "fixtures"


def test_quality_denominators_and_rank_changes():
    baseline = [{"query_id": "multi", "doc_ids": ["x", "a"]},
                {"query_id": "single", "doc_ids": ["z"]},
                {"query_id": "unjudged", "doc_ids": []}]
    candidate = [{"query_id": "multi", "doc_ids": ["a", "b"]},
                 {"query_id": "single", "doc_ids": ["x"]},
                 {"query_id": "unjudged", "doc_ids": []}]
    gold = {"multi": {"a": 2, "b": 1}, "single": {"z": 1}}
    metrics = evaluate(baseline, gold, 2)
    assert metrics["recall"] == metrics["mrr"] == .75
    assert metrics["mrr_single_hit"] == 1.0
    assert metrics["judged_queries"] == 2
    deltas, counts = compare_queries(baseline, candidate, gold, 2)
    assert counts["recall"] == {"improved": 1, "regressed": 1, "equal": 0}
    assert deltas[0]["rank_changes"][2] == {
        "doc_id": "b", "bm25_rank": None, "candidate_rank": 2, "relevance": 1}
    assert deltas[2]["metric_deltas"] == {}


def test_export_without_any_qrels(tmp_path, monkeypatch):
    (tmp_path / "documents.jsonl").write_bytes((FIXTURE / "documents.jsonl").read_bytes())
    output = tmp_path / "nested" / "ids.jsonl"
    monkeypatch.setattr(sys, "argv", ["mail_search", "--data", str(tmp_path), "export", "--mode", "bm25",
                        "--queries", str(FIXTURE / "queries_dev.jsonl"), "--output", str(output)])
    assert main() == 0
    rows = list(read_jsonl(output))
    assert len(rows) == 2
    assert set(rows[0]["doc_ids"]) == {"receipt-a", "receipt-b"}


def test_compare_publishes_consistent_fixture_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "indexes"))
    out = tmp_path / "report"
    report = run_compare(FIXTURE, ["encoder-a", "encoder-b"], FIXTURE / "queries_dev.jsonl",
                         FIXTURE / "qrels_dev.jsonl", 2, out, 3)
    assert json.loads((out / "report.json").read_text()) == report
    assert set(report["runs"]) == {"bm25", "encoder-a/encoder", "encoder-a/hybrid",
                                   "encoder-b/encoder", "encoder-b/hybrid"}
    for name, run in report["runs"].items():
        assert len(list(read_jsonl(out / name / "rankings.jsonl"))) == 2
        assert run["metrics"]["judged_queries"] == 2
        if name != "bm25":
            assert sum(run["vs_bm25"]["ndcg"].values()) == 2
            assert len(list(read_jsonl(out / name / "deltas.jsonl"))) == 2
    for name, model in report["models"].items():
        assert model["ready"]["profile_id"] == model["config"]["profile_id"] == name
        assert model["prepare_ms"] > 0 and model["ml_ready_ms"] > 0


@pytest.mark.parametrize("mode_header,timing,expected", [
    ("hybrid", "search;dur=77.5", (77.5, None)),
    ("bm25-fallback", "search;dur=0.1", (None, "unexpected mode: bm25-fallback")),
    ("hybrid", "network;dur=10", (None, "missing search duration")),
])
def test_http_samples_require_mode_and_server_duration(mode_header, timing, expected):
    def respond(request):
        return httpx.Response(200, headers={"X-Search-Mode": mode_header,
                                          "Server-Timing": timing}, json=[])
    query = read_queries(FIXTURE / "queries_dev.jsonl")[0]
    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        assert sample(client, query, 10, "hybrid") == expected
    assert latency(range(1, 101))["p99"] == 99
