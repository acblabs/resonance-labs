"""Structured DSP/reference explanations with optional Gemini grounding."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.schemas import LlmExplainRequest, LlmExplainResponse, LlmExplanation
from app.settings import Settings


class LlmExplanationError(RuntimeError):
    """Raised when the configured LLM provider cannot produce an explanation."""


SYSTEM_PROMPT = """You are ResonanceLab's lab assistant for active acoustic sensing.
Explain only from the supplied structured DSP and reference-comparison evidence.
Do not claim benchmarked material classification, identity, medical, legal, or safety certainty.
Do not ask for or infer from raw audio. The raw WAV is intentionally absent.
Return compact JSON with keys: summary, observations, material_hypotheses, caveats,
next_measurement.
Each list should contain short, evidence-grounded strings."""


def explain_probe_result(
    request: LlmExplainRequest,
    settings: Settings,
) -> LlmExplainResponse:
    """Return a grounded explanation from compact analysis/reference evidence."""

    evidence = build_evidence_packet(request)
    deterministic = deterministic_explanation(evidence)
    warnings = list(evidence.get("warnings", []))

    if not settings.llm_enabled:
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
                "LLM explanation is disabled; returning deterministic DSP/reference summary.",
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
    reference = (
        request.reference_comparison.model_dump(mode="json", exclude_none=True)
        if request.reference_comparison
        else None
    )
    if reference and len(reference.get("distances", [])) > 12:
        reference["distances"] = reference["distances"][:12]

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
            "transfer_bands": transfer_bands,
            "decay": {
                "decay_rate_per_second": _round_optional(
                    analysis.dsp.decay.decay_rate_per_second,
                    4,
                ),
                "rt60_seconds": _round_optional(analysis.dsp.decay.rt60_seconds, 4),
                "fit_r2": _round_optional(analysis.dsp.decay.fit_r2, 4),
            },
        },
        "calibration": (
            request.calibration.model_dump(mode="json", exclude_none=True)
            if request.calibration
            else None
        ),
        "reference_comparison": reference,
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
    calibration = evidence.get("calibration")
    reference = evidence.get("reference_comparison")
    nearest_object = reference.get("nearestObject") if reference else None
    nearest = reference.get("nearest") if reference else None
    free_air = reference.get("freeAir") if reference else None
    free_air_dominates = bool(reference.get("freeAirDominates")) if reference else False

    top_peak = _first(dsp.get("dominant_peaks", []))
    summary = (
        "The probe has enough structured DSP evidence to explain, but not to identify a "
        "material globally."
    )
    if reference and reference.get("status") == "ready":
        if free_air_dominates:
            summary = (
                "The current response is closer to the saved free-air/room reference than to "
                "saved object references."
            )
        elif nearest_object:
            summary = (
                "The current response is most similar to the saved "
                f"{nearest_object['label']} reference under this setup."
            )
        elif nearest:
            summary = (
                "The current response is closest to the saved "
                f"{nearest['label']} reference under this setup."
            )

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
    if calibration and calibration.get("status") == "ready":
        fill = calibration.get("fillPercent")
        if fill is not None:
            observations.append(
                f"Local profile-relative fill estimate is {fill:.0f}% "
                f"with {calibration.get('confidenceLabel', 'unknown')} confidence."
            )
    if reference and reference.get("status") == "ready":
        observations.append(
            "Reference comparison used "
            f"{reference.get('comparableFeatureCount', 0)} comparable DSP features."
        )
        if free_air:
            observations.append(f"Distance to free-air reference is {free_air['distance']:.2f}.")

    material_hypotheses: list[str] = []
    if free_air_dominates:
        material_hypotheses.append(
            "No strong object-response hypothesis; free-air/room path dominates."
        )
    elif nearest_object:
        material = nearest_object.get("material") or "unknown material"
        material_hypotheses.append(
            f"Same-setup similarity favors saved reference '{nearest_object['label']}' "
            f"with material label '{material}'."
        )
    elif nearest:
        material_hypotheses.append(
            f"Same-setup similarity favors saved reference '{nearest['label']}'."
        )
    else:
        material_hypotheses.append("No known-object reference is available for a material hint.")

    caveats = [
        "Similarity is not identity; this is not a benchmarked material classifier.",
        "Browser speaker, microphone, room path, and object placement can dominate the response.",
        "No raw audio was sent to the LLM path.",
    ]
    caveats.extend(_take_strings(quality.get("warnings", []), limit=3))
    if reference:
        caveats.extend(_take_strings(reference.get("warnings", []), limit=3))

    next_measurement = [
        (
            "Repeat the same probe without moving the device or object to check "
            "nearest-reference stability."
        ),
        (
            "Save or refresh a free-air reference if room position, browser, volume, or "
            "device changes."
        ),
    ]
    if free_air_dominates or not nearest_object:
        next_measurement.append(
            "Save a known-object reference in the same geometry before asking for a material hint."
        )
    if quality.get("snr_db") is not None and quality["snr_db"] < 12:
        next_measurement.append(
            "Increase repeat count or reduce room noise before trusting reference distances."
        )

    return LlmExplanation(
        summary=summary,
        observations=observations[:6],
        material_hypotheses=material_hypotheses[:4],
        caveats=caveats[:6],
        next_measurement=next_measurement[:5],
    )


def _generate_vertex_gemini_explanation(
    *,
    evidence: dict[str, Any],
    settings: Settings,
    fallback: LlmExplanation,
) -> LlmExplanation:
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
        raise LlmExplanationError(f"Gemini explanation request failed: {exc}") from exc

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise LlmExplanationError("Gemini explanation response was empty.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {
            "summary": text,
            "observations": fallback.observations,
            "material_hypotheses": fallback.material_hypotheses,
            "caveats": fallback.caveats,
            "next_measurement": fallback.next_measurement,
        }
    return _coerce_explanation(payload, fallback)


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
        "Separate measured observations from material hypotheses and caveats.\n\n"
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


def _coerce_explanation(payload: dict[str, Any], fallback: LlmExplanation) -> LlmExplanation:
    return LlmExplanation(
        summary=_string_or(payload.get("summary"), fallback.summary),
        observations=_list_or(payload.get("observations"), fallback.observations),
        material_hypotheses=_list_or(
            payload.get("material_hypotheses"),
            fallback.material_hypotheses,
        ),
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
        warnings.append("Low SNR; resonance and reference distances may be unstable.")
    reference = evidence.get("reference_comparison")
    if not reference or reference.get("status") != "ready":
        warnings.append("No ready reference comparison was supplied.")
    elif reference.get("freeAirDominates"):
        warnings.append("Free-air/room response dominates the known-object comparison.")
    return warnings


def _round_float(value: float, digits: int) -> float:
    return round(float(value), digits)


def _round_optional(value: float | None, digits: int) -> float | None:
    return None if value is None else _round_float(value, digits)


def _first(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    return values[0] if values else None


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
