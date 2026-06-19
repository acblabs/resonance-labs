"""Dataset manifest parsing and validation for Phase 4 baseline training."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .features import FeatureVector, extract_feature_vector_from_mapping, load_feature_vector

DATASET_FORMAT = "resonancelab.phase4.dataset"
DATASET_FORMAT_VERSION = 1
DEFAULT_BUCKETS_PERCENT = (0.0, 25.0, 50.0, 75.0, 100.0)
REQUIRED_GROUP_FIELDS = ("session_id", "glass_id", "device_id", "browser_id")


class ManifestValidationError(ValueError):
    """Raised when a Phase 4 dataset manifest is structurally invalid."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("Dataset manifest validation failed: " + "; ".join(self.errors))


@dataclass(frozen=True)
class RecordingLabel:
    """Ground-truth label for one fill-level recording."""

    fill_percent: float
    fill_bucket: str
    fill_mass_g: float | None = None
    vessel_empty_mass_g: float | None = None
    vessel_full_mass_g: float | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    ) -> RecordingLabel:
        fill_percent = _required_float(payload, "fill_percent")
        bucket = _string_or_none(payload.get("fill_bucket"))
        if bucket is None:
            bucket = bucket_name(nearest_fill_bucket(fill_percent, buckets_percent))
        return cls(
            fill_percent=fill_percent,
            fill_bucket=bucket,
            fill_mass_g=_optional_float(payload.get("fill_mass_g")),
            vessel_empty_mass_g=_optional_float(payload.get("vessel_empty_mass_g")),
            vessel_full_mass_g=_optional_float(payload.get("vessel_full_mass_g")),
        )

    def bucket_percent(self, buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT) -> float:
        return nearest_fill_bucket(self.fill_percent, buckets_percent)


@dataclass(frozen=True)
class RecordingContext:
    """Leakage-sensitive capture context for one recording."""

    session_id: str
    glass_id: str
    device_id: str
    browser_id: str
    room_id: str
    operator_id: str | None = None
    volume_setting: str | None = None
    material: str | None = None
    geometry: str | None = None
    notes: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RecordingContext:
        return cls(
            session_id=_required_string(payload, "session_id"),
            glass_id=_required_string(payload, "glass_id"),
            device_id=_required_string(payload, "device_id"),
            browser_id=_required_string(payload, "browser_id"),
            room_id=_required_string(payload, "room_id"),
            operator_id=_string_or_none(payload.get("operator_id")),
            volume_setting=_string_or_none(payload.get("volume_setting")),
            material=_string_or_none(payload.get("material")),
            geometry=_string_or_none(payload.get("geometry")),
            notes=_string_or_none(payload.get("notes")),
        )

    def group_value(self, field: str) -> str:
        value = getattr(self, field, None)
        if value is None:
            raise KeyError(f"Unknown or empty grouping field: {field}")
        return str(value)


@dataclass(frozen=True)
class DatasetRecord:
    """One manifest row representing a probe recording or extracted analysis."""

    record_id: str
    label: RecordingLabel
    context: RecordingContext
    recorded_at: str | None = None
    audio_path: str | None = None
    analysis_path: str | None = None
    features_path: str | None = None
    probe: Mapping[str, Any] | None = None
    quality: Mapping[str, Any] | None = None
    exclude: bool = False
    notes: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    ) -> DatasetRecord:
        return cls(
            record_id=_required_string(payload, "id"),
            recorded_at=_string_or_none(payload.get("recorded_at")),
            audio_path=_path_or_none(payload.get("audio_path")),
            analysis_path=_path_or_none(payload.get("analysis_path")),
            features_path=_path_or_none(payload.get("features_path")),
            label=RecordingLabel.from_mapping(
                _required_mapping(payload, "label"),
                buckets_percent=buckets_percent,
            ),
            context=RecordingContext.from_mapping(_required_mapping(payload, "context")),
            probe=_mapping_or_none(payload.get("probe")),
            quality=_mapping_or_none(payload.get("quality")),
            exclude=bool(payload.get("exclude", False)),
            notes=_string_or_none(payload.get("notes")),
        )

    def group_key(self, fields: Sequence[str]) -> tuple[str, ...]:
        return tuple(self.context.group_value(field) for field in fields)

    @property
    def usable(self) -> bool:
        if self.exclude:
            return False
        quality = self.quality or {}
        return quality.get("usable", True) is not False

    def feature_source_path(self) -> str | None:
        return self.features_path or self.analysis_path


@dataclass(frozen=True)
class DatasetManifest:
    """A validated Phase 4 dataset manifest."""

    dataset_id: str
    records: tuple[DatasetRecord, ...]
    path: Path | None = None
    created_at: str | None = None
    description: str | None = None
    label_buckets_percent: tuple[float, ...] = DEFAULT_BUCKETS_PERCENT
    owners: tuple[str, ...] = ()
    notes: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        path: Path | None = None,
    ) -> DatasetManifest:
        if payload.get("format") != DATASET_FORMAT:
            raise ManifestValidationError([f"format must be '{DATASET_FORMAT}'."])
        version = payload.get("format_version")
        if version != DATASET_FORMAT_VERSION:
            raise ManifestValidationError(
                [f"format_version must be {DATASET_FORMAT_VERSION}, got {version!r}."]
            )

        label_schema = _mapping_or_none(payload.get("label_schema")) or {}
        buckets = normalize_buckets(
            label_schema.get("buckets_percent", DEFAULT_BUCKETS_PERCENT)
        )
        manifest = cls(
            dataset_id=_required_string(payload, "dataset_id"),
            created_at=_string_or_none(payload.get("created_at")),
            description=_string_or_none(payload.get("description")),
            label_buckets_percent=buckets,
            owners=tuple(str(owner) for owner in _sequence(payload.get("owners"))),
            notes=_string_or_none(payload.get("notes")),
            records=tuple(
                DatasetRecord.from_mapping(record, buckets_percent=buckets)
                for record in _sequence(payload.get("records"))
                if isinstance(record, Mapping)
            ),
            path=path,
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        errors: list[str] = []
        if not self.records:
            errors.append("records must contain at least one dataset record.")
        if tuple(sorted(self.label_buckets_percent)) != self.label_buckets_percent:
            errors.append("label_schema.buckets_percent must be sorted ascending.")
        if len(set(self.label_buckets_percent)) != len(self.label_buckets_percent):
            errors.append("label_schema.buckets_percent values must be unique.")
        if len(self.label_buckets_percent) < 2:
            errors.append("label_schema.buckets_percent must contain at least two buckets.")
        if self.label_buckets_percent and (
            self.label_buckets_percent[0] != 0.0 or self.label_buckets_percent[-1] != 100.0
        ):
            errors.append("label_schema.buckets_percent must include 0 and 100 endpoints.")
        if any(bucket < 0 or bucket > 100 for bucket in self.label_buckets_percent):
            errors.append("label_schema.buckets_percent values must be within [0, 100].")

        seen_ids: set[str] = set()
        for record in self.records:
            if record.record_id in seen_ids:
                errors.append(f"duplicate record id: {record.record_id}")
            seen_ids.add(record.record_id)

            if not (0.0 <= record.label.fill_percent <= 100.0):
                errors.append(f"{record.record_id}: label.fill_percent must be within [0, 100].")
            if not math.isfinite(record.label.fill_percent):
                errors.append(f"{record.record_id}: label.fill_percent must be finite.")
            expected_bucket = bucket_name(
                nearest_fill_bucket(record.label.fill_percent, self.label_buckets_percent)
            )
            if record.label.fill_bucket != expected_bucket:
                errors.append(
                    f"{record.record_id}: label.fill_bucket {record.label.fill_bucket!r} "
                    f"does not match fill_percent bucket {expected_bucket!r}."
                )
            if record.feature_source_path() is None and record.audio_path is None:
                errors.append(
                    f"{record.record_id}: provide features_path, analysis_path, or audio_path."
                )
            if record.audio_path is not None:
                errors.extend(_validate_probe_mapping(record.record_id, record.probe))
            for field in REQUIRED_GROUP_FIELDS:
                try:
                    record.context.group_value(field)
                except KeyError:
                    errors.append(f"{record.record_id}: context.{field} is required.")

        if errors:
            raise ManifestValidationError(errors)

    def active_records(self) -> tuple[DatasetRecord, ...]:
        """Return records not explicitly excluded by the manifest."""

        return tuple(record for record in self.records if record.usable)

    def manifest_hash(self) -> str:
        """Stable hash of the manifest content for artifact traceability."""

        content = json.dumps(self._canonical_hash_payload(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def resolve_path(self, relative_path: str) -> Path:
        base = self.path.parent if self.path is not None else Path.cwd()
        return (base / relative_path).resolve()

    def _canonical_hash_payload(self) -> dict[str, Any]:
        return {
            "format": DATASET_FORMAT,
            "format_version": DATASET_FORMAT_VERSION,
            "dataset_id": self.dataset_id,
            "label_buckets_percent": list(self.label_buckets_percent),
            "records": [
                {
                    "id": record.record_id,
                    "recorded_at": record.recorded_at,
                    "label": {
                        "fill_percent": record.label.fill_percent,
                        "fill_bucket": record.label.fill_bucket,
                        "fill_mass_g": record.label.fill_mass_g,
                        "vessel_empty_mass_g": record.label.vessel_empty_mass_g,
                        "vessel_full_mass_g": record.label.vessel_full_mass_g,
                    },
                    "context": {
                        "session_id": record.context.session_id,
                        "glass_id": record.context.glass_id,
                        "device_id": record.context.device_id,
                        "browser_id": record.context.browser_id,
                        "room_id": record.context.room_id,
                        "operator_id": record.context.operator_id,
                        "volume_setting": record.context.volume_setting,
                        "material": record.context.material,
                        "geometry": record.context.geometry,
                    },
                    "paths": {
                        "audio": _path_hash(self, record.audio_path),
                        "analysis": _path_hash(self, record.analysis_path),
                        "features": _path_hash(self, record.features_path),
                    },
                    "probe": dict(record.probe or {}),
                    "quality": dict(record.quality or {}),
                    "exclude": record.exclude,
                }
                for record in sorted(self.records, key=lambda item: item.record_id)
            ],
        }


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load and validate a Phase 4 dataset manifest."""

    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ManifestValidationError(["manifest root must be a JSON object."])
    return DatasetManifest.from_mapping(payload, path=manifest_path.resolve())


def load_record_feature_vector(
    manifest: DatasetManifest,
    record: DatasetRecord,
) -> FeatureVector:
    """Load a record's canonical feature vector from feature or analysis JSON."""

    if record.features_path:
        return load_feature_vector(manifest.resolve_path(record.features_path))
    if record.analysis_path:
        analysis_path = manifest.resolve_path(record.analysis_path)
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        if not isinstance(analysis, Mapping):
            raise ValueError(f"{record.record_id}: analysis_path must contain a JSON object.")
        return extract_feature_vector_from_mapping(analysis, record_id=record.record_id)
    raise ValueError(f"{record.record_id}: no feature or analysis JSON path is available.")


def normalize_buckets(values: Any) -> tuple[float, ...]:
    """Normalize a manifest bucket list to finite float percentages."""

    try:
        buckets = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError(["label_schema.buckets_percent must be numeric."]) from exc
    if any(not math.isfinite(bucket) for bucket in buckets):
        raise ManifestValidationError(["label_schema.buckets_percent values must be finite."])
    return buckets


def nearest_fill_bucket(
    fill_percent: float,
    buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
) -> float:
    """Map a continuous fill percent to the nearest Phase 4 canonical bucket."""

    return min(buckets_percent, key=lambda bucket: abs(bucket - fill_percent))


def bucket_name(bucket_percent: float) -> str:
    """Return a stable class label for a canonical fill bucket."""

    bucket = int(round(bucket_percent))
    return "empty" if bucket == 0 else "full" if bucket == 100 else f"{bucket}_percent"


def bucket_names(buckets_percent: Sequence[float]) -> tuple[str, ...]:
    """Return stable class labels for a bucket schema."""

    return tuple(bucket_name(bucket) for bucket in buckets_percent)


def _path_hash(manifest: DatasetManifest, relative_path: str | None) -> dict[str, str | None]:
    if relative_path is None:
        return {"path": None, "sha256": None}
    resolved = manifest.resolve_path(relative_path)
    if not resolved.exists():
        return {"path": relative_path, "sha256": None}
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _validate_probe_mapping(record_id: str, probe: Mapping[str, Any] | None) -> list[str]:
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
    if probe is None:
        return [f"{record_id}: audio_path records must include a probe object."]
    errors = [
        f"{record_id}: probe.{name} is required for audio_path records."
        for name in required
        if name not in probe
    ]
    if probe.get("signal_type") != "log_chirp":
        errors.append(f"{record_id}: probe.signal_type must be 'log_chirp'.")
    return errors


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ManifestValidationError([f"{key} must be an object."])
    return value


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = _string_or_none(payload.get(key))
    if value is None:
        raise ManifestValidationError([f"{key} must be a non-empty string."])
    return value


def _required_float(payload: Mapping[str, Any], key: str) -> float:
    value = _optional_float(payload.get(key))
    if value is None:
        raise ManifestValidationError([f"{key} must be a finite number."])
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        finite = float(value)
    except (TypeError, ValueError):
        return None
    return finite if math.isfinite(finite) else None


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _path_or_none(value: Any) -> str | None:
    text = _string_or_none(value)
    return text.replace("\\", "/") if text else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return ()
