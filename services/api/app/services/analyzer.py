"""Upload validation and Phase 2 chirp DSP analysis."""

from __future__ import annotations

import math
from uuid import uuid4

from resonancelab.audio import WavDecodeError, decode_wav_pcm
from resonancelab.dsp import (
    ALIGNMENT_WARN_CONFIDENCE,
    SNR_WARN_DB,
    ChirpDspAnalysis,
    ChirpSpec,
    analyze_chirp_response,
    compute_audio_metrics,
)

from app.schemas import (
    AlignmentMetadata,
    AnalysisResponse,
    AudioUploadMetrics,
    DecayBandFeature,
    DecayFeature,
    DspAnalysis,
    FrequencySeries,
    PeakFeature,
    ProbeMetadata,
    ResponseTrace,
    SpectralFeatures,
    SpectrogramGrid,
    TransferBandFeature,
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
            f"{settings.max_recording_seconds:.2f}s upload limit."
        )
    _validate_probe_against_sample_rate(metadata, decoded.sample_rate_hz)

    try:
        dsp_analysis = analyze_chirp_response(
            decoded.samples,
            decoded.sample_rate_hz,
            _chirp_spec_from_metadata(metadata),
            pre_roll_seconds=_metadata_pre_roll_seconds(metadata),
            post_roll_seconds=_metadata_post_roll_seconds(metadata),
        )
    except ValueError as exc:
        raise AnalyzeUploadError(str(exc)) from exc
    warnings = _build_warnings(
        metadata=metadata,
        duration_seconds=metrics.duration_seconds,
        dsp_analysis=dsp_analysis,
    )

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
            method=dsp_analysis.alignment.method,
            confidence=dsp_analysis.alignment.confidence,
            estimated_latency_ms=dsp_analysis.alignment.estimated_latency_ms,
            detected_start_seconds=dsp_analysis.alignment.detected_start_seconds,
            expected_start_seconds=dsp_analysis.alignment.expected_start_seconds,
            notes=_alignment_notes(dsp_analysis),
        ),
        dsp=_dsp_response(dsp_analysis),
        warnings=warnings,
    )


def _build_warnings(
    *,
    metadata: ProbeMetadata,
    duration_seconds: float,
    dsp_analysis: ChirpDspAnalysis,
) -> list[str]:
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
    if dsp_analysis.alignment.confidence < ALIGNMENT_WARN_CONFIDENCE:
        warnings.append("Chirp alignment confidence is low; DSP features may be unreliable.")
    if dsp_analysis.signal_to_noise_db is None:
        warnings.append(
            "Signal-to-noise ratio could not be estimated; use a measurable pre-roll noise window."
        )
    elif dsp_analysis.signal_to_noise_db < SNR_WARN_DB:
        warnings.append(
            f"Signal-to-noise ratio is below the {SNR_WARN_DB:.0f} dB feasibility target."
        )
    if not dsp_analysis.dominant_peaks:
        warnings.append("No dominant ring-down peaks cleared the Phase 2 prominence threshold.")
    return warnings


def _chirp_spec_from_metadata(metadata: ProbeMetadata) -> ChirpSpec:
    config = metadata.probe_config
    return ChirpSpec(
        start_hz=float(config.start_hz),
        end_hz=float(config.end_hz),
        duration_seconds=config.duration_ms / 1000.0,
        amplitude=float(config.amplitude),
        fade_seconds=config.fade_ms / 1000.0,
    )


def _validate_probe_against_sample_rate(metadata: ProbeMetadata, sample_rate_hz: int) -> None:
    nyquist_hz = sample_rate_hz / 2.0
    config = metadata.probe_config
    if config.end_hz >= nyquist_hz:
        raise AnalyzeUploadError(
            f"Probe end_hz {config.end_hz} Hz must be lower than the WAV Nyquist "
            f"frequency {nyquist_hz:.1f} Hz."
        )


def _metadata_pre_roll_seconds(metadata: ProbeMetadata) -> float:
    browser = metadata.browser
    return _timing_interval_seconds(
        browser.recording_started_at_context_seconds,
        browser.chirp_started_at_context_seconds,
        fallback=metadata.probe_config.pre_roll_ms / 1000.0,
    )


def _metadata_post_roll_seconds(metadata: ProbeMetadata) -> float:
    browser = metadata.browser
    return _timing_interval_seconds(
        browser.chirp_ended_at_context_seconds,
        browser.capture_ended_at_context_seconds,
        fallback=metadata.probe_config.post_roll_ms / 1000.0,
    )


def _timing_interval_seconds(start: float | None, end: float | None, *, fallback: float) -> float:
    if start is None or end is None:
        return fallback
    duration = end - start
    return duration if math.isfinite(duration) and duration >= 0 else fallback


def _alignment_notes(dsp_analysis: ChirpDspAnalysis) -> list[str]:
    notes = [
        "Matched-filter alignment uses the configured logarithmic chirp as the reference.",
        (
            "Transfer-response features are regularized driven-path estimates, "
            "not calibrated predictions."
        ),
    ]
    if dsp_analysis.alignment.confidence < ALIGNMENT_WARN_CONFIDENCE:
        notes.append(
            "Low alignment confidence can indicate missing chirp audio or heavy browser processing."
        )
    return notes


def _dsp_response(analysis: ChirpDspAnalysis) -> DspAnalysis:
    return DspAnalysis(
        bandpass_low_hz=analysis.bandpass_low_hz,
        bandpass_high_hz=analysis.bandpass_high_hz,
        signal_to_noise_db=analysis.signal_to_noise_db,
        fft=SpectralFeatures(
            series=FrequencySeries(
                frequency_bins_hz=analysis.fft.series.frequency_bins_hz,
                magnitude_db=analysis.fft.series.magnitude_db,
            ),
            centroid_hz=analysis.fft.centroid_hz,
            bandwidth_hz=analysis.fft.bandwidth_hz,
            rolloff_hz=analysis.fft.rolloff_hz,
            spectral_floor_db=analysis.fft.spectral_floor_db,
        ),
        stft=SpectrogramGrid(
            kind=analysis.stft.kind,
            times_seconds=analysis.stft.times_seconds,
            frequency_bins_hz=analysis.stft.frequency_bins_hz,
            magnitude_db=analysis.stft.magnitude_db,
        ),
        mel_spectrogram=SpectrogramGrid(
            kind=analysis.mel_spectrogram.kind,
            times_seconds=analysis.mel_spectrogram.times_seconds,
            frequency_bins_hz=analysis.mel_spectrogram.frequency_bins_hz,
            magnitude_db=analysis.mel_spectrogram.magnitude_db,
        ),
        transfer_response=[
            TransferBandFeature(
                start_hz=band.start_hz,
                end_hz=band.end_hz,
                center_hz=band.center_hz,
                mean_db=band.mean_db,
                peak_db=band.peak_db,
            )
            for band in analysis.transfer_response
        ],
        impulse_response=ResponseTrace(
            method=analysis.impulse_response.method,
            times_seconds=analysis.impulse_response.times_seconds,
            magnitude_db=analysis.impulse_response.magnitude_db,
            regularization=analysis.impulse_response.regularization,
        ),
        dominant_peaks=[
            PeakFeature(
                frequency_hz=peak.frequency_hz,
                magnitude_db=peak.magnitude_db,
                prominence_db=peak.prominence_db,
                q_factor=peak.q_factor,
            )
            for peak in analysis.dominant_peaks
        ],
        decay=DecayFeature(
            method=analysis.decay.method,
            decay_rate_per_second=analysis.decay.decay_rate_per_second,
            rt60_seconds=analysis.decay.rt60_seconds,
            fit_r2=analysis.decay.fit_r2,
            window_start_seconds=analysis.decay.window_start_seconds,
            window_end_seconds=analysis.decay.window_end_seconds,
        ),
        decay_bands=[
            DecayBandFeature(
                label=band.label,
                start_hz=band.start_hz,
                end_hz=band.end_hz,
                decay_rate_per_second=band.decay_rate_per_second,
                rt60_seconds=band.rt60_seconds,
                fit_r2=band.fit_r2,
            )
            for band in analysis.decay_bands
        ],
    )
