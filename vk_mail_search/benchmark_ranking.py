"""Compare the mail rankers and check the selected ranker over HTTP."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter_ns
from urllib.parse import urlencode
from urllib.request import urlopen

from .data import Dataset, Query, jsonl, load_dataset, percentile
from .evaluate import load_predictions, run_search, score_predictions, validate_predictions, write_predictions
from .query_parser import parse_query
from .searchers import build_searcher


VARIANTS = (
    "dated:bm25", "dated:bm25-subject", "dated:dense", "dated-period:hybrid-subject",
    "dated:hybrid", "dated-period:hybrid",
)
GROUPS = ("paraphrase", "no_date", "near_event")
CUTOFFS = (10, 20)


def load_holdout(dataset: Dataset, path: Path) -> tuple[dict[str, Dataset], dict[str, str | None]]:
    queries = {}
    labels = {}
    groups = {}
    days = {}
    for line, row in jsonl(path):
        query = Query(row["query_id"], row["synthetic_user"], row["query"], row["query_date"])
        qid = query.query_id
        ids = row["doc_ids"]
        day = row["received_date"]
        if qid in queries or qid in dataset.queries or not isinstance(ids, list) or not ids:
            raise ValueError(f"{path}:{line}: повтор query_id или отсутствуют метки")
        date.fromisoformat(query.query_date)
        if day is not None:
            date.fromisoformat(day)
            if any(dataset.documents[doc_id].doc_dt != day for doc_id in ids):
                raise ValueError(f"{path}:{line}: письмо за другой день")
        if (row["group"] == "no_date") != (day is None):
            raise ValueError(f"{path}:{line}: группа не совпадает с датой получения")
        queries[qid], labels[qid], groups[qid], days[qid] = query, ids, row["group"], day
    all_queries = Dataset(dataset.documents, queries, {q: dict.fromkeys(ids, 1) for q, ids in labels.items()})
    validate_predictions(all_queries, labels)
    if Counter(groups.values()) != dict.fromkeys(GROUPS, 10):
        raise ValueError("В каждой группе отложенного набора должно быть 10 запросов")
    sets = {"holdout": all_queries}
    for group in GROUPS:
        sets[group] = Dataset(dataset.documents, {q: queries[q] for q in queries if groups[q] == group},
                              all_queries.qrels)
    return sets, days


def compare(dataset: Dataset, holdout_path: Path, out: Path, variants: list[str]) -> dict:
    sets, expected_days = load_holdout(dataset, holdout_path)
    sets["public"] = dataset
    # Compare candidate order only on exact received-date matches.
    for qid, query in dataset.queries.items():
        rel_days = {dataset.documents[doc_id].doc_dt for doc_id, grade in dataset.qrels[qid].items() if grade > 0}
        if len(rel_days) == 1:
            expected_days[qid], = rel_days
    combined = Dataset(dataset.documents, dataset.queries | sets["holdout"].queries,
                       dataset.qrels | sets["holdout"].qrels)
    exact = {}
    for qid, day in expected_days.items():
        query = combined.queries[qid]
        parsed = parse_query(query.query, query.query_date)
        if day and parsed.period and parsed.period.start.isoformat() == day == parsed.period.end.isoformat():
            exact[qid] = query
    sets["exact_received_date"] = Dataset(dataset.documents, exact, combined.qrels)

    summaries = {}
    hybrid_predictions = {}
    period_scores = {}
    for name in variants:
        searcher = build_searcher(name, dataset.documents)
        ids, timing = run_search(combined, searcher, 20, 20, warmup=10)
        summaries[name] = {"search_timing": timing, **{
            label: score_predictions(subset, {q: ids[q] for q in subset.queries}, CUTOFFS)
            for label, subset in sets.items()
        }}
        slug = name.replace(":", "-")
        write_predictions(out / f"predictions-{slug}.jsonl", ids, 20)
        write_report(out / f"{slug}.json", summaries[name])
        if name in ("dated:hybrid", "dated-period:hybrid"):
            hybrid_predictions[name] = ids
            period_scores[name] = {}
            for qid, query in exact.items():
                hits = searcher.search(query.query, query.synthetic_user, query.query_date, len(dataset.documents))
                period_scores[name][qid] = {doc_id: (i, score) for i, (doc_id, score) in enumerate(hits, 1)
                                           if combined.qrels[qid].get(doc_id, 0) > 0}
        del searcher
        print(f"Готово: {name}", flush=True)

    coverage = []
    invariants = None
    if len(period_scores) == 2:
        for qid, old in period_scores["dated:hybrid"].items():
            new = period_scores["dated-period:hybrid"][qid]
            for doc_id, (old_rank, old_score) in old.items():
                if old_score == 0:
                    new_rank, new_score = new[doc_id]
                    coverage.append(dict(query_id=qid, doc_id=doc_id, old_rank=old_rank, new_rank=new_rank,
                                         new_score=new_score))
        old_ids, new_ids = (hybrid_predictions[name] for name in ("dated:hybrid", "dated-period:hybrid"))
        for qid in sets["no_date"].queries:
            if old_ids[qid] != new_ids[qid]:
                raise ValueError(f"Изменился поиск без даты для {qid}")
        for qid in exact:
            day = expected_days[qid]
            old_fill = [item for item in old_ids[qid] if combined.documents[item].doc_dt != day]
            new_fill = [item for item in new_ids[qid] if combined.documents[item].doc_dt != day]
            if old_fill != new_fill:
                raise ValueError(f"Изменился добор вне периода для {qid}")
        invariants = {"no_date_unchanged": len(sets["no_date"].queries),
                      "outside_period_fill_unchanged": len(exact)}
    return {"holdout_sha256": sha256(holdout_path.read_bytes()).hexdigest(), "variants": summaries,
            "period_invariants": invariants, "period_hits_with_no_old_branch": coverage}


def benchmark_api(dataset: Dataset, url: str, searcher_name: str, expected: dict[str, list[str]],
                  repeats: int, concurrency: int) -> dict:
    validate_predictions(dataset, expected)
    queries = tuple(dataset.queries.values())
    requests = tuple(f"{url}?{urlencode(dict(q=q.query, mailbox=q.synthetic_user, as_of=q.query_date, k=20))}"
                     for q in queries)

    def request(index: int) -> tuple[float, float]:
        start = perf_counter_ns()
        with urlopen(requests[index], timeout=10) as response:
            row = json.load(response)
        elapsed = (perf_counter_ns() - start) / 1_000_000
        if [result["doc_id"] for result in row["results"]] != expected[queries[index].query_id]:
            raise ValueError(f"Выдача API отличается для {queries[index].query_id}")
        took = row["took_ms"]
        if not isfinite(took) or took < 0:
            raise ValueError("Некорректное серверное took_ms")
        return took, elapsed

    for index in range(min(10, len(queries))):
        request(index)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        server, roundtrip = zip(*pool.map(request, list(range(len(queries))) * repeats), strict=True)
    return {"searcher": searcher_name, "url": url, "k": 20, "requests": len(server), "concurrency": concurrency,
            "server_p99_ms": round(percentile(server, .99), 3),
            "http_p99_ms": round(percentile(roundtrip, .99), 3),
            "server_p99_under_1s": percentile(server, .99) < 1000}


def write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--holdout", type=Path, default=Path("benchmarks/mail_ranking_holdout.jsonl"))
    parser.add_argument("--out", type=Path, required=True)
    modes = parser.add_subparsers(dest="mode", required=True)
    compare_parser = modes.add_parser("compare")
    compare_parser.add_argument("--variant", choices=VARIANTS, action="append")
    api_parser = modes.add_parser("api")
    api_parser.add_argument("--url", required=True)
    api_parser.add_argument("--searcher", choices=VARIANTS, required=True)
    api_parser.add_argument("--pred", type=Path, required=True)
    api_parser.add_argument("--repeats", type=int, default=3)
    api_parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    if args.mode == "api" and min(args.repeats, args.concurrency) < 1:
        parser.error("--repeats и --concurrency должны быть положительными")
    public = load_dataset(args.data_dir)
    args.out.mkdir(exist_ok=True, parents=True)
    if args.mode == "compare":
        write_report(args.out / "comparison.json", compare(public, args.holdout, args.out, args.variant or VARIANTS))
    else:
        sets, _ = load_holdout(public, args.holdout)
        holdout = sets["holdout"]
        combined = Dataset(public.documents, public.queries | holdout.queries, public.qrels | holdout.qrels)
        report = benchmark_api(combined, args.url, args.searcher, load_predictions(args.pred),
                               args.repeats, args.concurrency)
        write_report(args.out / "api.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["server_p99_under_1s"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
