from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mail_search.search import MailboxIndex, reciprocal_rank_fusion


class RecordingEncoder:
    def index(self, passages, cache_path):
        return passages

    def top_ids(self, embeddings, eligible_ids, query, limit):
        self.eligible_ids = eligible_ids
        self.query = query
        return eligible_ids[::-1][:limit]


class HybridSearchTest(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        data_dir = Path(self.directory.name)
        rows = [
            ("lexical", "box", "2028-10-02", "Тема: Счёт 123"),
            ("semantic", "box", "2028-10-02", "Тема: Платёжный документ"),
            ("previous", "box", "2028-10-01", "Тема: Счёт"),
            ("future", "box", "2028-10-04", "Тема: Счёт"),
            ("unknown", "box", None, "Тема: Счёт"),
            ("other-box", "other", "2028-10-02", "Тема: Счёт"),
        ]
        with (data_dir / "documents.jsonl").open("w", encoding="utf-8") as stream:
            for doc_id, mailbox, day, text in rows:
                stream.write(json.dumps({
                    "doc_id": doc_id, "synthetic_user": mailbox, "doc_dt": day, "doc": text,
                }) + "\n")
        self.encoder = RecordingEncoder()
        self.index = MailboxIndex(data_dir, self.encoder)
        self.addCleanup(self.index.db.close)
        self.as_of = date(2028, 10, 3)

    def test_day_and_mailbox_filter_apply_before_vector_ranking(self):
        results = self.index.search("box", "Счёт ВЧЕРА", self.as_of, 2)
        self.assertEqual(self.encoder.eligible_ids, [1, 2])
        self.assertEqual(self.encoder.query, "Счёт")
        self.assertEqual([row["doc_id"] for row in results], ["lexical", "semantic"])

    def test_without_date_excludes_future_and_preserves_undated_mail(self):
        self.index.search("box", "Счёт", self.as_of, 1)
        self.assertEqual(self.encoder.eligible_ids, [1, 2, 3, 5])

    def test_bm25_can_be_selected_on_hybrid_index(self):
        results = self.index.search("box", "Счёт вчера", self.as_of, 10, hybrid=False)
        self.assertEqual([row["doc_id"] for row in results], ["lexical"])

    def test_fusion_keeps_candidates_unique_to_either_list(self):
        self.assertEqual(reciprocal_rank_fusion([1, 2], [3, 2]), [2, 1, 3])
