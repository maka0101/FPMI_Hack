from collections import defaultdict
from datetime import date
from http.client import HTTPConnection
import json
from math import ceil, log2
from random import Random
from statistics import mean
from threading import Thread
from urllib.parse import urlencode

from .search import parse_query, read_jsonl


LIMIT = 10
MODES = ("bm25", "hybrid")


def read_relevance(data_dir):
    gold = defaultdict(dict)
    for row in read_jsonl(data_dir / "qrels_dev.jsonl"):
        if row["relevance"] > 0:
            gold[row["query_id"]][row["doc_id"]] = row["relevance"]
    return gold


def ranking_metrics(doc_ids, relevance, limit):
    gains = [relevance.get(doc_id, 0) for doc_id in doc_ids[:limit]]
    ideal = sorted(relevance.values(), reverse=True)[:limit]
    return sum(gain > 0 for gain in gains) / len(relevance), dcg(gains) / dcg(ideal)


def dcg(gains):
    return sum((2 ** gain - 1) / log2(rank + 1) for rank, gain in enumerate(gains, 1))


def request_search(port, query, mode):
    params = urlencode({
        "mailbox": query["synthetic_user"],
        "as_of": query["query_date"],
        "q": query["query"],
        "mode": mode,
        "limit": LIMIT,
    })
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request("GET", f"/api/search?{params}")
        response = connection.getresponse()
        payload = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} для {query['query_id']}: {payload}")
        duration = float(response.getheader("Server-Timing").removeprefix("search;dur="))
        return [row["doc_id"] for row in payload], duration
    finally:
        connection.close()


def compare(server, data_dir, paraphrases_path, repeats, output):
    originals = list(read_jsonl(data_dir / "queries_dev.jsonl"))
    paraphrase_rows = list(read_jsonl(paraphrases_path))
    paraphrases = {row["query_id"]: row["query"] for row in paraphrase_rows}
    original_ids = {row["query_id"] for row in originals}
    if not originals or len(paraphrases) != len(paraphrase_rows) or paraphrases.keys() != original_ids:
        raise ValueError("Для каждого исходного запроса нужна одна уникальная строка перефразировки")

    rewritten = []
    for row in originals:
        text = paraphrases[row["query_id"]]
        as_of = date.fromisoformat(row["query_date"])
        if text == row["query"] or parse_query(text, as_of)[1] != parse_query(row["query"], as_of)[1]:
            raise ValueError(f"Некорректная перефразировка запроса {row['query_id']}")
        rewritten.append({**row, "query": text})

    gold = read_relevance(data_dir)
    corpora = {"original": originals, "paraphrase": rewritten}
    jobs = [(name, mode, row) for name, rows in corpora.items() for mode in MODES for row in rows]
    scores = defaultdict(list)
    timings = defaultdict(list)
    rng = Random(42)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for rows in corpora.values():
            for row in rng.sample(rows, min(8, len(rows))):
                for mode in MODES:
                    request_search(server.server_port, row, mode)
        for repeat in range(repeats):
            rng.shuffle(jobs)
            for name, mode, row in jobs:
                ids, duration = request_search(server.server_port, row, mode)
                key = (name, mode)
                timings[key].append(duration)
                if repeat == 0 and gold[row["query_id"]]:
                    scores[key].append(ranking_metrics(ids, gold[row["query_id"]], LIMIT))
    finally:
        server.shutdown()
        worker.join()

    report = {"limit": LIMIT, "repeats": repeats, "results": {}}
    for name, rows in corpora.items():
        report["results"][name] = {}
        for mode in MODES:
            samples = sorted(timings[name, mode])
            recall, ndcg = zip(*scores[name, mode])
            result = {
                "queries": len(rows),
                "recall_at_10": mean(recall),
                "ndcg_at_10": mean(ndcg),
                "server_p99_ms": samples[ceil(0.99 * len(samples)) - 1],
                "latency_samples": len(samples),
            }
            report["results"][name][mode] = result
            print(f"{name:10} {mode:6}  Recall@10 {result['recall_at_10']:.4f}  nDCG@10 {result['ndcg_at_10']:.4f}"
                  f"  Server p99 {result['server_p99_ms']:.2f} ms ({len(samples)} запросов)")
    if output:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
