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
    phase: Literal["phase_4_reference_comparison"]
    notes: list[str]


class DatasetCaptureLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_percent: float | None = Field(default=None, ge=0, le=100)
    fill_mass_g: float | None = Field(default=None, ge=0)
    vessel_empty_mass_g: float | None = Field(default=None, ge=0)
    vessel_full_mass_g: float | None = Field(default=None, ge=0)
    vessel_current_mass_g: float | None = Field(default=None, ge=0, exclude=True)

    @model_validator(mode="after")
    def derive_or_validate_fill_percent(self) -> DatasetCaptureLabel:
        if self.fill_percent is None:
            if (
                self.vessel_current_mass_g is None
                or self.vessel_empty_mass_g is None
                or self.vessel_full_mass_g is None
            ):
                raise ValueError(
                    "fill_percent is required unless vessel_current_mass_g, "
                    "vessel_empty_mass_g, and vessel_full_mass_g are provided."
                )
            capacity = self.vessel_full_mass_g - self.vessel_empty_mass_g
            if capacity <= 0:
                raise ValueError("vessel_full_mass_g must be greater than vessel_empty_mass_g.")
            fill_mass = self.vessel_current_mass_g - self.vessel_empty_mass_g
            self.fill_mass_g = fill_mass if self.fill_mass_g is None else self.fill_mass_g
            self.fill_percent = 100.0 * fill_mass / capacity

        if self.fill_percent < 0 or self.fill_percent > 100:
            raise ValueError("fill_percent must be within [0, 100].")
        return self


class DatasetCaptureContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    glass_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    browser_id: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    operator_id: str | None = None
    volume_setting: str | None = None
    material: str | None = None
    geometry: str | None = None
    notes: str | None = None


class DatasetCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: DatasetCaptureLabel
    context: DatasetCaptureContext
    store_audio: bool = True
    notes: str | None = None


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


class ExplainAnchorDistance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["empty", "half", "full"]
    label: str
    fillPercent: float
    distance: float


class ExplainReferenceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["free_air"]
    label: str
    distance: float


class ExplainCalibrationEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "incomplete"]
    fillPercent: float | None = None
    confidence: float = Field(ge=0, le=1)
    confidenceLabel: Literal["high", "medium", "low", "none"]
    nearestAnchor: ExplainAnchorDistance | None = None
    referenceMatch: ExplainReferenceMatch | None = None
    comparableFeatureCount: int = Field(ge=0)
    freeAirDistance: float | None = None
    warnings: list[str] = Field(default_factory=list)


class ExplainReferenceDistance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["free_air", "calibration_anchor", "known_object"]
    id: str
    label: str
    material: str | None = None
    state: str | None = None
    distance: float
    sampleCount: int = Field(ge=0)


class ExplainReferenceComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "empty"]
    nearest: ExplainReferenceDistance | None = None
    nearestObject: ExplainReferenceDistance | None = None
    freeAir: ExplainReferenceDistance | None = None
    distances: list[ExplainReferenceDistance] = Field(default_factory=list, max_length=24)
    comparableFeatureCount: int = Field(ge=0)
    margin: float | None = None
    confidence: float = Field(ge=0, le=1)
    confidenceLabel: Literal["high", "medium", "low", "none"]
    freeAirDominates: bool
    warnings: list[str] = Field(default_factory=list)


class LlmExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResponse
    calibration: ExplainCalibrationEstimate | None = None
    reference_comparison: ExplainReferenceComparison | None = None
    operator_question: str | None = Field(default=None, max_length=500)
    include_raw_audio: Literal[False] = False


class LlmExplanation(BaseModel):
    summary: str
    observations: list[str]
    material_hypotheses: list[str]
    caveats: list[str]
    next_measurement: list[str]


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


class DatasetCaptureStoredPaths(BaseModel):
    inbox_record_path: str
    audio_path: str | None = None
    analysis_path: str


class DatasetCaptureResponse(BaseModel):
    record_id: str
    status: Literal["stored"]
    inbox_prefix: str
    stored_paths: DatasetCaptureStoredPaths
    analysis: AnalysisResponse
