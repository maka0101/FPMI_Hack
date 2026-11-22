import re


MIN_QUERY_LENGTH = 180
MAX_SUMMARY_LENGTH = 480
SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+")
SEARCH_INTENT = re.compile(
    r"(?<!\bне )\b(?:разыщи(?:те)?|отыщи(?:те)?|найди(?:те)?|покажи(?:те)?|выведи(?:те)?|"
    r"(?:помоги(?:те)?|помочь|хочу)\s+(?:найти|отыскать)|ищу|нуж(?:ен|на|но|ны))\b", re.IGNORECASE,
)
CONSTRAINT = re.compile(
    r"^(?:(?:важно|уточнение|условие|номер|идентификатор|сумма)\b|"
    r"(?:только|именно|кроме|без|речь|при\s+этом)\b)", re.IGNORECASE,
)
EXACT_ANCHOR = re.compile(
    r"\bSYN-[A-Z0-9]+\b|"
    r"(?:[№#]\s*|\b(?:номер\w*|идентификатор\w*|код\w*)\s*[:=]?\s*)[\w-]*\d[\w-]*\b|"
    r"\b\d+(?:[.,]\d+)?\s*(?:руб(?:ль|ля|лей)?\b|копе(?:йка|йки|ек)\b|рублей\b|RUB\b|₽)|"
    r"\bсумм[ауые]\s*[:—–-]?\s*\d", re.IGNORECASE,
)


def summarize_query(text, *, protect_exact=True):
    """Extract a compact search intent from a long Russian query."""
    if len(text) < MIN_QUERY_LENGTH:
        return None

    clauses = [part.strip(" ,\t") for part in SENTENCE_BREAK.split(text) if part.strip(" ,\t")]
    selected = []
    for index in range(len(clauses) - 1, -1, -1):
        clause = clauses[index]
        matches = list(SEARCH_INTENT.finditer(clause))
        if not matches:
            continue
        intent = clause[matches[-1].start():]
        if len(intent.split()) < 3:
            continue
        selected = [intent, *(part for part_index, part in enumerate(clauses)
                              if part_index != index and CONSTRAINT.match(part))]
        break

    if not selected:
        if len(clauses) > 1:
            selected = [clauses[0], *clauses[-2:]]
        else:
            # In an unpunctuated monologue preserve both ends, including a late intent.
            words = text.split()
            selected = [" ".join(words[:16]), " ".join(words[-32:])]

    summary = " ".join(dict.fromkeys(selected))
    if len(summary) > MAX_SUMMARY_LENGTH:
        head = summary[:300].rsplit(" ", 1)[0]
        tail = summary[-177:].split(" ", 1)[-1]
        summary = f"{head} … {tail}"
    if protect_exact and EXACT_ANCHOR.search(summary):
        return None
    return summary if len(summary) < len(text) * 0.8 else None
