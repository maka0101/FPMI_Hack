from datetime import date
import unittest

from benchmarks.harrier_transfer.ranker import FieldIndex
from mail_search.search import parse_query


class TransferRankingTests(unittest.TestCase):
    def setUp(self):
        rows = [
            ("lexical", "user", "2026-11-19", "Тема: Отчёт"),
            ("field", "user", "2026-11-20", "Тема: Приёмка\nСклад"),
            ("semantic", "user", "2026-11-20", "Что-то ещё"),
            ("future", "user", "2026-11-22", "Тема: Приёмка"),
            ("unknown", "user", None, "Тема: Приёмка"),
            ("other", "other_user", "2026-11-20", "Тема: Приёмка"),
        ]
        self.index = FieldIndex(dict(doc_id=d, synthetic_user=u, doc_dt=t, doc=text)
                                for d, u, t, text in rows)
        self.as_of = date(2026, 11, 21)

    def test_period_retrieval_introduces_field_match(self):
        query = "приёмка с 19.11.2026 по 24.11.2026"
        outputs = self.index.rankings(query, "user", self.as_of, ["lexical"],
                                      ["future", "other", "unknown", "semantic"])
        self.assertEqual(outputs["fallback"], ["lexical", "field", "semantic"])
        self.assertEqual(outputs["fresh_only"], ["lexical", "semantic"])
        self.assertEqual(outputs["native"][0], "field")

    def test_relative_date_and_browse(self):
        query = "вчерашние письма"
        words, period = parse_query(query, self.as_of)
        self.assertEqual(words, [])
        self.assertEqual(period.start, date(2026, 11, 20))
        self.assertEqual(period.start, period.end)
        outputs = self.index.rankings(query, "user", self.as_of, ["future", "field", "unknown"], [])
        self.assertTrue(all(ids == ["field"] for ids in outputs.values()))

    def test_undated_unknown_date_no_bonus(self):
        outputs = self.index.rankings("приёмка", "user", self.as_of,
                                      ["unknown", "future", "other", "field"], ["unknown", "field"])
        self.assertEqual(outputs["baseline"], ["unknown", "field"])
        self.assertEqual(outputs["fallback"], ["field", "unknown"])
