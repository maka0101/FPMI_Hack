"""Summarize the expanded test with paired block-bootstrap intervals."""
import argparse
from itertools import combinations
import json
from math import ceil
from pathlib import Path
from statistics import mean

import numpy as np


ROOT = Path(__file__).resolve().parent / "expanded"
CANDIDATES = ("e5", "granite97", "user2-small", "harrier270", "granite-ru")
BOOTSTRAP_DRAWS = 20_000
ALPHA = 0.05


def load_runs(directory):
    runs = {name: json.loads((directory / f"{name}.json").read_text()) for name in CANDIDATES}
    for field in ("queries_sha256", "qrels_sha256"):
        if len({run[field] for run in runs.values()}) != 1:
            raise ValueError(f"Несовпадающие входы эксперимента: {field}")
    if len({run.get("summary_policy", "raw") for run in runs.values()}) != 1:
        raise ValueError("Кандидаты использовали разные политики суммаризации")
    metadata = {}
    scores = {}
    for name, run in runs.items():
        scores[name] = {}
        for row in run["samples"]:
            query_id = row["query_id"]
            info = {key: row[key] for key in ("case_id", "block_id", "kind", "variant")}
            if query_id in scores[name] or metadata.setdefault(query_id, info) != info:
                raise ValueError(f"Несовпадающий запрос: {query_id}")
            scores[name][query_id] = row["scores"]
    if any(rows.keys() != metadata.keys() for rows in scores.values()):
        raise ValueError("Кандидаты оценены на разных запросах")
    cases = {}
    for query_id, info in metadata.items():
        variants = cases.setdefault(info["case_id"], {})
        if info["variant"] in variants:
            raise ValueError(f"Повтор варианта в кейсе {info['case_id']}")
        variants[info["variant"]] = query_id
    for case_id, variants in cases.items():
        if variants.keys() != {"compact", "long"}:
            raise ValueError(f"Неполный кейс: {case_id}")
        if metadata[variants["compact"]]["block_id"] != metadata[variants["long"]]["block_id"]:
            raise ValueError(f"Варианты кейса в разных блоках: {case_id}")
    return runs, metadata, scores


def aggregate(rows):
    times = sorted(row["server_ms"] for row in rows)
    return {
        "queries": len(rows),
        "recall_at_10": mean(row["recall"] for row in rows),
        "ndcg_at_10": mean(row["ndcg"] for row in rows),
        "server_p99_ms": times[ceil(0.99 * len(times)) - 1],
    }


def block_draws(metadata, query_ids, values):
    blocks = sorted({metadata[qid]["block_id"] for qid in query_ids})
    by_id = {block: index for index, block in enumerate(blocks)}
    indexes = [by_id[metadata[qid]["block_id"]] for qid in query_ids]
    sizes = np.bincount(indexes, minlength=len(blocks))
    totals = np.zeros((len(blocks), values.shape[1]))
    np.add.at(totals, indexes, values)
    rng = np.random.default_rng(78143)
    weights = rng.multinomial(len(blocks), np.full(len(blocks), 1 / len(blocks)), size=BOOTSTRAP_DRAWS)
    return np.einsum("ij,jk->ik", weights, totals) / (weights @ sizes)[:, None]


def interval(draws, comparisons):
    tail = ALPHA / (2 * comparisons)
    return np.quantile(draws, [tail, 1 - tail]).tolist()


def summarize(directory):
    runs, metadata, scores = load_runs(directory)
    all_ids = sorted(metadata)
    compact = [qid for qid in all_ids if metadata[qid]["variant"] == "compact"]
    verbose = [qid for qid in all_ids if metadata[qid]["variant"] == "long"]
    groups = {"all": all_ids, "compact": compact, "long": verbose}
    results = {}
    for name, values in scores.items():
        results[name] = {
            "embedder": runs[name]["embedder"], "reranker": runs[name]["reranker"],
            "summary_extracted": sum(row["summary_extracted"] for row in runs[name]["samples"]),
            "two": {group: aggregate([values[qid]["two"] for qid in ids]) for group, ids in groups.items()},
            "three": {group: aggregate([values[qid]["three"] for qid in ids]) for group, ids in groups.items()},
            "three_by_kind": {
                kind: aggregate([values[qid]["three"] for qid in all_ids if metadata[qid]["kind"] == kind])
                for kind in sorted({info["kind"] for info in metadata.values()})
            },
        }

    values = np.array([[scores[name][qid]["three"]["ndcg"] for name in CANDIDATES] for qid in all_ids])
    draws = block_draws(metadata, all_ids, values)
    means = values.mean(axis=0)
    pairs = list(combinations(range(len(CANDIDATES)), 2))
    comparisons = []
    for first, second in pairs:
        comparisons.append({
            "first": CANDIDATES[first], "second": CANDIDATES[second],
            "delta_ndcg": float(means[first] - means[second]),
            "interval": interval(draws[:, first] - draws[:, second], len(pairs)),
        })
    leader = int(means.argmax())
    unresolved = [name for other, name in enumerate(CANDIDATES) if other != leader
                  and interval(draws[:, leader] - draws[:, other], len(pairs))[0] <= 0]

    deltas = np.array([[scores[name][qid]["three"]["ndcg"] - scores[name][qid]["two"]["ndcg"]
                        for name in CANDIDATES] for qid in verbose])
    ablation_draws = block_draws(metadata, verbose, deltas)
    for i, name in enumerate(CANDIDATES):
        results[name]["long_summary_ablation"] = {
            "delta_ndcg": float(deltas[:, i].mean()),
            "interval": interval(ablation_draws[:, i], len(CANDIDATES)),
        }

    return {
        "queries": len(all_ids), "cases": len(compact),
        "blocks": len({info["block_id"] for info in metadata.values()}),
        "summary_policy": runs["e5"].get("summary_policy", "raw"),
        "queries_sha256": runs["e5"]["queries_sha256"], "qrels_sha256": runs["e5"]["qrels_sha256"],
        "bootstrap_draws": BOOTSTRAP_DRAWS, "familywise_confidence": 1 - ALPHA,
        "point_estimate_leader": CANDIDATES[leader],
        "confirmed_winner": CANDIDATES[leader] if not unresolved else None,
        "unresolved_vs_leader": unresolved, "pairwise_ndcg": comparisons, "models": results,
        "bm25_control": {
            group: aggregate([scores["e5"][qid]["bm25"] for qid in ids]) for group, ids in groups.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--output", type=Path, default=ROOT / "results.json")
    args = parser.parse_args()
    data = summarize(args.runs)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, result in data["models"].items():
        print(name, "nDCG@10", f"{result['three']['all']['ndcg_at_10']:.4f}",
              "long Δ", f"{result['long_summary_ablation']['delta_ndcg']:+.4f}",
              "p99", f"{result['three']['all']['server_p99_ms']:.2f} ms")
    print("Leader:", data["point_estimate_leader"], "Confirmed:", data["confirmed_winner"],
          "Unresolved:", data["unresolved_vs_leader"])


if __name__ == "__main__":
    main()
