from __future__ import annotations

import json
import math
import os
import re
import struct
import unittest
import wave
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from app.main import create_app
from app.services.explainer import (
    BRIGHT_CENTROID_HZ,
    DARK_CENTROID_HZ,
    DRY_RT60_SECONDS,
    LIVE_RT60_SECONDS,
)
from app.settings import get_settings
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
        get_settings.cache_clear()
        self.client = TestClient(create_app())

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_request_id_header_is_returned(self) -> None:
        response = self.client.get("/health", headers={"X-Request-ID": "trace-test-123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "trace-test-123")

    def test_probe_config_contains_default_chirp(self) -> None:
        response = self.client.get("/api/v1/probe-config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default"]["signal_type"], "log_chirp")
        self.assertEqual(payload["default"]["amplitude"], 0.35)

    def test_explainability_descriptor_thresholds_match_frontend(self) -> None:
        report_source = (
            Path(__file__).resolve().parents[3]
            / "apps"
            / "web"
            / "src"
            / "lib"
            / "report"
            / "acousticReport.ts"
        ).read_text(encoding="utf-8")
        threshold_pattern = (
            r"const\s+"
            r"(?P<name>(?:DRY|LIVE)_RT60_SECONDS|(?:DARK|BRIGHT)_CENTROID_HZ)"
            r"\s*=\s*(?P<value>[0-9.]+);"
        )
        frontend_thresholds = {
            match.group("name"): float(match.group("value"))
            for match in re.finditer(threshold_pattern, report_source)
        }

        self.assertEqual(
            frontend_thresholds,
            {
                "DRY_RT60_SECONDS": DRY_RT60_SECONDS,
                "LIVE_RT60_SECONDS": LIVE_RT60_SECONDS,
                "DARK_CENTROID_HZ": DARK_CENTROID_HZ,
                "BRIGHT_CENTROID_HZ": BRIGHT_CENTROID_HZ,
            },
        )

    def test_models_endpoint_returns_typed_phase_status(self) -> None:
        response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["active_model"])
        self.assertEqual(payload["phase"], "phase_4_room_fingerprint")

    def test_openapi_documents_analysis_and_explain_response_models(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        analyze_schema = paths["/api/v1/analyze"]["post"]["responses"]["200"]
        self.assertEqual(
            analyze_schema["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/AnalysisResponse",
        )
        explain_schema = paths["/api/v1/explain"]["post"]["responses"]["200"]
        self.assertEqual(
            explain_schema["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/LlmExplainResponse",
        )
        self.assertNotIn("/api/v1/dataset/captures", paths)

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
        self.assertEqual(payload["dsp"]["impulse_response"]["method"], "regularized_deconvolution")
        self.assertGreater(len(payload["dsp"]["impulse_response"]["magnitude_db"]), 0)
        self.assertEqual(payload["dsp"]["matched_response"]["method"], "matched_filter_envelope")
        self.assertGreater(len(payload["dsp"]["matched_response"]["magnitude_db"]), 0)
        self.assertGreater(len(payload["dsp"]["mfcc"]["coefficients"]), 0)
        self.assertIn("mode_groups", payload["dsp"])
        self.assertIn("response_caveats", payload["dsp"])
        self.assertGreater(len(payload["dsp"]["decay_bands"]), 0)

    def test_analyze_logs_analysis_id_and_quality_signals(self) -> None:
        metadata = _probe_metadata()
        with self.assertLogs("app.services.analyzer", level="INFO") as captured:
            response = self.client.post(
                "/api/v1/analyze",
                headers={"X-Request-ID": "analysis-log-test"},
                files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
                data={"metadata": json.dumps(metadata)},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        events = [json.loads(record.getMessage()) for record in captured.records]
        completed = next(event for event in events if event["event"] == "analysis_completed")
        self.assertEqual(completed["request_id"], "analysis-log-test")
        self.assertEqual(completed["analysis_id"], payload["analysis_id"])
        self.assertEqual(completed["sample_rate_hz"], 48000)
        self.assertEqual(completed["capture_path"], "audio_worklet")
        self.assertIn("alignment_confidence", completed)
        self.assertIn("warning_count", completed)

    def test_analyze_logs_upload_rejection_reason(self) -> None:
        with self.assertLogs("app.api.routes", level="WARNING") as captured:
            response = self.client.post(
                "/api/v1/analyze",
                headers={"X-Request-ID": "reject-log-test"},
                files={"audio": ("probe.mp3", b"not-wav", "audio/mpeg")},
                data={"metadata": json.dumps(_probe_metadata())},
            )

        self.assertEqual(response.status_code, 400)
        events = [json.loads(record.getMessage()) for record in captured.records]
        rejected = next(event for event in events if event["event"] == "analyze_rejected")
        self.assertEqual(rejected["request_id"], "reject-log-test")
        self.assertEqual(rejected["content_type"], "audio/mpeg")
        self.assertIn("Unsupported content type", rejected["reason"])

    def test_analyze_rejects_probe_above_wav_nyquist(self) -> None:
        metadata = _probe_metadata()
        metadata["probe_config"]["end_hz"] = 10000
        response = self.client.post(
            "/api/v1/analyze",
            files={
                "audio": (
                    "low-rate.wav",
                    make_sine_wav(sample_rate_hz=16000, duration_seconds=1.0),
                    "audio/wav",
                )
            },
            data={"metadata": json.dumps(metadata)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Nyquist", response.json()["detail"])

    def test_analyze_uses_browser_timing_for_expected_chirp_start(self) -> None:
        metadata = _probe_metadata()
        metadata["probe_config"]["pre_roll_ms"] = 0
        metadata["browser"].update(
            {
                "recording_started_at_context_seconds": 10.0,
                "chirp_started_at_context_seconds": 10.25,
                "chirp_ended_at_context_seconds": 10.75,
                "capture_ended_at_context_seconds": 11.75,
            }
        )

        response = self.client.post(
            "/api/v1/analyze",
            files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
            data={"metadata": json.dumps(metadata)},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertAlmostEqual(payload["alignment"]["expected_start_seconds"], 0.25)
        self.assertNotIn(
            "Signal-to-noise ratio could not be estimated",
            " ".join(payload["warnings"]),
        )

    def test_explain_returns_structured_summary_without_raw_audio(self) -> None:
        analysis = self._analyze_probe_payload()
        with patch.dict(os.environ, {"RESONANCELAB_LLM_ENABLED": "false"}):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["explainability_version"], 1)
        self.assertFalse(payload["raw_audio_sent"])
        self.assertEqual(payload["provider"], "vertex_gemini")
        self.assertEqual(payload["model"], "gemini-3.1-pro-preview")
        self.assertEqual(payload["region"], "global")
        explanation = payload["explanation"]
        self.assertEqual(explanation["explainability_version"], 1)
        self.assertIsNotNone(explanation["summary_claim"])
        self.assertTrue(explanation["summary_claim"]["refs_resolved"])
        self.assertEqual(
            explanation["summary_claim"]["grounding_status"],
            "deterministic_rule",
        )
        self.assertGreater(len(explanation["observations"]), 0)
        self.assertGreater(len(explanation["observation_claims"]), 0)
        self.assertTrue(explanation["observation_claims"][0]["refs_resolved"])
        self.assertEqual(
            explanation["observation_claims"][0]["grounding_status"],
            "deterministic_rule",
        )
        self.assertIn(
            "/quality/alignment_confidence",
            explanation["observation_claims"][0]["evidence_refs"],
        )
        self.assertIn(
            "/quality/alignment_confidence",
            explanation["observation_claims"][0]["authoritative_values"],
        )
        self.assertGreater(len(explanation["acoustic_hypotheses"]), 0)
        self.assertGreater(len(explanation["experiment_design"]), 0)
        self.assertGreater(len(explanation["physics_tutoring"]), 0)
        self.assertGreater(len(explanation["troubleshooting"]), 0)
        self.assertGreater(len(explanation["evidence_critique"]), 0)
        self.assertNotIn("series", json.dumps(payload["evidence"]))
        for claim in _explanation_claims(explanation):
            self.assertTrue(claim["refs_resolved"], claim)
            self.assertEqual(claim["grounding_status"], "deterministic_rule", claim)
            self.assertTrue(claim["evidence_refs"], claim)
            for value in claim["authoritative_values"].values():
                self.assertNotIsInstance(value, (dict, list), claim)

    def test_explain_troubleshoots_low_confidence_captures(self) -> None:
        analysis = self._analyze_probe_payload()
        analysis["alignment"]["confidence"] = 0.18
        analysis["dsp"]["signal_to_noise_db"] = 8.0
        analysis["dsp"]["decay"]["fit_r2"] = 0.2

        with patch.dict(os.environ, {"RESONANCELAB_LLM_ENABLED": "false"}):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        explanation = response.json()["explanation"]
        troubleshooting = " ".join(explanation["troubleshooting"])
        critique = " ".join(explanation["evidence_critique"])
        self.assertIn("Alignment is below the preferred threshold", troubleshooting)
        self.assertIn("SNR is below the preferred threshold", troubleshooting)
        self.assertIn("Weak alignment", critique)

    def test_explain_rejects_oversized_json_body_before_model_parsing(self) -> None:
        with patch.dict(os.environ, {"RESONANCELAB_MAX_EXPLAIN_BODY_BYTES": "64"}):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                json={"analysis": self._analyze_probe_payload(), "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 413)

    def test_explain_reports_empty_gemini_token_exhaustion(self) -> None:
        analysis = self._analyze_probe_payload()

        class FakeGenerateContentConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingLevel:
            HIGH = "HIGH"

        class FakeTypes:
            GenerateContentConfig = FakeGenerateContentConfig
            ThinkingConfig = FakeThinkingConfig
            ThinkingLevel = FakeThinkingLevel

        class FakeModels:
            def generate_content(self, **kwargs):
                return SimpleNamespace(
                    text="",
                    candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=128,
                        candidates_token_count=0,
                        thoughts_token_count=64,
                        total_token_count=192,
                    ),
                )

        class FakeClient:
            models = FakeModels()

        with (
            patch.dict(
                os.environ,
                {
                    "RESONANCELAB_LLM_ENABLED": "true",
                    "RESONANCELAB_LLM_MAX_OUTPUT_TOKENS": "64",
                },
            ),
            patch("app.services.explainer._vertex_client", return_value=(FakeClient(), FakeTypes)),
        ):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertIn("finish_reasons=MAX_TOKENS", detail)
        self.assertIn("max_output_tokens=64", detail)
        self.assertIn("RESONANCELAB_LLM_MAX_OUTPUT_TOKENS", detail)

    def test_explain_logs_non_json_gemini_fallback(self) -> None:
        analysis = self._analyze_probe_payload()

        class FakeGenerateContentConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingLevel:
            HIGH = "HIGH"

        class FakeTypes:
            GenerateContentConfig = FakeGenerateContentConfig
            ThinkingConfig = FakeThinkingConfig
            ThinkingLevel = FakeThinkingLevel

        class FakeModels:
            def generate_content(self, **kwargs):
                return SimpleNamespace(
                    text="Plain-language fallback summary.",
                    candidates=[SimpleNamespace(finish_reason="STOP")],
                    usage_metadata=SimpleNamespace(total_token_count=42),
                )

        class FakeClient:
            models = FakeModels()

        with (
            patch.dict(os.environ, {"RESONANCELAB_LLM_ENABLED": "true"}),
            patch("app.services.explainer._vertex_client", return_value=(FakeClient(), FakeTypes)),
            self.assertLogs("app.services.explainer", level="WARNING") as captured,
        ):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                headers={"X-Request-ID": "llm-non-json-test"},
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertNotEqual(payload["explanation"]["summary"], "Plain-language fallback summary.")
        events = [json.loads(record.getMessage()) for record in captured.records]
        non_json = next(event for event in events if event["event"] == "llm_response_non_json")
        self.assertEqual(non_json["request_id"], "llm-non-json-test")
        self.assertEqual(non_json["analysis_id"], analysis["analysis_id"])
        summary_ungrounded = next(
            event for event in events if event["event"] == "llm_summary_ungrounded"
        )
        self.assertEqual(summary_ungrounded["reason"], "missing_summary_claim")

    def test_explain_drops_ungrounded_gemini_claims(self) -> None:
        analysis = self._analyze_probe_payload()
        generate_configs: list[dict] = []

        class FakeGenerateContentConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                generate_configs.append(kwargs)

        class FakeThinkingConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingLevel:
            HIGH = "HIGH"

        class FakeTypes:
            GenerateContentConfig = FakeGenerateContentConfig
            ThinkingConfig = FakeThinkingConfig
            ThinkingLevel = FakeThinkingLevel

        class FakeModels:
            def generate_content(self, **kwargs):
                payload = {
                    "summary": "Grounded Gemini summary.",
                    "summary_claim": {
                        "text": "Grounded Gemini summary.",
                        "evidence_refs": ["/quality/snr_db"],
                    },
                    "observation_claims": [
                        {
                            "text": "Grounded SNR claim.",
                            "evidence_refs": ["/quality/snr_db"],
                        },
                        {
                            "text": "Fabricated sensor claim.",
                            "evidence_refs": ["/dsp/not_a_real_field"],
                        },
                        {
                            "text": "Overbroad probe subtree claim.",
                            "evidence_refs": ["/probe"],
                        },
                    ],
                }
                return SimpleNamespace(
                    text=json.dumps(payload),
                    candidates=[SimpleNamespace(finish_reason="STOP")],
                    usage_metadata=SimpleNamespace(total_token_count=64),
                )

        class FakeClient:
            models = FakeModels()

        with (
            patch.dict(os.environ, {"RESONANCELAB_LLM_ENABLED": "true"}),
            patch("app.services.explainer._vertex_client", return_value=(FakeClient(), FakeTypes)),
            self.assertLogs("app.services.explainer", level="WARNING") as captured,
        ):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                headers={"X-Request-ID": "llm-grounding-test"},
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        explanation = response.json()["explanation"]
        self.assertEqual(explanation["summary"], "Grounded Gemini summary.")
        self.assertTrue(explanation["summary_claim"]["refs_resolved"])
        self.assertEqual(explanation["summary_claim"]["grounding_status"], "refs_resolved")
        self.assertEqual(explanation["observations"], ["Grounded SNR claim."])
        snr_value = explanation["observation_claims"][0]["authoritative_values"][
            "/quality/snr_db"
        ]
        self.assertIsInstance(snr_value, float)
        self.assertTrue(explanation["observation_claims"][0]["refs_resolved"])
        self.assertEqual(
            explanation["observation_claims"][0]["grounding_status"],
            "refs_resolved",
        )
        self.assertNotIn("Fabricated sensor claim", json.dumps(explanation))
        self.assertNotIn("Overbroad probe subtree claim", json.dumps(explanation))
        events = [json.loads(record.getMessage()) for record in captured.records]
        ungrounded = [
            event for event in events if event["event"] == "llm_claim_ungrounded"
        ]
        self.assertTrue(
            any("/dsp/not_a_real_field" in event["evidence_refs"] for event in ungrounded)
        )
        self.assertTrue(any(event["reason"] == "container_ref:/probe" for event in ungrounded))
        self.assertTrue(
            all(event["request_id"] == "llm-grounding-test" for event in ungrounded)
        )
        self.assertEqual(generate_configs[0]["response_mime_type"], "application/json")
        self.assertNotIn("response_schema", generate_configs[0])

    def test_explain_unwraps_single_object_gemini_array(self) -> None:
        analysis = self._analyze_probe_payload()

        class FakeGenerateContentConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingConfig:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class FakeThinkingLevel:
            HIGH = "HIGH"

        class FakeTypes:
            GenerateContentConfig = FakeGenerateContentConfig
            ThinkingConfig = FakeThinkingConfig
            ThinkingLevel = FakeThinkingLevel

        class FakeModels:
            def generate_content(self, **kwargs):
                payload = {
                    "summary": "Array-wrapped Gemini summary.",
                    "summary_claim": {
                        "text": "Array-wrapped Gemini summary.",
                        "evidence_refs": ["/quality/snr_db"],
                    },
                }
                return SimpleNamespace(
                    text=json.dumps([payload]),
                    candidates=[SimpleNamespace(finish_reason="STOP")],
                    usage_metadata=SimpleNamespace(total_token_count=64),
                )

        class FakeClient:
            models = FakeModels()

        with (
            patch.dict(os.environ, {"RESONANCELAB_LLM_ENABLED": "true"}),
            patch("app.services.explainer._vertex_client", return_value=(FakeClient(), FakeTypes)),
            self.assertLogs("app.services.explainer", level="WARNING") as captured,
        ):
            get_settings.cache_clear()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/explain",
                headers={"X-Request-ID": "llm-array-test"},
                json={"analysis": analysis, "include_raw_audio": False},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        explanation = response.json()["explanation"]
        self.assertEqual(explanation["summary"], "Array-wrapped Gemini summary.")
        self.assertEqual(explanation["summary_claim"]["grounding_status"], "refs_resolved")
        events = [json.loads(record.getMessage()) for record in captured.records]
        unwrapped = next(
            event for event in events if event["event"] == "llm_response_array_unwrapped"
        )
        self.assertEqual(unwrapped["request_id"], "llm-array-test")

    def test_explain_rejects_raw_audio_flag(self) -> None:
        analysis = self._analyze_probe_payload()
        response = self.client.post(
            "/api/v1/explain",
            json={"analysis": analysis, "include_raw_audio": True},
        )

        self.assertEqual(response.status_code, 422)

    def test_decode_wav_pcm_returns_mono_samples(self) -> None:
        decoded = decode_wav_pcm(make_sine_wav(sample_rate_hz=16000, duration_seconds=0.1))
        self.assertEqual(decoded.sample_rate_hz, 16000)
        self.assertEqual(decoded.channels, 1)
        self.assertEqual(len(decoded.samples), 1600)

    def test_decode_wav_pcm_normalizes_unsigned_8bit_edges(self) -> None:
        decoded = decode_wav_pcm(make_unsigned_8bit_wav())
        self.assertEqual(decoded.samples[0], -1.0)
        self.assertEqual(decoded.samples[1], 0.0)
        self.assertAlmostEqual(decoded.samples[-1], 127.0 / 128.0)

    def _analyze_probe_payload(self) -> dict:
        response = self.client.post(
            "/api/v1/analyze",
            files={"audio": ("probe.wav", make_probe_wav(), "audio/wav")},
            data={"metadata": json.dumps(_probe_metadata())},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()


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
            "user_agent": "room-fingerprint-test-browser",
        },
        "client_recorded_at": "2026-06-19T14:00:00Z",
    }


def _explanation_claims(explanation: dict) -> list[dict]:
    claims: list[dict] = []
    summary_claim = explanation.get("summary_claim")
    if summary_claim:
        claims.append(summary_claim)
    for key, value in explanation.items():
        if key.endswith("_claims") and isinstance(value, list):
            claims.extend(claim for claim in value if isinstance(claim, dict))
    return claims


if __name__ == "__main__":
    unittest.main()
