from __future__ import annotations

import json
import math
import os
import struct
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
from app.main import create_app
from app.schemas import DatasetCaptureLabel
from app.settings import get_settings
from fastapi.testclient import TestClient
from pydantic import ValidationError
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

    def test_dataset_capture_endpoint_is_hidden_when_disabled(self) -> None:
        response = self.client.post(
            "/api/v1/dataset/captures",
            files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
            data={
                "metadata": json.dumps(_probe_metadata()),
                "capture": json.dumps(_dataset_capture_payload()),
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_dataset_capture_writes_private_inbox_fragment_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "PHASE4_CAPTURE_ENABLED": "true",
                    "PHASE4_CAPTURE_OPERATOR_TOKEN": "secret-token",
                    "PHASE4_CAPTURE_LOCAL_DIR": directory,
                    "PHASE4_CAPTURE_INBOX_PREFIX": "phase4/inbox",
                },
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post(
                    "/api/v1/dataset/captures",
                    files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
                    data={
                        "metadata": json.dumps(_probe_metadata()),
                        "capture": json.dumps(_dataset_capture_payload()),
                    },
                    headers={"Authorization": "Bearer secret-token"},
                )
                get_settings.cache_clear()

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            record_id = payload["record_id"]
            self.assertEqual(payload["status"], "stored")
            self.assertEqual(payload["analysis"]["status"], "ok")

            root = Path(directory)
            record_path = root / payload["stored_paths"]["inbox_record_path"]
            fragment = json.loads(record_path.read_text(encoding="utf-8"))
            record = fragment["record"]

            self.assertTrue((root / payload["stored_paths"]["analysis_path"]).exists())
            self.assertTrue((root / payload["stored_paths"]["audio_path"]).exists())
            self.assertEqual(record["id"], record_id)
            self.assertEqual(record["audio_path"], f"audio/session-001/{record_id}.wav")
            self.assertEqual(
                record["analysis_path"],
                f"analysis/session-001/{record_id}.analysis.json",
            )
            self.assertEqual(
                fragment["source_paths"]["audio"],
                f"session-001/audio/{record_id}.wav",
            )
            self.assertNotIn("fill_bucket", record["label"])
            self.assertNotIn("usable", record["quality"])

    def test_dataset_capture_respects_server_raw_audio_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "PHASE4_CAPTURE_ENABLED": "true",
                    "PHASE4_CAPTURE_OPERATOR_TOKEN": "secret-token",
                    "PHASE4_CAPTURE_LOCAL_DIR": directory,
                    "PHASE4_CAPTURE_INBOX_PREFIX": "phase4/inbox",
                    "PHASE4_CAPTURE_STORE_RAW_AUDIO": "false",
                },
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post(
                    "/api/v1/dataset/captures",
                    files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
                    data={
                        "metadata": json.dumps(_probe_metadata()),
                        "capture": json.dumps(_dataset_capture_payload()),
                    },
                    headers={"Authorization": "Bearer secret-token"},
                )
                get_settings.cache_clear()

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            root = Path(directory)
            record_path = root / payload["stored_paths"]["inbox_record_path"]
            fragment = json.loads(record_path.read_text(encoding="utf-8"))
            record = fragment["record"]

            self.assertIsNone(payload["stored_paths"]["audio_path"])
            self.assertNotIn("audio_path", record)
            self.assertNotIn("audio", fragment["source_paths"])
            self.assertEqual(
                record["analysis_path"],
                f"analysis/session-001/{payload['record_id']}.analysis.json",
            )

    def test_dataset_capture_idempotency_key_stabilizes_record_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "PHASE4_CAPTURE_ENABLED": "true",
                    "PHASE4_CAPTURE_OPERATOR_TOKEN": "secret-token",
                    "PHASE4_CAPTURE_LOCAL_DIR": directory,
                    "PHASE4_CAPTURE_INBOX_PREFIX": "phase4/inbox",
                },
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                headers = {
                    "Authorization": "Bearer secret-token",
                    "Idempotency-Key": "same-audio-and-context",
                }
                response_a = client.post(
                    "/api/v1/dataset/captures",
                    files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
                    data={
                        "metadata": json.dumps(_probe_metadata()),
                        "capture": json.dumps(_dataset_capture_payload()),
                    },
                    headers=headers,
                )
                response_b = client.post(
                    "/api/v1/dataset/captures",
                    files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
                    data={
                        "metadata": json.dumps(_probe_metadata()),
                        "capture": json.dumps(_dataset_capture_payload()),
                    },
                    headers=headers,
                )
                get_settings.cache_clear()

            self.assertEqual(response_a.status_code, 200)
            self.assertEqual(response_b.status_code, 200)
            self.assertEqual(response_a.json()["record_id"], response_b.json()["record_id"])

    def test_dataset_capture_label_derives_mass_fill_and_rejects_bad_masses(self) -> None:
        label = DatasetCaptureLabel.model_validate(
            {
                "vessel_empty_mass_g": 200.0,
                "vessel_full_mass_g": 500.0,
                "vessel_current_mass_g": 350.0,
            }
        )

        self.assertEqual(label.fill_mass_g, 150.0)
        self.assertEqual(label.fill_percent, 50.0)

        with self.assertRaises(ValidationError):
            DatasetCaptureLabel.model_validate(
                {
                    "vessel_empty_mass_g": 200.0,
                    "vessel_full_mass_g": 200.0,
                    "vessel_current_mass_g": 200.0,
                }
            )

        with self.assertRaises(ValidationError):
            DatasetCaptureLabel.model_validate(
                {
                    "vessel_empty_mass_g": 200.0,
                    "vessel_full_mass_g": 500.0,
                    "vessel_current_mass_g": 550.0,
                }
            )

        with self.assertRaises(ValidationError):
            DatasetCaptureLabel.model_validate(
                {
                    "fill_percent": 50.0,
                    "fill_bucket": "50_percent",
                }
            )


def _probe_metadata() -> dict:
    return {
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
            "user_agent": "phase4-test-browser",
        },
        "client_recorded_at": "2026-06-19T14:00:00Z",
    }


def _dataset_capture_payload() -> dict:
    return {
        "label": {
            "fill_percent": 50.0,
            "fill_mass_g": 150.0,
            "vessel_empty_mass_g": 214.2,
            "vessel_full_mass_g": 514.2,
        },
        "context": {
            "session_id": "session-001",
            "glass_id": "glass-a",
            "device_id": "device-a",
            "browser_id": "chrome-test",
            "room_id": "room-a",
            "volume_setting": "system-60",
        },
        "store_audio": True,
    }


if __name__ == "__main__":
    unittest.main()
