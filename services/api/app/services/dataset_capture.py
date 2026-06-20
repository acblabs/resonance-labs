"""Private Phase 4 dataset capture persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from resonancelab.ml.manifest_builder import make_record_fragment, validate_record_fragment

from app.schemas import (
    AnalysisResponse,
    DatasetCaptureRequest,
    DatasetCaptureResponse,
    DatasetCaptureStoredPaths,
)
from app.settings import Settings


class DatasetCaptureStoreError(RuntimeError):
    """Raised when private capture artifacts cannot be persisted."""


class DatasetArtifactStore(Protocol):
    def write_bytes(self, object_name: str, data: bytes, *, content_type: str) -> None:
        """Write binary data to a storage object."""

    def write_json(self, object_name: str, payload: Mapping[str, object]) -> None:
        """Write JSON data to a storage object."""


class LocalDatasetArtifactStore:
    """Filesystem-backed store for local operator smoke tests."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def write_bytes(self, object_name: str, data: bytes, *, content_type: str) -> None:
        del content_type
        path = self._resolve_object(object_name)
        _write_bytes_atomic(path, data)

    def write_json(self, object_name: str, payload: Mapping[str, object]) -> None:
        path = self._resolve_object(object_name)
        _write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _resolve_object(self, object_name: str) -> Path:
        safe_name = _safe_object_name(object_name)
        path = (self.root / Path(*PurePosixPath(safe_name).parts)).resolve()
        if self.root != path and self.root not in path.parents:
            raise DatasetCaptureStoreError(f"Storage path escapes local root: {object_name}")
        return path


class GcsDatasetArtifactStore:
    """Cloud Storage-backed store for private capture deployments."""

    def __init__(self, bucket_name_value: str) -> None:
        try:
            from google.cloud import storage
        except ModuleNotFoundError as exc:
            raise DatasetCaptureStoreError(
                "google-cloud-storage is required when PHASE4_CAPTURE_GCS_BUCKET is configured."
            ) from exc

        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name_value)

    def write_bytes(self, object_name: str, data: bytes, *, content_type: str) -> None:
        blob = self.bucket.blob(_safe_object_name(object_name))
        blob.upload_from_string(data, content_type=content_type)

    def write_json(self, object_name: str, payload: Mapping[str, object]) -> None:
        blob = self.bucket.blob(_safe_object_name(object_name))
        blob.upload_from_string(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            content_type="application/json",
        )


def build_dataset_capture_store(settings: Settings) -> DatasetArtifactStore:
    """Build the configured artifact store for a private capture request."""

    if settings.phase4_capture_local_dir:
        return LocalDatasetArtifactStore(settings.phase4_capture_local_dir)
    if settings.phase4_capture_gcs_bucket:
        return _cached_gcs_store(settings.phase4_capture_gcs_bucket)
    raise DatasetCaptureStoreError(
        "Set PHASE4_CAPTURE_GCS_BUCKET or PHASE4_CAPTURE_LOCAL_DIR before enabling capture."
    )


@lru_cache(maxsize=4)
def _cached_gcs_store(bucket_name_value: str) -> GcsDatasetArtifactStore:
    return GcsDatasetArtifactStore(bucket_name_value)


def store_dataset_capture(
    *,
    audio_bytes: bytes,
    content_type: str,
    capture: DatasetCaptureRequest,
    analysis: AnalysisResponse,
    settings: Settings,
    idempotency_key: str | None = None,
    store: DatasetArtifactStore | None = None,
) -> DatasetCaptureResponse:
    """Persist one private Phase 4 capture into the configured inbox."""

    artifact_store = store or build_dataset_capture_store(settings)
    captured_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    session_id = _slug(capture.context.session_id)
    record_id = _record_id(session_id, idempotency_key=idempotency_key)
    inbox_prefix = _safe_object_name(f"{settings.phase4_capture_inbox_prefix}/{session_id}")
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    should_store_audio = capture.store_audio and settings.phase4_capture_store_raw_audio

    record_audio_path = f"audio/{session_id}/{record_id}.wav" if should_store_audio else None
    record_analysis_path = f"analysis/{session_id}/{record_id}.analysis.json"
    source_paths: dict[str, str] = {
        "analysis": f"{session_id}/analysis/{record_id}.analysis.json",
    }
    if record_audio_path:
        source_paths["audio"] = f"{session_id}/audio/{record_id}.wav"

    record = _manifest_record(
        record_id=record_id,
        captured_at=captured_at,
        capture=capture,
        analysis=analysis,
        audio_path=record_audio_path,
        analysis_path=record_analysis_path,
        audio_sha256=audio_hash,
    )
    fragment = make_record_fragment(
        record=record,
        source_paths=source_paths,
        created_at=captured_at,
    )
    validate_record_fragment(fragment, source=f"capture:{record_id}")

    analysis_object = f"{inbox_prefix}/analysis/{record_id}.analysis.json"
    record_object = f"{inbox_prefix}/records/{record_id}.record.json"
    artifact_store.write_json(analysis_object, analysis.model_dump(mode="json"))
    if should_store_audio:
        artifact_store.write_bytes(
            f"{inbox_prefix}/audio/{record_id}.wav",
            audio_bytes,
            content_type=content_type,
        )
    artifact_store.write_json(record_object, fragment)

    return DatasetCaptureResponse(
        record_id=record_id,
        status="stored",
        inbox_prefix=inbox_prefix,
        stored_paths=DatasetCaptureStoredPaths(
            inbox_record_path=record_object,
            audio_path=f"{inbox_prefix}/audio/{record_id}.wav" if record_audio_path else None,
            analysis_path=analysis_object,
        ),
        analysis=analysis,
    )


def _manifest_record(
    *,
    record_id: str,
    captured_at: str,
    capture: DatasetCaptureRequest,
    analysis: AnalysisResponse,
    audio_path: str | None,
    analysis_path: str,
    audio_sha256: str,
) -> dict[str, object]:
    label = capture.label.model_dump(mode="json", exclude_none=True)
    fill_percent = float(capture.label.fill_percent)
    label["fill_percent"] = fill_percent

    quality = {
        "alignment_confidence": analysis.alignment.confidence,
        "signal_to_noise_db": analysis.dsp.signal_to_noise_db,
        "warnings": list(analysis.warnings),
    }
    record: dict[str, object] = {
        "id": record_id,
        "recorded_at": analysis.probe.client_recorded_at or captured_at,
        "analysis_path": analysis_path,
        "label": label,
        "context": capture.context.model_dump(mode="json", exclude_none=True),
        "quality": quality,
        "probe": analysis.probe.probe_config.model_dump(mode="json"),
        "audio_sha256": audio_sha256,
    }
    if audio_path:
        record["audio_path"] = audio_path
    if capture.notes:
        record["notes"] = capture.notes
    return record


def _record_id(session_id: str, *, idempotency_key: str | None) -> str:
    if idempotency_key:
        digest = hashlib.sha256(f"{session_id}:{idempotency_key}".encode()).hexdigest()
        return f"{session_id}-{digest[:16]}"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{session_id}-{timestamp}-{uuid4().hex[:12]}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown"


def _safe_object_name(raw_name: str) -> str:
    normalized = raw_name.replace("\\", "/").strip("/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not normalized:
        raise DatasetCaptureStoreError(f"Unsafe storage object name: {raw_name!r}")
    return pure.as_posix()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(text)
        temporary_name = handle.name
    os.replace(temporary_name, path)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(data)
        temporary_name = handle.name
    os.replace(temporary_name, path)
