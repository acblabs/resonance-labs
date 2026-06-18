"""Pydantic schemas for probe configuration and analysis responses."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ModelsResponse(BaseModel):
    active_model: None
    phase: Literal["phase_3_calibration_demo"]
    notes: list[str]


class ProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: Literal["log_chirp"] = "log_chirp"
    start_hz: int = Field(default=500, ge=100, le=18000)
    end_hz: int = Field(default=10000, ge=200, le=20000)
    duration_ms: int = Field(default=500, ge=100, le=1000)
    pre_roll_ms: int = Field(default=250, ge=0, le=2000)
    post_roll_ms: int = Field(default=1000, ge=100, le=4000)
    amplitude: float = Field(default=0.35, ge=0.01, le=0.35)
    fade_ms: int = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def validate_frequency_order(self) -> ProbeConfig:
        if self.start_hz >= self.end_hz:
            raise ValueError("start_hz must be lower than end_hz.")
        if self.fade_ms * 2 > self.duration_ms:
            raise ValueError("fade_ms is too long for duration_ms.")
        return self


class BrowserCaptureMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_agent: str | None = None
    audio_context_sample_rate_hz: int | None = Field(default=None, ge=8000, le=192000)
    media_track_settings: dict[str, Any] = Field(default_factory=dict)
    requested_constraints: dict[str, Any] = Field(default_factory=dict)
    capture_path: Literal[
        "audio_worklet", "script_processor", "media_recorder", "unknown"
    ] = "unknown"
    recording_started_at_context_seconds: float | None = None
    chirp_started_at_context_seconds: float | None = None
    chirp_ended_at_context_seconds: float | None = None
    capture_ended_at_context_seconds: float | None = None


class ProbeMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    client_recorded_at: str | None = None
    probe_config: ProbeConfig = Field(default_factory=ProbeConfig)
    browser: BrowserCaptureMetadata = Field(default_factory=BrowserCaptureMetadata)


class ProbeConfigEnvelope(BaseModel):
    default: ProbeConfig
    limits: dict[str, Any]
    upload: dict[str, Any]
    warnings: list[str]


class AudioUploadMetrics(BaseModel):
    content_type: str
    filename: str | None
    byte_count: int
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    sample_count: int
    duration_seconds: float
    rms: float
    peak_amplitude: float
    dc_offset: float


class AlignmentMetadata(BaseModel):
    method: Literal["matched_filter_log_chirp"]
    confidence: float
    estimated_latency_ms: float | None
    detected_start_seconds: float | None = None
    expected_start_seconds: float | None = None
    notes: list[str]


class FrequencySeries(BaseModel):
    frequency_bins_hz: list[float]
    magnitude_db: list[float]


class SpectralFeatures(BaseModel):
    series: FrequencySeries
    centroid_hz: float | None
    bandwidth_hz: float | None
    rolloff_hz: float | None
    spectral_floor_db: float | None


class SpectrogramGrid(BaseModel):
    kind: Literal["stft", "mel"]
    times_seconds: list[float]
    frequency_bins_hz: list[float]
    magnitude_db: list[list[float]]


class TransferBandFeature(BaseModel):
    start_hz: float
    end_hz: float
    center_hz: float
    mean_db: float
    peak_db: float


class PeakFeature(BaseModel):
    frequency_hz: float
    magnitude_db: float
    prominence_db: float
    q_factor: float | None


class DecayFeature(BaseModel):
    method: Literal["rms_envelope_log_linear"]
    decay_rate_per_second: float | None
    rt60_seconds: float | None
    fit_r2: float | None
    window_start_seconds: float
    window_end_seconds: float


class DspAnalysis(BaseModel):
    bandpass_low_hz: float
    bandpass_high_hz: float
    signal_to_noise_db: float | None
    fft: SpectralFeatures
    stft: SpectrogramGrid
    mel_spectrogram: SpectrogramGrid
    transfer_response: list[TransferBandFeature]
    dominant_peaks: list[PeakFeature]
    decay: DecayFeature


class AnalysisResponse(BaseModel):
    analysis_id: UUID
    status: Literal["ok"]
    audio: AudioUploadMetrics
    probe: ProbeMetadata
    alignment: AlignmentMetadata
    dsp: DspAnalysis
    warnings: list[str]
