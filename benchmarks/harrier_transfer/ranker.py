"""Mailbox-scoped hybrid retrieval. Scoring never uses evaluation labels."""
from collections import Counter, defaultdict
from datetime import date
from math import log1p
import re

from mail_search.period_search import parse_query
from mail_search.search import normalize, WORD

# Group frequent inflectional endings while preserving short words and identifiers.
ENDING = re.compile(r"(иями|ями|ами|ого|его|ому|ему|ыми|ими|иях|ах|ях|ов|ев|ам|ям|ую|юю|ая|яя|ое|ее|ые|ие|ий|ый|ой|ом|ем|а|я|у|ю|е|ы|и|о)$")


def key(word):
    if len(word) < 5 or not word.isalpha():
        return word
    stem = ENDING.sub("", word)
    return stem if len(stem) >= 3 else word


def tokens(text):
    return [key(w) for w in WORD.findall(normalize(text))]


def votes(*arms):
    scores = defaultdict(float)
    for ids, weight in arms:
        for pos, doc_id in enumerate(ids, 1):
            scores[doc_id] += weight / (60 + pos)
    return scores


def ordered(scores):
    return sorted(scores, key=lambda doc_id: (-scores[doc_id], doc_id))


class FieldIndex:
    """Inverted index of title, opening paragraph and remaining body."""
    def __init__(self, documents):
        self.metadata = {}
        self.postings = defaultdict(list)
        for doc in documents:
            doc_id = doc["doc_id"]
            box, day = doc["synthetic_user"], doc["doc_dt"]
            self.metadata[doc_id] = box, day
            if "doc" not in doc:  # Compact metadata for replaying undated experiments.
                continue
            first, _, rest = doc["doc"].strip().partition("\n")
            label, sep, subject = first.partition(":")
            if not sep or normalize(label.strip()) not in {"тема", "subject"}:
                subject, rest = "", doc["doc"]
            body = tokens(rest)
            counts = Counter(body)
            counts.update(body[:32])
            for term, count in Counter(tokens(subject)).items():
                counts[term] += 5 * count
            for term, count in counts.items():
                self.postings[term].append((doc_id, count))

    def field_ranking(self, words, box, lower, upper):
        scores = defaultdict(float)
        for term in sorted({key(word) for word in words}):
            posting = self.postings.get(term, ())
            idf = log1p((len(self.metadata) - len(posting) + 0.5) / (len(posting) + 0.5))
            for doc_id, count in posting:
                owner, day = self.metadata[doc_id]
                if owner == box and day and lower <= day <= upper:
                    scores[doc_id] += idf * count / (count + 2)
        return ordered(scores)[:50]

    def rankings(self, query, box, as_of, lexical, dense):
        words, period = parse_query(query, as_of)
        upper = min(as_of, period.end).isoformat() if period else as_of.isoformat()
        lower = period.start.isoformat() if period else None

        def visible(doc_id):
            owner, day = self.metadata[doc_id]
            return owner == box and (day is None or day <= upper) and (
                lower is None or day is not None and lower <= day
            )

        lex = [d for d in lexical if visible(d)]
        sem = [d for d in dense if visible(d)]
        base = ordered(votes((lex[:50], .85), (sem[:50], 1 - .85))) if words else lex
        if not words:
            return dict.fromkeys(("baseline", "native", "blend", "rerank", "fallback", "fresh_only"), base[:10])
        if period:
            field = self.field_ranking(words, box, lower, upper)
            direct = ordered(votes((field, .85), (sem[:50], 1 - .85)))
            blend_scores = votes((lex[:50], .60), (sem[:50], .15), (field, .25))
            blended = ordered(blend_scores)
            head = set(base[:10])
            reranked = [doc for doc in blended if doc in head]
            # Preserve positions supported by FTS. Use the field branch to fill
            # semantic-only positions and unused slots if lexical evidence is sparse.
            supported = set(lex[:50])
            tail = iter(d for d in direct if d not in supported)
            fallback = []
            for position in range(10):
                current = base[position] if position < len(base) else None
                doc_id = current if current in supported else next(tail, None)
                if doc_id is not None:
                    fallback.append(doc_id)
            return {"baseline": base[:10], "fallback": fallback, "native": direct[:10], "blend": blended[:10],
                    "rerank": reranked, "fresh_only": base[:10]}

        scores = votes((lex[:200], .85), (sem[:200], 1 - .85))
        for doc_id, score in scores.items():
            day = self.metadata[doc_id][1]
            recency = 2 ** (-(as_of - date.fromisoformat(day)).days / 30) if day else 0
            scores[doc_id] = .55 * 61 * score + .45 * recency
        fresh = ordered(scores)[:10]
        return {"baseline": base[:10], **dict.fromkeys(("native", "blend", "rerank", "fallback", "fresh_only"), fresh)}
