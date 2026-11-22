"""Build fresh mail intents and relevance labels from the synthetic corpus."""
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from random import Random
import re

from mail_search.experiment_search import normalize, parse_query, read_jsonl


ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "mipt_mail_search_participants"
OUTPUT = ROOT / "expanded"
SEED = 71293

# Subject prefixes classify explicit notification templates. Search requests use different wording.
EVENTS = {
    "order": (r"^(?:есть |поступил |получен )?новый заказ(?:$|[ —.])", "извещения о том, что клиент оформил покупку"),
    "cancel": (r"^покупатель отменил заказ", "сообщения о том, что клиент отказался от оформленной покупки"),
    "refund": (r"^покупатель хочет вернуть товар", "обращения покупателей с просьбой принять товар обратно"),
    "receipt": (r"^(?:ваш чек\b|чек \+ бонус за покупку)", "электронные кассовые квитанции за покупки"),
    "fine": (r"^вам выставлен новый штраф", "оповещения о начисленной денежной санкции"),
    "invoice": (r"^счет на оплату", "выставленные платёжные документы, по которым предстоит заплатить"),
    "payment_ok": (r"^успешная оплата", "подтверждения, что списание денег прошло"),
    "payment_failed": (r"^операция отклонена", "оповещения о том, что деньги списать не удалось"),
    "recipe": (r"^ошибка в модуле [«\"]электронный рецепт", "уведомления о сбое при цифровой выписке лекарств"),
    "database": (r"^ошибка при работе в базе", "оповещения о неполадках при обращении к базе данных"),
    "acceptance": (r"^новый документ[\s—.]+уведомление о приемке", "подтверждения, что поставку приняли"),
}
SUBJECT = re.compile(r"^тема:[ \t]*([^\n]+)", re.IGNORECASE | re.MULTILINE)
AMOUNT = re.compile(
    r"\b(?:сумм[ау](?:\s+начисления)?|итого|к\s+оплате)\s*[:–—=-]?\s*"
    r"(\d{1,8}(?:[ \u00a0]\d{3})*)[.,](\d{2})(?!\d)", re.IGNORECASE,
)
REFERENCE = re.compile(r"\bSYN-[A-Z0-9]{6,14}\b", re.IGNORECASE)
MONEY_EVENTS = {"order", "receipt", "fine", "invoice", "payment_ok", "payment_failed"}

BACKGROUND = (
    "Ситуация такая, пересматриваю большой ящик после перерыва и пытаюсь восстановить ход событий. "
    "Рядом лежат старые переписки, черновики и автоответы, они только сбивают с толку.",
    "До этого я несколько раз листал архив вручную. В нём попадаются рассылки, служебные напоминания "
    "и письма с одинаково общими заголовками. От одного вида списка трудно понять, что к чему относится.",
    "Я сперва думал, что нужная запись видна по теме, но заголовки часто похожи. "
    "В ответах бывает много цитат и пересланных блоков, из-за этого всё выглядит как одна цепочка.",
    "У меня сейчас открыто несколько вкладок, где вперемешку обсуждения, договорённости "
    "и уведомления от разных систем. Старые заметки почти никак не помогают разобрать этот архив.",
    "Сотрудник передал мне материалы перед уходом. Осталась большая папка переписки, "
    "несколько черновых списков и скриншоты. По одному скриншоту сложно восстановить, какое письмо было первым.",
    "Пока разбирался, наткнулся на подтверждение брони и несколько сообщений из поддержки. "
    "В той же папке сохранились напоминания, графики, письма от коллег и автоматические отчёты с повторяющимися темами.",
    "Часть сообщений уже просмотрена, но отметки проставлены не везде. "
    "Меня интересует конкретная выдача в интерфейсе почты, чтобы открыть исходные сообщения и быстро их сверить.",
    "Работаю с этим архивом не каждый день и легко путаю цепочки. "
    "Между другими задачами возвращаюсь к нему урывками, поэтому деталей из разных разговоров накопилось много.",
    "В выписках не совпали номера страниц, затем коллеги прислали ещё один файл. "
    "Параллельно шли переносы встреч, обсуждения доставки, согласование документов и переписка с бухгалтерией.",
    "В разгаре работы система показывала разные статусы. На экране всё перемешалось: старые протоколы, "
    "обновления таблиц, оповещения о версиях и сообщения о технических работах.",
    "Я делаю сверку перед короткой встречей и собираю документы по частям. "
    "Часть сведений была в отдельном отчёте, часть обсуждали в общем чате и потом пересылали друг другу.",
    "Список не помещается на одном экране. В нём есть обсуждения доступа, уведомления о задачах, "
    "копии пересланных сообщений, старые приглашения и совершенно посторонние сервисные письма.",
    "Контекст может быть запутанным: сперва часть работы шла вручную, потом всё перенесли. "
    "Из-за порядка пересылок в архиве трудно отличить первый документ от более позднего разговора о нём.",
    "Пока я собирал материалы, пришло много напоминаний о других делах. Некоторые письма отмечены флажком, "
    "а часть осталась без меток, поэтому пользоваться сортировкой по флажкам оказалось неудобно.",
    "Обычно архив сортируется по дате добавления, а сейчас на экране ещё включена группировка по обсуждениям. "
    "Мне важнее содержимое нужной выдачи, чтобы потом привести записи в один порядок.",
    "В папках кроме рабочих обсуждений есть счета, уведомления об операциях и письма про возврат. "
    "Они перемежаются с отчётами и не имеют отношения к задаче, которую я сейчас уточняю.",
)
GOALS = ("Найди {object}.", "Мне нужны {object}.", "Покажи {object}.", "Выведи {object}.",
         "Можешь помочь отыскать {object}?", "В итоге я ищу {object}.")


def event_family(text):
    match = SUBJECT.search(text)
    subject = normalize((match[1] if match else text.split("\n", 1)[0]).strip())
    return next((family for family, (pattern, _) in EVENTS.items() if re.search(pattern, subject)), None)


def amount_field(text):
    values = {(int(whole.replace(" ", "").replace("\u00a0", "")), int(cents)) for whole, cents in AMOUNT.findall(text)}
    return next(iter(values)) if len(values) == 1 else None


def inflect(value, words):
    units = value % 10
    form = 2 if 11 <= value % 100 <= 14 else 0 if units == 1 else 1 if 2 <= units <= 4 else 2
    return f"{value} {words[form]}"


def spoken_amount(amount):
    rubles, cents = amount
    text = inflect(rubles, ("рубль", "рубля", "рублей"))
    if cents:
        text += " и " + inflect(cents, ("копейка", "копейки", "копеек"))
    return text


def balanced_sample(cases, limit, used, rng):
    buckets = defaultdict(list)
    for case in cases:
        buckets[(case["mailbox"], case["family"])].append(case)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    keys = sorted(buckets)
    rng.shuffle(keys)
    selected = []
    while len(selected) < limit and keys:
        for key in keys:
            bucket = buckets[key]
            while bucket:
                case = bucket.pop()
                if used.isdisjoint(case["ids"]):
                    selected.append(case)
                    used.update(case["ids"])
                    break
            if len(selected) == limit:
                break
        keys = [key for key in keys if buckets[key]]
    return selected


def build_cases():
    rng = Random(SEED)
    documents = list(read_jsonl(DATA / "documents.jsonl"))
    old_days = set()
    for row in read_jsonl(DATA / "queries_dev.jsonl"):
        _, day = parse_query(row["query"], date.fromisoformat(row["query_date"]))
        if day:
            old_days.add((row["synthetic_user"], day.isoformat()))
    used = {row["doc_id"] for row in read_jsonl(DATA / "qrels_dev.jsonl") if row["relevance"] > 0}
    latest = defaultdict(str)
    day_sizes = Counter()
    events = defaultdict(list)
    amounts = defaultdict(list)
    references = defaultdict(list)
    for row in documents:
        mailbox, day, doc_id = row["synthetic_user"], row["doc_dt"], row["doc_id"]
        text = row["doc"]
        latest[mailbox] = max(latest[mailbox], day or "")
        day_sizes[(mailbox, day)] += 1
        family = event_family(text)
        if family and day:
            events[(mailbox, day, family)].append(doc_id)
        if family in MONEY_EVENTS:
            amount = amount_field(text)
            if amount is not None:
                amounts[(mailbox, family, amount)].append(doc_id)
        for reference in sorted({match.group().upper() for match in REFERENCE.finditer(text)}):
            references[(mailbox, reference)].append(doc_id)
    doc_days = {row["doc_id"]: row["doc_dt"] for row in documents}

    def make_case(mailbox, kind, family, target, text, ids, query_date):
        key = json.dumps([mailbox, kind, family, target], ensure_ascii=False)
        anchor = min(day for doc_id in ids if (day := doc_days[doc_id])) if any(doc_days[x] for x in ids) else "undated"
        return {
            "case_id": "x-" + sha256(key.encode()).hexdigest()[:16], "block_id": f"{mailbox}/{anchor}",
            "mailbox": mailbox, "kind": kind, "family": family, "target": target,
            "object": text, "ids": sorted(ids), "query_date": query_date,
        }

    event_cases = [
        make_case(mailbox, "event_day", family, day, f"{EVENTS[family][1]}, полученные {day}", ids, day)
        for (mailbox, day, family), ids in sorted(events.items())
        if (mailbox, day) not in old_days and 1 <= len(ids) <= 80 and day_sizes[mailbox, day] - len(ids) >= 5
    ]
    amount_cases = [
        make_case(mailbox, "event_amount", family, amount,
                  f"{EVENTS[family][1]} на сумму {spoken_amount(amount)}", ids, latest[mailbox])
        for (mailbox, family, amount), ids in sorted(amounts.items()) if 1 <= len(ids) <= 8
    ]
    reference_cases = [
        make_case(mailbox, "reference", "reference", reference,
                  f"письма, где указан код {reference}", ids, latest[mailbox])
        for (mailbox, reference), ids in sorted(references.items()) if 1 <= len(ids) <= 8
    ]
    return sorted((
        *balanced_sample(event_cases, 80, used, rng),
        *balanced_sample(amount_cases, 260, used, rng),
        *balanced_sample(reference_cases, 100, used, rng),
    ), key=lambda case: case["case_id"])


def write_benchmark(cases):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rng = Random(SEED + 1)
    with (OUTPUT / "queries.jsonl").open("w", encoding="utf-8") as qf, (
        OUTPUT / "qrels.jsonl"
    ).open("w", encoding="utf-8") as rf:
        for position, case in enumerate(cases):
            goal = GOALS[position % len(GOALS)].format(object=case["object"])
            background = rng.sample(BACKGROUND, (2, 6, 15)[position % 3])
            # Rotate the intent location independently of the length tier.
            insertion = (0, len(background) // 2, len(background))[(position // 3) % 3]
            verbose = " ".join([*background[:insertion], goal, *background[insertion:]])
            for variant, text in (("compact", goal), ("long", verbose)):
                row = {key: case[key] for key in ("case_id", "block_id", "kind", "family", "target", "query_date")}
                row.update(query_id=f"{case['case_id']}-{variant}", synthetic_user=case["mailbox"],
                           variant=variant, query=text)
                qf.write(json.dumps(row, ensure_ascii=False) + "\n")
                for doc_id in case["ids"]:
                    rf.write(json.dumps({"query_id": row["query_id"], "doc_id": doc_id, "relevance": 1}) + "\n")
    print(f"{len(cases)} cases, {2 * len(cases)} queries, {2 * sum(len(c['ids']) for c in cases)} judgments")
    print(f"{len({c['mailbox'] for c in cases})} mailboxes, {len({c['block_id'] for c in cases})} blocks")
    print(dict(Counter(c["kind"] for c in cases)))


if __name__ == "__main__":
    write_benchmark(build_cases())
