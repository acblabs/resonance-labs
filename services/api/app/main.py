"""FastAPI entry point for ResonanceLab."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api import router
from app.observability import configure_logging, log_event
from app.settings import get_settings

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.title, version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        rejection_reason: str | None = None

        try:
            response, request, rejection_reason = await _prepare_request(
                request,
                max_explain_body_bytes=settings.max_explain_body_bytes,
            )
            if response is None:
                response = await call_next(request)
        except Exception:
            log_event(
                logger,
                "http_request_exception",
                level=logging.ERROR,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=_duration_ms(started),
                content_length=request.headers.get("content-length"),
                client_host=_client_host(request),
                exc_info=True,
            )
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        status_code = response.status_code
        log_event(
            logger,
            "http_request",
            level=_request_log_level(status_code),
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=_duration_ms(started),
            content_length=request.headers.get("content-length"),
            client_host=_client_host(request),
            rejection_reason=rejection_reason,
        )
        return response

    app.include_router(router)
    return app


def _explain_body_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": "Explain request body exceeds the JSON payload limit."},
    )


async def _prepare_request(
    request: Request,
    *,
    max_explain_body_bytes: int,
) -> tuple[JSONResponse | None, Request, str | None]:
    if request.method != "POST" or request.url.path != "/api/v1/explain":
        return None, request, None

    raw_content_length = request.headers.get("content-length")
    if raw_content_length:
        try:
            content_length = int(raw_content_length)
        except ValueError:
            return (
                JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                ),
                request,
                "invalid_content_length",
            )
        if content_length > max_explain_body_bytes:
            return (
                _explain_body_too_large_response(),
                request,
                "explain_content_length_exceeds_limit",
            )
        return None, request, None

    capped_request = await _request_with_capped_replayed_body(
        request,
        max_bytes=max_explain_body_bytes,
    )
    if capped_request is None:
        return (
            _explain_body_too_large_response(),
            request,
            "explain_stream_exceeds_limit",
        )
    return None, capped_request, None


async def _request_with_capped_replayed_body(
    request: Request,
    *,
    max_bytes: int,
) -> Request | None:
    body_parts: list[bytes] = []
    byte_count = 0
    async for chunk in request.stream():
        byte_count += len(chunk)
        if byte_count > max_bytes:
            return None
        body_parts.append(chunk)
    body = b"".join(body_parts)
    body_sent = False

    async def receive():
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        body_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)


def _duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def _request_log_level(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


app = create_app()
