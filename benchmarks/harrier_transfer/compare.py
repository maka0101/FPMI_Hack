"""Replay the fixed queries, validate the baseline and compare top-ten rankings."""
import argparse
from collections import defaultdict
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean

from mail_search.comparison import ranking_metrics
from mail_search.search import read_jsonl
from .ranker import FieldIndex

HERE = Path(__file__).resolve().parent
VK_DATA = HERE.parents[1] / "mipt_mail_search_participants"
CORPORA = ("vk", "sara", "vectrix", "w3c")


def load_fixture(corpus, directory=HERE / "fixtures"):
    with gzip.open(directory / f"{corpus}.json.gz", "rt", encoding="utf8") as stream:
        return json.load(stream)


def metrics(rows, rankings):
    totals = defaultdict(list)
    for row, ranking in zip(rows, rankings, strict=True):
        gold = {doc: grade for doc, grade in row["gold"].items() if grade > 0}
        if not gold:
            continue
        for k in (5, 10):
            recall, ndcg = ranking_metrics(ranking, gold, k)
            mrr = next((1 / i for i, doc in enumerate(ranking[:k], 1) if doc in gold), 0.)
            totals[k].append((recall, ndcg, mrr))
    return {f"@{k}": dict(zip(("recall", "ndcg", "mrr"), (round(mean(v), 6) for v in zip(*scores))))
            for k, scores in totals.items()}


def validate(ids, query, metadata):
    if len(ids) > 10 or len(ids) != len(set(ids)):
        raise ValueError(f"Invalid top ten for {query}")
    for doc_id in ids:
        owner, day = metadata[doc_id]
        if owner != query["synthetic_user"] or (day and day > query["query_date"]):
            raise ValueError(f"Ineligible {doc_id} for {query}")


def compare(corpus, source, data_dir=None):
    if data_dir is not None:
        with (data_dir / "documents.jsonl").open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != source["index"]["corpus_sha256"]:
            raise ValueError("Corpus differs from the frozen queries")
        documents = read_jsonl(data_dir / "documents.jsonl")
    else:
        documents = (dict(doc_id=d, synthetic_user=box, doc_dt=day) for d, box, day in source["metadata"])
    index = FieldIndex(documents)
    results = {}
    for name, rows in source["sets"].items():
        rankings = defaultdict(list)
        for row in rows:
            q = row["query"]
            run = index.rankings(q["query"], q["synthetic_user"], date.fromisoformat(q["query_date"]),
                                 row["lex"], row["dense"])
            if run.pop("baseline") != row["main"]:
                raise ValueError(f"Baseline differs from main for {name}/{q['query_id']}")
            run.update(main=row["main"], ensemble=row["ensemble"])
            for model, ids in run.items():
                validate(ids, q, index.metadata)
                rankings[model].append(ids)
        results[name] = {"queries": len(rows), "scored": sum(any(g > 0 for g in r["gold"].values()) for r in rows),
                         "metrics": {k: metrics(rows, v) for k, v in rankings.items()}}
    return {"corpus": corpus, "default": "fallback",
            "main_commit": "0c27fa74cb93cfe00839074321eb3b7081a38a8c",
            "ensemble_commit": "da14429dac3083480e4b41b0b301ea4c907fc83b",
            "index": source["index"], "sets": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--fixtures", type=Path, default=HERE / "fixtures")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for corpus in (args.corpus,) if args.corpus else CORPORA:
        result = compare(corpus, load_fixture(corpus, args.fixtures), VK_DATA if corpus == "vk" else None)
        (args.out_dir / f"{corpus}.json").write_text(json.dumps(result, indent=2) + "\n")
        print(corpus, sum(s["queries"] for s in result["sets"].values()), flush=True)


if __name__ == "__main__":
    main()
