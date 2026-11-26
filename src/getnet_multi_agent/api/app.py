"""FastAPI application factory: middleware, JSON errors, startup ingestion and routers."""

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from getnet_multi_agent.api import chat, conversations, health, operator
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.llm import get_llm
from getnet_multi_agent.core.logging import get_logger, setup_logging
from getnet_multi_agent.core.request_context import get_request_id, start_request
from getnet_multi_agent.core.settings import get_settings
from getnet_multi_agent.state import db as dbmod
from getnet_multi_agent.state import tickets

log = get_logger("api")


def _ingest_background(app: FastAPI) -> None:
    from getnet_multi_agent.rag import ingest, store

    s = app.state.settings
    app.state.ingest_status = "running"
    try:
        if store.count(s) == 0:
            start_request()
            n = ingest.ingest(s, app.state.llm)
            log.info("ingestion finished", extra={"fields": {"chunks": n}})
        app.state.ingest_status = "done"
    except Exception as e:  # service stays live; readiness reports the failure
        app.state.ingest_status = f"failed: {type(e).__name__}"
        log.error("ingestion failed", extra={"fields": {"error": f"{type(e).__name__}: {e}"[:300]}})


def create_app(settings=None, llm=None, run_ingestion: bool = True) -> FastAPI:
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = app.state.settings = settings or get_settings()
        app.state.db = dbmod.connect(s)
        app.state.llm = llm or get_llm(s)
        app.state.ingest_status = "pending"
        db = app.state.db
        metrics.set_ticket_stats_provider(lambda: tickets.open_stats(db))
        if run_ingestion:
            threading.Thread(target=_ingest_background, args=(app,), daemon=True).start()
        yield

    app = FastAPI(title="Getnet Multi-Agent Support", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = start_request(request.headers.get("x-request-id"))
        t0 = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path not in ("/metrics", "/health/live", "/health/ready"):
            log.info("http", extra={"fields": {"path": request.url.path, "method": request.method,
                                               "status": response.status_code,
                                               "latency_ms": int((time.monotonic() - t0) * 1000)}})
        return response

    def _error(status: int, code: str, message) -> JSONResponse:
        return JSONResponse(status_code=status, content={
            "error": {"code": code, "message": message}, "request_id": get_request_id()})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        d = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return _error(exc.status_code, d.get("code", "error"), d.get("message", ""))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return _error(422, "validation_error", [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()])

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("unhandled", extra={"fields": {"error": type(exc).__name__}})
        metrics.REQUESTS.labels(route="error", status="error").inc()
        return _error(500, "internal_error", "unexpected error")

    @app.get("/metrics")
    def metrics_endpoint():
        body, ctype = metrics.render()
        return Response(body, media_type=ctype)

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(operator.router)
    return app


app = create_app()
