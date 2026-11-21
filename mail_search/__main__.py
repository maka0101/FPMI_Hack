import argparse
from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sys

import httpx

from .engine import Engine
from .experiments import (evaluate, latency, rank_queries, read_gold, read_queries,
                          run_compare, write_jsonl)


DEFAULT_DATA = Path(__file__).resolve().parent.parent / "mipt_mail_search_participants"
MODES = ("bm25", "encoder", "hybrid")


def integer(lo, hi=None):
    def parse(text):
        value = int(text)
        if value < lo or (hi is not None and value > hi):
            raise argparse.ArgumentTypeError(f"Значение вне диапазона [{lo}, {hi or '∞'}]")
        return value
    return parse


def profile_names(text):
    names = [name.strip() for name in text.split(",")]
    if (len(set(names)) != len(names)
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) for name in names)):
        raise argparse.ArgumentTypeError("Укажите уникальные имена профилей через запятую")
    return names


def timeout_seconds(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("Таймаут должен быть положительным конечным числом")
    return value


def add_engine_args(parser):
    parser.add_argument("--mode", choices=MODES, default=os.getenv("SEARCH_MODE", "bm25"))
    parser.add_argument("--profile", default=os.getenv("MODEL_PROFILE", "encoder-a"))
    parser.add_argument("--ml-url", default=os.getenv("ML_URL", "http://127.0.0.1:8001"))
    add_timeout(parser)


def add_timeout(parser):
    parser.add_argument("--ml-timeout", type=timeout_seconds, default=os.getenv("ML_TIMEOUT", "0.5"))


def parser():
    root = argparse.ArgumentParser(description="Поиск по корпусу писем хакатона")
    root.add_argument("--data", type=Path, default=Path(os.getenv("DATA_DIR", DEFAULT_DATA)))
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Запустить веб-интерфейс")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=integer(1, 65535), default=8000)
    add_engine_args(serve)
    prepare = commands.add_parser("prepare", help="Подготовить версионированные индексы")
    compare = commands.add_parser("compare", help="Сравнить BM25 с encoder и hybrid")
    for command in (prepare, compare):
        command.add_argument("--profiles", type=profile_names, default="encoder-a,encoder-b")
    add_timeout(compare)
    compare.add_argument("--out", type=Path, default=Path("runs/dev"))
    bench = commands.add_parser("benchmark", help="Оценить качество текущей конфигурации")
    export = commands.add_parser("export", help="Получить rankings.jsonl без разметки")
    add_engine_args(bench)
    add_engine_args(export)
    bench.add_argument("--output", type=Path)
    export.add_argument("--output", type=Path, required=True)
    for command in (compare, bench):
        command.add_argument("--qrels", type=Path)
    load = commands.add_parser("loadtest", help="Измерить серверный p99 по HTTP")
    load.add_argument("--url", default="http://127.0.0.1:8000")
    load.add_argument("--mode", choices=MODES, default=os.getenv("SEARCH_MODE", "bm25"))
    load.add_argument("--warmup", type=integer(0), default=99)
    load.add_argument("--requests", type=integer(1), default=990)
    load.add_argument("--concurrency", type=integer(1), default=4)
    load.add_argument("--hardware", help="Описание CPU и RAM целевого сервера")
    load.add_argument("--output", type=Path)
    for command in (compare, bench, export, load):
        command.add_argument("--limit", type=integer(1, 1000), default=10)
        command.add_argument("--queries", type=Path)
    return root


def main():
    root = parser()
    args = root.parse_args()
    if args.command == "prepare":
        from .ml import prepare
        for profile in args.profiles:
            print(json.dumps(prepare(args.data, profile), ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        with closing(Engine(args.data, mode=args.mode, profile_id=args.profile,
                            ml_url=args.ml_url, timeout=args.ml_timeout)) as engine:
            app = create_app(engine, demo_fallback=os.getenv("DEMO_FALLBACK", "0") == "1")
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
        return 0

    queries = args.queries or args.data / "queries_dev.jsonl"
    if args.command == "loadtest":
        from .loadtest import load_test
        report = load_test(args.url, args.mode, queries, args.limit, args.warmup,
                           args.requests, args.concurrency, args.hardware)
        content = json.dumps(report, ensure_ascii=False, indent=2)
        print(content)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content + "\n", encoding="utf-8")
        return 0 if report["passed"] else 1

    # A private query file has no implicit relationship to the public labels.
    qrels = getattr(args, "qrels", None)
    if not args.queries and qrels is None:
        qrels = args.data / "qrels_dev.jsonl"
    if args.command == "compare":
        run_compare(args.data, args.profiles, queries, qrels, args.limit, args.out, args.ml_timeout)
        print(args.out / "report.json")
        return 0
    if args.command == "benchmark" and qrels is None:
        root.error("Для оценки собственных запросов укажите --qrels. Для выдачи используйте export")
    with closing(Engine(args.data, mode=args.mode, profile_id=args.profile,
                        ml_url=args.ml_url, timeout=args.ml_timeout)) as engine:
        engine.ready()
        rankings, times = rank_queries(engine, read_queries(queries), args.limit)
    if args.command == "benchmark":
        scores = evaluate(rankings, read_gold(qrels), args.limit)
        print(f"Queries: {len(rankings)} (judged: {scores['judged_queries']})")
        for name in ("recall", "ndcg", "mrr", "mrr_single_hit"):
            if scores[name] is not None:
                print(f"{name}@{args.limit}: {scores[name]:.4f}")
        print(f"Single-hit queries: {scores['single_hit_queries']}")
        print(f"Search p99: {latency(times)['p99']:.2f} ms")
    if args.output:
        write_jsonl(args.output, rankings)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        sys.exit(f"Ошибка: {exc}")
