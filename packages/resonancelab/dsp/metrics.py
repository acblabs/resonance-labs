"""Basic audio metrics used by the Phase 1 dummy analyzer."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - exercised only before local deps are installed.
    np = None

logger = logging.getLogger(__name__)
_warned_numpy_fallback = False


@dataclass(frozen=True)
class AudioMetrics:
    """Small set of sanity-check metrics returned by the dummy endpoint."""

    duration_seconds: float
    rms: float
    peak_amplitude: float
    dc_offset: float
    sample_count: int


def compute_audio_metrics(samples: Sequence[float], sample_rate_hz: int) -> AudioMetrics:
    """Compute duration, RMS, peak, and DC offset for normalized mono samples."""

    sample_count = len(samples)
    if sample_count == 0 or sample_rate_hz <= 0:
        return AudioMetrics(
            duration_seconds=0.0,
            rms=0.0,
            peak_amplitude=0.0,
            dc_offset=0.0,
            sample_count=sample_count,
        )

    if np is not None:
        array = np.asarray(samples, dtype=np.float64)
        return AudioMetrics(
            duration_seconds=sample_count / sample_rate_hz,
            rms=float(np.sqrt(np.mean(np.square(array)))),
            peak_amplitude=float(np.max(np.abs(array))),
            dc_offset=float(np.mean(array)),
            sample_count=sample_count,
        )

    global _warned_numpy_fallback
    if not _warned_numpy_fallback:
        logger.warning("numpy_unavailable_audio_metrics_fallback")
        _warned_numpy_fallback = True

    total = 0.0
    total_squares = 0.0
    peak = 0.0
    for sample in samples:
        total += sample
        total_squares += sample * sample
        peak = max(peak, abs(sample))

    return AudioMetrics(
        duration_seconds=sample_count / sample_rate_hz,
        rms=math.sqrt(total_squares / sample_count),
        peak_amplitude=peak,
        dc_offset=total / sample_count,
        sample_count=sample_count,
    )
