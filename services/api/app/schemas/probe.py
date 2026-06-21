"""Pydantic schemas for probe configuration and analysis responses."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from resonancelab.dsp import DEFAULT_DECAY_BANDS_HZ, IMPULSE_RESPONSE_MAX_POINTS


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ModelsResponse(BaseModel):
    active_model: None
    phase: Literal["phase_4_room_fingerprint"]
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
    frequency_bins_hz: list[float] = Field(max_length=2048)
    magnitude_db: list[float] = Field(max_length=2048)

    @model_validator(mode="after")
    def validate_lengths(self) -> FrequencySeries:
        if len(self.frequency_bins_hz) != len(self.magnitude_db):
            raise ValueError("frequency_bins_hz and magnitude_db must have the same length.")
        return self


class SpectralFeatures(BaseModel):
    series: FrequencySeries
    centroid_hz: float | None
    bandwidth_hz: float | None
    rolloff_hz: float | None
    spectral_floor_db: float | None


class SpectrogramGrid(BaseModel):
    kind: Literal["stft", "mel"]
    times_seconds: list[float] = Field(max_length=120)
    frequency_bins_hz: list[float] = Field(max_length=256)
    magnitude_db: list[list[float]] = Field(max_length=256)

    @model_validator(mode="after")
    def validate_grid_shape(self) -> SpectrogramGrid:
        if len(self.magnitude_db) != len(self.frequency_bins_hz):
            raise ValueError("magnitude_db row count must match frequency_bins_hz length.")
        if any(len(row) != len(self.times_seconds) for row in self.magnitude_db):
            raise ValueError("each magnitude_db row must match times_seconds length.")
        if len(self.times_seconds) * len(self.frequency_bins_hz) > 40000:
            raise ValueError("spectrogram grid is too large.")
        return self


class TransferBandFeature(BaseModel):
    start_hz: float
    end_hz: float
    center_hz: float
    mean_db: float
    peak_db: float


class ResponseTrace(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    method: Literal["regularized_deconvolution", "matched_filter_envelope"]
    times_seconds: list[float] = Field(max_length=IMPULSE_RESPONSE_MAX_POINTS)
    magnitude_db: list[float] = Field(max_length=IMPULSE_RESPONSE_MAX_POINTS)
    regularization: float
    peak_time_seconds: float | None = None
    direct_to_late_db: float | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> ResponseTrace:
        if len(self.times_seconds) != len(self.magnitude_db):
            raise ValueError("times_seconds and magnitude_db must have the same length.")
        return self


class PeakFeature(BaseModel):
    frequency_hz: float
    magnitude_db: float
    prominence_db: float
    q_factor: float | None


class DecayFeature(BaseModel):
    method: Literal["rms_envelope_log_linear"]
    decay_rate_per_second: float | None
    rt60_seconds: float | None
    fit_r2: float | None = Field(
        default=None,
        description=(
            "Weighted coefficient of determination for the floor-adjusted "
            "RMS-envelope log-linear fit."
        ),
    )
    window_start_seconds: float
    window_end_seconds: float


class DecayBandFeature(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    label: Literal["low", "mid", "high"]
    start_hz: float
    end_hz: float
    decay_rate_per_second: float | None
    rt60_seconds: float | None
    fit_r2: float | None


class MfccCoefficientFeature(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    index: int = Field(ge=0, le=32)
    mean: float
    std: float
    minimum: float
    maximum: float


class MfccSummaryFeature(BaseModel):
    method: Literal["log_mel_dct_ii"]
    coefficients: list[MfccCoefficientFeature] = Field(max_length=20)


class ModeGroupFeature(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    start_hz: float
    end_hz: float
    center_hz: float
    peak_count: int = Field(ge=1, le=12)
    frequencies_hz: list[float] = Field(max_length=12)
    dominant_frequency_hz: float
    max_prominence_db: float
    q_factor: float | None
    warning_labels: list[str] = Field(max_length=6)


class ResponseCaveatFeature(BaseModel):
    id: str = Field(max_length=64)
    severity: Literal["info", "review", "warning"]
    message: str = Field(max_length=240)


class DspAnalysis(BaseModel):
    bandpass_low_hz: float
    bandpass_high_hz: float
    signal_to_noise_db: float | None
    fft: SpectralFeatures
    stft: SpectrogramGrid
    mel_spectrogram: SpectrogramGrid
    transfer_response: list[TransferBandFeature] = Field(max_length=16)
    impulse_response: ResponseTrace
    matched_response: ResponseTrace
    mfcc: MfccSummaryFeature
    dominant_peaks: list[PeakFeature] = Field(max_length=12)
    mode_groups: list[ModeGroupFeature] = Field(max_length=8)
    decay: DecayFeature
    decay_bands: list[DecayBandFeature] = Field(max_length=len(DEFAULT_DECAY_BANDS_HZ))
    response_caveats: list[ResponseCaveatFeature] = Field(max_length=8)


class AnalysisResponse(BaseModel):
    analysis_id: UUID
    status: Literal["ok"]
    audio: AudioUploadMetrics
    probe: ProbeMetadata
    alignment: AlignmentMetadata
    dsp: DspAnalysis
    warnings: list[str] = Field(max_length=64)


class LlmExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResponse
    operator_question: str | None = Field(default=None, max_length=500)
    include_raw_audio: Literal[False] = False


class LlmExplanation(BaseModel):
    summary: str
    observations: list[str] = Field(max_length=8)
    acoustic_hypotheses: list[str] = Field(max_length=8)
    experiment_design: list[str] = Field(max_length=8)
    physics_tutoring: list[str] = Field(max_length=8)
    troubleshooting: list[str] = Field(max_length=8)
    evidence_critique: list[str] = Field(max_length=8)
    caveats: list[str] = Field(max_length=8)
    next_measurement: list[str] = Field(max_length=8)


class LlmExplainResponse(BaseModel):
    status: Literal["ok", "disabled"]
    provider: Literal["vertex_gemini"]
    model: str
    region: str
    thinking_level: str
    raw_audio_sent: bool
    explanation: LlmExplanation
    evidence: dict[str, Any]
    warnings: list[str]
