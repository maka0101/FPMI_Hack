"""Search raw mail or rebuild retrieval pools for the fixed comparison queries."""
import argparse
from datetime import date
import gzip
import json
from pathlib import Path

from mail_search.ml import CandidateRequest, VectorIndex, prepare
from mail_search.search import MailboxIndex, parse_query
from mail_search.search import read_jsonl
from .compare import CORPORA, VK_DATA, load_fixture
from .ranker import FieldIndex


def retrieve(query, lexical, vectors):
    as_of = date.fromisoformat(query["query_date"])
    box, text = query["synthetic_user"], query["query"]
    if box not in lexical.mailboxes:
        raise ValueError("Unknown mailbox")
    words, period = parse_query(text, as_of)
    rows = lexical.search_parsed(box, words, as_of, period, 200)
    dense = []
    if words:
        request = CandidateRequest(synthetic_user=box, query=text, query_date=as_of,
                                   target_range=period, limit=200,
                                   corpus_sha256=vectors.metadata["corpus_sha256"])
        dense = [hit.doc_id for hit in vectors.search(request)]
    return [row["doc_id"] for row in rows], dense


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=VK_DATA)
    actions = parser.add_subparsers(dest="action", required=True)
    search = actions.add_parser("search")
    search.add_argument("mailbox")
    search.add_argument("day", type=date.fromisoformat)
    search.add_argument("query")
    search.add_argument("--model", choices=("native", "blend", "rerank", "fallback", "fresh_only"), default="fallback")
    rebuild = actions.add_parser("rebuild")
    rebuild.add_argument("corpus", choices=CORPORA)
    rebuild.add_argument("out", type=Path)
    args = parser.parse_args()
    prepare(args.data, "harrier270")
    vectors = VectorIndex(args.data, "harrier270")
    lexical = MailboxIndex(args.data)
    try:
        if args.action == "search":
            index = FieldIndex(read_jsonl(args.data / "documents.jsonl"))
            query = dict(query=args.query, synthetic_user=args.mailbox, query_date=args.day.isoformat())
            lex, dense = retrieve(query, lexical, vectors)
            print(json.dumps(index.rankings(args.query, args.mailbox, args.day, lex, dense)[args.model]))
        else:
            source = load_fixture(args.corpus)
            if source["index"]["corpus_sha256"] != vectors.metadata["corpus_sha256"]:
                raise ValueError("Wrong corpus for these queries")
            source["index"] = vectors.metadata
            for rows in source["sets"].values():
                for row in rows:
                    row["lex"], row["dense"] = retrieve(row["query"], lexical, vectors)
            with gzip.open(args.out, "wt", encoding="utf8") as stream:
                json.dump(source, stream, ensure_ascii=False)
    finally:
        lexical.db.close()


if __name__ == "__main__":
    main()
