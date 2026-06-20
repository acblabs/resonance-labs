"""FastAPI entry point for ResonanceLab."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api import router
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.title, version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def reject_large_explain_requests(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/v1/explain":
            raw_content_length = request.headers.get("content-length")
            if raw_content_length:
                try:
                    content_length = int(raw_content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length header."},
                    )
                if content_length > settings.max_explain_body_bytes:
                    return _explain_body_too_large_response()
            else:
                capped_request = await _request_with_capped_replayed_body(
                    request,
                    max_bytes=settings.max_explain_body_bytes,
                )
                if capped_request is None:
                    return _explain_body_too_large_response()
                request = capped_request
        return await call_next(request)

    app.include_router(router)
    return app


def _explain_body_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": "Explain request body exceeds the JSON payload limit."},
    )


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


app = create_app()
