from datetime import date
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .engine import Engine, MLUnavailable
from .search import DateRange


MAIL_HEADER = re.compile(r"^(от|от кого|отправитель|тема):[^\S\r\n]*([^\r\n]*)", re.IGNORECASE)


class Summary(BaseModel):
    doc_id: str
    subject: str
    day: str | None
    preview: str


class Message(BaseModel):
    doc_id: str
    subject: str
    day: str | None
    body: str


class Anchor(BaseModel):
    doc_id: str
    subject: str
    day: date
    sender: str | None


class NearbySummary(Summary):
    offset_days: int


class NearbyResults(BaseModel):
    anchor: Anchor
    window: DateRange | None
    results: list[NearbySummary]


def anchor_card(message):
    subject, sender, body = message["subject"], None, message["body"]
    while header := MAIL_HEADER.match(body):
        name, value = header[1].lower(), header[2].strip()
        if name == "тема":
            subject = subject or value
        else:
            sender = sender or value or None
        body = body[header.end():].lstrip()
    return Anchor(doc_id=message["doc_id"], subject=subject, day=message["day"], sender=sender)


def create_app(engine: Engine, demo_fallback: bool = False) -> FastAPI:
    app = FastAPI(title="Поиск по почте")

    @app.middleware("http")
    async def search_timing(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        if request.url.path in ("/api/search", "/api/search/anchors", "/api/search/around"):
            elapsed = (perf_counter() - started) * 1000
            response.headers["Server-Timing"] = f"search;dur={elapsed:.3f}"
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse({"error": "Некорректные параметры запроса"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        error = "Страница не найдена" if exc.status_code == 404 else str(exc.detail)
        return JSONResponse({"error": error}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(MLUnavailable)
    async def ml_unavailable(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=503)

    def reference_date(mailbox: str, as_of: str | None) -> date:
        if mailbox not in engine.mailboxes:
            raise ValueError("Неизвестный почтовый ящик")
        value = as_of or engine.mailboxes[mailbox]
        return date.fromisoformat(value) if value else date.today()

    if os.environ.get("MAIL_SEARCH_FRONTEND_V2") == "1":
        frontend = Path(__file__).with_name("frontend_v2")

        @app.get("/", response_class=HTMLResponse)
        @app.get("/v2", response_class=HTMLResponse)
        async def frontend_v2():
            return FileResponse(frontend / "index.html", media_type="text/html")

        @app.get("/v2/search.js")
        async def frontend_v2_script():
            return FileResponse(frontend / "search.js", media_type="text/javascript")

    if os.environ.get("MAIL_SEARCH_FRONTEND_V1") == "1":
        legacy_page = Path(__file__).with_name("index.html")

        @app.get("/v1", response_class=HTMLResponse)
        async def frontend_v1():
            return FileResponse(legacy_page, media_type="text/html")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        return engine.ready()

    @app.get("/api/mailboxes")
    async def mailboxes() -> dict[str, str | None]:
        return engine.mailboxes

    @app.get("/api/search", response_model=list[Summary])
    def search(response: Response, mailbox: str = "", q: str = "", as_of: str | None = None,
               limit: Annotated[int | None, Query(ge=1, le=1000)] = None):
        if limit is None:
            limit = 10 if q.strip() else 20
        day = reference_date(mailbox, as_of)
        rows, mode, target = engine.search_with_info(mailbox, q, day, limit, demo_fallback=demo_fallback)
        response.headers["X-Search-Mode"] = mode
        if target:
            if target.start == target.end:
                response.headers["X-Target-Day"] = target.start.isoformat()
            else:
                response.headers["X-Target-From"] = target.start.isoformat()
                response.headers["X-Target-To"] = target.end.isoformat()
        return rows

    @app.get("/api/search/anchors", response_model=list[Anchor])
    def anchors(response: Response, mailbox: str, q: str, as_of: str | None = None):
        if not q.strip():
            raise ValueError("Опишите письмо-ориентир")
        day = reference_date(mailbox, as_of)
        rows, mode, _ = engine.search_with_info(
            mailbox, q, day, 3, demo_fallback=demo_fallback, dated_only=True,
        )
        response.headers["X-Search-Mode"] = mode
        return [anchor_card(engine.index.message(mailbox, row["doc_id"], day)) for row in rows]

    @app.get("/api/search/around", response_model=NearbyResults)
    def around(response: Response, mailbox: str, anchor_doc_id: str,
               direction: Literal["before", "after", "around"], q: str = "",
               as_of: str | None = None, days: int = 3):
        if days not in (3, 7):
            raise ValueError("Размер окна должен быть 3 или 7 дней")
        day = reference_date(mailbox, as_of)
        anchor = engine.index.message(mailbox, anchor_doc_id, day)
        if anchor is None or anchor["day"] is None:
            return JSONResponse({"error": "Письмо-ориентир недоступно"}, status_code=404)
        rows, mode, window = engine.search_around(
            mailbox, q, day, anchor, direction, days, demo_fallback=demo_fallback,
        )
        response.headers["X-Search-Mode"] = mode
        return {"anchor": anchor_card(anchor), "window": window, "results": rows}

    @app.get("/api/message", response_model=Message)
    def message(mailbox: str = "", doc_id: str = "", as_of: str | None = None):
        day = reference_date(mailbox, as_of)
        result = engine.index.message(mailbox, doc_id, day)
        if result is None:
            return JSONResponse({"error": "Письмо недоступно"}, status_code=404)
        return result

    return app
