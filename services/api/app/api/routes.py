"""HTTP routes for the ResonanceLab API."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.schemas import (
    AnalysisResponse,
    HealthResponse,
    LlmExplainRequest,
    LlmExplainResponse,
    ModelsResponse,
    ProbeConfig,
    ProbeConfigEnvelope,
    ProbeMetadata,
)
from app.services import (
    AnalyzeUploadError,
    LlmExplanationError,
    analyze_probe_upload,
    explain_probe_result,
)
from app.settings import get_settings

router = APIRouter()
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="resonancelab-api",
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/api/v1/probe-config", response_model=ProbeConfigEnvelope)
async def probe_config() -> ProbeConfigEnvelope:
    settings = get_settings()
    default = ProbeConfig()
    return ProbeConfigEnvelope(
        default=default,
        limits={
            "start_hz": {"min": 100, "max": 18000},
            "end_hz": {"min": 200, "max": 20000},
            "duration_ms": {"min": 100, "max": 1000},
            "pre_roll_ms": {"min": 0, "max": 2000},
            "post_roll_ms": {"min": 100, "max": 4000},
            "amplitude": {"min": 0.01, "max": 0.35},
            "fade_ms": {"min": 0, "max": 100},
        },
        upload={
            "max_upload_bytes": settings.max_upload_bytes,
            "max_recording_seconds": settings.max_recording_seconds,
            "allowed_content_types": list(settings.allowed_content_types),
            "preferred_content_type": "audio/wav",
        },
        warnings=[
            "Do not run active probes through headphones or earbuds.",
            "The API returns acoustic DSP features for room fingerprinting and reporting.",
        ],
    )


@router.get("/api/v1/models", response_model=ModelsResponse)
async def models() -> ModelsResponse:
    return ModelsResponse(
        active_model=None,
        phase="phase_4_room_fingerprint",
        notes=[
            "No ML model is loaded.",
            (
                "The analyze endpoint returns chirp-aligned DSP features for room "
                "acoustic fingerprints."
            ),
            "The explain endpoint consumes compact structured DSP evidence and never raw WAV.",
        ],
    )


@router.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze(
    request: Request,
    audio: Annotated[UploadFile, File(description="PCM WAV probe recording.")],
    metadata: Annotated[str, Form(description="JSON-encoded ProbeMetadata.")] = "{}",
) -> AnalysisResponse:
    settings = get_settings()
    _reject_large_content_length(request, settings.max_upload_bytes)
    parsed_metadata = _parse_metadata(metadata)
    audio_bytes = await _read_upload_limited(audio, settings.max_upload_bytes)

    try:
        return analyze_probe_upload(
            audio_bytes=audio_bytes,
            content_type=audio.content_type or "application/octet-stream",
            filename=audio.filename,
            metadata=parsed_metadata,
            settings=settings,
        )
    except AnalyzeUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/v1/explain", response_model=LlmExplainResponse)
async def explain(request: LlmExplainRequest) -> LlmExplainResponse:
    settings = get_settings()
    try:
        return explain_probe_result(request, settings)
    except LlmExplanationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _parse_metadata(raw_metadata: str) -> ProbeMetadata:
    try:
        payload = json.loads(raw_metadata or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"metadata must be valid JSON: {exc.msg}",
        ) from exc

    try:
        return ProbeMetadata.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


def _reject_large_content_length(request: Request, max_upload_bytes: int) -> None:
    raw_content_length = request.headers.get("content-length")
    if raw_content_length is None:
        return

    try:
        content_length = int(raw_content_length)
    except ValueError:
        return

    if content_length > max_upload_bytes + MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body exceeds the upload limit.",
        )


async def _read_upload_limited(audio: UploadFile, max_upload_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0

    while True:
        chunk = await audio.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break

        total_bytes += len(chunk)
        if total_bytes > max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded audio exceeds the {max_upload_bytes} byte limit.",
            )
        chunks.append(chunk)

    return b"".join(chunks)
