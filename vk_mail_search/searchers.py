"""The search contract shared by the benchmark, API and rankers."""

from collections.abc import Mapping
from typing import Protocol

from .data import Document


class Searcher(Protocol):
    def search(self, query: str, mailbox: str, as_of: str | None, k: int) -> list[tuple[str, float]]:
        """Return at most k unique (doc_id, score) tuples, best first."""
        ...


def build_searcher(name: str, docs: Mapping[str, Document]) -> Searcher:
    """Build a standard searcher or a ranking variant for evaluation."""
    base, _, spec = name.partition(":")
    if base in ("dated", "dated-period"):
        from .dated import DatedSearcher

        default = "hybrid" if base == "dated-period" else "bm25"
        inner = build_searcher(spec or default, docs)
        return DatedSearcher(inner, docs.values(), period_first=base == "dated-period")
    if base == "hybrid":
        from .hybrid import HybridSearcher, parse_config

        config = parse_config(spec)
        return HybridSearcher({"bm25": build_searcher("bm25", docs), "dense": build_searcher("dense", docs)}, config)
    if spec:
        raise ValueError(f"Параметры поддерживаются только у hybrid: {name}")
    if name in ("bm25", "bm25-subject"):
        from .bm25 import BM25Searcher

        return BM25Searcher(docs.values(), subject_weight=2.0 if name == "bm25-subject" else 1.0)
    if name == "hybrid-subject":
        from collections import Counter

        from .hybrid import FusionConfig, HybridSearcher

        sizes = Counter(doc.synthetic_user for doc in docs.values())
        config = FusionConfig(depth=max(sizes.values(), default=1))
        return HybridSearcher({"bm25": build_searcher("bm25-subject", docs),
                               "dense": build_searcher("dense", docs)}, config)
    if name == "dense":
        try:
            from .dense import DenseSearcher
        except ModuleNotFoundError as exc:
            if exc.name == f"{__package__}.dense":
                raise ValueError("Для dense подключите ветку task/vk-search-dense.") from exc
            raise RuntimeError("Установите зависимости dense из requirements-embeddings.txt.") from exc
        return DenseSearcher(docs)
    raise ValueError(f"Неизвестный поисковик: {name}. Поддерживаются bm25, bm25-subject, dense, hybrid, "
                     "hybrid-subject, dated:<имя> и dated-period:<гибрид>.")
