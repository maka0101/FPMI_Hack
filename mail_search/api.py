from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Annotated

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .engine import Engine, MLUnavailable


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


def create_app(engine: Engine, demo_fallback: bool = False) -> FastAPI:
    app = FastAPI(title="Поиск по почте")
    page = Path(__file__).with_name("index.html").read_text(encoding="utf-8")

    @app.middleware("http")
    async def search_timing(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        if request.url.path == "/api/search":
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

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return page

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
            response.headers["X-Target-Day"] = target.isoformat()
        return rows

    @app.get("/api/message", response_model=Message)
    def message(mailbox: str = "", doc_id: str = "", as_of: str | None = None):
        day = reference_date(mailbox, as_of)
        result = engine.index.message(mailbox, doc_id, day)
        if result is None:
            return JSONResponse({"error": "Письмо недоступно"}, status_code=404)
        return result

    return app
