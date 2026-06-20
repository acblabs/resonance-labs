"""HTTP routes for the ResonanceLab API."""

from __future__ import annotations

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.schemas import (
    AnalysisResponse,
    DatasetCaptureRequest,
    DatasetCaptureResponse,
    HealthResponse,
    ModelsResponse,
    ProbeConfig,
    ProbeConfigEnvelope,
    ProbeMetadata,
)
from app.services import (
    AnalyzeUploadError,
    DatasetCaptureStoreError,
    analyze_probe_upload,
    store_dataset_capture,
)
from app.settings import Settings, get_settings

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
            "The API returns DSP features; Phase 3 fill estimates require local "
            "browser calibration.",
        ],
    )


@router.get("/api/v1/models", response_model=ModelsResponse)
async def models() -> ModelsResponse:
    return ModelsResponse(
        active_model=None,
        phase="phase_3_calibration_demo",
        notes=[
            "No ML model is loaded.",
            "The analyze endpoint returns chirp-aligned DSP features and confidence signals.",
            "Profile-relative fill estimates run in the browser against local IndexedDB anchors.",
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


@router.post("/api/v1/dataset/captures", response_model=DatasetCaptureResponse)
async def capture_dataset_record(
    request: Request,
    audio: Annotated[UploadFile, File(description="PCM WAV probe recording.")],
    metadata: Annotated[str, Form(description="JSON-encoded ProbeMetadata.")],
    capture: Annotated[str, Form(description="JSON-encoded DatasetCaptureRequest.")],
) -> DatasetCaptureResponse:
    settings = get_settings()
    _authorize_dataset_capture(request, settings)
    _reject_large_content_length(request, settings.max_upload_bytes)
    parsed_metadata = _parse_metadata(metadata)
    parsed_capture = _parse_capture(capture)
    audio_bytes = await _read_upload_limited(audio, settings.max_upload_bytes)

    try:
        analysis = analyze_probe_upload(
            audio_bytes=audio_bytes,
            content_type=audio.content_type or "application/octet-stream",
            filename=audio.filename,
            metadata=parsed_metadata,
            settings=settings,
        )
        return store_dataset_capture(
            audio_bytes=audio_bytes,
            content_type=audio.content_type or "application/octet-stream",
            capture=parsed_capture,
            analysis=analysis,
            settings=settings,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
    except AnalyzeUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DatasetCaptureStoreError as exc:
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


def _parse_capture(raw_capture: str) -> DatasetCaptureRequest:
    try:
        payload = json.loads(raw_capture or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"capture must be valid JSON: {exc.msg}",
        ) from exc

    try:
        return DatasetCaptureRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


def _authorize_dataset_capture(request: Request, settings: Settings) -> None:
    if not settings.phase4_capture_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    if not settings.phase4_capture_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PHASE4_CAPTURE_OPERATOR_TOKEN must be configured before capture is enabled.",
        )

    supplied = _operator_token(request)
    if supplied is None or not hmac.compare_digest(supplied, settings.phase4_capture_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A valid operator token is required for private dataset capture.",
        )


def _operator_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    header_token = request.headers.get("x-resonancelab-operator-token")
    return header_token.strip() if header_token else None


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
