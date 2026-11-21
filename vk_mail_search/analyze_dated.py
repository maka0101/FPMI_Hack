"""Diagnose dated BM25 misses on the public benchmark."""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path
import re

from .data import Dataset, load_dataset
from .evaluate import load_predictions, score_predictions
from .query_parser import parse_query
from .searchers import build_searcher


MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
PUBLIC_TEMPLATE = re.compile(
    r"^(?:найди|покажи) (.+), полученные (?:вчера|(\d{1,2}) (\S+) (\d{4}) года)\.$",
    re.I,
)


def analyze(dataset: Dataset, predictions: dict[str, list[str]]) -> dict:
    metrics = score_predictions(dataset, predictions, (10, 20))
    searcher = build_searcher("dated:bm25", dataset.documents)
    mixed = {}
    cases = []
    totals = Counter()
    by_day = defaultdict(set)
    for document in dataset.documents.values():
        by_day[document.synthetic_user, document.doc_dt].add(document.doc_id)
    for query_id, query in dataset.queries.items():
        parsed = parse_query(query.query, query.query_date)
        template = PUBLIC_TEMPLATE.fullmatch(query.query)
        if not template:
            raise ValueError(f"Неизвестный шаблон публичного запроса {query_id}")
        _, day_number, month, year = template.groups()
        expected_date = (date(int(year), MONTHS.index(month.casefold()) + 1, int(day_number)) if year
                         else date.fromisoformat(query.query_date) - timedelta(days=1))
        day = expected_date.isoformat()
        expected_topic = template[1].casefold().replace("ё", "е")
        topic_ok = parsed.topic == expected_topic
        date_ok = bool(parsed.period and parsed.period.start.isoformat() == day
                       and parsed.period.end.isoformat() == day)
        totals["correct_topic"] += topic_ok
        totals["correct_date"] += date_ok
        grades = dataset.qrels[query_id]
        relevant = {doc_id for doc_id, grade in grades.items() if grade > 0}
        day_ids = by_day[query.synthetic_user, day]
        ids = predictions[query_id]
        if day_ids & relevant and day_ids - relevant:
            mixed[query_id] = ids
        misses = relevant - set(ids[:10])
        if not misses:
            continue
        full = searcher.search(query.query, query.synthetic_user, query.query_date,
                               len(dataset.documents))
        if [doc_id for doc_id, _ in full[:20]] != ids:
            raise ValueError(f"Топ-20 не совпал с dated:bm25 для {query_id}")
        ranks = {doc_id: (i, score) for i, (doc_id, score) in enumerate(full, 1)}
        excess = max(0, len(relevant) - 10)
        totals["unavoidable_at_10"] += excess
        totals["lost_slots_at_10"] += len(misses) - excess
        totals["missed_at_10_in_top_20"] += len(misses & set(ids[10:]))
        totals["missed_at_20"] += len(relevant - set(ids))
        totals["unavoidable_at_20"] += max(0, len(relevant) - 20)
        details = []
        for doc_id in sorted(misses, key=lambda item: (ranks.get(item, (float("inf"),))[0], item)):
            rank, score = ranks.get(doc_id, (None, None))
            above = full[:rank - 1] if rank else full[:20]
            if not date_ok or not topic_ok:
                reason = "query_parse"
            elif doc_id not in day_ids:
                reason = "outside_period"
            elif rank and sum(item in relevant for item, _ in above) >= 10:
                reason = "limit_at_10"
            elif not score:
                reason = "no_lexical_match"
            else:
                reason = "outranked_by_nonrelevant"
            details.append({
                "doc_id": doc_id, "rank": rank, "in_top_20": doc_id in ids, "score": score,
                "reason": reason,
                "higher_nonrelevant_ids": [item for item, _ in above if item not in relevant],
            })
        cases.append({
            **asdict(query), "expected_day": day, "expected_topic": expected_topic,
            "parsed_period": parsed.period.label() if parsed.period else None,
            "parsed_topic": parsed.topic, "date_ok": date_ok, "topic_ok": topic_ok,
            "day_candidates": len(day_ids), "relevant_count": len(relevant),
            "unavoidable_at_10": excess, "top_20": ids, "misses": details,
        })
        recoverable = [miss for miss in details if miss["reason"] != "limit_at_10"]
        totals["queries_with_improvable_rank"] += bool(recoverable)
        totals["queries_with_improvable_in_top_20"] += any(miss["in_top_20"] for miss in recoverable)
        totals["improvable_in_top_20"] += sum(miss["in_top_20"] for miss in recoverable)
    subset = Dataset(dataset.documents, {qid: dataset.queries[qid] for qid in mixed}, dataset.qrels)
    return {
        "all": metrics, "mixed_same_day": score_predictions(subset, mixed, (10, 20)),
        "counts": dict(totals), "queries_with_misses": len(cases), "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--pred", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(load_dataset(args.data_dir), load_predictions(args.pred))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
