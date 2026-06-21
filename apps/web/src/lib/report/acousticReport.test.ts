import { describe, expect, it } from "vitest";
import { join } from "node:path";
import { readFileSync } from "node:fs";
import type { AnalysisResponse } from "$lib/audio/types";
import {
  acousticReportFilename,
  buildAcousticReport,
  buildDeviceValidation,
  compareAcousticReports,
  parseAcousticReportPayload,
  wrapTextForWidth,
} from "./acousticReport";

describe("acoustic report helpers", () => {
  it("builds a versioned report without raw audio payloads", () => {
    const report = buildAcousticReport(
      makeAnalysis(),
      null,
      new Date("2026-06-20T16:30:00Z"),
    );

    expect(report.schema_version).toBe("resonancelab.acoustic_report.v1");
    expect(report.descriptors.room_character).toBe("Live");
    expect(report.descriptors.brightness).toBe("Bright");
    expect(report.validation.status).toBe("pass");
    expect(report.method_notes.join(" ")).toContain("regularized driven-path");
    expect(report.method_notes.join(" ")).toContain("impulse envelope");
    expect(report.analysis.dsp.decay_bands).toHaveLength(3);
    expect(findForbiddenKeys(report)).toEqual([]);
  });

  it("round-trips the golden public-safe analysis fixture", () => {
    const report = buildAcousticReport(
      loadGoldenAnalysisFixture(),
      null,
      new Date("2026-06-20T16:30:00Z"),
    );

    expect(report.validation.status).toBe("pass");
    expect(report.validation.required_score).toBe(1);
    expect(report.method_notes.join(" ")).toContain("not calibrated");
    expect(report.descriptors.dominant_mode).toBe("2.06 kHz, Q >300");
  });

  it("caps very high Q display and emits an explicit caveat", () => {
    const report = buildAcousticReport(makeAnalysis({ qFactor: 1175 }));

    expect(report.descriptors.dominant_mode).toContain("Q >300");
    expect(report.descriptors.dominant_mode_note).toContain("Very narrow dominant peak");
    expect(report.caveats.join(" ")).toContain("Very narrow dominant peak");
  });

  it("marks low-confidence captures as failed validation", () => {
    const validation = buildDeviceValidation(
      makeAnalysis({
        alignmentConfidence: 0.12,
        signalToNoiseDb: 7,
        peakAmplitude: 0.998,
      }),
    );

    expect(validation.status).toBe("fail");
    expect(
      validation.checks.find((check) => check.id === "alignment_confidence")
        ?.status,
    ).toBe("fail");
    expect(
      validation.checks.find((check) => check.id === "snr_db")?.status,
    ).toBe("fail");
    expect(
      validation.checks.find((check) => check.id === "peak_amplitude")?.status,
    ).toBe("fail");
  });

  it("weights required checks more heavily than advisory checks", () => {
    const validation = buildDeviceValidation(
      makeAnalysis({
        capturePath: "unknown",
        mediaTrackSettings: { echoCancellation: true },
      }),
    );

    expect(validation.status).toBe("review");
    expect(validation.required_score).toBe(1);
    expect(validation.advisory_score).toBeLessThan(1);
    expect(validation.score).toBeGreaterThan(validation.advisory_score);
    expect(validation.score_model).toContain("required checks carry double");
  });

  it("pins duration, sample-rate, capture-path, and decay validation boundaries", () => {
    expect(
      checkStatus(makeAnalysis({ durationSeconds: 1.75 * 0.9 }), "duration"),
    ).toBe("pass");
    expect(
      checkStatus(makeAnalysis({ durationSeconds: 1.75 * 0.75 }), "duration"),
    ).toBe("review");
    expect(
      checkStatus(makeAnalysis({ durationSeconds: 1.75 * 0.74 }), "duration"),
    ).toBe("fail");

    expect(checkStatus(makeAnalysis({ sampleRateHz: 44100 }), "sample_rate")).toBe(
      "pass",
    );
    expect(checkStatus(makeAnalysis({ sampleRateHz: 16000 }), "sample_rate")).toBe(
      "review",
    );
    expect(checkStatus(makeAnalysis({ sampleRateHz: 15999 }), "sample_rate")).toBe(
      "fail",
    );

    expect(checkStatus(makeAnalysis({ capturePath: "audio_worklet" }), "capture_path")).toBe(
      "pass",
    );
    expect(
      checkStatus(makeAnalysis({ capturePath: "script_processor" }), "capture_path"),
    ).toBe("review");
    expect(checkStatus(makeAnalysis({ capturePath: "unknown" }), "capture_path")).toBe(
      "fail",
    );

    expect(checkStatus(makeAnalysis({ fitR2: 0.55, rt60Seconds: 0.8 }), "decay_fit")).toBe(
      "pass",
    );
    expect(checkStatus(makeAnalysis({ fitR2: 0.3, rt60Seconds: 0.8 }), "decay_fit")).toBe(
      "review",
    );
    expect(checkStatus(makeAnalysis({ fitR2: null, rt60Seconds: null }), "decay_fit")).toBe(
      "fail",
    );
  });

  it("marks truncated wrapped export text with an ellipsis", () => {
    const wrapped = wrapTextForWidth(
      "one two three four five six",
      (value) => value.length,
      11,
      2,
    );

    expect(wrapped.truncated).toBe(true);
    expect(wrapped.lines).toEqual(["one two", "three fo..."]);
  });

  it("uses stable report filenames", () => {
    const report = buildAcousticReport(
      makeAnalysis(),
      null,
      new Date("2026-06-20T16:30:00Z"),
    );

    expect(acousticReportFilename(report, "json")).toBe(
      "resonancelab-12345678-2026-06-20T16-30-00-000Z.json",
    );
  });

  it("parses exported report JSON and compares repeat captures", () => {
    const first = buildAcousticReport(
      makeAnalysis(),
      null,
      new Date("2026-06-20T16:30:00Z"),
    );
    const second = buildAcousticReport(
      makeAnalysis({
        alignmentConfidence: 0.66,
        signalToNoiseDb: 19.5,
        rt60Seconds: 0.92,
      }),
      null,
      new Date("2026-06-20T16:35:00Z"),
    );

    const parsed = parseAcousticReportPayload(JSON.parse(JSON.stringify(first)));
    const comparison = compareAcousticReports(parsed, second);

    expect(comparison.same_capture_condition).toBe(true);
    expect(comparison.metrics.find((metric) => metric.id === "snr")?.delta).toBe(
      "-4.0 dB",
    );
    expect(comparison.metrics.find((metric) => metric.id === "rt60")?.second).toBe(
      "0.920 s",
    );
    expect(comparison.transfer_bands[0].delta).toBe("0.0 dB");
  });

  it("rejects non-report comparison imports", () => {
    expect(() => parseAcousticReportPayload({ schema_version: "elsewhere" })).toThrow(
      "ResonanceLab acoustic report",
    );
  });
});

function makeAnalysis(
  overrides: {
    alignmentConfidence?: number;
    signalToNoiseDb?: number | null;
    peakAmplitude?: number;
    durationSeconds?: number;
    sampleRateHz?: number;
    capturePath?: AnalysisResponse["probe"]["browser"]["capture_path"];
    fitR2?: number | null;
    rt60Seconds?: number | null;
    qFactor?: number | null;
    mediaTrackSettings?: Partial<MediaTrackSettings>;
  } = {},
): AnalysisResponse {
  const alignmentConfidence = overrides.alignmentConfidence ?? 0.72;
  const signalToNoiseDb = overrides.signalToNoiseDb ?? 23.5;
  const peakAmplitude = overrides.peakAmplitude ?? 0.42;
  const durationSeconds = overrides.durationSeconds ?? 1.75;
  const sampleRateHz = overrides.sampleRateHz ?? 48000;
  const fitR2 = overrides.fitR2 === undefined ? 0.64 : overrides.fitR2;
  const rt60Seconds =
    overrides.rt60Seconds === undefined ? 0.817 : overrides.rt60Seconds;
  const qFactor = overrides.qFactor === undefined ? 1175 : overrides.qFactor;
  return {
    analysis_id: "12345678-90ab-cdef-1234-567890abcdef",
    status: "ok",
    audio: {
      content_type: "audio/wav",
      filename: "probe.wav",
      byte_count: 165000,
      sample_rate_hz: sampleRateHz,
      channels: 1,
      sample_width_bytes: 2,
      frame_count: 84000,
      sample_count: 84000,
      duration_seconds: durationSeconds,
      rms: 0.04,
      peak_amplitude: peakAmplitude,
      dc_offset: 0.0001,
    },
    probe: {
      client_recorded_at: "2026-06-20T16:29:58Z",
      probe_config: {
        signal_type: "log_chirp",
        start_hz: 500,
        end_hz: 10000,
        duration_ms: 500,
        pre_roll_ms: 250,
        post_roll_ms: 1000,
        amplitude: 0.35,
        fade_ms: 10,
      },
      browser: {
        user_agent: "test-browser",
        audio_context_sample_rate_hz: sampleRateHz,
        media_track_settings: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          ...overrides.mediaTrackSettings,
        } as MediaTrackSettings,
        requested_constraints: {},
        capture_path: overrides.capturePath ?? "audio_worklet",
      },
    },
    alignment: {
      method: "matched_filter_log_chirp",
      confidence: alignmentConfidence,
      estimated_latency_ms: 4,
      detected_start_seconds: 0.254,
      expected_start_seconds: 0.25,
      notes: ["matched filter"],
    },
    dsp: {
      bandpass_low_hz: 300,
      bandpass_high_hz: 12500,
      signal_to_noise_db: signalToNoiseDb,
      fft: {
        centroid_hz: 4200,
        bandwidth_hz: 1800,
        rolloff_hz: 8400,
        spectral_floor_db: -72,
        series: {
          frequency_bins_hz: [500, 1000, 2000],
          magnitude_db: [-20, -12, -18],
        },
      },
      stft: {
        kind: "stft",
        times_seconds: [0, 0.5],
        frequency_bins_hz: [500, 1000],
        magnitude_db: [
          [-80, -40],
          [-70, -35],
        ],
      },
      mel_spectrogram: {
        kind: "mel",
        times_seconds: [0, 0.5],
        frequency_bins_hz: [500, 1000],
        magnitude_db: [
          [-80, -40],
          [-70, -35],
        ],
      },
      transfer_response: [
        {
          start_hz: 500,
          end_hz: 1000,
          center_hz: 750,
          mean_db: -16,
          peak_db: -12,
        },
      ],
      impulse_response: {
        method: "regularized_deconvolution",
        times_seconds: [0, 0.01, 0.02],
        magnitude_db: [-12, 0, -24],
        regularization: 0.0001,
      },
      dominant_peaks: [
        {
          frequency_hz: 2063.2,
          magnitude_db: -9,
          prominence_db: 15,
          q_factor: qFactor,
        },
      ],
      decay: {
        method: "rms_envelope_log_linear",
        decay_rate_per_second: 8.45,
        rt60_seconds: rt60Seconds,
        fit_r2: fitR2,
        window_start_seconds: 0.859,
        window_end_seconds: 1.75,
      },
      decay_bands: [
        {
          label: "low",
          start_hz: 100,
          end_hz: 500,
          decay_rate_per_second: 7.8,
          rt60_seconds: 0.885,
          fit_r2: 0.58,
        },
        {
          label: "mid",
          start_hz: 500,
          end_hz: 2000,
          decay_rate_per_second: 8.45,
          rt60_seconds: rt60Seconds,
          fit_r2: fitR2,
        },
        {
          label: "high",
          start_hz: 2000,
          end_hz: 8000,
          decay_rate_per_second: 10.5,
          rt60_seconds: 0.658,
          fit_r2: 0.62,
        },
      ],
    },
    warnings: [],
  };
}

function loadGoldenAnalysisFixture(): AnalysisResponse {
  const fixturePath = join(
    process.cwd(),
    "src/lib/report/fixtures/golden-analysis.json",
  );
  return JSON.parse(readFileSync(fixturePath, "utf-8")) as AnalysisResponse;
}

function checkStatus(analysis: AnalysisResponse, id: string) {
  const validation = buildDeviceValidation(analysis);
  const check = validation.checks.find((candidate) => candidate.id === id);
  expect(check, `missing validation check ${id}`).toBeTruthy();
  return check?.status;
}

function findForbiddenKeys(value: unknown): string[] {
  const forbidden = new Set(["wavBlob", "samples", "raw_audio", "rawAudio"]);
  if (Array.isArray(value)) {
    return value.flatMap((item) => findForbiddenKeys(item));
  }
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => [
      ...(forbidden.has(key) ? [key] : []),
      ...findForbiddenKeys(child),
    ]);
  }
  return [];
}
