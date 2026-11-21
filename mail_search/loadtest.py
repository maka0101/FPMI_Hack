"""HTTP latency harness. Samples come from the backend's Server-Timing header."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import math
import re

import httpx

from .experiments import host_info, latency, sha256, read_queries
from .search import parse_query


SEARCH_TIMING = re.compile(r"(?:^|,)\s*search\s*;\s*dur=([\d.]+)\s*(?:,|$)")


def sample(client, query, limit, mode):
    try:
        response = client.get("/api/search", params={
            "mailbox": query["synthetic_user"], "as_of": query["query_date"],
            "q": query["query"], "limit": limit,
        })
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"
        actual = response.headers.get("x-search-mode")
        if actual != mode:
            words, _ = parse_query(query["query"], date.fromisoformat(query["query_date"]))
            if words or actual != "browse":
                return None, f"unexpected mode: {actual}"
        if not isinstance(response.json(), list):
            return None, "invalid result"
        match = SEARCH_TIMING.search(response.headers.get("server-timing", ""))
        if not match:
            return None, "missing search duration"
        duration = float(match[1])
        if not math.isfinite(duration) or duration < 0:
            return None, "invalid search duration"
        return duration, None
    except (httpx.RequestError, ValueError) as error:
        return None, type(error).__name__


def load_test(url, mode, query_path, limit, warmup, requests, concurrency, hardware):
    queries = read_queries(query_path)
    with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
        ready = client.get("/readyz")
        ready.raise_for_status()
        identity = ready.json()
        if identity.get("mode") != mode:
            raise ValueError(f"Сервис запущен в режиме {identity.get('mode')}, ожидается {mode}")
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            def batch(count):
                inputs = (queries[i % len(queries)] for i in range(count))
                results = list(pool.map(lambda query: sample(client, query, limit, mode), inputs))
                return ([ms for ms, error in results if error is None],
                        dict(Counter(error for _, error in results if error is not None)))

            _, warmup_errors = batch(warmup)
            durations, errors = batch(requests)
    server_ms = latency(durations)
    return {"protocol": "internal-http-v1", "url": url, "requested_mode": mode,
            "ready": identity, "k": limit, "query_file": str(query_path),
            "query_sha256": sha256(query_path), "unique_queries_in_file": len(queries),
            "warmup_requests": warmup, "measured_requests": requests, "successful": len(durations),
            "concurrency": concurrency, "cache": "process kept alive after warmup",
            "server_hardware": hardware, "load_generator": host_info(),
            "server_ms": server_ms, "warmup_errors": warmup_errors, "errors": errors,
            "passed": not warmup_errors and not errors and server_ms.get("p99", math.inf) < 1000}
