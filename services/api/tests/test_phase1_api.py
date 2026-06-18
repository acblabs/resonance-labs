from __future__ import annotations

import json
import struct
import unittest
import wave
from io import BytesIO

from app.main import create_app
from fastapi.testclient import TestClient
from resonancelab.audio import decode_wav_pcm


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


def make_unsigned_8bit_wav() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(8000)
        writer.writeframes(bytes([0, 128, 255]))
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

    def test_analyze_returns_audio_metrics(self) -> None:
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
            files={"audio": ("probe.wav", make_sine_wav(), "audio/wav")},
            data={"metadata": json.dumps(metadata)},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["audio"]["sample_rate_hz"], 48000)
        self.assertGreater(payload["audio"]["rms"], 0.0)
        self.assertIn("dc_offset", payload["audio"])
        self.assertEqual(payload["alignment"]["method"], "phase1_placeholder")

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
