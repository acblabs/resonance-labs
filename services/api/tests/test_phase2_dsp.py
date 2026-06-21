from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import numpy as np
from resonancelab.audio import decode_wav_pcm
from resonancelab.dsp import (
    ChirpSpec,
    analyze_chirp_response,
    apply_fft_bandpass,
    compute_impulse_response,
    compute_transfer_response,
    estimate_decay,
    find_dominant_peaks,
    generate_log_chirp,
)
from resonancelab.dsp.analysis import _estimate_q_factor

FIXTURES_DIR = Path(__file__).with_name("fixtures")
FIXTURE_PATH = FIXTURES_DIR / "phase2_golden_probe.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SAMPLE_RATE_HZ = int(FIXTURE["sample_rate_hz"])
GOLDEN_CHIRP = ChirpSpec(**FIXTURE["chirp"])
PRE_ROLL_SECONDS = float(FIXTURE["pre_roll_seconds"])
POST_ROLL_SECONDS = float(FIXTURE["post_roll_seconds"])
ACOUSTIC_DELAY_SECONDS = float(FIXTURE["acoustic_delay_seconds"])
EXPECTED = FIXTURE["expected"]


def golden_probe_samples() -> np.ndarray:
    chirp = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
    total_seconds = PRE_ROLL_SECONDS + GOLDEN_CHIRP.duration_seconds + POST_ROLL_SECONDS + 0.04
    samples = np.random.default_rng(int(FIXTURE["noise_seed"])).normal(
        loc=0.0,
        scale=float(FIXTURE["noise_std"]),
        size=int(total_seconds * SAMPLE_RATE_HZ),
    )

    chirp_start = int(round((PRE_ROLL_SECONDS + ACOUSTIC_DELAY_SECONDS) * SAMPLE_RATE_HZ))
    samples[chirp_start : chirp_start + chirp.size] += chirp

    ring_start = chirp_start + chirp.size
    time = np.arange(samples.size - ring_start, dtype=np.float64) / SAMPLE_RATE_HZ
    for tone in FIXTURE["ringdown_tones"]:
        frequency_hz = float(tone["frequency_hz"])
        amplitude = float(tone["amplitude"])
        decay_rate = float(tone["decay_rate_per_second"])
        samples[ring_start:] += (
            amplitude * np.exp(-decay_rate * time) * np.sin(2.0 * math.pi * frequency_hz * time)
        )
    return samples


class Phase2DspGoldenTests(unittest.TestCase):
    def test_python_chirp_matches_cross_language_fixture(self) -> None:
        fixture = json.loads((FIXTURES_DIR / "cross_language_log_chirp.json").read_text())
        config = fixture["config"]
        sample_indices = np.asarray(fixture["sample_indices"], dtype=np.int64)
        expected = np.asarray(fixture["samples"], dtype=np.float32)

        actual = generate_log_chirp(
            ChirpSpec(
                start_hz=config["start_hz"],
                end_hz=config["end_hz"],
                duration_seconds=config["duration_ms"] / 1000.0,
                amplitude=config["amplitude"],
                fade_seconds=config["fade_ms"] / 1000.0,
            ),
            int(fixture["sample_rate_hz"]),
        ).astype(np.float32)

        np.testing.assert_allclose(actual[sample_indices], expected, atol=fixture["atol"], rtol=0.0)

    def test_chirp_analysis_matches_golden_fixture(self) -> None:
        analysis = analyze_chirp_response(
            golden_probe_samples(),
            SAMPLE_RATE_HZ,
            GOLDEN_CHIRP,
            pre_roll_seconds=PRE_ROLL_SECONDS,
            post_roll_seconds=POST_ROLL_SECONDS,
        )

        self.assertGreater(analysis.alignment.confidence, EXPECTED["min_alignment_confidence"])
        self.assertIsNotNone(analysis.alignment.estimated_latency_ms)
        self.assertAlmostEqual(
            analysis.alignment.estimated_latency_ms or 0.0,
            EXPECTED["alignment_latency_ms"],
            delta=EXPECTED["alignment_latency_tolerance_ms"],
        )
        self.assertIsNotNone(analysis.signal_to_noise_db)
        self.assertGreater(
            analysis.signal_to_noise_db or 0.0,
            EXPECTED["min_signal_to_noise_db"],
        )

        self.assertGreaterEqual(len(analysis.dominant_peaks), 2)
        self.assertAlmostEqual(
            analysis.dominant_peaks[0].frequency_hz,
            EXPECTED["primary_peak_hz"],
            delta=EXPECTED["primary_peak_tolerance_hz"],
        )
        self.assertIsNotNone(analysis.decay.decay_rate_per_second)
        self.assertGreater(analysis.decay.decay_rate_per_second or 0.0, 2.0)
        self.assertLess(analysis.decay.rt60_seconds or 999.0, 2.0)
        self.assertGreater(len(analysis.impulse_response.times_seconds), 10)
        self.assertEqual(
            len(analysis.impulse_response.times_seconds),
            len(analysis.impulse_response.magnitude_db),
        )
        self.assertEqual({band.label for band in analysis.decay_bands}, {"low", "mid", "high"})
        self.assertTrue(any(band.rt60_seconds is not None for band in analysis.decay_bands))

    def test_recorded_style_wav_fixture_exercises_colored_probe(self) -> None:
        fixture = json.loads((FIXTURES_DIR / "phase2_recorded_style_probe.json").read_text())
        config = fixture["probe_config"]
        expected = fixture["expected"]
        decoded = decode_wav_pcm((FIXTURES_DIR / fixture["wav_file"]).read_bytes())

        analysis = analyze_chirp_response(
            decoded.samples,
            decoded.sample_rate_hz,
            ChirpSpec(
                start_hz=config["start_hz"],
                end_hz=config["end_hz"],
                duration_seconds=config["duration_seconds"],
                amplitude=config["amplitude"],
                fade_seconds=config["fade_seconds"],
            ),
            pre_roll_seconds=config["pre_roll_seconds"],
            post_roll_seconds=config["post_roll_seconds"],
        )

        self.assertEqual(decoded.sample_rate_hz, fixture["sample_rate_hz"])
        self.assertGreater(
            analysis.alignment.confidence,
            expected["min_alignment_confidence"],
        )
        self.assertLess(
            analysis.alignment.confidence,
            expected["max_alignment_confidence"],
        )
        self.assertAlmostEqual(
            analysis.alignment.estimated_latency_ms or 0.0,
            expected["latency_ms"],
            delta=expected["latency_tolerance_ms"],
        )
        self.assertGreater(analysis.signal_to_noise_db or 0.0, expected["min_signal_to_noise_db"])
        self.assertAlmostEqual(
            analysis.dominant_peaks[0].frequency_hz,
            expected["primary_peak_hz"],
            delta=expected["primary_peak_tolerance_hz"],
        )
        self.assertAlmostEqual(
            analysis.dominant_peaks[1].frequency_hz,
            expected["secondary_peak_hz"],
            delta=expected["secondary_peak_tolerance_hz"],
        )
        self.assertGreater(
            analysis.decay.decay_rate_per_second or 0.0,
            expected["min_decay_rate_per_second"],
        )
        self.assertLess(
            analysis.decay.decay_rate_per_second or 999.0,
            expected["max_decay_rate_per_second"],
        )

    def test_bandpass_attenuates_out_of_band_tone(self) -> None:
        time = np.arange(int(0.35 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        signal = 0.8 * np.sin(2.0 * math.pi * 500.0 * time)
        signal += 0.8 * np.sin(2.0 * math.pi * 6000.0 * time)

        filtered = apply_fft_bandpass(signal, SAMPLE_RATE_HZ, 400.0, 700.0, transition_hz=50.0)

        self.assertGreater(_tone_amplitude(filtered, 500.0), 0.60)
        self.assertLess(_tone_amplitude(filtered, 6000.0), 0.04)

    def test_bandpass_zero_padding_reduces_end_to_start_wraparound(self) -> None:
        samples = np.zeros(4096, dtype=np.float64)
        samples[-1] = 1.0

        filtered = apply_fft_bandpass(samples, SAMPLE_RATE_HZ, 700.0, 1400.0, transition_hz=80.0)

        self.assertLess(
            float(np.max(np.abs(filtered[:128]))),
            0.02 * float(np.max(np.abs(filtered))),
        )

    def test_spectrogram_shapes_are_stable(self) -> None:
        analysis = analyze_chirp_response(
            golden_probe_samples(),
            SAMPLE_RATE_HZ,
            GOLDEN_CHIRP,
            pre_roll_seconds=PRE_ROLL_SECONDS,
            post_roll_seconds=POST_ROLL_SECONDS,
        )

        self.assertEqual(analysis.stft.kind, "stft")
        self.assertGreater(len(analysis.stft.times_seconds), 10)
        self.assertLessEqual(len(analysis.stft.times_seconds), 120)
        self.assertGreater(len(analysis.stft.frequency_bins_hz), 20)
        self.assertLessEqual(len(analysis.stft.frequency_bins_hz), 128)
        self.assertTrue(_finite_grid(analysis.stft.magnitude_db))

        self.assertEqual(analysis.mel_spectrogram.kind, "mel")
        self.assertEqual(len(analysis.mel_spectrogram.frequency_bins_hz), 40)
        self.assertEqual(len(analysis.mel_spectrogram.magnitude_db), 40)
        self.assertTrue(_finite_grid(analysis.mel_spectrogram.magnitude_db))

    def test_transfer_response_uses_regularized_deconvolution(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        captured = 0.5 * reference

        bands = compute_transfer_response(
            captured,
            reference,
            SAMPLE_RATE_HZ,
            min_hz=GOLDEN_CHIRP.start_hz,
            max_hz=GOLDEN_CHIRP.end_hz,
        )

        self.assertGreater(len(bands), 0)
        means = [band.mean_db for band in bands]
        self.assertTrue(all(math.isfinite(value) for value in means))
        in_band_means = [
            band.mean_db for band in bands if band.end_hz <= GOLDEN_CHIRP.end_hz * 0.9
        ]
        self.assertGreater(len(in_band_means), 0)
        self.assertLess(max(abs(value + 6.0) for value in in_band_means), 3.0)

    def test_transfer_response_handles_longer_response_window(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        captured = np.zeros(reference.size + int(round(0.25 * SAMPLE_RATE_HZ)))
        captured[: reference.size] = 0.5 * reference

        bands = compute_transfer_response(
            captured,
            reference,
            SAMPLE_RATE_HZ,
            min_hz=GOLDEN_CHIRP.start_hz,
            max_hz=GOLDEN_CHIRP.end_hz,
        )

        in_band_means = [
            band.mean_db for band in bands if band.end_hz <= GOLDEN_CHIRP.end_hz * 0.9
        ]
        self.assertGreater(len(in_band_means), 0)
        self.assertTrue(all(math.isfinite(value) for value in in_band_means))
        self.assertLess(max(abs(value + 6.0) for value in in_band_means), 3.0)

    def test_impulse_proxy_is_compact_normalized_deconvolution(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        captured = np.zeros(reference.size + int(round(0.10 * SAMPLE_RATE_HZ)))
        captured[16 : 16 + reference.size] += reference

        analysis = analyze_chirp_response(
            captured,
            SAMPLE_RATE_HZ,
            GOLDEN_CHIRP,
            pre_roll_seconds=0.0,
            post_roll_seconds=0.10,
        )

        trace = analysis.impulse_response
        self.assertEqual(trace.method, "regularized_deconvolution")
        self.assertLessEqual(len(trace.times_seconds), 192)
        self.assertEqual(len(trace.times_seconds), len(trace.magnitude_db))
        self.assertAlmostEqual(max(trace.magnitude_db), 0.0, places=6)

    def test_impulse_proxy_recovers_delayed_linear_response(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        delay_seconds = 0.014
        reflection_seconds = 0.062
        delay_samples = int(round(delay_seconds * SAMPLE_RATE_HZ))
        reflection_samples = int(round(reflection_seconds * SAMPLE_RATE_HZ))
        captured = np.zeros(reference.size + int(round(0.16 * SAMPLE_RATE_HZ)))
        captured[delay_samples : delay_samples + reference.size] += reference
        captured[reflection_samples : reflection_samples + reference.size] += 0.35 * reference[
            : captured.size - reflection_samples
        ]

        trace = compute_impulse_response(
            captured,
            reference,
            SAMPLE_RATE_HZ,
            max_seconds=0.12,
            max_points=192,
        )

        self.assertGreater(len(trace.times_seconds), 20)
        peak_index = int(np.argmax(trace.magnitude_db))
        self.assertAlmostEqual(trace.times_seconds[peak_index], delay_seconds, delta=0.003)
        self.assertAlmostEqual(max(trace.magnitude_db), 0.0, places=6)
        self.assertTrue(all(math.isfinite(value) for value in trace.magnitude_db))

    def test_impulse_proxy_returns_empty_for_zero_energy_reference(self) -> None:
        trace = compute_impulse_response(
            np.ones(256, dtype=np.float64),
            np.zeros(128, dtype=np.float64),
            SAMPLE_RATE_HZ,
        )

        self.assertEqual(trace.times_seconds, [])
        self.assertEqual(trace.magnitude_db, [])

    def test_decay_window_start_uses_fallback_slice_start(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        expected_start = int(round(PRE_ROLL_SECONDS * SAMPLE_RATE_HZ))
        detected_start = expected_start - int(round(0.05 * SAMPLE_RATE_HZ))
        samples = np.random.default_rng(37).normal(
            loc=0.0,
            scale=0.0004,
            size=expected_start + reference.size + int(round(0.20 * SAMPLE_RATE_HZ)),
        )
        samples[detected_start : detected_start + reference.size] += reference

        analysis = analyze_chirp_response(
            samples,
            SAMPLE_RATE_HZ,
            GOLDEN_CHIRP,
            pre_roll_seconds=PRE_ROLL_SECONDS,
            post_roll_seconds=0.02,
        )

        expected_window_start = (expected_start + reference.size) / SAMPLE_RATE_HZ
        self.assertAlmostEqual(
            analysis.decay.window_start_seconds,
            expected_window_start,
            places=6,
        )

    def test_snr_noise_window_excludes_early_detected_chirp(self) -> None:
        reference = generate_log_chirp(GOLDEN_CHIRP, SAMPLE_RATE_HZ)
        expected_start = int(round(PRE_ROLL_SECONDS * SAMPLE_RATE_HZ))
        detected_start = expected_start - int(round(0.05 * SAMPLE_RATE_HZ))
        samples = np.random.default_rng(117).normal(
            loc=0.0,
            scale=0.00015,
            size=expected_start + reference.size + int(round(0.4 * SAMPLE_RATE_HZ)),
        )
        samples[detected_start : detected_start + reference.size] += reference

        analysis = analyze_chirp_response(
            samples,
            SAMPLE_RATE_HZ,
            GOLDEN_CHIRP,
            pre_roll_seconds=PRE_ROLL_SECONDS,
            post_roll_seconds=POST_ROLL_SECONDS,
        )

        self.assertGreater(analysis.alignment.confidence, 0.9)
        self.assertIsNotNone(analysis.signal_to_noise_db)
        self.assertGreater(analysis.signal_to_noise_db or 0.0, 35.0)

    def test_flat_envelope_does_not_emit_rt60(self) -> None:
        time = np.arange(int(0.4 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        flat = 0.04 * np.sin(2.0 * math.pi * 1200.0 * time)

        decay = estimate_decay(flat, SAMPLE_RATE_HZ, window_start_seconds=1.25)

        self.assertIsNone(decay.decay_rate_per_second)
        self.assertIsNone(decay.rt60_seconds)
        self.assertIsNone(decay.fit_r2)

    def test_analytic_damped_sinusoid_recovers_peak_and_decay_rate(self) -> None:
        frequency_hz = 1375.0
        decay_rate = 4.5
        time = np.arange(int(0.9 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        samples = 0.32 * np.exp(-decay_rate * time) * np.sin(2.0 * math.pi * frequency_hz * time)

        peaks = find_dominant_peaks(
            samples,
            SAMPLE_RATE_HZ,
            min_hz=500.0,
            max_hz=2500.0,
            max_peaks=1,
            min_prominence_db=3.0,
        )
        decay = estimate_decay(samples, SAMPLE_RATE_HZ, window_start_seconds=0.0)

        self.assertGreaterEqual(len(peaks), 1)
        self.assertAlmostEqual(peaks[0].frequency_hz, frequency_hz, delta=8.0)
        self.assertIsNotNone(decay.decay_rate_per_second)
        self.assertAlmostEqual(decay.decay_rate_per_second or 0.0, decay_rate, delta=0.55)

    def test_decay_estimate_is_stable_under_moderate_noise(self) -> None:
        frequency_hz = 1240.0
        decay_rate = 4.0
        time = np.arange(int(0.85 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        clean = 0.26 * np.exp(-decay_rate * time) * np.sin(2.0 * math.pi * frequency_hz * time)

        estimates: list[float] = []
        for seed in range(5):
            noise = np.random.default_rng(seed).normal(0.0, 0.0018, size=time.size)
            decay = estimate_decay(clean + noise, SAMPLE_RATE_HZ, window_start_seconds=0.0)
            self.assertIsNotNone(decay.decay_rate_per_second)
            estimates.append(decay.decay_rate_per_second or 0.0)

        self.assertLess(max(abs(value - decay_rate) for value in estimates), 0.9)

    def test_decay_estimate_rejects_low_dynamic_range_tail(self) -> None:
        time = np.arange(int(0.8 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        barely_decaying = 0.04 * np.exp(-0.25 * time) * np.sin(2.0 * math.pi * 1000.0 * time)

        decay = estimate_decay(barely_decaying, SAMPLE_RATE_HZ, window_start_seconds=0.0)

        self.assertIsNone(decay.decay_rate_per_second)
        self.assertIsNone(decay.rt60_seconds)
        self.assertIsNone(decay.fit_r2)

    def test_parabolic_peak_interpolation_recovers_non_bin_tone(self) -> None:
        frequency_hz = 1375.37
        time = np.arange(int(0.5 * SAMPLE_RATE_HZ), dtype=np.float64) / SAMPLE_RATE_HZ
        samples = 0.25 * np.sin(2.0 * math.pi * frequency_hz * time)

        peaks = find_dominant_peaks(
            samples,
            SAMPLE_RATE_HZ,
            min_hz=900.0,
            max_hz=1800.0,
            max_peaks=1,
            min_prominence_db=12.0,
        )

        self.assertGreaterEqual(len(peaks), 1)
        self.assertAlmostEqual(peaks[0].frequency_hz, frequency_hz, delta=0.25)

    def test_q_factor_interpolates_half_power_crossings(self) -> None:
        frequencies = np.arange(990.0, 1011.0, 1.0)
        peak_index = int(np.where(frequencies == 1000.0)[0][0])
        peak = 1.0
        half_power = peak / math.sqrt(2.0)
        magnitude = np.zeros_like(frequencies)

        for index, frequency_hz in enumerate(frequencies):
            distance = abs(frequency_hz - 1000.0)
            if distance <= 3.0:
                magnitude[index] = peak - (peak - half_power) * (distance / 3.4)
            else:
                magnitude[index] = max(0.05, half_power - 0.08 * (distance - 3.4))

        q_factor = _estimate_q_factor(frequencies, magnitude, peak_index)
        right_crossing = frequencies[peak_index + 3] + (
            (half_power - magnitude[peak_index + 3])
            / (magnitude[peak_index + 4] - magnitude[peak_index + 3])
        )
        expected_bandwidth = 2.0 * (right_crossing - frequencies[peak_index])

        self.assertIsNotNone(q_factor)
        self.assertAlmostEqual(q_factor or 0.0, 1000.0 / expected_bandwidth, delta=0.5)


def _tone_amplitude(samples: np.ndarray, frequency_hz: float) -> float:
    time = np.arange(samples.size, dtype=np.float64) / SAMPLE_RATE_HZ
    basis = np.exp(-2j * math.pi * frequency_hz * time)
    return float(2.0 * abs(np.dot(samples, basis)) / samples.size)


def _finite_grid(values: list[list[float]]) -> bool:
    if not values:
        return False
    width = len(values[0])
    return all(len(row) == width and all(math.isfinite(value) for value in row) for row in values)


if __name__ == "__main__":
    unittest.main()
