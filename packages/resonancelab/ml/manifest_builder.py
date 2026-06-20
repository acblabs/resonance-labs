"""Build immutable Phase 4 dataset snapshots from private capture inbox records."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .dataset import (
    DATASET_FORMAT,
    DATASET_FORMAT_VERSION,
    DEFAULT_BUCKETS_PERCENT,
    DatasetManifest,
    ManifestValidationError,
)

RECORD_FRAGMENT_FORMAT = "resonancelab.phase4.record"
RECORD_FRAGMENT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class ManifestBuildResult:
    """Summary of a finalized Phase 4 dataset snapshot."""

    manifest_path: Path
    record_count: int
    copied_paths: tuple[str, ...]


def finalize_phase4_dataset(
    *,
    inbox_dir: str | Path,
    snapshot_dir: str | Path,
    dataset_id: str,
    manifest_name: str = "manifest.json",
    buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    created_at: str | None = None,
    description: str | None = None,
    owners: Sequence[str] = (),
    notes: str | None = None,
    overwrite: bool = False,
) -> ManifestBuildResult:
    """Materialize a validated dataset manifest and copy inbox artifacts into a snapshot."""

    inbox_root = Path(inbox_dir).resolve()
    snapshot_root = Path(snapshot_dir).resolve()
    if not inbox_root.exists():
        raise FileNotFoundError(f"Inbox directory does not exist: {inbox_root}")
    snapshot_root.mkdir(parents=True, exist_ok=True)

    manifest_path = (snapshot_root / manifest_name).resolve()
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(f"Manifest already exists: {manifest_path}")

    fragments = _load_record_fragments(inbox_root)
    if not fragments:
        raise ManifestValidationError(["record inbox does not contain any .record.json files."])

    records: list[dict[str, Any]] = []
    copied_paths: list[str] = []
    seen_ids: set[str] = set()
    for fragment_path, fragment in fragments:
        record = _record_for_manifest(
            _required_mapping(fragment, "record"),
            source=fragment_path,
        )
        _validate_single_record(
            record,
            buckets_percent=buckets_percent,
            source=fragment_path,
        )
        record_id = _required_string(record, "id", source=fragment_path)
        if record_id in seen_ids:
            raise ManifestValidationError([f"duplicate record id: {record_id}"])
        seen_ids.add(record_id)

        source_paths = _mapping_or_empty(fragment.get("source_paths"))
        for field_name, source_key in (
            ("audio_path", "audio"),
            ("analysis_path", "analysis"),
            ("features_path", "features"),
        ):
            target_relative = record.get(field_name)
            if not target_relative:
                continue
            safe_target = _safe_relative_path(str(target_relative))
            record[field_name] = safe_target
            source_relative = source_paths.get(source_key)
            if source_relative is None:
                source_relative = safe_target
            source_path = _resolve_under(inbox_root, str(source_relative))
            target_path = _resolve_under(snapshot_root, safe_target)
            _copy_artifact(source_path, target_path, overwrite=overwrite)
            copied_paths.append(safe_target)

        records.append(record)

    timestamp = (
        created_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    manifest_payload: dict[str, Any] = {
        "format": DATASET_FORMAT,
        "format_version": DATASET_FORMAT_VERSION,
        "dataset_id": dataset_id,
        "created_at": timestamp,
        "label_schema": {"buckets_percent": [float(bucket) for bucket in buckets_percent]},
        "records": sorted(records, key=lambda item: str(item["id"])),
    }
    if description:
        manifest_payload["description"] = description
    if owners:
        manifest_payload["owners"] = list(owners)
    if notes:
        manifest_payload["notes"] = notes

    DatasetManifest.from_mapping(manifest_payload, path=manifest_path)
    _write_json_atomic(manifest_path, manifest_payload)
    return ManifestBuildResult(
        manifest_path=manifest_path,
        record_count=len(records),
        copied_paths=tuple(sorted(copied_paths)),
    )


def make_record_fragment(
    *,
    record: Mapping[str, Any],
    source_paths: Mapping[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Return a standard capture-inbox record fragment."""

    return {
        "format": RECORD_FRAGMENT_FORMAT,
        "format_version": RECORD_FRAGMENT_FORMAT_VERSION,
        "created_at": created_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "record": dict(record),
        "source_paths": dict(source_paths),
    }


def validate_record_fragment(
    fragment: Mapping[str, Any],
    *,
    buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    source: str | Path = "<record-fragment>",
) -> None:
    """Validate one inbox record fragment before it is written or finalized."""

    source_label = str(source)
    if fragment.get("format") != RECORD_FRAGMENT_FORMAT:
        raise ManifestValidationError(
            [f"{source_label}: format must be '{RECORD_FRAGMENT_FORMAT}'."]
        )
    if fragment.get("format_version") != RECORD_FRAGMENT_FORMAT_VERSION:
        raise ManifestValidationError(
            [f"{source_label}: format_version must be {RECORD_FRAGMENT_FORMAT_VERSION}."]
        )

    record = _record_for_manifest(
        _required_mapping(fragment, "record"),
        source=source_label,
    )
    _validate_single_record(record, buckets_percent=buckets_percent, source=source_label)

    source_paths = _mapping_or_empty(fragment.get("source_paths"))
    for key, value in source_paths.items():
        try:
            _safe_relative_path(value)
        except ManifestValidationError as exc:
            raise ManifestValidationError(
                [f"{source_label}: source_paths.{key}: {error}" for error in exc.errors]
            ) from exc


def _load_record_fragments(inbox_root: Path) -> list[tuple[Path, Mapping[str, Any]]]:
    fragments: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(inbox_root.rglob("*.record.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ManifestValidationError([f"{path}: record fragment must be a JSON object."])
        if payload.get("format") != RECORD_FRAGMENT_FORMAT:
            raise ManifestValidationError(
                [f"{path}: format must be '{RECORD_FRAGMENT_FORMAT}'."]
            )
        if payload.get("format_version") != RECORD_FRAGMENT_FORMAT_VERSION:
            raise ManifestValidationError(
                [f"{path}: format_version must be {RECORD_FRAGMENT_FORMAT_VERSION}."]
            )
        validate_record_fragment(payload, source=path)
        fragments.append((path, payload))
    return fragments


def _record_for_manifest(record: Mapping[str, Any], *, source: str | Path) -> dict[str, Any]:
    normalized = dict(record)
    try:
        label = dict(_required_mapping(normalized, "label"))
    except ManifestValidationError as exc:
        raise ManifestValidationError([f"{source}: {error}" for error in exc.errors]) from exc
    label.pop("fill_bucket", None)
    normalized["label"] = label
    try:
        _required_string(normalized, "id", source=source)
    except ManifestValidationError as exc:
        raise ManifestValidationError([f"{source}: {error}" for error in exc.errors]) from exc
    return normalized


def _validate_single_record(
    record: Mapping[str, Any],
    *,
    buckets_percent: Sequence[float],
    source: str | Path,
) -> None:
    try:
        DatasetManifest.from_mapping(
            {
                "format": DATASET_FORMAT,
                "format_version": DATASET_FORMAT_VERSION,
                "dataset_id": "fragment-validation",
                "label_schema": {"buckets_percent": [float(bucket) for bucket in buckets_percent]},
                "records": [dict(record)],
            }
        )
    except ManifestValidationError as exc:
        raise ManifestValidationError([f"{source}: {error}" for error in exc.errors]) from exc


def _copy_artifact(source_path: Path, target_path: Path, *, overwrite: bool) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"Referenced inbox artifact does not exist: {source_path}")
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"Snapshot artifact already exists: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary_name = handle.name
    os.replace(temporary_name, path)


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ManifestValidationError([f"{key} must be an object."])
    return value


def _mapping_or_empty(value: Any) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _required_string(payload: Mapping[str, Any], key: str, *, source: Path) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        raise ManifestValidationError([f"{source}: record.{key} must be a non-empty string."])
    return str(value).strip()


def _safe_relative_path(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or normalized == "":
        raise ManifestValidationError([f"unsafe relative path: {raw_path!r}"])
    return pure.as_posix()


def _resolve_under(root: Path, relative_path: str) -> Path:
    safe_relative = _safe_relative_path(relative_path)
    resolved = (root / Path(*PurePosixPath(safe_relative).parts)).resolve()
    if root != resolved and root not in resolved.parents:
        raise ManifestValidationError([f"path escapes root: {relative_path!r}"])
    return resolved
