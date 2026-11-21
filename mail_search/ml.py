"""Prepare immutable vector indexes and serve mailbox-scoped CPU retrieval."""

import argparse
from collections import defaultdict
from datetime import date
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import tempfile
from threading import Lock

from fastapi import FastAPI, HTTPException
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
import uvicorn
import yaml

from .ml_profiles import Digest, Encoder, Profile, file_hash, read_profile, stable_hash
from .search import DATE_IN_QUERY


INDEX_FORMAT = 1


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    synthetic_user: str = Field(min_length=1)
    query: str
    query_date: date
    target_day: date | None = None
    limit: int = Field(ge=1, le=1000)
    corpus_sha256: Digest


class Candidate(BaseModel):
    doc_id: str
    score: float


class CandidateResponse(BaseModel):
    profile_id: str
    profile_sha256: Digest
    index_version: str
    candidates: list[Candidate]


def index_identity(data_dir: Path, profile: Profile) -> dict:
    dependencies = ["numpy"]
    if profile.adapter == "sentence-transformers":
        dependencies.extend(["sentence-transformers", "transformers", "torch", "tokenizers"])
    elif profile.adapter == "onnx-e5":
        dependencies.extend(["onnxruntime", "tokenizers"])
    identity = {
        "format_version": INDEX_FORMAT,
        "corpus_sha256": file_hash(data_dir / "documents.jsonl"),
        "document_settings": profile.document_settings(),
        "runtime": {name: version(name) for name in dependencies},
    }
    return {**identity, "index_version": stable_hash(identity)}


def describe(profile: Profile, manifest: dict) -> dict:
    return {
        **profile.model_dump(exclude={"files_sha256", "weights_dir"}),
        "profile_sha256": stable_hash(profile.model_dump()),
        "index_version": manifest["index_version"],
        "corpus_sha256": manifest["corpus_sha256"],
        "document_count": manifest["document_count"],
        "runtime": manifest["runtime"],
    }


def verified_manifest(directory: Path, identity: dict) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError("index manifest is incompatible with the profile or corpus")
    for name in ("rows.json", "vectors.npy"):
        if file_hash(directory / name) != manifest["files_sha256"][name]:
            raise ValueError(f"index checksum mismatch for {name}")
    return manifest


def build_index(source: Path, directory: Path, profile: Profile, encoder: Encoder, identity: dict) -> dict:
    rows = []
    texts = []
    doc_ids = set()
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for line in stream:
            digest.update(line)
            if not line.strip():
                continue
            document = json.loads(line)
            doc_id, mailbox, day = document["doc_id"], document["synthetic_user"], document["doc_dt"]
            if not isinstance(doc_id, str) or not doc_id or doc_id in doc_ids:
                raise ValueError("empty or duplicate doc_id in corpus")
            if not isinstance(mailbox, str) or not mailbox:
                raise ValueError("empty synthetic_user in corpus")
            doc_ids.add(doc_id)
            rows.append([doc_id, mailbox, date.fromisoformat(day).isoformat() if day is not None else None])
            text = document["doc"].strip() if profile.adapter == "onnx-e5" else document["doc"]
            texts.append(profile.document_template.replace("{doc}", text))
    if digest.hexdigest() != identity["corpus_sha256"]:
        raise ValueError("corpus changed during preparation, run prepare again")
    (directory / "rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    vectors = np.lib.format.open_memmap(directory / "vectors.npy", mode="w+", dtype=np.float32,
                                        shape=(len(rows), profile.dimensions))
    order = range(len(rows))
    batch_size = 64
    if profile.adapter == "onnx-e5":
        # Group similar lengths to reduce padding while preserving the row mapping.
        order = sorted(order, key=lambda idx: len(texts[idx]))
        batch_size = 32
    for start in range(0, len(rows), batch_size):
        batch_rows = list(order[start:start + batch_size])
        encoded = encoder.encode([texts[idx] for idx in batch_rows])
        if encoded.shape != (len(batch_rows), profile.dimensions) or not np.isfinite(encoded).all():
            raise ValueError("encoder returned invalid vectors")
        vectors[batch_rows] = encoded
    vectors.flush()
    del vectors
    manifest = {
        **identity,
        "document_count": len(rows),
        "files_sha256": {name: file_hash(directory / name) for name in ("rows.json", "vectors.npy")},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def prepare(data_dir: Path, profile_id: str) -> dict:
    profile = read_profile(profile_id)
    root = Path(os.getenv("ARTIFACT_DIR", ".artifacts"))
    identity = index_identity(data_dir, profile)
    directory = root / "indexes" / identity["index_version"]
    directory.parent.mkdir(parents=True, exist_ok=True)
    # The lock is per index. Different models and corpora can be prepared concurrently.
    with directory.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if directory.exists():
            return describe(profile, verified_manifest(directory, identity))
        encoder = Encoder(profile, root)
        with tempfile.TemporaryDirectory(dir=directory.parent, prefix=".build-") as staging:
            staged_index = Path(staging) / "index"
            staged_index.mkdir()
            manifest = build_index(data_dir / "documents.jsonl", staged_index, profile, encoder, identity)
            staged_index.rename(directory)
    return describe(profile, manifest)


class VectorIndex:
    def __init__(self, data_dir: Path, profile_id: str):
        profile = read_profile(profile_id)
        root = Path(os.getenv("ARTIFACT_DIR", ".artifacts"))
        identity = index_identity(data_dir, profile)
        directory = root / "indexes" / identity["index_version"]
        manifest = verified_manifest(directory, identity)
        self.metadata = describe(profile, manifest)
        self.encoder = Encoder(profile, root)
        self.query_prefix = profile.query_prefix
        self.strip_query_date = profile.adapter == "onnx-e5"
        self.encode_lock = Lock()
        self.vectors = np.load(directory / "vectors.npy", mmap_mode="r", allow_pickle=False)
        rows = json.loads((directory / "rows.json").read_text(encoding="utf-8"))
        if self.vectors.shape != (len(rows), profile.dimensions) or len(rows) != manifest["document_count"]:
            raise ValueError("invalid index shape")
        self.mailboxes = defaultdict(list)
        for idx, (doc_id, mailbox, day) in enumerate(rows):
            self.mailboxes[mailbox].append((idx, doc_id, day))
        warm = self.encoder.encode([self.query_prefix + "тест"])
        if warm.shape != (1, profile.dimensions) or not np.isfinite(warm).all():
            raise ValueError("encoder failed warm-up")

    def search(self, request: CandidateRequest) -> list[Candidate]:
        as_of = request.query_date.isoformat()
        target = request.target_day.isoformat() if request.target_day else None
        eligible = [(idx, doc_id) for idx, doc_id, day in self.mailboxes.get(request.synthetic_user, ())
                    if (day is None or day <= as_of) and (target is None or day == target)]
        if not eligible:
            return []
        text = request.query
        if self.strip_query_date:
            text = " ".join(DATE_IN_QUERY.sub(" ", text, count=1).split())
        with self.encode_lock:
            query_vector = self.encoder.encode([self.query_prefix + text])[0]
        if not np.isfinite(query_vector).all():
            raise ValueError("encoder returned non-finite query vector")
        indexes, doc_ids = zip(*eligible)
        scores = np.einsum("ij,j->i", self.vectors[list(indexes)], query_vector)
        ranked = sorted(zip(doc_ids, scores), key=lambda hit: (-hit[1], hit[0]))
        return [Candidate(doc_id=doc_id, score=float(score)) for doc_id, score in ranked[:request.limit]]


def create_app(data_dir: Path, profile_id: str) -> FastAPI:
    app = FastAPI(title="Mail Search ML", version="1")
    index = None
    try:
        index = VectorIndex(data_dir, profile_id)
        failure = ""
    except (OSError, ValueError, KeyError, ImportError, RuntimeError, yaml.YAMLError) as exc:
        failure = f"{type(exc).__name__}: {exc}"

    def ready() -> VectorIndex:
        if index is None:
            raise HTTPException(503, detail={"profile_id": profile_id, "error": failure})
        return index

    @app.get("/readyz")
    def readyz():
        return {"status": "ready", **ready().metadata}

    @app.get("/healthz")
    def healthz():
        return {"status": "alive"}

    @app.post("/v1/candidates", response_model=CandidateResponse)
    def candidates(request: CandidateRequest):
        active = ready()
        if request.corpus_sha256 != active.metadata["corpus_sha256"]:
            raise HTTPException(409, detail="corpus_sha256 differs from the prepared index")
        return CandidateResponse(profile_id=profile_id, index_version=active.metadata["index_version"],
                                 profile_sha256=active.metadata["profile_sha256"], candidates=active.search(request))

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(os.getenv("DATA_DIR", "mipt_mail_search_participants")))
    parser.add_argument("--profile", default=os.getenv("MODEL_PROFILE", "encoder-a"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(create_app(args.data, args.profile), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
