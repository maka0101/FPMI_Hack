from collections import defaultdict
from datetime import date
from pathlib import Path
from unittest import TestCase

from mail_search.experiment_search import MAX_QUERY_CHARS, parse_query, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "mipt_mail_search_participants"
SUITE = ROOT / "benchmarks" / "expanded"


class ExpandedBenchmarkTest(TestCase):
    def test_variants_have_identical_labels_and_keep_mailbox_and_day(self):
        rows = list(read_jsonl(SUITE / "queries.jsonl"))
        labels = defaultdict(set)
        for row in read_jsonl(SUITE / "qrels.jsonl"):
            labels[row["query_id"]].add(row["doc_id"])
        queries = {row["query_id"]: row for row in rows}
        self.assertEqual(len(queries), len(rows))
        self.assertEqual(queries.keys(), labels.keys())

        old_targets = {row["doc_id"] for row in read_jsonl(DATA / "qrels_dev.jsonl") if row["relevance"] > 0}
        targets = set().union(*labels.values())
        self.assertTrue(old_targets.isdisjoint(targets))
        mail = {row["doc_id"]: (row["synthetic_user"], row["doc_dt"])
                for row in read_jsonl(DATA / "documents.jsonl") if row["doc_id"] in targets}

        pairs = defaultdict(dict)
        case_by_doc = {}
        for row in rows:
            as_of = date.fromisoformat(row["query_date"])
            self.assertLessEqual(len(row["query"]), MAX_QUERY_CHARS)
            day = parse_query(row["query"], as_of)[1]
            query_id = row["query_id"]
            pairs[row["case_id"]][row["variant"]] = (row["synthetic_user"], as_of, day, labels[query_id])
            for doc_id in labels[query_id]:
                mailbox, doc_day = mail[doc_id]
                self.assertEqual(mailbox, row["synthetic_user"])
                self.assertTrue(doc_day is None or doc_day <= row["query_date"])
                if day:
                    self.assertEqual(doc_day, day.isoformat())
                self.assertEqual(case_by_doc.setdefault(doc_id, row["case_id"]), row["case_id"])

        for variants in pairs.values():
            self.assertEqual(variants.keys(), {"compact", "long"})
            self.assertEqual(variants["compact"], variants["long"])
