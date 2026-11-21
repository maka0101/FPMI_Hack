"""Quality evaluation shared by benchmark, export and profile comparison."""

from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter, sleep

import httpx

from .engine import Engine
from .ml_profiles import file_hash as sha256, read_profile
from .search import read_jsonl


def host_info():
    cpu = platform.processor() or platform.machine()
    memory = None
    if Path("/proc/cpuinfo").exists():
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        for line in lines:
            key, _, value = line.partition(":")
            if key.strip() == "model name":
                cpu = value.strip()
                break
    if platform.system() == "Darwin":
        cpu = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        memory = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
    if "SC_PHYS_PAGES" in os.sysconf_names:
        memory = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    return {"platform": platform.platform(), "cpu": cpu, "logical_cpus": os.cpu_count(),
            "ram_bytes": memory, "python": platform.python_version()}


def read_queries(path):
    queries = list(read_jsonl(path))
    if not queries:
        raise ValueError("Файл запросов пуст")
    if len({row["query_id"] for row in queries}) != len(queries):
        raise ValueError("Повтор query_id в наборе запросов")
    return queries


def read_gold(path):
    gold = defaultdict(dict)
    for row in read_jsonl(path):
        if row["relevance"] > 0:
            gold[row["query_id"]][row["doc_id"]] = row["relevance"]
    return gold


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False), file=stream)


def latency(samples):
    if not samples:
        return {}
    ordered = sorted(samples)
    return {f"p{p}": ordered[math.ceil(p / 100 * len(samples)) - 1] for p in (50, 95, 99)}


def rank_queries(engine, queries, limit):
    rankings, times = [], []
    for row in queries:
        day = date.fromisoformat(row["query_date"])
        started = perf_counter()
        results = engine.search(row["synthetic_user"], row["query"], day, limit)
        times.append((perf_counter() - started) * 1000)
        ids = [result["doc_id"] for result in results]
        if len(set(ids)) != len(ids) or len(ids) > limit:
            raise ValueError(f"Некорректная выдача для {row['query_id']}")
        rankings.append({"query_id": row["query_id"], "doc_ids": ids})
    return rankings, times


def dcg(gains):
    return sum((2 ** gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))


def metrics(ids, relevance, limit):
    gains = [relevance.get(doc, 0) for doc in ids[:limit]]
    ideal = sorted(relevance.values(), reverse=True)[:limit]
    return {"recall": sum(gain > 0 for gain in gains) / len(relevance),
            "ndcg": dcg(gains) / dcg(ideal),
            "mrr": next((1 / rank for rank, gain in enumerate(gains, 1) if gain), 0.0)}


def evaluate(rankings, gold, limit):
    per_query = {row["query_id"]: metrics(row["doc_ids"], gold[row["query_id"]], limit)
                 for row in rankings if gold.get(row["query_id"])}
    single = [score["mrr"] for qid, score in per_query.items() if len(gold[qid]) == 1]
    if not per_query:
        raise ValueError("Для запросов нет положительных qrels. Для экспорта используйте export")
    scores = {key: sum(score[key] for score in per_query.values()) / len(per_query)
              for key in ("recall", "ndcg", "mrr")}
    scores.update(judged_queries=len(per_query), single_hit_queries=len(single),
                  mrr_single_hit=sum(single) / len(single) if single else None)
    return scores


def compare_queries(baseline, candidate, gold, limit):
    rows = []
    counts = {key: {"improved": 0, "regressed": 0, "equal": 0}
              for key in ("recall", "ndcg", "mrr")}
    for before, after in zip(baseline, candidate, strict=True):
        qid = before["query_id"]
        if qid != after["query_id"]:
            raise ValueError("Порядок запросов не совпадает с baseline")
        relevance = gold.get(qid, {})
        old = {doc: i for i, doc in enumerate(before["doc_ids"], 1)}
        new = {doc: i for i, doc in enumerate(after["doc_ids"], 1)}
        diff = {}
        if relevance:
            first = metrics(before["doc_ids"], relevance, limit)
            second = metrics(after["doc_ids"], relevance, limit)
            for key in counts:
                diff[key] = second[key] - first[key]
                direction = "equal" if abs(diff[key]) < 1e-12 else (
                    "improved" if diff[key] > 0 else "regressed")
                counts[key][direction] += 1
        changes = [{"doc_id": doc, "relevance": relevance.get(doc, 0),
                    "bm25_rank": old.get(doc), "candidate_rank": new.get(doc)}
                   for doc in dict.fromkeys([*old, *new]) if old.get(doc) != new.get(doc)]
        rows.append({"query_id": qid, "metric_deltas": diff, "rank_changes": changes})
    return rows, counts


@contextmanager
def local_ml(data_dir, profile):
    # The child binds its own loopback port. A failure to bind fails the run.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    cmd = [sys.executable, "-m", "mail_search.ml", "--data", str(data_dir),
           "--profile", profile, "--host", "127.0.0.1", "--port", str(port)]
    with subprocess.Popen(cmd) as child:
        try:
            deadline = monotonic() + 120
            with httpx.Client(timeout=1, trust_env=False) as client:
                while child.poll() is None:
                    try:
                        response = client.get(f"{url}/readyz")
                        if response.is_success:
                            ready = response.json()
                            if ready.get("profile_id") != profile:
                                raise ValueError("ML ответил с чужим профилем")
                            break
                    except httpx.RequestError:
                        pass
                    if monotonic() >= deadline:
                        raise RuntimeError(f"Таймаут запуска ML для {profile}")
                    sleep(0.1)
                else:
                    raise RuntimeError(f"ML для {profile} завершился с кодом {child.returncode}")
            yield url, ready
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()


def revision():
    try:
        root = Path(__file__).resolve().parent.parent
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return os.getenv("MAIL_RELEASE")


def run_compare(data_dir, profiles, query_path, qrels_path, limit, out, timeout):
    from .ml import prepare

    queries = read_queries(query_path)
    gold = read_gold(qrels_path) if qrels_path else {}
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"Каталог {out} занят. Укажите новый --out, чтобы сохранить оба прогона")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "k": limit,
              "queries": len(queries), "profiles": profiles, "hardware": host_info(),
              "git_revision": revision(), "command": sys.argv[1:], "ml_timeout_s": timeout,
              "threads_env": {key: os.getenv(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
              "cache": "one sequential pass per mode; indexes loaded; no query warmup",
              "source_sha256": {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
              "inputs": {key: {"path": str(path), "sha256": sha256(path)} for key, path in
                         [("corpus", data_dir / "documents.jsonl"), ("queries", query_path),
                          ("qrels", qrels_path)] if path is not None},
              "models": {}, "runs": {}}
    with TemporaryDirectory(dir=out.parent) as tmp:
        # Publish report and rankings together only after every strict run succeeds.
        dest = Path(tmp) / "result"
        def run(mode, profile="encoder-a", url="http://127.0.0.1:8001"):
            key = "bm25" if mode == "bm25" else f"{profile}/{mode}"
            print(f"Поиск {key}, K={limit}", file=sys.stderr, flush=True)
            with closing(Engine(data_dir, mode=mode, profile_id=profile, ml_url=url,
                                timeout=timeout)) as engine:
                if engine.ready()["corpus_sha256"] != report["inputs"]["corpus"]["sha256"]:
                    raise ValueError("Корпус изменился между вариантами поиска")
                ranks, times = rank_queries(engine, queries, limit)
            scores = evaluate(ranks, gold, limit) if qrels_path else None
            write_jsonl(dest / key / "rankings.jsonl", ranks)
            report["runs"][key] = {"metrics": scores, "search_ms": latency(times)}
            return ranks

        baseline = run("bm25")
        for profile in profiles:
            started = perf_counter()
            metadata = prepare(data_dir, profile)
            prepare_ms = (perf_counter() - started) * 1000
            started = perf_counter()
            with local_ml(data_dir, profile) as (url, ready):
                ready_ms = (perf_counter() - started) * 1000
                if (ready.get("corpus_sha256") != report["inputs"]["corpus"]["sha256"]
                        or ready.get("index_version") != metadata["index_version"]
                        or ready.get("profile_sha256") != metadata["profile_sha256"]):
                    raise ValueError("ML загрузил другой индекс или корпус")
                report["models"][profile] = {"config": read_profile(profile).model_dump(),
                                             "prepared": metadata, "ready": ready,
                                             "prepare_ms": prepare_ms, "ml_ready_ms": ready_ms}
                for mode in ("encoder", "hybrid"):
                    ranks = run(mode, profile, url)
                    changes, counts = compare_queries(baseline, ranks, gold, limit)
                    key = f"{profile}/{mode}"
                    write_jsonl(dest / key / "deltas.jsonl", changes)
                    report["runs"][key]["vs_bm25"] = counts if qrels_path else None
        (dest / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        dest.replace(out)
    return report
