"""Shared retrieval and ML protocol for the web application and CLI."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import file_digest
import logging
import math
from pathlib import Path
from threading import Lock
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .search import MailboxIndex, parse_query


class MLUnavailable(RuntimeError):
    pass


class MLTimeout(MLUnavailable):
    pass


class Identity(BaseModel):
    model_config = ConfigDict(strict=True)
    profile_id: Annotated[str, Field(min_length=1)]
    index_version: Annotated[str, Field(min_length=1)]
    profile_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class Ready(Identity):
    corpus_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Candidate(BaseModel):
    model_config = ConfigDict(strict=True)
    doc_id: Annotated[str, Field(min_length=1)]
    score: Annotated[float, Field(allow_inf_nan=False)]


class Ranking(Identity):
    candidates: list[Candidate]


class MLClient:
    def __init__(self, url, timeout, profile_id, corpus_sha256):
        self.http = httpx.Client(base_url=url.rstrip("/") + "/", timeout=timeout, trust_env=False)
        self.profile_id = profile_id
        self.corpus_sha256 = corpus_sha256
        self.identity: Ready | None = None
        self.lock = Lock()

    def request(self, method, path, schema, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
            response.raise_for_status()
            return schema.model_validate_json(response.content)
        except httpx.TimeoutException as exc:
            raise MLTimeout("Превышено время ожидания ML") from exc
        except (httpx.HTTPError, ValidationError) as exc:
            raise MLUnavailable("ML недоступен или вернул некорректный ответ") from exc

    def ready(self, refresh=True):
        with self.lock:
            if refresh or self.identity is None:
                info = self.request("GET", "readyz", Ready)
                if info.profile_id != self.profile_id or info.corpus_sha256 != self.corpus_sha256:
                    raise MLUnavailable("Профиль или корпус ML расходится с конфигурацией backend")
                if self.identity and self.identity != info:
                    raise MLUnavailable("Версия индекса или настройки профиля ML изменились")
                self.identity = info
            return self.identity

    def candidates(self, mailbox, query, as_of, target_day, limit):
        identity = self.ready(refresh=False)
        data = {
            "synthetic_user": mailbox, "query": query, "query_date": as_of.isoformat(),
            "target_day": target_day.isoformat() if target_day else None, "limit": limit,
            "corpus_sha256": self.corpus_sha256,
        }
        ranking = self.request("POST", "v1/candidates", Ranking, json=data)
        if (ranking.profile_id != identity.profile_id or ranking.index_version != identity.index_version
                or ranking.profile_sha256 != identity.profile_sha256):
            raise MLUnavailable("Получены кандидаты другого профиля или версии индекса")
        ids = [candidate.doc_id for candidate in ranking.candidates]
        if len(ids) > limit or len(set(ids)) != len(ids):
            raise MLUnavailable("ML нарушил лимит или вернул повторяющиеся doc_id")
        order = [(-candidate.score, candidate.doc_id) for candidate in ranking.candidates]
        if order != sorted(order):
            raise MLUnavailable("ML вернул кандидатов вне порядка ранжирования")
        return ids


def fuse(lexical, semantic, limit, bm25_weight=0.5):
    scores = {}
    rows = {}
    for ranking, weight in ((lexical, bm25_weight), (semantic, 1 - bm25_weight)):
        for position, row in enumerate(ranking, 1):
            doc_id = row["doc_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (60 + position)
            rows[doc_id] = row
    return [rows[doc_id] for doc_id in sorted(rows, key=lambda key: (-scores[key], key))[:limit]]


class Engine:
    def __init__(self, data_dir: Path, mode="hybrid", profile_id="harrier270",
                 ml_url="http://127.0.0.1:8001", timeout=0.5):
        if mode not in {"bm25", "encoder", "hybrid"}:
            raise ValueError("Неизвестный режим поиска")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Таймаут ML должен быть положительным")
        self.bm25_weight = 0.85 if profile_id == "harrier270" else 0.5
        self.mode = mode
        self.index = MailboxIndex(data_dir)
        self.mailboxes = self.index.mailboxes
        with (data_dir / "documents.jsonl").open("rb") as stream:
            self.corpus_sha256 = file_digest(stream, "sha256").hexdigest()
        self.ml = MLClient(ml_url, timeout, profile_id, self.corpus_sha256) if mode != "bm25" else None
        self.pool = ThreadPoolExecutor(thread_name_prefix="ml-candidates") if mode == "hybrid" else None

    def ready(self):
        info = {"status": "ready", "mode": self.mode, "corpus_sha256": self.corpus_sha256}
        if self.mode == "hybrid":
            info["bm25_weight"] = self.bm25_weight
        if self.ml:
            info.update(self.ml.ready().model_dump())
        return info

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=True)
        if self.ml:
            self.ml.http.close()
        self.index.db.close()

    def search(self, mailbox: str, query: str, as_of: date, limit: int = 10):
        rows, _, _ = self.search_with_info(mailbox, query, as_of, limit)
        return rows

    def search_with_info(self, mailbox, query, as_of, limit, demo_fallback=False):
        if mailbox not in self.mailboxes:
            raise ValueError("Неизвестный почтовый ящик")
        if not 1 <= limit <= 1000:
            raise ValueError("Лимит должен быть от 1 до 1000")
        if len(query) > 1000:
            raise ValueError("Запрос должен содержать не более 1000 символов")
        words, target = parse_query(query, as_of)
        if target and target > as_of:
            return [], self.mode, target
        if not words or self.mode == "bm25":
            return self.index.search_parsed(mailbox, words, as_of, target, limit), "bm25" if words else "browse", target
        if self.mode == "encoder":
            ids = self.ml.candidates(mailbox, query, as_of, target, limit)
            return self.index.candidate_rows(ids, mailbox, as_of, target), self.mode, target

        depth = min(1000, max(50, limit))
        pending = self.pool.submit(self.ml.candidates, mailbox, query, as_of, target, depth)
        lexical = self.index.search_parsed(mailbox, words, as_of, target, depth)
        try:
            ids = pending.result()
        except MLTimeout:
            if not demo_fallback:
                raise
            logging.getLogger(__name__).warning("ML timeout in hybrid demo, returning BM25")
            return lexical[:limit], "bm25-fallback", target
        semantic = self.index.candidate_rows(ids, mailbox, as_of, target)
        return fuse(lexical, semantic, limit, self.bm25_weight), self.mode, target
