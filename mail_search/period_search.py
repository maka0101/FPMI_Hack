"""Period parsing and date-scoped FTS retrieval shared with the main backend."""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from .search import MailboxIndex as LegacyMailboxIndex, WORD, STOP_WORDS, normalize, fts_expression


MONTHS = {
    name: month
    for month, name in enumerate(
        "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
        start=1,
    )
}
RELATIVE_DAYS = {"сегодня": 0, "вчера": 1, "позавчера": 2}
MONTH_NAME = "|".join(MONTHS)
YESTERDAY = r"вчерашн(?:ий|яя|ее|ие|его|ей|ему|им|ем|юю|их|ими|ею)"
RELATIVE = rf"(?:позавчера|вчера|сегодня|{YESTERDAY}(?:\s+(?:день|дня|дню|днем|днём|дне)\b)?)"
ISO_DAY = r"\d{4}-\d{2}-\d{2}"
MONTH_DAY = rf"\d{{1,2}}\s+(?:{MONTH_NAME})(?:\s+\d{{4}}(?:\s+года\b)?)?"
SHORT_NUMERIC = r"\d{1,2}\.\d{1,2}"
FULL_DATE = rf"(?:{RELATIVE}|{ISO_DAY}|{SHORT_NUMERIC}\.\d{{4}}|{MONTH_DAY})"
RANGE_DATE = rf"(?:{FULL_DATE}|{SHORT_NUMERIC})"
DATE_IN_QUERY = re.compile(
    rf"\b(?:получен\w*\s+|прислан\w*\s+|приш(?:ло|ли|едшие)\s+)?"
    rf"(?:со?\s+(?P<start>{RANGE_DATE}|\d{{1,2}})\s+по\s+(?P<end>{RANGE_DATE})(?!\.\d)"
    rf"|(?P<single>{FULL_DATE}))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Начало периода позже его конца")


def date_parts(text, as_of):
    """Return year, month, day. Omitted parts are shared by the range endpoints."""
    if text.startswith("вчерашн"):
        text = "вчера"
    if text in RELATIVE_DAYS:
        try:
            day = as_of - timedelta(days=RELATIVE_DAYS[text])
        except OverflowError as error:
            raise ValueError("Вычисленная дата выходит за допустимый диапазон") from error
        return day.year, day.month, day.day
    if "-" in text:
        day = date.fromisoformat(text)
        return day.year, day.month, day.day
    fields = text.split(".") if "." in text else text.split()
    month = None
    if len(fields) > 1:
        month = int(fields[1]) if fields[1].isdigit() else MONTHS[fields[1]]
    return int(fields[2]) if len(fields) >= 3 else None, month, int(fields[0])


def parse_period(match, as_of):
    if match["single"]:
        year, month, day = date_parts(match["single"], as_of)
        single = date(year if year is not None else as_of.year, month, day)
        return DateRange(single, single)

    start_year, start_month, start_day = date_parts(match["start"], as_of)
    end_year, end_month, end_day = date_parts(match["end"], as_of)
    start_month = start_month if start_month is not None else end_month
    # An omitted year can span New Year, e.g. «с 29 декабря по 2 января 2028».
    crosses_year = start_month > end_month
    if end_year is None:
        end_year = as_of.year if start_year is None else start_year + crosses_year
    if start_year is None:
        start_year = end_year - crosses_year
    return DateRange(date(start_year, start_month, start_day), date(end_year, end_month, end_day))


def parse_query(text, as_of):
    text = normalize(text)
    match = DATE_IN_QUERY.search(text)
    target = None
    if match:
        target = parse_period(match, as_of)
        text = text[:match.start()] + " " + text[match.end():]

    words = list(dict.fromkeys(WORD.findall(text)))
    return [word for word in words if word not in STOP_WORDS][:32], target


class MailboxIndex(LegacyMailboxIndex):
    def search(self, mailbox, query, as_of, limit=20):
        if mailbox not in self.mailboxes or not 1 <= limit <= 1000:
            raise ValueError("Invalid mailbox or result limit")
        words, period = parse_query(query, as_of)
        return self.search_parsed(mailbox, words, as_of, period, limit)

    def search_parsed(self, mailbox, words, as_of, period, limit, *,
                      exclude_doc_id=None, near_day=None):
        if period and period.start > as_of:
            return []
        filters = "m.mailbox = ? AND (m.day IS NULL OR m.day <= ?)"
        params = [mailbox, as_of.isoformat()]
        if period:
            filters += " AND m.day BETWEEN ? AND ?"
            params.extend((period.start.isoformat(), period.end.isoformat()))
        if exclude_doc_id is not None:
            filters += " AND m.doc_id <> ?"
            params.append(exclude_doc_id)

        fields = "m.doc_id, m.subject, m.day, substr(m.body, 1, 240) AS preview"
        if words:
            sql = f"""
                SELECT {fields} FROM mail_fts JOIN mail AS m ON m.id = mail_fts.rowid
                WHERE mail_fts MATCH ? AND {filters}
                ORDER BY bm25(mail_fts, 3.0, 1.0), m.day DESC, m.doc_id LIMIT ?
            """
            params.insert(0, fts_expression(words))
        else:
            order = "m.day DESC, m.doc_id"
            if near_day is not None:
                order = "abs(julianday(m.day) - julianday(?)), m.doc_id"
                params.append(near_day.isoformat())
            sql = f"""
                SELECT {fields} FROM mail AS m WHERE {filters}
                ORDER BY {order} LIMIT ?
            """
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, [*params, limit])]
