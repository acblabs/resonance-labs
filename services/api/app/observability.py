"""Small structured logging helpers for API traceability."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID


def configure_logging(log_level: str) -> None:
    """Configure root logging for JSON message payloads on stdout/stderr."""

    level = getattr(logging, log_level.strip().upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(message)s")
    root.setLevel(level)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Emit one structured log event as JSON."""

    payload = {
        "event": event,
        **{key: value for key, value in fields.items() if value is not None},
    }
    logger.log(
        level,
        json.dumps(payload, default=_json_default, separators=(",", ":"), sort_keys=True),
        exc_info=exc_info,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)
