import type { ProbeConfig } from './types';

type NumericLimit = {
  min: number;
  max: number;
};

export const PROBE_LIMITS: Record<Exclude<keyof ProbeConfig, 'signal_type'>, NumericLimit> = {
  start_hz: { min: 100, max: 18000 },
  end_hz: { min: 200, max: 20000 },
  duration_ms: { min: 100, max: 1000 },
  pre_roll_ms: { min: 0, max: 2000 },
  post_roll_ms: { min: 100, max: 4000 },
  amplitude: { min: 0.01, max: 0.35 },
  fade_ms: { min: 0, max: 100 }
};

export const FALLBACK_PROBE_CONFIG: ProbeConfig = {
  signal_type: 'log_chirp',
  start_hz: 500,
  end_hz: 10000,
  duration_ms: 500,
  pre_roll_ms: 250,
  post_roll_ms: 1000,
  amplitude: 0.35,
  fade_ms: 10
};

export function generateLogChirp(config: ProbeConfig, sampleRateHz: number): Float32Array {
  const safeConfig = clampProbeConfig(config);
  const durationSeconds = safeConfig.duration_ms / 1000;
  const sampleCount = Math.max(1, Math.round(durationSeconds * sampleRateHz));
  const samples = new Float32Array(sampleCount);
  const startHz = safeConfig.start_hz;
  const endHz = safeConfig.end_hz;
  const sweepRate = Math.log(endHz / startHz) / durationSeconds;
  const fadeSamples = Math.round((safeConfig.fade_ms / 1000) * sampleRateHz);

  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / sampleRateHz;
    const phase = (2 * Math.PI * startHz * (Math.exp(sweepRate * time) - 1)) / sweepRate;
    samples[index] = Math.sin(phase) * safeConfig.amplitude * fadeGain(index, sampleCount, fadeSamples);
  }

  return samples;
}

export function clampProbeConfig(config: ProbeConfig): ProbeConfig {
  const durationMs = clamp(config.duration_ms, PROBE_LIMITS.duration_ms);
  const startHz = clamp(config.start_hz, PROBE_LIMITS.start_hz);
  let safeStartHz = startHz;
  let endHz = clamp(config.end_hz, PROBE_LIMITS.end_hz);

  if (safeStartHz >= endHz) {
    if (safeStartHz < PROBE_LIMITS.end_hz.max) {
      endHz = Math.min(PROBE_LIMITS.end_hz.max, safeStartHz + 100);
    } else {
      safeStartHz = Math.max(PROBE_LIMITS.start_hz.min, endHz - 100);
    }
  }

  return {
    signal_type: 'log_chirp',
    start_hz: safeStartHz,
    end_hz: endHz,
    duration_ms: durationMs,
    pre_roll_ms: clamp(config.pre_roll_ms, PROBE_LIMITS.pre_roll_ms),
    post_roll_ms: clamp(config.post_roll_ms, PROBE_LIMITS.post_roll_ms),
    amplitude: clamp(config.amplitude, PROBE_LIMITS.amplitude),
    fade_ms: Math.min(clamp(config.fade_ms, PROBE_LIMITS.fade_ms), Math.floor(durationMs / 2))
  };
}

function fadeGain(index: number, sampleCount: number, fadeSamples: number): number {
  if (fadeSamples <= 0) {
    return 1;
  }

  const fadeIn = cosineRamp(Math.min(1, index / fadeSamples));
  const fadeOut = cosineRamp(Math.min(1, (sampleCount - index - 1) / fadeSamples));
  return Math.max(0, Math.min(fadeIn, fadeOut));
}

function cosineRamp(position: number): number {
  return 0.5 - 0.5 * Math.cos(Math.PI * position);
}

function clamp(value: number, limit: NumericLimit): number {
  if (!Number.isFinite(value)) {
    return limit.min;
  }
  return Math.min(limit.max, Math.max(limit.min, value));
}
