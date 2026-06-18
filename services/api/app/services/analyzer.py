"""Phase 1 upload validation and dummy audio analysis."""

from __future__ import annotations

from uuid import uuid4

from resonancelab.audio import WavDecodeError, decode_wav_pcm
from resonancelab.dsp import compute_audio_metrics

from app.schemas import (
    AlignmentMetadata,
    AnalysisResponse,
    AudioUploadMetrics,
    ProbeMetadata,
)
from app.settings import Settings


class AnalyzeUploadError(ValueError):
    """Raised when an uploaded probe cannot be accepted for analysis."""


def analyze_probe_upload(
    *,
    audio_bytes: bytes,
    content_type: str,
    filename: str | None,
    metadata: ProbeMetadata,
    settings: Settings,
) -> AnalysisResponse:
    """Validate and summarize an uploaded WAV probe recording."""

    normalized_content_type = content_type.split(";")[0].strip().lower()
    if normalized_content_type not in settings.allowed_content_types:
        allowed = ", ".join(settings.allowed_content_types)
        raise AnalyzeUploadError(f"Unsupported content type '{content_type}'. Allowed: {allowed}.")

    byte_count = len(audio_bytes)
    if byte_count == 0:
        raise AnalyzeUploadError("Uploaded audio is empty.")
    if byte_count > settings.max_upload_bytes:
        raise AnalyzeUploadError(
            f"Uploaded audio is {byte_count} bytes, which exceeds the "
            f"{settings.max_upload_bytes} byte limit."
        )

    try:
        decoded = decode_wav_pcm(audio_bytes)
    except WavDecodeError as exc:
        raise AnalyzeUploadError(str(exc)) from exc

    metrics = compute_audio_metrics(decoded.samples, decoded.sample_rate_hz)
    if metrics.duration_seconds > settings.max_recording_seconds:
        raise AnalyzeUploadError(
            f"Recording duration {metrics.duration_seconds:.2f}s exceeds the "
            f"{settings.max_recording_seconds:.2f}s Phase 1 limit."
        )

    warnings = _build_warnings(metadata=metadata, duration_seconds=metrics.duration_seconds)

    return AnalysisResponse(
        analysis_id=uuid4(),
        status="ok",
        audio=AudioUploadMetrics(
            content_type=normalized_content_type,
            filename=filename,
            byte_count=byte_count,
            sample_rate_hz=decoded.sample_rate_hz,
            channels=decoded.channels,
            sample_width_bytes=decoded.sample_width_bytes,
            frame_count=decoded.frame_count,
            sample_count=metrics.sample_count,
            duration_seconds=metrics.duration_seconds,
            rms=metrics.rms,
            peak_amplitude=metrics.peak_amplitude,
            dc_offset=metrics.dc_offset,
        ),
        probe=metadata,
        alignment=AlignmentMetadata(
            method="phase1_placeholder",
            confidence=None,
            estimated_latency_ms=None,
            notes=[
                "Phase 1 confirms upload, decode, and signal metrics.",
                "Matched-filter alignment lands in Phase 2.",
            ],
        ),
        warnings=warnings,
    )


def _build_warnings(*, metadata: ProbeMetadata, duration_seconds: float) -> list[str]:
    warnings: list[str] = []
    settings = metadata.browser.media_track_settings
    for key in ("echoCancellation", "noiseSuppression", "autoGainControl"):
        value = settings.get(key)
        if value is True:
            warnings.append(
                f"Browser reported {key}=true; acoustic measurements may be distorted."
            )

    expected_duration = (
        metadata.probe_config.pre_roll_ms
        + metadata.probe_config.duration_ms
        + metadata.probe_config.post_roll_ms
    ) / 1000.0
    if duration_seconds < expected_duration * 0.75:
        warnings.append("Recording is shorter than expected for the probe configuration.")
    if duration_seconds > expected_duration * 1.5:
        warnings.append("Recording is longer than expected for the probe configuration.")
    return warnings
