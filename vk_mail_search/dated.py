"""Put letters received in the period named by the query first; rank them by topic.

Letters outside the period are not dropped: they follow, so a misread date only
reorders the result instead of losing it.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable

from .data import Document
from .hybrid import HybridSearcher
from .query_parser import ParsedQuery, parse_query
from .searchers import Searcher

Hits = list[tuple[str, float]]


class DatedSearcher:
    def __init__(self, inner: Searcher, documents: Iterable[Document], *, period_first: bool = False):
        self.period_hybrid = inner if period_first and isinstance(inner, HybridSearcher) else None
        if period_first and self.period_hybrid is None:
            raise ValueError("Слияние по периоду требует гибридного поисковика")
        self.inner = inner
        by_box: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._sizes: dict[str, int] = defaultdict(int)
        for doc in documents:
            self._sizes[doc.synthetic_user] += 1
            if doc.doc_dt is not None:
                by_box[doc.synthetic_user].append((doc.doc_dt, doc.doc_id))
        self._dated = {box: sorted(rows) for box, rows in by_box.items()}

    def in_period(self, mailbox: str, parsed: ParsedQuery, as_of: str | None) -> list[str]:
        rows = self._dated.get(mailbox, [])
        start, end = parsed.period.start.isoformat(), parsed.period.end.isoformat()
        if as_of is not None:
            end = min(end, as_of)
        lo, hi = bisect_left(rows, (start, "")), bisect_right(rows, (end, "￿"))
        return [doc_id for _, doc_id in rows[lo:hi]]

    def search(self, query: str, mailbox: str, as_of: str | None, k: int) -> Hits:
        return self.search_parsed(parse_query(query, as_of), mailbox, as_of, k)

    def search_parsed(self, parsed: ParsedQuery, mailbox: str, as_of: str | None, k: int) -> Hits:
        if k <= 0:
            return []
        if parsed.period is None:
            return self.inner.search(parsed.text, mailbox, as_of, k)
        period = self.in_period(mailbox, parsed, as_of)
        depth = max(k, self._sizes.get(mailbox, 0))
        inside = set(period)
        if self.period_hybrid is not None and inside and parsed.topic:
            first, rest = self.period_hybrid.search_period(parsed.topic, mailbox, as_of, inside, depth, k)
        else:
            ranked = self.inner.search(parsed.topic, mailbox, as_of, depth) if parsed.topic else []
            first = [(doc_id, score) for doc_id, score in ranked if doc_id in inside]
            rest = [(doc_id, score) for doc_id, score in ranked if doc_id not in inside] if len(period) < k else []
        seen = {doc_id for doc_id, _ in first}
        # Period letters the topic ranker did not return (e.g. no shared words): newest first.
        first += [(doc_id, 0.0) for doc_id in reversed(period) if doc_id not in seen]
        return (first + rest)[:k]
