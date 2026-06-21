"""Structured DSP explanations with optional Gemini grounding."""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any

from app.observability import log_event
from app.schemas import LlmExplainRequest, LlmExplainResponse, LlmExplanation
from app.settings import Settings

logger = logging.getLogger(__name__)


class LlmExplanationError(RuntimeError):
    """Raised when the configured LLM provider cannot produce an explanation."""


SYSTEM_PROMPT = """You are ResonanceLab's lab assistant for active acoustic sensing.
Explain only from the supplied structured DSP evidence.
Frame outputs as room acoustic fingerprints, not spatial maps or object identity claims.
Do not claim medical, legal, safety, material, or geometry certainty.
Do not ask for or infer from raw audio. The raw WAV is intentionally absent.
Return compact JSON with keys: summary, observations, acoustic_hypotheses,
experiment_design, physics_tutoring, troubleshooting, evidence_critique,
caveats, next_measurement.
Each list should contain short, evidence-grounded strings."""


def explain_probe_result(
    request: LlmExplainRequest,
    settings: Settings,
    request_id: str | None = None,
) -> LlmExplainResponse:
    """Return a grounded explanation from compact analysis evidence."""

    evidence = build_evidence_packet(request)
    deterministic = deterministic_explanation(evidence)
    warnings = list(evidence.get("warnings", []))

    if not settings.llm_enabled:
        log_event(
            logger,
            "llm_explain_completed",
            request_id=request_id,
            analysis_id=request.analysis.analysis_id,
            status="disabled",
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
        )
        return LlmExplainResponse(
            status="disabled",
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
            thinking_level=settings.llm_thinking_level,
            raw_audio_sent=False,
            explanation=deterministic,
            evidence=evidence,
            warnings=[
                "LLM explanation is disabled; returning deterministic DSP summary.",
                *warnings,
            ],
        )

    if settings.llm_provider != "vertex_gemini":
        raise LlmExplanationError(
            f"Unsupported LLM provider '{settings.llm_provider}'. Expected 'vertex_gemini'."
        )

    generated = _generate_vertex_gemini_explanation(
        evidence=evidence,
        settings=settings,
        fallback=deterministic,
        request_id=request_id,
    )
    return LlmExplainResponse(
        status="ok",
        provider="vertex_gemini",
        model=settings.llm_model,
        region=settings.llm_location,
        thinking_level=settings.llm_thinking_level,
        raw_audio_sent=False,
        explanation=generated,
        evidence=evidence,
        warnings=warnings,
    )


def build_evidence_packet(request: LlmExplainRequest) -> dict[str, Any]:
    """Compact a rich analysis response into the only evidence sent to the LLM."""

    analysis = request.analysis
    peaks = [
        {
            "frequency_hz": _round_float(peak.frequency_hz, 2),
            "magnitude_db": _round_float(peak.magnitude_db, 2),
            "prominence_db": _round_float(peak.prominence_db, 2),
            "q_factor": _round_optional(peak.q_factor, 2),
        }
        for peak in analysis.dsp.dominant_peaks[:5]
    ]
    transfer_bands = [
        {
            "start_hz": _round_float(band.start_hz, 1),
            "end_hz": _round_float(band.end_hz, 1),
            "mean_db": _round_float(band.mean_db, 2),
            "peak_db": _round_float(band.peak_db, 2),
        }
        for band in analysis.dsp.transfer_response[:8]
    ]
    decay_bands = [
        {
            "label": band.label,
            "start_hz": _round_float(band.start_hz, 1),
            "end_hz": _round_float(band.end_hz, 1),
            "rt60_seconds": _round_optional(band.rt60_seconds, 4),
            "fit_r2": _round_optional(band.fit_r2, 4),
        }
        for band in analysis.dsp.decay_bands[:3]
    ]
    mfcc = [
        {
            "index": coefficient.index,
            "mean": _round_float(coefficient.mean, 4),
            "std": _round_float(coefficient.std, 4),
            "minimum": _round_float(coefficient.minimum, 4),
            "maximum": _round_float(coefficient.maximum, 4),
        }
        for coefficient in analysis.dsp.mfcc.coefficients[:8]
    ]
    mode_groups = [
        {
            "start_hz": _round_float(group.start_hz, 1),
            "end_hz": _round_float(group.end_hz, 1),
            "center_hz": _round_float(group.center_hz, 2),
            "peak_count": group.peak_count,
            "dominant_frequency_hz": _round_float(group.dominant_frequency_hz, 2),
            "max_prominence_db": _round_float(group.max_prominence_db, 2),
            "q_factor": _round_optional(group.q_factor, 2),
            "warning_labels": group.warning_labels,
        }
        for group in analysis.dsp.mode_groups[:5]
    ]
    response_caveats = [
        {
            "id": caveat.id,
            "severity": caveat.severity,
            "message": caveat.message,
        }
        for caveat in analysis.dsp.response_caveats[:8]
    ]
    evidence: dict[str, Any] = {
        "analysis_id": str(analysis.analysis_id),
        "audio": {
            "sample_rate_hz": analysis.audio.sample_rate_hz,
            "duration_seconds": _round_float(analysis.audio.duration_seconds, 4),
            "rms": _round_float(analysis.audio.rms, 6),
            "peak_amplitude": _round_float(analysis.audio.peak_amplitude, 6),
            "capture_path": analysis.probe.browser.capture_path,
        },
        "probe": analysis.probe.probe_config.model_dump(mode="json"),
        "quality": {
            "alignment_confidence": _round_float(analysis.alignment.confidence, 4),
            "detected_start_seconds": _round_optional(
                analysis.alignment.detected_start_seconds,
                4,
            ),
            "snr_db": _round_optional(analysis.dsp.signal_to_noise_db, 2),
            "warnings": analysis.warnings,
        },
        "dsp": {
            "bandpass_low_hz": _round_float(analysis.dsp.bandpass_low_hz, 1),
            "bandpass_high_hz": _round_float(analysis.dsp.bandpass_high_hz, 1),
            "spectral_centroid_hz": _round_optional(analysis.dsp.fft.centroid_hz, 2),
            "spectral_bandwidth_hz": _round_optional(analysis.dsp.fft.bandwidth_hz, 2),
            "spectral_rolloff_hz": _round_optional(analysis.dsp.fft.rolloff_hz, 2),
            "spectral_floor_db": _round_optional(analysis.dsp.fft.spectral_floor_db, 2),
            "dominant_peaks": peaks,
            "mode_groups": mode_groups,
            "transfer_bands": transfer_bands,
            "response_traces": {
                "matched_filter": {
                    "peak_time_seconds": _round_optional(
                        analysis.dsp.matched_response.peak_time_seconds,
                        5,
                    ),
                    "direct_to_late_db": _round_optional(
                        analysis.dsp.matched_response.direct_to_late_db,
                        2,
                    ),
                    "points": len(analysis.dsp.matched_response.times_seconds),
                },
                "regularized_deconvolution": {
                    "peak_time_seconds": _round_optional(
                        analysis.dsp.impulse_response.peak_time_seconds,
                        5,
                    ),
                    "direct_to_late_db": _round_optional(
                        analysis.dsp.impulse_response.direct_to_late_db,
                        2,
                    ),
                    "regularization": _round_float(
                        analysis.dsp.impulse_response.regularization,
                        8,
                    ),
                    "points": len(analysis.dsp.impulse_response.times_seconds),
                },
            },
            "decay": {
                "decay_rate_per_second": _round_optional(
                    analysis.dsp.decay.decay_rate_per_second,
                    4,
                ),
                "rt60_seconds": _round_optional(analysis.dsp.decay.rt60_seconds, 4),
                "fit_r2": _round_optional(analysis.dsp.decay.fit_r2, 4),
            },
            "decay_bands": decay_bands,
            "mfcc": {
                "method": analysis.dsp.mfcc.method,
                "coefficients": mfcc,
            },
            "response_caveats": response_caveats,
        },
        "operator_question": request.operator_question,
        "raw_audio_present": False,
        "warnings": [],
    }
    evidence["warnings"] = _evidence_warnings(evidence)
    return evidence


def deterministic_explanation(evidence: dict[str, Any]) -> LlmExplanation:
    """Produce a useful local explanation even when the LLM is disabled."""

    quality = evidence["quality"]
    dsp = evidence["dsp"]

    top_peak = _first(dsp.get("dominant_peaks", []))
    rt60 = dsp["decay"].get("rt60_seconds")
    centroid = dsp.get("spectral_centroid_hz")
    summary = "This chirp produced a structured acoustic fingerprint of the capture space."
    if rt60 is not None:
        if rt60 < 0.25:
            summary = "This capture has a short decay tail, suggesting a relatively dry space."
        elif rt60 > 0.75:
            summary = "This capture has a longer decay tail, suggesting a livelier echo response."
    if centroid is not None and centroid > 3000:
        summary += " The spectrum is weighted toward brighter high-frequency energy."

    observations = [
        (
            "Alignment confidence is "
            f"{quality['alignment_confidence']:.3f}; SNR is "
            f"{_format_optional(quality.get('snr_db'), ' dB')}."
        ),
        (
            "Spectral centroid is "
            f"{_format_optional(dsp.get('spectral_centroid_hz'), ' Hz')} and rolloff is "
            f"{_format_optional(dsp.get('spectral_rolloff_hz'), ' Hz')}."
        ),
    ]
    if top_peak:
        observations.append(
            "Dominant peak is "
            f"{top_peak['frequency_hz']:.1f} Hz with "
            f"{top_peak['prominence_db']:.1f} dB prominence."
        )
    decay_bands = [
        band
        for band in dsp.get("decay_bands", [])
        if band.get("rt60_seconds") is not None
    ]
    if decay_bands:
        band_summary = ", ".join(
            f"{band['label']} {band['rt60_seconds']:.2f}s" for band in decay_bands[:3]
        )
        observations.append(f"Band-limited RT60 proxies are {band_summary}.")
    response_balance = _response_balance_observation(dsp.get("response_traces", {}))
    if response_balance:
        observations.append(response_balance)
    mode_groups = dsp.get("mode_groups", [])
    if mode_groups:
        strongest = mode_groups[0]
        labels = ", ".join(strongest.get("warning_labels", [])) or "stable"
        observations.append(
            "Low-frequency grouping centers near "
            f"{strongest['center_hz']:.1f} Hz with labels: {labels}."
        )
    mfcc_coefficients = dsp.get("mfcc", {}).get("coefficients", [])
    if mfcc_coefficients:
        compact_mfcc = ", ".join(
            f"C{item['index']} {item['mean']:.2f}" for item in mfcc_coefficients[:4]
        )
        observations.append(f"MFCC mean summary begins {compact_mfcc}.")

    acoustic_hypotheses: list[str] = []
    if rt60 is None:
        acoustic_hypotheses.append("Decay tail was not stable enough for an RT60 proxy.")
    elif rt60 < 0.25:
        acoustic_hypotheses.append("Short decay suggests a dry or strongly damped capture space.")
    elif rt60 > 0.75:
        acoustic_hypotheses.append(
            "Longer decay suggests a reflective or echo-prone capture space."
        )
    else:
        acoustic_hypotheses.append("Mid-length decay suggests a moderately live capture space.")
    if top_peak:
        acoustic_hypotheses.append(
            f"The strongest modal feature is near {top_peak['frequency_hz']:.1f} Hz."
        )
    if len(decay_bands) >= 2:
        slowest = max(decay_bands, key=lambda band: band["rt60_seconds"])
        acoustic_hypotheses.append(
            f"The {slowest['label']} band has the slowest visible decay in this capture."
        )

    caveats = [
        "This is an acoustic fingerprint, not a spatial reconstruction of room geometry.",
        "Browser speaker, microphone, device placement, and gain processing affect the response.",
        "No raw audio was sent to the LLM path.",
    ]
    caveats.extend(
        str(caveat["message"])
        for caveat in dsp.get("response_caveats", [])
        if str(caveat.get("message", "")).strip()
    )
    caveats.extend(_take_strings(quality.get("warnings", []), limit=3))

    next_measurement = [
        (
            "Repeat the same probe without moving the device to check fingerprint stability."
        ),
        "Keep the same device position and chirp settings when checking whether caveats clear.",
    ]
    if quality.get("snr_db") is not None and quality["snr_db"] < 12:
        next_measurement.append(
            "Reduce room noise or increase playback volume slightly before trusting descriptors."
        )

    return LlmExplanation(
        summary=summary,
        observations=observations[:6],
        acoustic_hypotheses=acoustic_hypotheses[:4],
        experiment_design=_experiment_design_guidance(evidence)[:6],
        physics_tutoring=_physics_tutoring(evidence)[:6],
        troubleshooting=_troubleshooting_guidance(evidence)[:6],
        evidence_critique=_evidence_critique(evidence)[:6],
        caveats=caveats[:6],
        next_measurement=next_measurement[:5],
    )


def _experiment_design_guidance(evidence: dict[str, Any]) -> list[str]:
    quality = evidence["quality"]
    probe = evidence["probe"]
    dsp = evidence["dsp"]

    guidance = [
        (
            "Collect at least three repeats without moving the device, then compare "
            "alignment, SNR, RT60 proxy, transfer bands, and dominant peaks."
        ),
        (
            "For before/after tests, change only one factor at a time: device position, "
            "playback volume, acoustic treatment, door state, or furnishing state."
        ),
        (
            "Keep the chirp fixed at "
            f"{probe['start_hz']}-{probe['end_hz']} Hz for "
            f"{probe['duration_ms']} ms when comparing reports."
        ),
    ]
    if quality.get("snr_db") is not None and quality["snr_db"] < 18:
        guidance.append(
            "Run a quieter-room or slightly louder-speaker repeat before using this "
            "capture as the baseline."
        )
    if dsp.get("mode_groups"):
        guidance.append(
            "If modal peaks matter, repeat after moving the device a small distance to "
            "check whether the same peak group persists."
        )
    decay_fit = dsp.get("decay", {}).get("fit_r2")
    if decay_fit is not None and decay_fit < 0.55:
        guidance.append(
            "Extend post-roll or reduce noise in a follow-up run before relying on "
            "decay comparisons."
        )
    return guidance


def _physics_tutoring(evidence: dict[str, Any]) -> list[str]:
    dsp = evidence["dsp"]
    top_peak = _first(dsp.get("dominant_peaks", []))
    rt60 = dsp.get("decay", {}).get("rt60_seconds")

    tutoring = [
        (
            "A logarithmic chirp sweeps low to high frequencies so the matched filter "
            "can align the received sweep and expose early energy plus ring-down."
        ),
        (
            "The FFT summary describes frequency coloration: centroid tracks the "
            "spectral center of mass and rolloff marks where most energy has accumulated."
        ),
    ]
    if top_peak:
        q_factor = top_peak.get("q_factor")
        q_text = "unknown Q" if q_factor is None else f"Q {q_factor:.1f}"
        tutoring.append(
            "A room-mode candidate is a prominent narrow spectral feature; this run's "
            f"strongest peak is near {top_peak['frequency_hz']:.1f} Hz with {q_text}."
        )
    if rt60 is not None:
        tutoring.append(
            "The RT60 proxy estimates how long the envelope would take to decay by "
            f"60 dB if the fitted decay trend continued; this run reports {rt60:.2f}s."
        )
    slowest = _slowest_decay_band(dsp.get("decay_bands", []))
    if slowest:
        tutoring.append(
            "Damping is frequency-dependent here: the "
            f"{slowest['label']} band has the slowest measured decay proxy."
        )
    return tutoring


def _troubleshooting_guidance(evidence: dict[str, Any]) -> list[str]:
    quality = evidence["quality"]
    dsp = evidence["dsp"]
    audio = evidence["audio"]
    troubleshooting: list[str] = []

    alignment = quality["alignment_confidence"]
    if alignment < 0.5:
        troubleshooting.append(
            "Alignment is below the preferred threshold; keep the device still, avoid "
            "external sound, and verify the chirp is audible from the speaker."
        )
    snr = quality.get("snr_db")
    if snr is None:
        troubleshooting.append(
            "SNR was not available; leave clean pre-roll silence before the chirp and "
            "avoid talking or moving near the microphone."
        )
    elif snr < 18:
        troubleshooting.append(
            "SNR is below the preferred threshold; reduce background noise or raise "
            "speaker volume while staying below clipping."
        )
    if audio.get("capture_path") != "audio_worklet":
        troubleshooting.append(
            "Capture did not use AudioWorklet; repeat in a browser/origin where the "
            "worklet recorder loads for more predictable timing."
        )
    decay = dsp.get("decay", {})
    if decay.get("rt60_seconds") is None or (
        decay.get("fit_r2") is not None and decay["fit_r2"] < 0.55
    ):
        troubleshooting.append(
            "Decay confidence is weak; use a longer post-roll, quieter room, or repeat "
            "without moving the device."
        )
    for caveat in dsp.get("response_caveats", []):
        if caveat.get("severity") in {"review", "warning"}:
            troubleshooting.append(str(caveat["message"]))
    if not troubleshooting:
        troubleshooting.append(
            "No low-confidence blocker is visible; prioritize repeat stability before "
            "making before/after claims."
        )
    return troubleshooting


def _evidence_critique(evidence: dict[str, Any]) -> list[str]:
    quality = evidence["quality"]
    dsp = evidence["dsp"]

    critique = [
        (
            "The evidence supports relative room-fingerprint comparisons, not room "
            "geometry, object identity, material certainty, or medical/safety claims."
        ),
        (
            "A single run cannot prove repeatability; confidence improves when repeated "
            "captures preserve the same alignment, SNR, transfer bands, and peak groups."
        ),
    ]
    if quality["alignment_confidence"] < 0.5:
        critique.append(
            "Weak alignment makes timing, transfer, and decay interpretations more fragile."
        )
    if quality.get("snr_db") is not None and quality["snr_db"] < 18:
        critique.append(
            "The noise floor is high enough that weaker peaks or decay tails may be unstable."
        )
    if _any_very_high_q(dsp.get("dominant_peaks", [])):
        critique.append(
            "Very high Q values can indicate device or tonal artifacts as well as room "
            "resonance, so treat them as candidates."
        )
    if not dsp.get("mode_groups"):
        critique.append(
            "No low-mode grouping was retained, so modal interpretation should stay broad."
        )
    return critique


def _generate_vertex_gemini_explanation(
    *,
    evidence: dict[str, Any],
    settings: Settings,
    fallback: LlmExplanation,
    request_id: str | None,
) -> LlmExplanation:
    started = time.perf_counter()
    try:
        client, types = _vertex_client(settings.llm_project_id, settings.llm_location)
        response = client.models.generate_content(
            model=settings.llm_model,
            contents=_prompt_from_evidence(evidence),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level=_thinking_level(types, settings.llm_thinking_level),
                ),
            ),
        )
    except Exception as exc:  # pragma: no cover - exercised only with live Vertex credentials.
        log_event(
            logger,
            "llm_request_failed",
            level=logging.ERROR,
            request_id=request_id,
            analysis_id=evidence.get("analysis_id"),
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
            duration_ms=_duration_ms(started),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise LlmExplanationError(f"Gemini explanation request failed: {exc}") from exc

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        finish_reasons = _candidate_finish_reasons(response)
        log_event(
            logger,
            "llm_response_empty",
            level=logging.WARNING,
            request_id=request_id,
            analysis_id=evidence.get("analysis_id"),
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
            duration_ms=_duration_ms(started),
            finish_reasons=finish_reasons,
            usage=_usage_summary(response),
        )
        raise LlmExplanationError(_empty_gemini_response_message(response, settings))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log_event(
            logger,
            "llm_response_non_json",
            level=logging.WARNING,
            request_id=request_id,
            analysis_id=evidence.get("analysis_id"),
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
            duration_ms=_duration_ms(started),
            finish_reasons=_candidate_finish_reasons(response),
            usage=_usage_summary(response),
            response_preview=text[:160],
        )
        payload = {
            "summary": text,
            "observations": fallback.observations,
            "acoustic_hypotheses": fallback.acoustic_hypotheses,
            "experiment_design": fallback.experiment_design,
            "physics_tutoring": fallback.physics_tutoring,
            "troubleshooting": fallback.troubleshooting,
            "evidence_critique": fallback.evidence_critique,
            "caveats": fallback.caveats,
            "next_measurement": fallback.next_measurement,
        }
        generated = _coerce_explanation(payload, fallback)
        log_event(
            logger,
            "llm_explain_completed",
            request_id=request_id,
            analysis_id=evidence.get("analysis_id"),
            status="ok_non_json_fallback",
            provider="vertex_gemini",
            model=settings.llm_model,
            region=settings.llm_location,
            duration_ms=_duration_ms(started),
            usage=_usage_summary(response),
        )
        return generated

    generated = _coerce_explanation(payload, fallback)
    log_event(
        logger,
        "llm_explain_completed",
        request_id=request_id,
        analysis_id=evidence.get("analysis_id"),
        status="ok",
        provider="vertex_gemini",
        model=settings.llm_model,
        region=settings.llm_location,
        duration_ms=_duration_ms(started),
        finish_reasons=_candidate_finish_reasons(response),
        usage=_usage_summary(response),
    )
    return generated


@lru_cache(maxsize=4)
def _vertex_client(project_id: str | None, location: str):
    from google import genai
    from google.genai import types

    return (
        genai.Client(
            enterprise=True,
            project=project_id,
            location=location,
            http_options=types.HttpOptions(api_version="v1"),
        ),
        types,
    )


def _prompt_from_evidence(evidence: dict[str, Any]) -> str:
    return (
        "Explain this ResonanceLab probe result from structured evidence only. "
        "Separate measured observations, acoustic hypotheses, experiment design, "
        "physics tutoring, troubleshooting, evidence critique, and caveats.\n\n"
        f"{json.dumps(evidence, sort_keys=True, separators=(',', ':'))}"
    )


def _thinking_level(types: Any, configured: str) -> Any:
    normalized = configured.upper()
    if normalized not in {"LOW", "MEDIUM", "HIGH", "MINIMAL"}:
        normalized = "HIGH"
    enum = getattr(types, "ThinkingLevel", None)
    if enum is None:
        return normalized
    return getattr(enum, normalized, normalized)


def _empty_gemini_response_message(response: Any, settings: Settings) -> str:
    details = [
        "Gemini explanation response was empty",
        f"model={settings.llm_model}",
        f"thinking_level={settings.llm_thinking_level}",
        f"max_output_tokens={settings.llm_max_output_tokens}",
    ]
    finish_reasons = _candidate_finish_reasons(response)
    if finish_reasons:
        details.append(f"finish_reasons={','.join(finish_reasons)}")
    usage_summary = _usage_summary(response)
    if usage_summary:
        details.append(f"usage={usage_summary}")
    if "MAX_TOKENS" in finish_reasons:
        details.append(
            "increase RESONANCELAB_LLM_MAX_OUTPUT_TOKENS or lower "
            "RESONANCELAB_LLM_THINKING_LEVEL"
        )
    return "; ".join(details) + "."


def _candidate_finish_reasons(response: Any) -> list[str]:
    reasons: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is None:
            continue
        name = getattr(reason, "name", None) or str(reason)
        reasons.append(name.rsplit(".", 1)[-1])
    return reasons


def _usage_summary(response: Any) -> str | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None

    parts: list[str] = []
    for key in (
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "total_token_count",
    ):
        value = getattr(usage, key, None)
        if value is not None:
            parts.append(f"{key}={value}")
    return ",".join(parts) or None


def _duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _coerce_explanation(payload: dict[str, Any], fallback: LlmExplanation) -> LlmExplanation:
    return LlmExplanation(
        summary=_string_or(payload.get("summary"), fallback.summary),
        observations=_list_or(payload.get("observations"), fallback.observations),
        acoustic_hypotheses=_list_or(
            payload.get("acoustic_hypotheses"),
            fallback.acoustic_hypotheses,
        ),
        experiment_design=_list_or(payload.get("experiment_design"), fallback.experiment_design),
        physics_tutoring=_list_or(payload.get("physics_tutoring"), fallback.physics_tutoring),
        troubleshooting=_list_or(payload.get("troubleshooting"), fallback.troubleshooting),
        evidence_critique=_list_or(payload.get("evidence_critique"), fallback.evidence_critique),
        caveats=_list_or(payload.get("caveats"), fallback.caveats),
        next_measurement=_list_or(payload.get("next_measurement"), fallback.next_measurement),
    )


def _evidence_warnings(evidence: dict[str, Any]) -> list[str]:
    warnings = ["Raw audio is not included in the LLM evidence packet."]
    quality = evidence["quality"]
    if quality["alignment_confidence"] < 0.35:
        warnings.append("Low chirp alignment confidence; explanation should be treated as weak.")
    snr = quality.get("snr_db")
    if snr is not None and snr < 12:
        warnings.append("Low SNR; acoustic descriptors may be unstable.")
    return warnings


def _response_balance_observation(response_traces: Any) -> str | None:
    if not isinstance(response_traces, dict):
        return None
    matched = response_traces.get("matched_filter")
    deconvolved = response_traces.get("regularized_deconvolution")
    parts: list[str] = []
    if isinstance(matched, dict):
        parts.append(
            "matched direct/late "
            f"{_format_optional(matched.get('direct_to_late_db'), ' dB')}"
        )
    if isinstance(deconvolved, dict):
        parts.append(
            "deconvolved direct/late "
            f"{_format_optional(deconvolved.get('direct_to_late_db'), ' dB')}"
        )
    if not parts:
        return None
    return "Response balance shows " + "; ".join(parts) + "."


def _round_float(value: float, digits: int) -> float:
    return round(float(value), digits)


def _round_optional(value: float | None, digits: int) -> float | None:
    return None if value is None else _round_float(value, digits)


def _first(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    return values[0] if values else None


def _slowest_decay_band(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    decay_bands = [
        band
        for band in values
        if band.get("rt60_seconds") is not None
    ]
    if not decay_bands:
        return None
    return max(decay_bands, key=lambda band: band["rt60_seconds"])


def _any_very_high_q(values: list[dict[str, Any]]) -> bool:
    return any(
        peak.get("q_factor") is not None and peak["q_factor"] > 300
        for peak in values
    )


def _format_optional(value: float | None, suffix: str) -> str:
    if value is None:
        return "not available"
    if suffix == " Hz":
        return f"{value:.1f}{suffix}"
    if suffix == " dB":
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _take_strings(values: list[Any], *, limit: int) -> list[str]:
    return [str(value) for value in values[:limit] if str(value).strip()]


def _string_or(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _list_or(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    strings = [str(item).strip() for item in value if str(item).strip()]
    return strings[:8] if strings else fallback
