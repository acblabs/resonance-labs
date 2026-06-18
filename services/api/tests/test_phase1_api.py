from __future__ import annotations

import json
import math
import struct
import unittest
import wave
from io import BytesIO

import numpy as np
from app.main import create_app
from fastapi.testclient import TestClient
from resonancelab.audio import decode_wav_pcm
from resonancelab.dsp import ChirpSpec, generate_log_chirp


def make_sine_wav(*, sample_rate_hz: int = 48000, duration_seconds: float = 0.25) -> bytes:
    frame_count = int(sample_rate_hz * duration_seconds)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate_hz)
        frames = bytearray()
        for index in range(frame_count):
            sample = int(0.25 * 32767 * (1 if index % 32 < 16 else -1))
            frames.extend(struct.pack("<h", sample))
        writer.writeframes(bytes(frames))
    return buffer.getvalue()


def make_probe_wav(*, sample_rate_hz: int = 48000) -> bytes:
    chirp = generate_log_chirp(
        ChirpSpec(
            start_hz=500.0,
            end_hz=10000.0,
            duration_seconds=0.5,
            amplitude=0.30,
            fade_seconds=0.01,
        ),
        sample_rate_hz,
    )
    total_seconds = 1.75
    samples = np.random.default_rng(7).normal(
        loc=0.0,
        scale=0.0008,
        size=int(total_seconds * sample_rate_hz),
    )
    start = int(0.25 * sample_rate_hz) + int(0.004 * sample_rate_hz)
    samples[start : start + chirp.size] += chirp

    ring_start = start + chirp.size
    time = np.arange(samples.size - ring_start, dtype=np.float64) / sample_rate_hz
    ringdown = 0.08 * np.exp(-5.0 * time) * np.sin(2.0 * math.pi * 1475.0 * time)
    samples[ring_start:] += ringdown
    return encode_float_wav(samples, sample_rate_hz)


def make_unsigned_8bit_wav() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(8000)
        writer.writeframes(bytes([0, 128, 255]))
    return buffer.getvalue()


def encode_float_wav(samples: np.ndarray, sample_rate_hz: int) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate_hz)
        clipped = np.clip(samples, -1.0, 1.0)
        pcm = (clipped * 32767.0).astype("<i2")
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()


class Phase1ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_probe_config_contains_default_chirp(self) -> None:
        response = self.client.get("/api/v1/probe-config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default"]["signal_type"], "log_chirp")
        self.assertEqual(payload["default"]["amplitude"], 0.35)

    def test_models_endpoint_returns_typed_phase_status(self) -> None:
        response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["active_model"])
        self.assertEqual(payload["phase"], "phase_3_calibration_demo")

    def test_openapi_documents_analyze_response_model(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        analyze_schema = response.json()["paths"]["/api/v1/analyze"]["post"]["responses"]["200"]
        self.assertEqual(
            analyze_schema["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/AnalysisResponse",
        )

    def test_analyze_returns_audio_and_phase2_dsp_metrics(self) -> None:
        metadata = {
            "probe_config": {
                "signal_type": "log_chirp",
                "start_hz": 500,
                "end_hz": 10000,
                "duration_ms": 500,
                "pre_roll_ms": 250,
                "post_roll_ms": 1000,
                "amplitude": 0.35,
                "fade_ms": 10,
            },
            "browser": {
                "audio_context_sample_rate_hz": 48000,
                "capture_path": "audio_worklet",
            },
        }
        response = self.client.post(
            "/api/v1/analyze",
            files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
            data={"metadata": json.dumps(metadata)},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["audio"]["sample_rate_hz"], 48000)
        self.assertGreater(payload["audio"]["rms"], 0.0)
        self.assertIn("dc_offset", payload["audio"])
        self.assertEqual(payload["alignment"]["method"], "matched_filter_log_chirp")
        self.assertGreater(payload["alignment"]["confidence"], 0.85)
        self.assertNotIn("offset_ms", payload["alignment"])
        self.assertIn("dsp", payload)
        self.assertGreater(payload["dsp"]["signal_to_noise_db"], 12.0)
        self.assertIn("spectral_floor_db", payload["dsp"]["fft"])
        self.assertNotIn("noise_floor_db", payload["dsp"]["fft"])
        self.assertGreater(len(payload["dsp"]["fft"]["series"]["frequency_bins_hz"]), 0)
        self.assertGreater(len(payload["dsp"]["stft"]["magnitude_db"]), 0)
        self.assertGreater(len(payload["dsp"]["mel_spectrogram"]["magnitude_db"]), 0)
        self.assertGreater(len(payload["dsp"]["transfer_response"]), 0)

    def test_decode_wav_pcm_returns_mono_samples(self) -> None:
        decoded = decode_wav_pcm(make_sine_wav(sample_rate_hz=16000, duration_seconds=0.1))
        self.assertEqual(decoded.sample_rate_hz, 16000)
        self.assertEqual(decoded.channels, 1)
        self.assertEqual(len(decoded.samples), 1600)

    def test_decode_wav_pcm_normalizes_unsigned_8bit_edges(self) -> None:
        decoded = decode_wav_pcm(make_unsigned_8bit_wav())
        self.assertEqual(decoded.samples[0], -1.0)
        self.assertAlmostEqual(decoded.samples[-1], 1.0)


if __name__ == "__main__":
    unittest.main()
