from datetime import date
from hashlib import sha256
import json
from random import Random
from threading import Thread

from .comparison import LIMIT, model_metadata, ranking_metrics, read_relevance, request_search
from .query_summary import summarize_query
from .search import read_jsonl, split_query


def evaluate_expanded(server, index, suite_dir, output, bm25_control=False, raw_summary=False):
    queries_path = suite_dir / "queries.jsonl"
    qrels_path = suite_dir / "qrels.jsonl"
    gold = read_relevance(suite_dir, qrels_path.name)
    queries = list(read_jsonl(queries_path))
    if not queries or len(queries) != len(gold) or {q["query_id"] for q in queries} != gold.keys():
        raise ValueError("В расширенном тесте каждому запросу нужны оценки релевантности")

    rng = Random(71405)
    rng.shuffle(queries)
    suffix = "-rerank" if index.reranker else ""
    summary_mode = "hybrid-summary-raw" if raw_summary else "hybrid-summary"
    controls = {"two": "hybrid" + suffix, "three": summary_mode + suffix}
    if bm25_control:
        controls["bm25"] = "bm25"
    groups = {name: [row for row in queries if row["variant"] == name] for name in ("compact", "long")}
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    samples = []
    try:
        for rows in groups.values():
            for query in rows[:8]:
                for mode in controls.values():
                    request_search(server.server_port, query, mode)
        for position, query in enumerate(queries, start=1):
            query_id = query["query_id"]
            as_of = date.fromisoformat(query["query_date"])
            _, _, semantic_query = split_query(query["query"], as_of)
            summary = summarize_query(semantic_query, protect_exact=not raw_summary)
            modes = list(controls.items())
            if summary is None:
                # The two hybrid modes run the same computation when no summary is produced.
                modes = [(name, mode) for name, mode in modes if name != "two"]
            rng.shuffle(modes)
            scores = {}
            for name, mode in modes:
                ids, elapsed = request_search(server.server_port, query, mode)
                recall, ndcg = ranking_metrics(ids, gold[query_id], LIMIT)
                scores[name] = {"recall": recall, "ndcg": ndcg, "server_ms": elapsed}
            if "two" not in scores:
                scores["two"] = scores["three"].copy()
            samples.append({
                **{key: query[key] for key in ("query_id", "case_id", "block_id", "kind", "variant")},
                "summary_extracted": summary is not None, "scores": scores,
            })
            if position % 100 == 0:
                print(f"{position}/{len(queries)} запросов", flush=True)
    finally:
        server.shutdown()
        worker.join()

    report = {
        "embedder": model_metadata(index.embedder), "reranker": model_metadata(index.reranker),
        "summary_policy": "raw" if raw_summary else "protect_exact",
        "queries_sha256": sha256(queries_path.read_bytes()).hexdigest(),
        "qrels_sha256": sha256(qrels_path.read_bytes()).hexdigest(),
        "samples": sorted(samples, key=lambda sample: sample["query_id"]),
    }
    output.write_text(json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8")
