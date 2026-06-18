import { describe, expect, it } from 'vitest';
import { FALLBACK_PROBE_CONFIG, clampProbeConfig, generateLogChirp } from './chirp';

describe('chirp safety helpers', () => {
  it('clamps unsafe amplitude before sample generation', () => {
    const samples = generateLogChirp({ ...FALLBACK_PROBE_CONFIG, amplitude: 2 }, 48000);
    const peak = Math.max(...samples.map((sample) => Math.abs(sample)));

    expect(peak).toBeLessThanOrEqual(0.35);
  });

  it('keeps start frequency below end frequency', () => {
    const config = clampProbeConfig({
      ...FALLBACK_PROBE_CONFIG,
      start_hz: 25000,
      end_hz: 100
    });

    expect(config.start_hz).toBeLessThan(config.end_hz);
  });
});
