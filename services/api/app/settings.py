"""Runtime settings for the ResonanceLab API."""

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
    max_explain_body_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("RESONANCELAB_MAX_EXPLAIN_BODY_BYTES", str(512 * 1024))
        )
    )
    allowed_content_types: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "RESONANCELAB_ALLOWED_CONTENT_TYPES",
            "audio/wav,audio/wave,audio/x-wav,application/octet-stream",
        )
    )
    llm_enabled: bool = field(default_factory=lambda: _bool_env("RESONANCELAB_LLM_ENABLED", False))
    llm_provider: str = field(
        default_factory=lambda: os.getenv("RESONANCELAB_LLM_PROVIDER", "vertex_gemini").strip()
    )
    llm_project_id: str | None = field(
        default_factory=lambda: _optional_env("RESONANCELAB_LLM_PROJECT_ID")
        or _optional_env("GOOGLE_CLOUD_PROJECT")
    )
    llm_location: str = field(
        default_factory=lambda: os.getenv(
            "RESONANCELAB_LLM_LOCATION",
            os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        ).strip()
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv(
            "RESONANCELAB_LLM_MODEL",
            "gemini-3.1-pro-preview",
        ).strip()
    )
    llm_thinking_level: str = field(
        default_factory=lambda: os.getenv("RESONANCELAB_LLM_THINKING_LEVEL", "HIGH")
        .strip()
        .upper()
    )
    llm_temperature: float = field(
        default_factory=lambda: float(os.getenv("RESONANCELAB_LLM_TEMPERATURE", "0.2"))
    )
    llm_max_output_tokens: int = field(
        default_factory=lambda: int(os.getenv("RESONANCELAB_LLM_MAX_OUTPUT_TOKENS", "8192"))
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
