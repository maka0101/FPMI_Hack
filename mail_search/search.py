import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from threading import Lock


MONTHS = {
    name: month
    for month, name in enumerate(
        "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
        start=1,
    )
}
RELATIVE_DAYS = {"сегодня": 0, "вчера": 1, "позавчера": 2}
WORD = re.compile(r"[^\W_]+")
RUSSIAN = re.compile(r"[а-я]+")
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
STOP_WORDS = set(
    "а без в во где для до за и из как ли мне на найди найти о об от по покажи "
    "полученные письмо письма писем про с со что это".split()
)


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def normalize(text):
    return text.lower().replace("ё", "е")


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


def fts_expression(words):
    clauses = []
    for word in words:
        exact = f'"{word}"'
        if len(word) >= 5 and RUSSIAN.fullmatch(word):
            # Keep an exact match and allow common differences in Russian endings.
            prefix = word[:max(4, len(word) - (3 if len(word) >= 8 else 2))]
            clauses.append(f'({exact} OR "{prefix}"*)')
        else:
            clauses.append(exact)
    return " OR ".join(clauses)


class MailboxIndex:
    def __init__(self, data_dir):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = Lock()
        self.db.executescript("""
            CREATE TABLE mail (
                id INTEGER PRIMARY KEY,
                doc_id TEXT UNIQUE NOT NULL,
                mailbox TEXT NOT NULL,
                day TEXT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL
            );
            CREATE INDEX inbox ON mail(mailbox, day DESC, doc_id);
            CREATE VIRTUAL TABLE mail_fts USING fts5(subject, body, prefix='4 5 6');
        """)
        with self.db:
            for row in read_jsonl(data_dir / "documents.jsonl"):
                text = row["doc"].strip()
                heading, _, body = text.partition("\n")
                if normalize(heading).startswith("тема:"):
                    subject = heading.partition(":")[2].strip()
                    searchable_body = body.strip()
                else:
                    subject = ""
                    searchable_body = text
                cursor = self.db.execute(
                    "INSERT INTO mail(doc_id, mailbox, day, subject, body) VALUES (?, ?, ?, ?, ?)",
                    (row["doc_id"], row["synthetic_user"], row["doc_dt"], subject, text),
                )
                self.db.execute(
                    "INSERT INTO mail_fts(rowid, subject, body) VALUES (?, ?, ?)",
                    (cursor.lastrowid, normalize(subject), normalize(searchable_body)),
                )
        self.mailboxes = {
            row["mailbox"]: row["latest_day"]
            for row in self.db.execute(
                "SELECT mailbox, max(day) AS latest_day FROM mail GROUP BY mailbox ORDER BY mailbox"
            )
        }

    def search(self, mailbox, query, as_of, limit=20):
        if mailbox not in self.mailboxes:
            raise ValueError("Неизвестный почтовый ящик")
        if not 1 <= limit <= 1000:
            raise ValueError("Лимит должен быть от 1 до 1000")

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

    def candidate_rows(self, doc_ids, mailbox, as_of, period):
        """Resolve the ML ranking against the same visibility rules as FTS."""
        if not doc_ids:
            return []
        sql = """
            SELECT m.doc_id, m.subject, m.day, substr(m.body, 1, 240) AS preview
            FROM json_each(?) AS candidate JOIN mail AS m ON m.doc_id = candidate.value
            WHERE m.mailbox = ? AND (m.day IS NULL OR m.day <= ?)
        """
        params = [json.dumps(doc_ids), mailbox, as_of.isoformat()]
        if period:
            sql += " AND m.day BETWEEN ? AND ?"
            params.extend((period.start.isoformat(), period.end.isoformat()))
        with self.lock:
            rows = {row["doc_id"]: dict(row) for row in self.db.execute(sql, params)}
        return [rows[doc_id] for doc_id in doc_ids if doc_id in rows]

    def message(self, mailbox, doc_id, as_of):
        with self.lock:
            row = self.db.execute(
                """SELECT doc_id, subject, day, body FROM mail
                   WHERE mailbox = ? AND doc_id = ? AND (day IS NULL OR day <= ?)""",
                (mailbox, doc_id, as_of.isoformat()),
            ).fetchone()
        return dict(row) if row else None
