"""Canonical Phase 4 feature extraction from Phase 2 DSP analysis payloads."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from resonancelab import __version__

FEATURE_FORMAT = "resonancelab.phase4.features"
FEATURE_FORMAT_VERSION = 1
FEATURE_SCHEMA_VERSION = 2
MAX_PEAK_FEATURES = 5
MEL_SUMMARY_BANDS = 20
DB_FEATURE_ABS_LIMIT = 180.0
EPSILON = 1e-12


@dataclass(frozen=True)
class ModelFeature:
    """A single named scalar used by the Phase 4 baseline model."""

    name: str
    value: float
    unit: str
    source: str


@dataclass(frozen=True)
class FeatureVector:
    """Stable scalar feature bundle extracted from one analyzed probe."""

    schema_version: int
    features: tuple[ModelFeature, ...]
    record_id: str | None = None
    quality: Mapping[str, float | int | str | None] | None = None
    summary: Mapping[str, float | int | str | None] | None = None

    def as_mapping(self) -> dict[str, float]:
        """Return feature values keyed by stable feature name."""

        return {feature.name: feature.value for feature in self.features}

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize to the feature file format consumed by baseline training."""

        return {
            "format": FEATURE_FORMAT,
            "format_version": FEATURE_FORMAT_VERSION,
            "record_id": self.record_id,
            "schema_version": self.schema_version,
            "extractor": {
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "package_version": __version__,
                "numpy_version": np.__version__,
            },
            "features": [
                {
                    "name": feature.name,
                    "value": feature.value,
                    "unit": feature.unit,
                    "source": feature.source,
                }
                for feature in self.features
            ],
            "quality": dict(self.quality or {}),
            "summary": dict(self.summary or {}),
        }


def extract_feature_vector_from_mapping(
    payload: Mapping[str, Any],
    *,
    record_id: str | None = None,
) -> FeatureVector:
    """Extract tabular ML features from an API analysis response or DSP-only mapping."""

    dsp = _mapping(payload.get("dsp")) if isinstance(payload.get("dsp"), Mapping) else payload
    alignment = _mapping(payload.get("alignment"))
    audio = _mapping(payload.get("audio"))
    features: list[ModelFeature] = []

    _add_log2(features, "spectral_centroid_log_hz", _get(dsp, "fft.centroid_hz"), "fft")
    _add_log2(features, "spectral_bandwidth_log_hz", _get(dsp, "fft.bandwidth_hz"), "fft")
    _add_log2(features, "spectral_rolloff_log_hz", _get(dsp, "fft.rolloff_hz"), "fft")
    _add_feature(features, "spectral_floor_db", _get(dsp, "fft.spectral_floor_db"), "db", "fft")

    _add_log2(
        features,
        "decay_rate_log2_per_second",
        _get(dsp, "decay.decay_rate_per_second"),
        "decay",
    )
    _add_log2(features, "rt60_log2_seconds", _get(dsp, "decay.rt60_seconds"), "decay")

    peaks = _sequence(_get(dsp, "dominant_peaks"))[:MAX_PEAK_FEATURES]
    for index, peak in enumerate(peaks, start=1):
        peak_mapping = _mapping(peak)
        _add_log2(
            features,
            f"peak_{index}_log_hz",
            peak_mapping.get("frequency_hz"),
            f"dominant_peaks[{index - 1}]",
        )
        _add_feature(
            features,
            f"peak_{index}_magnitude_db",
            peak_mapping.get("magnitude_db"),
            "db",
            f"dominant_peaks[{index - 1}]",
        )
        _add_feature(
            features,
            f"peak_{index}_prominence_db",
            peak_mapping.get("prominence_db"),
            "db",
            f"dominant_peaks[{index - 1}]",
        )
        _add_log2(
            features,
            f"peak_{index}_log_q",
            peak_mapping.get("q_factor"),
            f"dominant_peaks[{index - 1}]",
        )

    for band in _sequence(_get(dsp, "transfer_response")):
        band_mapping = _mapping(band)
        center = _finite_float(band_mapping.get("center_hz"))
        if center is None:
            continue
        suffix = f"{int(round(center))}hz"
        source = f"transfer_response.{suffix}"
        _add_feature(
            features,
            f"transfer_{suffix}_mean_db",
            band_mapping.get("mean_db"),
            "db",
            source,
        )
        _add_feature(
            features,
            f"transfer_{suffix}_peak_db",
            band_mapping.get("peak_db"),
            "db",
            source,
        )

    _add_mel_spectrogram_summaries(features, _mapping(_get(dsp, "mel_spectrogram")))

    quality = _quality_summary(payload=payload, dsp=dsp, alignment=alignment, audio=audio)
    summary = {
        "primary_peak_hz": _finite_float(_get(dsp, "dominant_peaks.0.frequency_hz")),
        "spectral_centroid_hz": _finite_float(_get(dsp, "fft.centroid_hz")),
        "spectral_rolloff_hz": _finite_float(_get(dsp, "fft.rolloff_hz")),
        "decay_rate_per_second": _finite_float(_get(dsp, "decay.decay_rate_per_second")),
        "rt60_seconds": _finite_float(_get(dsp, "decay.rt60_seconds")),
        "decay_fit_r2": _finite_float(_get(dsp, "decay.fit_r2")),
        "transfer_band_count": len(_sequence(_get(dsp, "transfer_response"))),
        "feature_count": len(features),
    }

    return FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        record_id=record_id or _string_or_none(payload.get("record_id")),
        features=tuple(sorted(features, key=lambda feature: feature.name)),
        quality=quality,
        summary=summary,
    )


def load_feature_vector(path: str | Path) -> FeatureVector:
    """Load a Phase 4 feature vector file."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") == FEATURE_FORMAT:
        features = tuple(_load_feature(feature) for feature in _sequence(payload.get("features")))
        return FeatureVector(
            schema_version=int(payload.get("schema_version", FEATURE_SCHEMA_VERSION)),
            record_id=_string_or_none(payload.get("record_id")),
            features=tuple(sorted(features, key=lambda feature: feature.name)),
            quality=_mapping(payload.get("quality")),
            summary=_mapping(payload.get("summary")),
        )

    if isinstance(payload.get("features"), Mapping):
        features = tuple(
            ModelFeature(name=str(name), value=value, unit="unknown", source="legacy_feature_map")
            for name, value in _finite_items(_mapping(payload.get("features")))
        )
        return FeatureVector(
            schema_version=int(payload.get("schema_version", FEATURE_SCHEMA_VERSION)),
            record_id=_string_or_none(payload.get("record_id")),
            features=tuple(sorted(features, key=lambda feature: feature.name)),
            quality=_mapping(payload.get("quality")),
            summary=_mapping(payload.get("summary")),
        )

    return extract_feature_vector_from_mapping(payload)


def write_feature_vector(path: str | Path, feature_vector: FeatureVector) -> None:
    """Write a feature vector with deterministic JSON formatting."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(feature_vector.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def feature_matrix(
    rows: Iterable[Mapping[str, float]],
    *,
    feature_names: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Build a dense matrix with NaN placeholders for missing feature values."""

    row_list = [dict(row) for row in rows]
    if feature_names is None:
        feature_names = sorted({name for row in row_list for name in row})
    names = list(feature_names)
    matrix = np.full((len(row_list), len(names)), np.nan, dtype=np.float64)
    for row_index, row in enumerate(row_list):
        for column_index, name in enumerate(names):
            value = _finite_float(row.get(name))
            if value is not None:
                matrix[row_index, column_index] = value
    return matrix, names


def _load_feature(payload: Any) -> ModelFeature:
    mapping = _mapping(payload)
    name = _string_or_none(mapping.get("name"))
    value = _finite_float(mapping.get("value"))
    if name is None or value is None:
        raise ValueError("feature entries must contain finite 'name' and 'value' fields.")
    return ModelFeature(
        name=name,
        value=value,
        unit=_string_or_none(mapping.get("unit")) or "unknown",
        source=_string_or_none(mapping.get("source")) or "feature_file",
    )


def _add_mel_spectrogram_summaries(features: list[ModelFeature], grid: Mapping[str, Any]) -> None:
    values = _finite_array(grid.get("magnitude_db"))
    if values.size == 0 or values.ndim != 2 or not np.isfinite(values).any():
        return
    values = _fill_nan(values)
    values = _resample_frequency_rows(values, MEL_SUMMARY_BANDS)
    band_means = np.nanmean(values, axis=1)
    band_stds = np.nanstd(values, axis=1)
    first_half = values[:, : max(1, values.shape[1] // 2)]
    second_half = values[:, values.shape[1] // 2 :]
    temporal_delta = (
        np.nanmean(second_half, axis=1) - np.nanmean(first_half, axis=1)
        if second_half.size
        else np.zeros(values.shape[0], dtype=np.float64)
    )

    _add_feature(features, "mel_global_mean_db", float(np.nanmean(values)), "db", "mel")
    _add_feature(features, "mel_global_std_db", float(np.nanstd(values)), "db", "mel")
    _add_feature(
        features,
        "mel_temporal_delta_db",
        float(np.mean(temporal_delta)),
        "db",
        "mel",
    )
    _add_feature(
        features,
        "mel_spectral_contrast_db",
        float(np.nanpercentile(values, 90.0) - np.nanpercentile(values, 10.0)),
        "db",
        "mel",
    )

    for index, (mean_db, std_db, delta_db) in enumerate(
        zip(band_means, band_stds, temporal_delta, strict=False),
        start=1,
    ):
        _add_feature(features, f"mel_band_{index:02d}_mean_db", mean_db, "db", "mel")
        _add_feature(features, f"mel_band_{index:02d}_std_db", std_db, "db", "mel")
        _add_feature(features, f"mel_band_{index:02d}_delta_db", delta_db, "db", "mel")


def _resample_frequency_rows(values: np.ndarray, target_rows: int) -> np.ndarray:
    if values.shape[0] == target_rows:
        return values
    source_positions = np.linspace(0.0, 1.0, values.shape[0])
    target_positions = np.linspace(0.0, 1.0, target_rows)
    resampled = np.empty((target_rows, values.shape[1]), dtype=np.float64)
    for column_index in range(values.shape[1]):
        resampled[:, column_index] = np.interp(
            target_positions,
            source_positions,
            values[:, column_index],
        )
    return resampled


def _fill_nan(values: np.ndarray) -> np.ndarray:
    if np.isfinite(values).all():
        return values
    filled = np.array(values, dtype=np.float64, copy=True)
    finite = filled[np.isfinite(filled)]
    fallback = float(np.median(finite)) if finite.size else 0.0
    for row_index in range(filled.shape[0]):
        row = filled[row_index]
        row_finite = row[np.isfinite(row)]
        row_fill = float(np.median(row_finite)) if row_finite.size else fallback
        row[~np.isfinite(row)] = row_fill
    return filled


def _quality_summary(
    *,
    payload: Mapping[str, Any],
    dsp: Mapping[str, Any],
    alignment: Mapping[str, Any],
    audio: Mapping[str, Any],
) -> dict[str, float | int | str | None]:
    warnings = payload.get("warnings")
    warning_count = (
        len(warnings)
        if isinstance(warnings, Sequence) and not isinstance(warnings, str)
        else 0
    )
    return {
        "alignment_confidence": _finite_float(alignment.get("confidence")),
        "signal_to_noise_db": _finite_float(dsp.get("signal_to_noise_db")),
        "audio_duration_seconds": _finite_float(audio.get("duration_seconds")),
        "audio_sample_rate_hz": _finite_float(audio.get("sample_rate_hz")),
        "warning_count": warning_count,
    }


def _add_log2(
    features: list[ModelFeature],
    name: str,
    value: Any,
    source: str,
) -> None:
    finite = _finite_float(value)
    if finite is None or finite <= 0:
        return
    _add_feature(features, name, math.log2(max(finite, EPSILON)), "log2", source)


def _add_feature(
    features: list[ModelFeature],
    name: str,
    value: Any,
    unit: str,
    source: str,
) -> None:
    finite = _finite_float(value)
    if finite is None:
        return
    if unit == "db":
        finite = float(np.clip(finite, -DB_FEATURE_ABS_LIMIT, DB_FEATURE_ABS_LIMIT))
    features.append(ModelFeature(name=name, value=finite, unit=unit, source=source))


def _get(payload: Mapping[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if isinstance(value, Mapping):
            value = value.get(part)
        elif isinstance(value, Sequence) and not isinstance(value, str) and part.isdigit():
            index = int(part)
            value = value[index] if 0 <= index < len(value) else None
        else:
            return None
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


def _finite_array(value: Any) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return np.array([], dtype=np.float64)
    if array.size == 0:
        return np.array([], dtype=np.float64)
    if array.ndim == 1:
        return array[np.isfinite(array)]
    return np.where(np.isfinite(array), array, np.nan)


def _finite_float(value: Any) -> float | None:
    try:
        finite = float(value)
    except (TypeError, ValueError):
        return None
    return finite if math.isfinite(finite) else None


def _finite_items(mapping: Mapping[str, Any]) -> Iterable[tuple[str, float]]:
    for name, value in mapping.items():
        finite = _finite_float(value)
        if finite is not None:
            yield str(name), finite


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
