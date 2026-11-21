from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mail_search.query_summary import summarize_query
from mail_search.search import MailboxIndex, reciprocal_rank_fusion


class RecordingEncoder:
    def index(self, passages, cache_path):
        return passages

    def top_ids(self, embeddings, eligible_ids, query, limit):
        self.eligible_ids = eligible_ids
        self.query = query
        return eligible_ids[::-1][:limit]


class RecordingReranker:
    def rank(self, query, passages):
        self.query = query
        self.passages = passages
        return list(reversed(range(len(passages))))


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

    def test_reranker_can_promote_a_candidate_below_the_output_limit(self):
        reranker = RecordingReranker()
        self.index.reranker = reranker
        hybrid = self.index.search("box", "Счёт вчера", self.as_of, 1)
        reranked = self.index.search("box", "Счёт вчера", self.as_of, 1, rerank=True)
        self.assertEqual([row["doc_id"] for row in hybrid], ["lexical"])
        self.assertEqual([row["doc_id"] for row in reranked], ["semantic"])
        self.assertEqual(reranker.query, "Счёт")
        self.assertEqual(reranker.passages, ["Тема: Счёт 123", "Тема: Платёжный документ"])

    def test_summary_branch_can_add_a_candidate_inside_the_same_filters(self):
        context = "Сначала я просмотрел старую переписку и собрал документы. " * 7
        query = context + "Мне нужны счета, полученные вчера. Важно сохранить номер 123."
        with patch.object(self.encoder, "top_ids", side_effect=([1], [2])) as top_ids:
            results = self.index.search("box", query, self.as_of, 2, protect_exact=False)
        self.assertEqual([row["doc_id"] for row in results], ["lexical", "semantic"])
        original, summary = [call.args for call in top_ids.call_args_list]
        self.assertEqual(original[1], [1, 2])
        self.assertEqual(summary[1], [1, 2])
        self.assertIn("нужны счета", summary[2])
        self.assertIn("номер 123", summary[2])
        self.assertNotIn("вчера", summary[2])
        self.assertLess(len(summary[2]), len(original[2]))

    def test_duplicate_dense_list_does_not_get_an_extra_vote(self):
        query = "Я просмотрел старую переписку в архиве. " * 8 + "Найди счёт вчера."
        with patch.object(self.encoder, "top_ids", side_effect=([2], [2])):
            results = self.index.search("box", query, self.as_of, 1)
        self.assertEqual([row["doc_id"] for row in results], ["lexical"])

    def test_compact_query_is_not_summarized(self):
        self.assertIsNone(summarize_query("Покажи счёт 123"))

    def test_protected_mode_does_not_add_a_vote_for_an_exact_reference_or_amount(self):
        background = "Я просмотрел старую переписку и заглянул в архив. " * 8
        for intent in ("Покажи письмо с кодом SYN-83D5F19A.", "Мне нужны подтверждения на сумму 13 рублей и 50 копеек."):
            query = background + intent
            self.assertIsNone(summarize_query(query))
            self.assertIsNotNone(summarize_query(query, protect_exact=False))
