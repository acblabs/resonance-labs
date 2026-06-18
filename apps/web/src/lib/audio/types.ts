export type CapturePath = 'audio_worklet' | 'script_processor' | 'media_recorder' | 'unknown';

export type ProbeConfig = {
  signal_type: 'log_chirp';
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

export type AnalysisResponse = {
  analysis_id: string;
  status: 'ok';
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
    method: 'phase1_placeholder';
    confidence: number | null;
    estimated_latency_ms: number | null;
    notes: string[];
  };
  warnings: string[];
};
