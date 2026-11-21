import json
import re
import sqlite3
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
DATE_IN_QUERY = re.compile(
    r"\b(?:получен\w*\s+|прислан\w*\s+|приш(?:ло|ли|едшие)\s+)?"
    r"(?:(?P<relative>позавчера|вчера|сегодня)\b"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})\b"
    r"|(?P<numeric>\d{1,2}\.\d{1,2}\.\d{4})\b"
    r"|(?P<day>\d{1,2})\s+(?P<month>" + "|".join(MONTHS) + r")\b"
    r"(?:\s+(?P<year>\d{4})(?:\s+года\b)?)?)",
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


def split_query(text, as_of):
    match = DATE_IN_QUERY.search(text)
    target = None
    if match:
        if match["relative"]:
            target = as_of - timedelta(days=RELATIVE_DAYS[match["relative"].lower()])
        elif match["iso"]:
            target = date.fromisoformat(match["iso"])
        elif match["numeric"]:
            day, month, year = map(int, match["numeric"].split("."))
            target = date(year, month, day)
        else:
            target = date(int(match["year"] or as_of.year), MONTHS[match["month"].lower()], int(match["day"]))
        text = text[:match.start()] + " " + text[match.end():]

    words = list(dict.fromkeys(WORD.findall(normalize(text))))
    return [word for word in words if word not in STOP_WORDS][:32], target, " ".join(text.split())


def parse_query(text, as_of):
    words, target, _ = split_query(text, as_of)
    return words, target


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
    def __init__(self, data_dir, embedder=None, embeddings_cache=None):
        self.embedder = embedder
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
        if embedder is not None:
            passages = [row["body"] for row in self.db.execute("SELECT body FROM mail ORDER BY id")]
            self.embeddings = embedder.index(passages, embeddings_cache)

    def search(self, mailbox, query, as_of, limit=20, *, hybrid=True):
        if mailbox not in self.mailboxes:
            raise ValueError("Неизвестный почтовый ящик")
        if not 1 <= limit <= 1000:
            raise ValueError("Лимит должен быть от 1 до 1000")

        words, target_day, semantic_query = split_query(query, as_of)
        if target_day and target_day > as_of:
            return []
        filters = "m.mailbox = ? AND (m.day IS NULL OR m.day <= ?)"
        params = [mailbox, as_of.isoformat()]
        if target_day:
            filters += " AND m.day = ?"
            params.append(target_day.isoformat())

        use_vectors = hybrid and self.embedder is not None and bool(words)
        fields = "m.id, m.doc_id, m.subject, m.day, substr(m.body, 1, 240) AS preview"
        pool_size = max(limit, 50) if use_vectors else limit
        if words:
            sql = f"""
                SELECT {fields} FROM mail_fts JOIN mail AS m ON m.id = mail_fts.rowid
                WHERE mail_fts MATCH ? AND {filters}
                ORDER BY bm25(mail_fts, 3.0, 1.0), m.day DESC, m.doc_id LIMIT ?
            """
            sql_params = [fts_expression(words), *params, pool_size]
        else:
            sql = f"""
                SELECT {fields} FROM mail AS m WHERE {filters}
                ORDER BY m.day DESC, m.doc_id LIMIT ?
            """
            sql_params = [*params, limit]
        with self.lock:
            lexical = self.db.execute(sql, sql_params).fetchall()
        if not use_vectors:
            return [search_result(row) for row in lexical]

        with self.lock:
            eligible = self.db.execute(
                f"SELECT m.id FROM mail m WHERE {filters} ORDER BY m.day DESC, m.doc_id",
                params,
            ).fetchall()
        if not eligible:
            return []

        eligible_ids = [row["id"] for row in eligible]
        dense_ids = self.embedder.top_ids(self.embeddings, eligible_ids, semantic_query, pool_size)
        ranked = reciprocal_rank_fusion([row["id"] for row in lexical], dense_ids)[:limit]
        placeholders = ",".join("?" for _ in ranked)
        with self.lock:
            results = {
                row["id"]: search_result(row)
                for row in self.db.execute(
                    f"SELECT {fields} FROM mail m WHERE m.id IN ({placeholders})", ranked
                )
            }
        return [results[mail_id] for mail_id in ranked]

    def message(self, mailbox, doc_id, as_of):
        with self.lock:
            row = self.db.execute(
                """SELECT doc_id, subject, day, body FROM mail
                   WHERE mailbox = ? AND doc_id = ? AND (day IS NULL OR day <= ?)""",
                (mailbox, doc_id, as_of.isoformat()),
            ).fetchone()
        return dict(row) if row else None


def reciprocal_rank_fusion(*rankings):
    scores = {}
    for ranking in rankings:
        for position, mail_id in enumerate(ranking, start=1):
            scores[mail_id] = scores.get(mail_id, 0.0) + 1 / (60 + position)
    return sorted(scores, key=scores.__getitem__, reverse=True)


def search_result(row):
    return {"doc_id": row["doc_id"], "subject": row["subject"], "day": row["day"], "preview": row["preview"]}
