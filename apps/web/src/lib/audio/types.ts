export type CapturePath =
  | "audio_worklet"
  | "script_processor"
  | "media_recorder"
  | "unknown";

export type ProbeConfig = {
  signal_type: "log_chirp";
  start_hz: number;
  end_hz: number;
  duration_ms: number;
  pre_roll_ms: number;
  post_roll_ms: number;
  amplitude: number;
  fade_ms: number;
};

export type BrowserCaptureMetadata = {
  user_agent: string | null;
  audio_context_sample_rate_hz: number | null;
  media_track_settings: Record<string, unknown>;
  requested_constraints: Record<string, unknown>;
  capture_path: CapturePath;
  recording_started_at_context_seconds?: number;
  chirp_started_at_context_seconds?: number;
  chirp_ended_at_context_seconds?: number;
  capture_ended_at_context_seconds?: number;
};

export type ProbeMetadata = {
  client_recorded_at: string | null;
  probe_config: ProbeConfig;
  browser: BrowserCaptureMetadata;
};

export type ProbeCapture = {
  wavBlob: Blob;
  samples: Float32Array;
  sampleRateHz: number;
  metadata: ProbeMetadata;
};

export type ProbeConfigEnvelope = {
  default: ProbeConfig;
  limits: Record<string, unknown>;
  upload: {
    max_upload_bytes: number;
    max_recording_seconds: number;
    allowed_content_types: string[];
    preferred_content_type: string;
  };
  warnings: string[];
};

export type FrequencySeries = {
  frequency_bins_hz: number[];
  magnitude_db: number[];
};

export type SpectralFeatures = {
  series: FrequencySeries;
  centroid_hz: number | null;
  bandwidth_hz: number | null;
  rolloff_hz: number | null;
  spectral_floor_db: number | null;
};

export type SpectrogramGrid = {
  kind: "stft" | "mel";
  times_seconds: number[];
  frequency_bins_hz: number[];
  magnitude_db: number[][];
};

export type TransferBandFeature = {
  start_hz: number;
  end_hz: number;
  center_hz: number;
  mean_db: number;
  peak_db: number;
};

export type ResponseTrace = {
  method: "regularized_deconvolution" | "matched_filter_envelope";
  times_seconds: number[];
  magnitude_db: number[];
  regularization: number;
  peak_time_seconds: number | null;
  direct_to_late_db: number | null;
};

export type PeakFeature = {
  frequency_hz: number;
  magnitude_db: number;
  prominence_db: number;
  q_factor: number | null;
};

export type DecayFeature = {
  method: "rms_envelope_log_linear";
  decay_rate_per_second: number | null;
  rt60_seconds: number | null;
  fit_r2: number | null;
  window_start_seconds: number;
  window_end_seconds: number;
};

export type DecayBandFeature = {
  label: "low" | "mid" | "high";
  start_hz: number;
  end_hz: number;
  decay_rate_per_second: number | null;
  rt60_seconds: number | null;
  fit_r2: number | null;
};

export type MfccCoefficientFeature = {
  index: number;
  mean: number;
  std: number;
  minimum: number;
  maximum: number;
};

export type MfccSummaryFeature = {
  method: "log_mel_dct_ii";
  coefficients: MfccCoefficientFeature[];
};

export type ModeGroupFeature = {
  start_hz: number;
  end_hz: number;
  center_hz: number;
  peak_count: number;
  frequencies_hz: number[];
  dominant_frequency_hz: number;
  max_prominence_db: number;
  q_factor: number | null;
  warning_labels: string[];
};

export type ResponseCaveatFeature = {
  id: string;
  severity: "info" | "review" | "warning";
  message: string;
};

export type DspAnalysis = {
  bandpass_low_hz: number;
  bandpass_high_hz: number;
  signal_to_noise_db: number | null;
  fft: SpectralFeatures;
  stft: SpectrogramGrid;
  mel_spectrogram: SpectrogramGrid;
  transfer_response: TransferBandFeature[];
  impulse_response: ResponseTrace;
  matched_response: ResponseTrace;
  mfcc: MfccSummaryFeature;
  dominant_peaks: PeakFeature[];
  mode_groups: ModeGroupFeature[];
  decay: DecayFeature;
  decay_bands: DecayBandFeature[];
  response_caveats: ResponseCaveatFeature[];
};

export type AnalysisResponse = {
  analysis_id: string;
  status: "ok";
  audio: {
    content_type: string;
    filename: string | null;
    byte_count: number;
    sample_rate_hz: number;
    channels: number;
    sample_width_bytes: number;
    frame_count: number;
    sample_count: number;
    duration_seconds: number;
    rms: number;
    peak_amplitude: number;
    dc_offset: number;
  };
  probe: ProbeMetadata;
  alignment: {
    method: "matched_filter_log_chirp";
    confidence: number;
    estimated_latency_ms: number | null;
    detected_start_seconds: number | null;
    expected_start_seconds: number | null;
    notes: string[];
  };
  dsp: DspAnalysis;
  warnings: string[];
};

export type ExplanationClaim = {
  text: string;
  evidence_refs: string[];
  refs_resolved: boolean;
  grounding_status: "deterministic_rule" | "refs_resolved" | "unverified";
  grounding_reason: string | null;
  authoritative_values: Record<string, unknown>;
};

export type LlmExplanation = {
  explainability_version: number;
  summary: string;
  summary_claim?: ExplanationClaim | null;
  observations: string[];
  observation_claims?: ExplanationClaim[];
  acoustic_hypotheses: string[];
  acoustic_hypothesis_claims?: ExplanationClaim[];
  experiment_design: string[];
  experiment_design_claims?: ExplanationClaim[];
  physics_tutoring: string[];
  physics_tutoring_claims?: ExplanationClaim[];
  troubleshooting: string[];
  troubleshooting_claims?: ExplanationClaim[];
  evidence_critique: string[];
  evidence_critique_claims?: ExplanationClaim[];
  caveats: string[];
  caveat_claims?: ExplanationClaim[];
  next_measurement: string[];
  next_measurement_claims?: ExplanationClaim[];
};

export type LlmExplainResponse = {
  explainability_version: number;
  status: "ok" | "disabled";
  provider: "vertex_gemini";
  model: string;
  region: string;
  thinking_level: string;
  raw_audio_sent: boolean;
  explanation: LlmExplanation;
  evidence: Record<string, unknown>;
  warnings: string[];
};
