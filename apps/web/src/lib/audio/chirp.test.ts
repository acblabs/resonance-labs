import { describe, expect, it } from 'vitest';
import { join } from 'node:path';
import { readFileSync } from 'node:fs';
import { FALLBACK_PROBE_CONFIG, clampProbeConfig, generateLogChirp } from './chirp';
import type { ProbeConfig } from './types';

type GoldenChirpFixture = {
  sample_rate_hz: number;
  config: ProbeConfig;
  atol: number;
  sample_indices: number[];
  samples: number[];
};

function loadGoldenChirpFixture(): GoldenChirpFixture {
  const fixturePath = join(
    process.cwd(),
    '../../services/api/tests/fixtures/cross_language_log_chirp.json'
  );
  return JSON.parse(readFileSync(fixturePath, 'utf-8')) as GoldenChirpFixture;
}

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

  it('matches the Python DSP reference chirp fixture', () => {
    const fixture = loadGoldenChirpFixture();
    const samples = generateLogChirp(fixture.config, fixture.sample_rate_hz);

    expect(fixture.sample_indices.length).toBe(fixture.samples.length);
    for (let fixtureIndex = 0; fixtureIndex < fixture.sample_indices.length; fixtureIndex += 1) {
      const sampleIndex = fixture.sample_indices[fixtureIndex];
      expect(Math.abs(samples[sampleIndex] - fixture.samples[fixtureIndex])).toBeLessThanOrEqual(
        fixture.atol
      );
    }
  });
});
