"""Runtime settings for the Phase 1 API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, default)
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class Settings:
    title: str = field(
        default_factory=lambda: os.getenv("RESONANCELAB_API_TITLE", "ResonanceLab API")
    )
    version: str = field(default_factory=lambda: os.getenv("RESONANCELAB_VERSION", "0.1.0"))
    environment: str = field(default_factory=lambda: os.getenv("RESONANCELAB_ENV", "local"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "RESONANCELAB_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
        )
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("RESONANCELAB_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024))
        )
    )
    max_recording_seconds: float = field(
        default_factory=lambda: float(os.getenv("RESONANCELAB_MAX_RECORDING_SECONDS", "8.0"))
    )
    allowed_content_types: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "RESONANCELAB_ALLOWED_CONTENT_TYPES",
            "audio/wav,audio/wave,audio/x-wav,application/octet-stream",
        )
    )
    phase4_capture_enabled: bool = field(
        default_factory=lambda: _bool_env("PHASE4_CAPTURE_ENABLED", False)
    )
    phase4_capture_token: str | None = field(
        default_factory=lambda: _optional_env("PHASE4_CAPTURE_OPERATOR_TOKEN")
    )
    phase4_capture_gcs_bucket: str | None = field(
        default_factory=lambda: _optional_env("PHASE4_CAPTURE_GCS_BUCKET")
    )
    phase4_capture_inbox_prefix: str = field(
        default_factory=lambda: os.getenv("PHASE4_CAPTURE_INBOX_PREFIX", "phase4/inbox").strip(
            "/"
        )
    )
    phase4_capture_local_dir: str | None = field(
        default_factory=lambda: _optional_env("PHASE4_CAPTURE_LOCAL_DIR")
    )
    phase4_capture_store_raw_audio: bool = field(
        default_factory=lambda: _bool_env("PHASE4_CAPTURE_STORE_RAW_AUDIO", True)
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
