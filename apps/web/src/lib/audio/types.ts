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
  user_agent: string;
  audio_context_sample_rate_hz: number;
  media_track_settings: MediaTrackSettings;
  requested_constraints: MediaStreamConstraints;
  capture_path: CapturePath;
  recording_started_at_context_seconds?: number;
  chirp_started_at_context_seconds?: number;
  chirp_ended_at_context_seconds?: number;
  capture_ended_at_context_seconds?: number;
};

export type ProbeMetadata = {
  client_recorded_at: string;
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

export type DspAnalysis = {
  bandpass_low_hz: number;
  bandpass_high_hz: number;
  signal_to_noise_db: number | null;
  fft: SpectralFeatures;
  stft: SpectrogramGrid;
  mel_spectrogram: SpectrogramGrid;
  transfer_response: TransferBandFeature[];
  dominant_peaks: PeakFeature[];
  decay: DecayFeature;
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

export type LlmExplanation = {
  summary: string;
  observations: string[];
  material_hypotheses: string[];
  caveats: string[];
  next_measurement: string[];
};

export type LlmExplainResponse = {
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

export type DatasetCaptureLabel = {
  fill_percent?: number;
  fill_mass_g?: number;
  vessel_empty_mass_g?: number;
  vessel_full_mass_g?: number;
  vessel_current_mass_g?: number;
};

export type DatasetCaptureContext = {
  session_id: string;
  glass_id: string;
  device_id: string;
  browser_id: string;
  room_id: string;
  operator_id?: string;
  volume_setting?: string;
  material?: string;
  geometry?: string;
  notes?: string;
};

export type DatasetCaptureRequest = {
  label: DatasetCaptureLabel;
  context: DatasetCaptureContext;
  store_audio: boolean;
  notes?: string;
};

export type DatasetCaptureResponse = {
  record_id: string;
  status: "stored";
  inbox_prefix: string;
  stored_paths: {
    inbox_record_path: string;
    audio_path: string | null;
    analysis_path: string;
  };
  analysis: AnalysisResponse;
};
