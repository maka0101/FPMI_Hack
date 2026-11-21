from collections import defaultdict
from datetime import date
from hashlib import sha256
from http.client import HTTPConnection
import json
from math import ceil, log2
from random import Random
from statistics import mean
from threading import Thread
from urllib.parse import urlencode

from .search import CANDIDATE_POOL, DATE_IN_QUERY, RERANK_LIMIT, parse_query, read_jsonl


LIMIT = 10
MODES = ("bm25", "hybrid")


def read_relevance(data_dir, filename="qrels_dev.jsonl"):
    gold = defaultdict(dict)
    for row in read_jsonl(data_dir / filename):
        if row["relevance"] > 0:
            gold[row["query_id"]][row["doc_id"]] = row["relevance"]
    return gold


def ranking_metrics(doc_ids, relevance, limit):
    gains = [relevance.get(doc_id, 0) for doc_id in doc_ids[:limit]]
    ideal = sorted(relevance.values(), reverse=True)[:limit]
    return sum(gain > 0 for gain in gains) / len(relevance), dcg(gains) / dcg(ideal)


def dcg(gains):
    return sum((2 ** gain - 1) / log2(rank + 1) for rank, gain in enumerate(gains, 1))


def request_search(port, query, mode, limit=LIMIT, *, bm25_weight=None):
    params = {
        "mailbox": query["synthetic_user"],
        "as_of": query["query_date"],
        "q": query["query"],
        "mode": mode,
        "limit": limit,
    }
    if bm25_weight is not None:
        params["bm25_weight"] = bm25_weight
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request("GET", f"/api/search?{urlencode(params)}")
        response = connection.getresponse()
        payload = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} для {query['query_id']}: {payload}")
        duration = float(response.getheader("Server-Timing").removeprefix("search;dur="))
        return [row["doc_id"] for row in payload], duration
    finally:
        connection.close()


def query_groups(data_dir, paraphrases_path, include_undated=False):
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

    corpora = {"original": originals, "paraphrase": rewritten}
    if include_undated:
        corpora["paraphrase_no_day"] = [
            {**row, "query": DATE_IN_QUERY.sub(" ", row["query"], count=1).strip()} for row in rewritten
        ]
    return corpora


def compare(server, index, data_dir, paraphrases_path, repeats, output, include_undated=False):
    corpora = query_groups(data_dir, paraphrases_path, include_undated)
    originals = corpora["original"]
    gold = read_relevance(data_dir)
    modes = (*MODES, "hybrid-rerank") if index.reranker else MODES
    receipts = [row for row in originals if "электронными чеками" in row["query"].lower()]
    jobs = [(name, mode, row) for name, rows in corpora.items() for mode in modes for row in rows]
    scores = defaultdict(list)
    timings = defaultdict(list)
    rankings = defaultdict(dict)
    receipt_pool_misses = {}
    candidate_hash = sha256()
    rng = Random(42)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for rows in corpora.values():
            for row in rng.sample(rows, min(8, len(rows))):
                for mode in modes:
                    request_search(server.server_port, row, mode)
        for repeat in range(repeats):
            rng.shuffle(jobs)
            for name, mode, row in jobs:
                ids, duration = request_search(server.server_port, row, mode)
                key = (name, mode)
                timings[key].append(duration)
                if repeat == 0:
                    query_id = row["query_id"]
                    rankings[key][query_id] = ids
                    if gold[query_id]:
                        scores[key].append(ranking_metrics(ids, gold[query_id], LIMIT))
        if index.reranker:
            for name, rows in corpora.items():
                for row in rows:
                    candidates, _ = request_search(server.server_port, row, "hybrid", RERANK_LIMIT)
                    query_id = row["query_id"]
                    if not set(rankings[name, "hybrid-rerank"][query_id]).issubset(candidates):
                        raise RuntimeError(f"Ранжировщик вернул письмо вне top-{RERANK_LIMIT}: {query_id}")
                    candidate_hash.update(json.dumps([name, query_id, candidates]).encode())
        for row in receipts:
            query_id = row["query_id"]
            lexical_pool, _ = request_search(server.server_port, row, "bm25", CANDIDATE_POOL)
            receipt_pool_misses[query_id] = set(gold[query_id]).difference(lexical_pool)
    finally:
        server.shutdown()
        worker.join()

    report = {
        "limit": LIMIT, "repeats": repeats,
        "embedder": model_metadata(index.embedder), "reranker": model_metadata(index.reranker),
        "results": {},
    }
    if index.reranker:
        report["rerank_candidates"] = {"limit": RERANK_LIMIT, "sha256": candidate_hash.hexdigest()}
    for name, rows in corpora.items():
        report["results"][name] = {}
        for mode in modes:
            samples = sorted(timings[name, mode])
            recall, ndcg = zip(*scores[name, mode])
            result = {
                "queries": len(rows),
                "server_p99_ms": samples[ceil(0.99 * len(samples)) - 1],
                "latency_samples": len(samples),
            }
            if name == "paraphrase_no_day":
                result["known_target_recall_at_10"] = mean(recall)
                quality = f"Known target Recall@10 {mean(recall):.4f}"
            else:
                result.update(recall_at_10=mean(recall), ndcg_at_10=mean(ndcg))
                quality = f"Recall@10 {mean(recall):.4f}  nDCG@10 {mean(ndcg):.4f}"
            report["results"][name][mode] = result
            print(f"{name:18} {mode:13} {quality}  Server p99 {result['server_p99_ms']:.2f} ms"
                  f" ({len(samples)} запросов)", flush=True)
    if receipts:
        report["receipts_missed_by_bm25"] = {
            "bm25_candidate_limit": CANDIDATE_POOL,
            "query_document_pairs": sum(map(len, receipt_pool_misses.values())),
            "recovered_at_10": {
                mode: sum(len(doc_ids.intersection(rankings["original", mode][query_id]))
                          for query_id, doc_ids in receipt_pool_misses.items())
                for mode in modes if mode != "bm25"
            },
        }
    if output:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def model_metadata(model):
    return {"name": model.name, "device": model.device, "precision": model.precision} if model else None
