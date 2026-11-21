import argparse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

from .comparison import compare, ranking_metrics, read_relevance
from .model_catalog import EMBEDDERS, RERANKERS
from .search import MAX_QUERY_CHARS, MailboxIndex, read_jsonl


DEFAULT_DATA = Path(__file__).resolve().parent.parent / "mipt_mail_search_participants"
DEFAULT_CACHE = DEFAULT_DATA.parent / ".cache"


def benchmark(index, data_dir, limit, output):
    queries = list(read_jsonl(data_dir / "queries_dev.jsonl"))
    gold = read_relevance(data_dir)

    recalls, ndcgs, mrrs, timings, rankings = [], [], [], [], []
    for query in queries:
        relevance = gold[query["query_id"]]
        as_of = date.fromisoformat(query["query_date"])
        started = perf_counter()
        results = index.search(query["synthetic_user"], query["query"], as_of, limit)
        timings.append((perf_counter() - started) * 1000)
        ids = [result["doc_id"] for result in results]
        rankings.append({"query_id": query["query_id"], "doc_ids": ids})

        gains = [relevance.get(doc_id, 0) for doc_id in ids]
        if relevance:
            recall, ndcg = ranking_metrics(ids, relevance, limit)
            recalls.append(recall)
            ndcgs.append(ndcg)
        if len(relevance) == 1:
            mrrs.append(next((1 / rank for rank, gain in enumerate(gains, 1) if gain), 0))

    if output:
        with output.open("w", encoding="utf-8") as stream:
            for ranking in rankings:
                stream.write(json.dumps(ranking, ensure_ascii=False) + "\n")
    print(f"Queries: {len(queries)}")
    if recalls:
        print(f"Recall@{limit}: {sum(recalls) / len(recalls):.4f}")
        print(f"nDCG@{limit}:   {sum(ndcgs) / len(ndcgs):.4f}")
    if mrrs:
        print(f"MRR@{limit}:    {sum(mrrs) / len(mrrs):.4f} (single-hit queries: {len(mrrs)})")
    if timings:
        timings.sort()
        print(f"Search p99: {timings[math.ceil(0.99 * len(timings)) - 1]:.2f} ms")


def create_server(index, port, *, quiet=False):
    page = Path(__file__).with_name("index.html").read_bytes()
    modes = ["bm25"]
    if index.embedder:
        modes.extend(("hybrid", "hybrid-summary-raw", "hybrid-summary"))
    if index.reranker:
        modes.extend(("hybrid-rerank", "hybrid-summary-raw-rerank", "hybrid-summary-rerank"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_string, *args):
            if not quiet:
                super().log_message(format_string, *args)

        def parse_request(self):
            self.request_started_at = perf_counter()
            return super().parse_request()

        def respond(self, status, content, content_type="application/json", *, timed=False):
            if content_type == "application/json":
                content = json.dumps(content, ensure_ascii=False).encode("utf-8")
            duration = (perf_counter() - self.request_started_at) * 1000 if timed else None
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            if duration is not None:
                self.send_header("Server-Timing", f"search;dur={duration:.6f}")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            request = urlsplit(self.path)
            if request.path == "/":
                self.respond(200, page, "text/html")
                return
            if request.path == "/api/mailboxes":
                self.respond(200, index.mailboxes)
                return
            if request.path not in {"/api/search", "/api/message"}:
                self.respond(404, {"error": "Страница не найдена"})
                return

            params = parse_qs(request.query)
            try:
                mailbox = params.get("mailbox", [""])[0]
                if mailbox not in index.mailboxes:
                    raise ValueError("Неизвестный почтовый ящик")
                default_day = index.mailboxes[mailbox] or date.today().isoformat()
                as_of = date.fromisoformat(params.get("as_of", [default_day])[0])
                if request.path == "/api/search":
                    query = params.get("q", [""])[0]
                    if len(query) > MAX_QUERY_CHARS:
                        raise ValueError(f"Запрос должен содержать не более {MAX_QUERY_CHARS} символов")
                    mode = params.get("mode", [modes[-1]])[0]
                    if mode not in modes:
                        raise ValueError(f"Доступные режимы поиска: {', '.join(modes)}")
                    limit = int(params.get("limit", ["20"])[0])
                    result = index.search(
                        mailbox, query, as_of, limit, hybrid=mode != "bm25", rerank=mode.endswith("-rerank"),
                        summary_branch="-summary" in mode, protect_exact="-raw" not in mode,
                    )
                else:
                    doc_id = params.get("doc_id", [""])[0]
                    result = index.message(mailbox, doc_id, as_of)
            except ValueError as error:
                self.respond(400, {"error": str(error)})
                return
            if result is None:
                self.respond(404, {"error": "Письмо недоступно"})
                return
            self.respond(200, result, timed=request.path == "/api/search")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(index, port):
    with create_server(index, port) as server:
        print(f"Почта: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def build_index(args):
    name = args.embedder or ("e5" if args.model_dir else None)
    if name is None:
        return MailboxIndex(args.data)
    if name == "e5":
        from .embeddings import E5Encoder

        embedder = E5Encoder(args.model_dir or DEFAULT_CACHE / "e5-model")
    else:
        from .torch_models import TorchEncoder

        embedder = TorchEncoder(name, args.model_dir or DEFAULT_CACHE / "models" / name, args.device)

    reranker = None
    if args.reranker:
        from .torch_models import CrossEncoder

        model_dir = args.reranker_dir or DEFAULT_CACHE / "models" / args.reranker
        reranker = CrossEncoder(args.reranker, model_dir, args.device)
    cache = args.embeddings_cache or DEFAULT_CACHE / f"{name}-embeddings.npz"
    return MailboxIndex(args.data, embedder, cache, reranker)


def main():
    parser = argparse.ArgumentParser(description="Поиск по корпусу писем хакатона")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve", help="Запустить локальный веб-интерфейс")
    server.add_argument("--port", type=int, default=8000)
    bench = commands.add_parser("benchmark", help="Оценить поиск на открытом бенчмарке")
    bench.add_argument("--limit", type=int, default=10)
    bench.add_argument("--output", type=Path, help="Сохранить ранжированные doc_id в JSONL")
    comparison = commands.add_parser("compare", help="Сравнить BM25 с гибридом через HTTP")
    comparison.add_argument("--paraphrases", type=Path,
                            default=DEFAULT_DATA.parent / "benchmarks" / "paraphrases.jsonl")
    comparison.add_argument("--repeats", type=int, default=5)
    comparison.add_argument("--output", type=Path, help="Сохранить метрики в JSON")
    comparison.add_argument("--include-undated", action="store_true", help="Проверить поиск известных писем без дня")
    expanded = commands.add_parser("evaluate-expanded", help="Сравнить две и три ветки на расширенной разметке")
    expanded.add_argument("--suite", type=Path, default=DEFAULT_DATA.parent / "benchmarks" / "expanded")
    expanded.add_argument("--output", type=Path, required=True)
    expanded.add_argument("--bm25-control", action="store_true")
    expanded.add_argument("--raw-summary", action="store_true", help="Отключить защиту точных кодов и сумм")
    for command in (server, comparison, expanded):
        command.add_argument("--embedder", choices=("e5", *EMBEDDERS),
                             default=None if command is server else "e5")
        command.add_argument("--model-dir", type=Path, help="Каталог весов энкодера")
        command.add_argument("--embeddings-cache", type=Path)
        command.add_argument("--reranker", choices=RERANKERS)
        command.add_argument("--reranker-dir", type=Path)
        command.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    args = parser.parse_args()
    if args.command == "benchmark" and not 1 <= args.limit <= 1000:
        parser.error("--limit должен быть от 1 до 1000")
    if args.command == "compare" and args.repeats < 1:
        parser.error("--repeats должен быть положительным")
    if args.command == "benchmark":
        benchmark(MailboxIndex(args.data), args.data, args.limit, args.output)
        return
    if args.reranker_dir and not args.reranker:
        parser.error("--reranker-dir требует --reranker")
    if args.reranker and not (args.embedder or args.model_dir):
        parser.error("--reranker требует --embedder или --model-dir")
    index = build_index(args)
    if args.command == "serve":
        serve(index, args.port)
    elif args.command == "compare":
        with create_server(index, 0, quiet=True) as http_server:
            compare(http_server, index, args.data, args.paraphrases, args.repeats, args.output, args.include_undated)
    elif args.command == "evaluate-expanded":
        from .expanded_evaluation import evaluate_expanded

        with create_server(index, 0, quiet=True) as http_server:
            evaluate_expanded(http_server, index, args.suite, args.output, args.bm25_control, args.raw_summary)


if __name__ == "__main__":
    main()
