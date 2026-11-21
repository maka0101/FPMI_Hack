"""Measure weighted two-list RRF through the local search HTTP endpoint."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from random import Random
from statistics import mean
from threading import Thread

from mail_search.__main__ import DEFAULT_DATA, build_index, create_server
from mail_search.comparison import LIMIT, model_metadata, query_groups, ranking_metrics, read_relevance, request_search
from mail_search.search import CANDIDATE_POOL, read_jsonl


SEED = 20261121
COARSE_PERCENT = range(0, 101, 10)
FINE_PERCENT = {"harrier270": range(65, 86), "e5": range(85, 100), "granite97": range(85, 100)}


def measure(server, groups, gold, repeats, weights, cutoff):
    port = server.server_port
    rng = Random(SEED)
    jobs = [(group, query, i) for group, rows in groups.items() for query in rows for i in weights]
    timings = defaultdict(list)
    scores = defaultdict(dict)
    controls = {}
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for group, rows in groups.items():
            for row in rng.sample(rows, min(8, len(rows))):
                for i in (weights[0], weights[len(weights) // 2], weights[-1]):
                    request_search(port, row, "hybrid", cutoff, bm25_weight=i / 100)
            for row in rows:
                for i, mode in ((50, "hybrid"), (100, "bm25")):
                    if i in weights:
                        controls[group, row["query_id"], i] = request_search(port, row, mode, cutoff)[0]
        for repeat in range(repeats):
            rng.shuffle(jobs)
            for group, query, i in jobs:
                qid = query["query_id"]
                ids, ms = request_search(port, query, "hybrid", cutoff, bm25_weight=i / 100)
                if len(ids) > cutoff or len(set(ids)) != len(ids):
                    raise ValueError(f"Некорректная выдача для {qid}")
                key = group, i
                timings[key].append(ms)
                if repeat:
                    continue
                control = controls.get((group, qid, i))
                if control is not None and ids != control:
                    raise ValueError(f"Разошлись контрольные выдачи для {group}/{qid}/{i}")
                relevant = gold[qid]
                recall, ndcg = ranking_metrics(ids, relevant, cutoff)
                rr = next((1 / pos for pos, doc in enumerate(ids, 1) if doc in relevant), 0)
                scores[key][qid] = (recall, ndcg, rr)
            print(f"Проход {repeat + 1}/{repeats}, {len(jobs)} HTTP-запросов", flush=True)
    finally:
        server.shutdown()
        worker.join()

    results = {}
    for group in groups:
        results[group] = []
        for i in weights:
            key = group, i
            values = scores[key]
            times = sorted(timings[key])
            single = [v[2] for qid, v in values.items() if len(gold[qid]) == 1]
            results[group].append({
                "bm25_weight": i / 100, "dense_weight": (100 - i) / 100,
                "queries": len(values), "single_target_queries": len(single),
                f"recall_at_{cutoff}": mean(v[0] for v in values.values()),
                f"ndcg_at_{cutoff}": mean(v[1] for v in values.values()),
                f"mrr_at_{cutoff}_single": mean(single) if single else None,
                f"mrr_at_{cutoff}_all": mean(v[2] for v in values.values()),
                "latency_samples": len(times), "server_p99_ms": times[ceil(.99 * len(times)) - 1],
            })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", required=True, choices=("harrier270", "granite97", "e5"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cutoff", type=int, default=LIMIT)
    parser.add_argument("--fine", action="store_true", help="Шаг 0,01 вокруг лучших весов на исходных запросах")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--paraphrases", type=Path, default=DEFAULT_DATA.parent / "benchmarks/paraphrases.jsonl")
    parser.set_defaults(model_dir=None, embeddings_cache=None, reranker=None, device="auto")
    args = parser.parse_args()
    if not 1 <= args.cutoff <= 1000:
        parser.error("--cutoff должен быть от 1 до 1000")
    if args.repeats < 1:
        parser.error("--repeats должен быть положительным")
    inputs = [args.data / filename for filename in ("documents.jsonl", "queries_dev.jsonl", "qrels_dev.jsonl")]
    if args.fine:
        groups = {"original": list(read_jsonl(args.data / "queries_dev.jsonl"))}
        weights = FINE_PERCENT[args.embedder]
    else:
        groups = query_groups(args.data, args.paraphrases)
        inputs.append(args.paraphrases)
        weights = COARSE_PERCENT
    gold = read_relevance(args.data)
    if any(not gold.get(row["query_id"]) for rows in groups.values() for row in rows):
        raise ValueError("Запрос без положительной разметки")
    index = build_index(args)
    with create_server(index, 0, quiet=True) as server:
        results = measure(server, groups, gold, args.repeats, weights, args.cutoff)
    report = {
        "embedder": model_metadata(index.embedder), "mode": "hybrid", "seed": SEED,
        "cutoff": args.cutoff, "candidate_pool": CANDIDATE_POOL, "rrf_constant": 60, "repeats": args.repeats,
        "sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in inputs}, "results": results,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
