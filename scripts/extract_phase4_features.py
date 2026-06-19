from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from resonancelab.audio import decode_wav_pcm
from resonancelab.dsp import ChirpSpec, analyze_chirp_response
from resonancelab.ml.dataset import DatasetManifest, DatasetRecord, load_manifest
from resonancelab.ml.features import (
    extract_feature_vector_from_mapping,
    write_feature_vector,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract canonical Phase 4 feature JSON files from manifest records."
    )
    parser.add_argument("--manifest", required=True, help="Path to the dataset manifest.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where <record-id>.features.json files will be written.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    skipped = []
    for record in manifest.active_records():
        output_path = output_dir / f"{record.record_id}.features.json"
        if output_path.exists() and not args.overwrite:
            skipped.append({"record_id": record.record_id, "reason": "feature file exists"})
            continue

        feature_vector = _extract_record_features(manifest, record)
        write_feature_vector(output_path, feature_vector)
        written.append({"record_id": record.record_id, "path": str(output_path)})

    print(json.dumps({"written": written, "skipped": skipped}, indent=2, sort_keys=True))
    return 0


def _extract_record_features(manifest: DatasetManifest, record: DatasetRecord):
    if record.analysis_path:
        analysis_path = manifest.resolve_path(record.analysis_path)
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        return extract_feature_vector_from_mapping(payload, record_id=record.record_id)
    if record.audio_path:
        payload = _analyze_audio_record(manifest, record)
        return extract_feature_vector_from_mapping(payload, record_id=record.record_id)
    raise ValueError(f"{record.record_id}: no analysis_path or audio_path available.")


def _analyze_audio_record(manifest: DatasetManifest, record: DatasetRecord) -> dict[str, Any]:
    if not record.audio_path:
        raise ValueError(f"{record.record_id}: audio_path is missing.")
    probe = dict(record.probe or {})
    _validate_probe(record.record_id, probe)
    chirp = ChirpSpec(
        start_hz=float(probe["start_hz"]),
        end_hz=float(probe["end_hz"]),
        duration_seconds=float(probe["duration_ms"]) / 1000.0,
        amplitude=float(probe["amplitude"]),
        fade_seconds=float(probe["fade_ms"]) / 1000.0,
    )
    decoded = decode_wav_pcm(manifest.resolve_path(record.audio_path).read_bytes())
    dsp = analyze_chirp_response(
        decoded.samples,
        decoded.sample_rate_hz,
        chirp,
        pre_roll_seconds=float(probe["pre_roll_ms"]) / 1000.0,
        post_roll_seconds=float(probe["post_roll_ms"]) / 1000.0,
    )
    warnings = _analysis_warnings(dsp.signal_to_noise_db, dsp.alignment.confidence)
    return {
        "record_id": record.record_id,
        "audio": {
            "sample_rate_hz": decoded.sample_rate_hz,
            "duration_seconds": decoded.frame_count / decoded.sample_rate_hz,
        },
        "alignment": {
            "confidence": dsp.alignment.confidence,
            "estimated_latency_ms": dsp.alignment.estimated_latency_ms,
        },
        "dsp": {
            "signal_to_noise_db": dsp.signal_to_noise_db,
            "fft": {
                "centroid_hz": dsp.fft.centroid_hz,
                "bandwidth_hz": dsp.fft.bandwidth_hz,
                "rolloff_hz": dsp.fft.rolloff_hz,
                "spectral_floor_db": dsp.fft.spectral_floor_db,
            },
            "stft": {
                "kind": dsp.stft.kind,
                "times_seconds": dsp.stft.times_seconds,
                "frequency_bins_hz": dsp.stft.frequency_bins_hz,
                "magnitude_db": dsp.stft.magnitude_db,
            },
            "mel_spectrogram": {
                "kind": dsp.mel_spectrogram.kind,
                "times_seconds": dsp.mel_spectrogram.times_seconds,
                "frequency_bins_hz": dsp.mel_spectrogram.frequency_bins_hz,
                "magnitude_db": dsp.mel_spectrogram.magnitude_db,
            },
            "transfer_response": [
                {
                    "start_hz": band.start_hz,
                    "end_hz": band.end_hz,
                    "center_hz": band.center_hz,
                    "mean_db": band.mean_db,
                    "peak_db": band.peak_db,
                }
                for band in dsp.transfer_response
            ],
            "dominant_peaks": [
                {
                    "frequency_hz": peak.frequency_hz,
                    "magnitude_db": peak.magnitude_db,
                    "prominence_db": peak.prominence_db,
                    "q_factor": peak.q_factor,
                }
                for peak in dsp.dominant_peaks
            ],
            "decay": {
                "method": dsp.decay.method,
                "decay_rate_per_second": dsp.decay.decay_rate_per_second,
                "rt60_seconds": dsp.decay.rt60_seconds,
                "fit_r2": dsp.decay.fit_r2,
                "window_start_seconds": dsp.decay.window_start_seconds,
                "window_end_seconds": dsp.decay.window_end_seconds,
            },
        },
        "warnings": warnings,
    }


def _validate_probe(record_id: str, probe: dict[str, Any]) -> None:
    required = (
        "signal_type",
        "start_hz",
        "end_hz",
        "duration_ms",
        "pre_roll_ms",
        "post_roll_ms",
        "amplitude",
        "fade_ms",
    )
    missing = [name for name in required if name not in probe]
    if missing:
        raise ValueError(
            f"{record_id}: audio_path records must include exact probe fields; "
            f"missing {', '.join(missing)}."
        )
    if probe["signal_type"] != "log_chirp":
        raise ValueError(f"{record_id}: only log_chirp audio_path records are supported.")


def _analysis_warnings(signal_to_noise_db: float | None, alignment_confidence: float) -> list[str]:
    warnings: list[str] = []
    if alignment_confidence < 0.20:
        warnings.append("Chirp alignment confidence is below the Phase 4 quality threshold.")
    if signal_to_noise_db is None:
        warnings.append("Signal-to-noise ratio could not be estimated.")
    elif signal_to_noise_db < 12.0:
        warnings.append("Signal-to-noise ratio is below the 12 dB Phase 4 quality threshold.")
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
