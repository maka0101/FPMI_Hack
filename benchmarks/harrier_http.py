"""Measure the default /api/search ranking and Server-Timing on the public queries."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from random import Random

import httpx

from mail_search.__main__ import DEFAULT_DATA
from mail_search.experiments import evaluate, host_info, latency, read_gold, read_queries


def measure(client, queries):
    ready = client.get("/readyz")
    ready.raise_for_status()
    info = ready.json()
    if (info["mode"], info["profile_id"], info["bm25_weight"]) != ("hybrid", "harrier270", 0.85):
        raise ValueError(f"Unexpected backend: {info}")
    rng = Random(42)
    times = []
    rankings = {}
    for iteration in range(4):
        rows = rng.sample(queries, len(queries) if iteration else min(10, len(queries)))
        for row in rows:
            response = client.get("/api/search", params={
                "mailbox": row["synthetic_user"], "q": row["query"], "as_of": row["query_date"],
            })
            response.raise_for_status()
            ids = [item["doc_id"] for item in response.json()]
            if response.headers.get("X-Search-Mode") != "hybrid" or len(set(ids)) != len(ids) or len(ids) > 10:
                raise ValueError(f"Unexpected response for {row['query_id']}")
            if iteration:
                if rankings.setdefault(row["query_id"], ids) != ids:
                    raise ValueError(f"Unstable ranking for {row['query_id']}")
                times.append(float(response.headers["Server-Timing"].removeprefix("search;dur=")))
    return info, rankings, times


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    queries = read_queries(args.data / "queries_dev.jsonl")
    gold = read_gold(args.data / "qrels_dev.jsonl")
    with httpx.Client(base_url=args.url, timeout=10, trust_env=False) as client:
        ready, rankings, times = measure(client, queries)
    if set(rankings) != set(gold) or max(map(len, rankings.values())) != 10:
        raise ValueError("Check query coverage and default output depth")
    rows = [{"query_id": qid, "doc_ids": ids} for qid, ids in sorted(rankings.items())]
    report = {
        "ready": ready, "hardware": host_info(), "cutoff": 10, "bm25_weight": ready["bm25_weight"],
        "sha256": {f: sha256((args.data / f).read_bytes()).hexdigest()
                   for f in ("documents.jsonl", "queries_dev.jsonl", "qrels_dev.jsonl")},
        "metrics": evaluate(rows, gold, 10), "server_ms": latency(times),
        "requests": len(times), "rankings": rows,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
