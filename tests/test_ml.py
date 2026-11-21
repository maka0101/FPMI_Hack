from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest
import yaml

from mail_search.ml import create_app, prepare
from mail_search.ml_profiles import Encoder, read_profile

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES = Path(__file__).resolve().parents[1] / "models" / "profiles"


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    data = tmp_path / "data"
    profiles = tmp_path / "profiles"
    artifacts = tmp_path / "artifacts"
    shutil.copytree(FIXTURES, data)
    shutil.copytree(PROFILES, profiles)
    monkeypatch.setenv("ARTIFACT_DIR", str(artifacts))
    monkeypatch.setenv("PROFILE_DIR", str(profiles))
    return data, profiles, artifacts


def request(meta, **updates):
    return {"synthetic_user": "box-a", "query_date": "2028-10-02", "query": "чек вчера",
            "target_day": "2028-10-01", "limit": 2, "corpus_sha256": meta["corpus_sha256"], **updates}


@pytest.mark.parametrize("profile_id", ["encoder-a", "encoder-b"])
def test_scope_before_top_k_and_response_identity(workspace, profile_id):
    data, _, _ = workspace
    meta = prepare(data, profile_id)
    client = TestClient(create_app(data, profile_id))
    ready = client.get("/readyz").json()
    hits = client.post("/v1/candidates", json=request(meta)).json()
    for key in ("profile_id", "index_version", "profile_sha256"):
        assert hits[key] == ready[key] == meta[key]
    assert {row["doc_id"] for row in hits["candidates"]} == {"receipt-a", "receipt-b"}
    # An empty feature vector ties every score, independent of insertion order.
    r = client.post("/v1/candidates", json=request(meta, query="", target_day=None, limit=10))
    assert [row["doc_id"] for row in r.json()["candidates"]] == ["receipt-a", "receipt-b", "travel", "undated"]
    for updates in ({"synthetic_user": "missing"}, {"target_day": "2028-10-03"}):
        assert client.post("/v1/candidates", json=request(meta, **updates)).json()["candidates"] == []
    assert client.post("/v1/candidates", json=request(meta, corpus_sha256="0" * 64)).status_code == 409


def test_immutable_vectors_reused_for_query_changes(workspace, monkeypatch):
    data, profiles, artifacts = workspace
    first = prepare(data, "encoder-a")
    path = artifacts / "indexes" / first["index_version"] / "vectors.npy"
    modified = path.stat().st_mtime_ns
    profile_path = profiles / "encoder-a.yaml"
    config = yaml.safe_load(profile_path.read_text())
    config["query_prefix"] = "запрос "
    profile_path.write_text(yaml.safe_dump(config))
    with monkeypatch.context() as m:
        def forbid_rebuild(*args):
            pytest.fail("unnecessary re-encoding")
        m.setattr(Encoder, "encode", forbid_rebuild)
        second = prepare(data, "encoder-a")
    assert first["index_version"] == second["index_version"]
    assert first["profile_sha256"] != second["profile_sha256"]
    assert path.stat().st_mtime_ns == modified
    config["document_template"] = "документ {doc}"
    profile_path.write_text(yaml.safe_dump(config))
    assert TestClient(create_app(data, "encoder-a")).get("/readyz").status_code == 503
    third = prepare(data, "encoder-a")
    assert third["index_version"] != first["index_version"]
    corpus = data / "documents.jsonl"
    with corpus.open("a") as stream:
        stream.write("\n")
    assert TestClient(create_app(data, "encoder-a")).get("/readyz").status_code == 503
    fourth = prepare(data, "encoder-a")
    assert fourth["index_version"] != third["index_version"]


def test_parallel_prepare_and_damaged_artifact(workspace):
    data, _, artifacts = workspace
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(lambda _: prepare(data, "encoder-a"), range(2))
    assert a == b
    vectors = artifacts / "indexes" / a["index_version"] / "vectors.npy"
    vectors.write_bytes(b"truncated")
    client = TestClient(create_app(data, "encoder-a"))
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    assert client.post("/v1/candidates", json=request(a)).status_code == 503


def test_failed_build_leaves_no_visible_index(workspace):
    data, _, artifacts = workspace
    corpus = data / "documents.jsonl"
    first = corpus.read_text().splitlines()[0]
    with corpus.open("a") as stream:
        stream.write(first + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        prepare(data, "encoder-a")
    assert not list((artifacts / "indexes").glob("*/manifest.json"))


def test_pinned_local_model_stops_before_inference_without_weights(workspace):
    _, profiles, artifacts = workspace
    profile = read_profile("e5-small")
    with pytest.raises(FileNotFoundError):
        Encoder(profile, artifacts)
    path = profiles / "e5-small.yaml"
    config = yaml.safe_load(path.read_text())
    config["tokenizer_revision"] = "main"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="pinned"):
        read_profile("e5-small")
