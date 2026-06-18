import { describe, expect, it } from 'vitest';
import type { AnalysisResponse, ProbeConfig } from '$lib/audio/types';
import {
  captureSignature,
  createCalibrationAnchor,
  createFreeAirReference,
  createCalibrationProfile,
  estimateFillLevel,
  exportCalibrationProfile,
  extractCalibrationFeatureVector,
  importCalibrationProfile,
  withFreeAirReference,
  withCalibrationAnchor
} from './calibration';

const PROBE_CONFIG: ProbeConfig = {
  signal_type: 'log_chirp',
  start_hz: 500,
  end_hz: 10000,
  duration_ms: 500,
  pre_roll_ms: 250,
  post_roll_ms: 1000,
  amplitude: 0.35,
  fade_ms: 10
};

describe('calibration feature extraction', () => {
  it('extracts a finite local feature vector from Phase 2 DSP output', () => {
    const vector = extractCalibrationFeatureVector(makeAnalysis('feature-check', 1500));

    expect(vector.schemaVersion).toBe(1);
    expect(vector.summary.primaryPeakHz).toBe(1500);
    expect(vector.features.length).toBeGreaterThan(12);
    expect(vector.features.every((feature) => Number.isFinite(feature.value))).toBe(true);
  });
});

describe('calibration estimator', () => {
  it('returns incomplete until empty, half, and full anchors exist', () => {
    const profile = withCalibrationAnchor(
      createCalibrationProfile('test'),
      createCalibrationAnchor('empty', makeAnalysis('empty', 1600))
    );

    const estimate = estimateFillLevel(makeAnalysis('query', 1500), profile);

    expect(estimate.status).toBe('incomplete');
    expect(estimate.fillPercent).toBeNull();
    expect(estimate.warnings[0]).toContain('Missing');
  });

  it('interpolates along the nearest calibrated feature segment', () => {
    const emptyHz = 1600;
    const halfHz = 1400;
    const fullHz = 1200;
    const quarterHz = geometricMean(emptyHz, halfHz);
    const profile = completeProfile(emptyHz, halfHz, fullHz);

    const estimate = estimateFillLevel(makeAnalysis('quarter', quarterHz), profile);

    expect(estimate.status).toBe('ready');
    expect(estimate.fillPercent ?? 0).toBeGreaterThan(22);
    expect(estimate.fillPercent ?? 0).toBeLessThan(28);
    expect(estimate.references.globalMeanPercent).toBe(50);
    expect(estimate.references.nearestAnchorPercent).not.toBeNull();
    expect(estimate.comparableFeatureCount).toBeGreaterThan(8);
  });

  it('does not collapse clean single-repeat demo profiles to low confidence', () => {
    const profile = completeProfile(1600, 1400, 1200);

    const estimate = estimateFillLevel(makeAnalysis('clean-quarter', geometricMean(1600, 1400)), profile);

    expect(estimate.confidenceLabel).not.toBe('low');
    expect(estimate.warnings.join(' ')).toContain('only one repeat');
    expect(estimate.warnings.join(' ')).toContain('No free-air reference');
  });

  it('appends repeated anchors and estimates from the aggregate feature vector', () => {
    let profile = createCalibrationProfile('test');
    profile = withCalibrationAnchor(
      profile,
      createCalibrationAnchor('empty', makeAnalysis('empty-a', 1620))
    );
    profile = withCalibrationAnchor(
      profile,
      createCalibrationAnchor('empty', makeAnalysis('empty-b', 1580))
    );

    const empty = profile.anchors.empty;

    expect(empty?.sampleCount).toBe(2);
    expect(empty?.stability.repeated).toBe(true);
    expect(empty?.featureVector.summary.primaryPeakHz).toBeCloseTo(geometricMean(1620, 1580), 6);
  });

  it('uses a canonical capture signature for saved observations', () => {
    const analysis = makeAnalysis('signature-check', 1500, {
      userAgent: 'Mozilla/5.0 Chrome/126.0.0.0'
    });
    const anchor = createCalibrationAnchor('empty', analysis);

    expect(anchor.captureSignature).toBe(captureSignature(analysis));
    expect(anchor.captureSignature).toBe('48000:48000:audio_worklet:chrome:false/false/false');
  });

  it('beats global-mean and nearest-anchor baselines on a monotone synthetic profile', () => {
    const targetPercent = 25;
    const profile = completeProfile(2000, 1600, 1200);
    const queryHz = geometricMean(2000, 1600);

    const estimate = estimateFillLevel(makeAnalysis('baseline-quarter', queryHz), profile);
    const calibratedError = Math.abs((estimate.fillPercent ?? 0) - targetPercent);
    const globalMeanError = Math.abs(estimate.references.globalMeanPercent - targetPercent);
    const nearestAnchorError = Math.abs(
      (estimate.references.nearestAnchorPercent ?? Number.POSITIVE_INFINITY) - targetPercent
    );

    expect(estimate.status).toBe('ready');
    expect(calibratedError).toBeLessThan(globalMeanError);
    expect(calibratedError).toBeLessThan(nearestAnchorError);
  });

  it('penalizes low-quality or incompatible probes instead of forcing high confidence', () => {
    const profile = completeProfile(1600, 1400, 1200);
    const mismatchedConfig = { ...PROBE_CONFIG, end_hz: 9000 };
    const lowQuality = makeAnalysis('low-quality', 1300, {
      alignmentConfidence: 0.12,
      signalToNoiseDb: 7,
      probeConfig: mismatchedConfig
    });

    const estimate = estimateFillLevel(lowQuality, profile);

    expect(estimate.status).toBe('ready');
    expect(estimate.confidenceLabel).toBe('low');
    expect(estimate.confidence).toBeLessThan(0.25);
    expect(estimate.warnings.join(' ')).toContain('Probe settings differ');
    expect(estimate.warnings.join(' ')).toContain('signal-to-noise');
  });

  it('warns when browser capture compatibility differs from saved anchors', () => {
    const profile = completeProfile(1600, 1400, 1200);

    const estimate = estimateFillLevel(
      makeAnalysis('query-44100', 1300, { sampleRateHz: 44100 }),
      profile
    );

    expect(estimate.warnings.join(' ')).toContain('sample rate differs');
    expect(estimate.confidenceLabel).toBe('low');
  });

  it('tracks free-air references separately from fill anchors', () => {
    let profile = completeProfile(1600, 1400, 1200);
    profile = withFreeAirReference(
      profile,
      createFreeAirReference(makeAnalysis('free-air', 900))
    );

    const estimate = estimateFillLevel(makeAnalysis('query', 1300), profile);

    expect(profile.freeAirReference?.sampleCount).toBe(1);
    expect(estimate.freeAirDistance).not.toBeNull();
    expect(estimate.warnings.join(' ')).not.toContain('No free-air reference');
  });

  it('exports and imports normalized local profile JSON', () => {
    const profile = withFreeAirReference(
      completeProfile(1600, 1400, 1200),
      createFreeAirReference(makeAnalysis('free-air', 900))
    );

    const imported = importCalibrationProfile(exportCalibrationProfile(profile));

    expect(imported.id).not.toBe(profile.id);
    expect(imported.name).toContain('import');
    expect(imported.anchors.empty?.sampleCount).toBe(1);
    expect(imported.freeAirReference?.sampleCount).toBe(1);
  });
});

function completeProfile(emptyHz: number, halfHz: number, fullHz: number) {
  let profile = createCalibrationProfile('test');
  profile = withCalibrationAnchor(profile, createCalibrationAnchor('empty', makeAnalysis('empty', emptyHz)));
  profile = withCalibrationAnchor(profile, createCalibrationAnchor('half', makeAnalysis('half', halfHz)));
  profile = withCalibrationAnchor(profile, createCalibrationAnchor('full', makeAnalysis('full', fullHz)));
  return profile;
}

function makeAnalysis(
  id: string,
  primaryPeakHz: number,
  options: {
    alignmentConfidence?: number;
    signalToNoiseDb?: number;
    probeConfig?: ProbeConfig;
    sampleRateHz?: number;
    userAgent?: string;
    echoCancellation?: boolean;
  } = {}
): AnalysisResponse {
  const alignmentConfidence = options.alignmentConfidence ?? 0.92;
  const signalToNoiseDb = options.signalToNoiseDb ?? 24;
  const config = options.probeConfig ?? PROBE_CONFIG;
  const sampleRateHz = options.sampleRateHz ?? 48000;
  const lowShift = (primaryPeakHz - 1400) / 100;

  return {
    analysis_id: id,
    status: 'ok',
    audio: {
      content_type: 'audio/wav',
      filename: 'probe.wav',
      byte_count: 128000,
      sample_rate_hz: sampleRateHz,
      channels: 1,
      sample_width_bytes: 2,
      frame_count: 84000,
      sample_count: 84000,
      duration_seconds: 1.75,
      rms: 0.08,
      peak_amplitude: 0.4,
      dc_offset: 0
    },
    probe: {
      client_recorded_at: '2026-06-18T12:00:00.000Z',
      probe_config: config,
      browser: {
        user_agent: options.userAgent ?? 'Chrome vitest',
        audio_context_sample_rate_hz: sampleRateHz,
        media_track_settings: {
          echoCancellation: options.echoCancellation ?? false,
          noiseSuppression: false,
          autoGainControl: false
        },
        requested_constraints: {},
        capture_path: 'audio_worklet'
      }
    },
    alignment: {
      method: 'matched_filter_log_chirp',
      confidence: alignmentConfidence,
      estimated_latency_ms: 4,
      detected_start_seconds: 0.254,
      expected_start_seconds: 0.25,
      notes: []
    },
    dsp: {
      bandpass_low_hz: 300,
      bandpass_high_hz: 12500,
      signal_to_noise_db: signalToNoiseDb,
      fft: {
        series: {
          frequency_bins_hz: [800, primaryPeakHz, 4000],
          magnitude_db: [-50, -20, -35]
        },
        centroid_hz: primaryPeakHz * 1.18,
        bandwidth_hz: primaryPeakHz * 0.42,
        rolloff_hz: primaryPeakHz * 2.6,
        spectral_floor_db: -70
      },
      stft: {
        kind: 'stft',
        times_seconds: [],
        frequency_bins_hz: [],
        magnitude_db: []
      },
      mel_spectrogram: {
        kind: 'mel',
        times_seconds: [],
        frequency_bins_hz: [],
        magnitude_db: []
      },
      transfer_response: [
        band(500, 1000, -15 + lowShift, -9 + lowShift),
        band(1000, 2000, -12 + lowShift * 0.7, -7 + lowShift * 0.5),
        band(2000, 4000, -18 - lowShift * 0.4, -12 - lowShift * 0.3),
        band(4000, 8000, -25 - lowShift * 0.2, -18 - lowShift * 0.2)
      ],
      dominant_peaks: [
        {
          frequency_hz: primaryPeakHz,
          magnitude_db: -18,
          prominence_db: 19,
          q_factor: 8
        },
        {
          frequency_hz: primaryPeakHz * 1.7,
          magnitude_db: -24,
          prominence_db: 12,
          q_factor: 5
        }
      ],
      decay: {
        method: 'rms_envelope_log_linear',
        decay_rate_per_second: 4 + lowShift * 0.2,
        rt60_seconds: 1.7 - lowShift * 0.04,
        fit_r2: 0.91,
        window_start_seconds: 0.75,
        window_end_seconds: 1.75
      }
    },
    warnings:
      alignmentConfidence < 0.2 || signalToNoiseDb < 12
        ? ['Synthetic low-quality calibration probe.']
        : []
  };
}

function band(start: number, end: number, meanDb: number, peakDb: number) {
  return {
    start_hz: start,
    end_hz: end,
    center_hz: (start + end) / 2,
    mean_db: meanDb,
    peak_db: peakDb
  };
}

function geometricMean(left: number, right: number): number {
  return 2 ** ((Math.log2(left) + Math.log2(right)) / 2);
}
