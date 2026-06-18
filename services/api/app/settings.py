"""Runtime settings for the Phase 1 API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, default)
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    title: str = os.getenv("RESONANCELAB_API_TITLE", "ResonanceLab API")
    version: str = os.getenv("RESONANCELAB_VERSION", "0.1.0")
    environment: str = os.getenv("RESONANCELAB_ENV", "local")
    cors_origins: tuple[str, ...] = _csv_env(
        "RESONANCELAB_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    )
    max_upload_bytes: int = int(os.getenv("RESONANCELAB_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
    max_recording_seconds: float = float(os.getenv("RESONANCELAB_MAX_RECORDING_SECONDS", "8.0"))
    allowed_content_types: tuple[str, ...] = _csv_env(
        "RESONANCELAB_ALLOWED_CONTENT_TYPES",
        "audio/wav,audio/wave,audio/x-wav,application/octet-stream",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
