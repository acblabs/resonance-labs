"""Phase 2 chirp-aligned DSP feature extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

EPSILON = 1e-12
# Use the same boundary for selecting detected alignment and warning users. Below this,
# trust the scheduled chirp start over a weak matched-filter maximum.
ALIGNMENT_ACCEPT_CONFIDENCE = 0.20
ALIGNMENT_WARN_CONFIDENCE = 0.20
SNR_WARN_DB = 12.0
MIN_POST_WINDOW_SECONDS = 0.10
DEFAULT_TRANSFER_BANDS_HZ = (
    (100.0, 250.0),
    (250.0, 500.0),
    (500.0, 1000.0),
    (1000.0, 2000.0),
    (2000.0, 4000.0),
    (4000.0, 8000.0),
    (8000.0, 12000.0),
    (12000.0, 16000.0),
    (16000.0, 20000.0),
)


@dataclass(frozen=True)
class ChirpSpec:
    """Logarithmic chirp parameters shared by browser and API analysis."""

    start_hz: float
    end_hz: float
    duration_seconds: float
    amplitude: float
    fade_seconds: float


@dataclass(frozen=True)
class AlignmentResult:
    """Matched-filter chirp alignment result."""

    method: Literal["matched_filter_log_chirp"]
    confidence: float
    detected_start_sample: int | None
    expected_start_sample: int | None
    selected_start_sample: int
    offset_samples: int | None
    estimated_latency_ms: float | None
    detected_start_seconds: float | None
    expected_start_seconds: float | None


@dataclass(frozen=True)
class FrequencySeries:
    """Compact frequency-domain trace for charting."""

    frequency_bins_hz: list[float]
    magnitude_db: list[float]


@dataclass(frozen=True)
class SpectrogramGrid:
    """Compact time/frequency grid, stored as frequency rows by time columns."""

    kind: Literal["stft", "mel"]
    times_seconds: list[float]
    frequency_bins_hz: list[float]
    magnitude_db: list[list[float]]


@dataclass(frozen=True)
class SpectralSummary:
    """FFT trace and scalar spectral shape descriptors."""

    series: FrequencySeries
    centroid_hz: float | None
    bandwidth_hz: float | None
    rolloff_hz: float | None
    spectral_floor_db: float | None


@dataclass(frozen=True)
class PeakFeature:
    """Dominant local maximum in the ring-down spectrum."""

    frequency_hz: float
    magnitude_db: float
    prominence_db: float
    q_factor: float | None


@dataclass(frozen=True)
class TransferBand:
    """Mean transfer-response magnitude in a frequency band."""

    start_hz: float
    end_hz: float
    center_hz: float
    mean_db: float
    peak_db: float


@dataclass(frozen=True)
class DecayEstimate:
    """Exponential ring-down fit from the post-chirp envelope."""

    method: Literal["rms_envelope_log_linear"]
    decay_rate_per_second: float | None
    rt60_seconds: float | None
    fit_r2: float | None
    window_start_seconds: float
    window_end_seconds: float


@dataclass(frozen=True)
class ChirpDspAnalysis:
    """Full Phase 2 DSP analysis bundle."""

    bandpass_low_hz: float
    bandpass_high_hz: float
    signal_to_noise_db: float | None
    alignment: AlignmentResult
    fft: SpectralSummary
    stft: SpectrogramGrid
    mel_spectrogram: SpectrogramGrid
    transfer_response: list[TransferBand]
    dominant_peaks: list[PeakFeature]
    decay: DecayEstimate


def generate_log_chirp(spec: ChirpSpec, sample_rate_hz: int) -> npt.NDArray[np.float64]:
    """Generate the same cosine-tapered logarithmic chirp used by the browser."""

    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")
    if spec.start_hz <= 0 or spec.end_hz <= spec.start_hz:
        raise ValueError("chirp frequencies must satisfy 0 < start_hz < end_hz.")
    if spec.duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive.")

    sample_count = max(1, int(round(spec.duration_seconds * sample_rate_hz)))
    time = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    sweep_rate = math.log(spec.end_hz / spec.start_hz) / spec.duration_seconds
    phase = 2.0 * math.pi * spec.start_hz * (np.exp(sweep_rate * time) - 1.0) / sweep_rate
    samples = np.sin(phase) * spec.amplitude

    fade_samples = int(round(max(0.0, spec.fade_seconds) * sample_rate_hz))
    if fade_samples > 0:
        fade = _cosine_fade(sample_count, fade_samples)
        samples = samples * fade

    return samples.astype(np.float64, copy=False)


def apply_fft_bandpass(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    low_hz: float,
    high_hz: float,
    *,
    transition_hz: float | None = None,
) -> npt.NDArray[np.float64]:
    """Apply a zero-phase FFT-domain bandpass with cosine transition bands."""

    array = _as_mono_float64(samples)
    if array.size == 0:
        return array
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")

    nyquist_hz = sample_rate_hz / 2.0
    low_hz = max(0.0, float(low_hz))
    high_hz = min(float(high_hz), nyquist_hz)
    if low_hz >= high_hz:
        raise ValueError("bandpass low_hz must be lower than high_hz.")

    transition = transition_hz
    if transition is None:
        transition = max(25.0, min(500.0, (high_hz - low_hz) * 0.08))
    transition = max(0.0, float(transition))

    transient_samples = int(math.ceil(4.0 * sample_rate_hz / max(transition, 1.0)))
    pad_samples = min(
        max(array.size // 2, transient_samples, 1),
        max(array.size, int(round(sample_rate_hz * 0.5))),
    )
    padded = np.pad(array, (pad_samples, pad_samples))
    fft_size = _next_power_of_two(padded.size)

    spectrum = np.fft.rfft(padded, n=fft_size)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate_hz)
    mask = np.zeros_like(frequencies)

    passband = (frequencies >= low_hz) & (frequencies <= high_hz)
    mask[passband] = 1.0

    if transition > 0:
        if low_hz > 0:
            lower = (frequencies >= max(0.0, low_hz - transition)) & (frequencies < low_hz)
            mask[lower] = 0.5 - 0.5 * np.cos(
                math.pi * (frequencies[lower] - (low_hz - transition)) / transition
            )

        upper = (frequencies > high_hz) & (frequencies <= min(nyquist_hz, high_hz + transition))
        mask[upper] = 0.5 + 0.5 * np.cos(
            math.pi * (frequencies[upper] - high_hz) / transition
        )

    filtered = np.fft.irfft(spectrum * mask, n=fft_size)
    return filtered[pad_samples : pad_samples + array.size].astype(np.float64, copy=False)


def analyze_chirp_response(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    chirp: ChirpSpec,
    *,
    pre_roll_seconds: float,
    post_roll_seconds: float,
) -> ChirpDspAnalysis:
    """Compute Phase 2 DSP features from a recorded active chirp probe."""

    raw = _as_mono_float64(samples)
    if raw.size == 0:
        raise ValueError("samples must not be empty.")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")

    nyquist_hz = sample_rate_hz / 2.0
    bandpass_low_hz = max(40.0, chirp.start_hz * 0.6)
    bandpass_high_hz = min(nyquist_hz * 0.98, chirp.end_hz * 1.25)
    if bandpass_low_hz >= bandpass_high_hz:
        bandpass_low_hz = max(20.0, min(chirp.start_hz, nyquist_hz * 0.45))
        bandpass_high_hz = min(nyquist_hz * 0.98, max(chirp.end_hz, bandpass_low_hz + 100.0))

    filtered = apply_fft_bandpass(raw, sample_rate_hz, bandpass_low_hz, bandpass_high_hz)
    reference = generate_log_chirp(chirp, sample_rate_hz)
    expected_start_sample = max(0, int(round(pre_roll_seconds * sample_rate_hz)))
    alignment = align_chirp(
        filtered,
        reference,
        sample_rate_hz,
        expected_start_sample=expected_start_sample,
    )

    chirp_start = min(max(0, alignment.selected_start_sample), raw.size)
    chirp_end = min(raw.size, chirp_start + reference.size)
    post_start = chirp_end
    post_end = min(
        raw.size,
        post_start + max(0, int(round(post_roll_seconds * sample_rate_hz))),
    )
    chirp_window = _slice_with_padding(filtered, chirp_start, reference.size)
    post_window = filtered[post_start:post_end]
    minimum_post_samples = max(64, int(MIN_POST_WINDOW_SECONDS * sample_rate_hz))
    if post_window.size < minimum_post_samples:
        post_start = min(raw.size, max(post_start, expected_start_sample + reference.size))
        post_end = raw.size
        post_window = filtered[post_start:post_end]

    signal_to_noise_db = _estimate_snr_db(
        filtered,
        signal_start=chirp_start,
        signal_end=chirp_end,
        noise_end=min(expected_start_sample, chirp_start),
    )
    spectrum_window = post_window if post_window.size >= 64 else chirp_window
    fft = compute_spectral_summary(
        spectrum_window,
        sample_rate_hz,
        min_hz=max(20.0, chirp.start_hz * 0.5),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.35, chirp.start_hz + 100.0)),
    )
    transfer_response = compute_transfer_response(
        chirp_window,
        reference,
        sample_rate_hz,
        min_hz=chirp.start_hz,
        max_hz=min(chirp.end_hz, nyquist_hz),
    )
    peaks = find_dominant_peaks(
        spectrum_window,
        sample_rate_hz,
        min_hz=max(80.0, chirp.start_hz * 0.5),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.25, chirp.start_hz + 100.0)),
    )
    stft = compute_stft_grid(
        filtered,
        sample_rate_hz,
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.25, 2000.0)),
    )
    mel = compute_mel_spectrogram(
        filtered,
        sample_rate_hz,
        min_hz=max(20.0, chirp.start_hz * 0.4),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.25, 2000.0)),
    )
    decay = estimate_decay(
        post_window,
        sample_rate_hz,
        window_start_seconds=post_start / sample_rate_hz,
    )

    return ChirpDspAnalysis(
        bandpass_low_hz=bandpass_low_hz,
        bandpass_high_hz=bandpass_high_hz,
        signal_to_noise_db=signal_to_noise_db,
        alignment=alignment,
        fft=fft,
        stft=stft,
        mel_spectrogram=mel,
        transfer_response=transfer_response,
        dominant_peaks=peaks,
        decay=decay,
    )


def align_chirp(
    samples: npt.ArrayLike,
    reference_chirp: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    expected_start_sample: int | None = None,
) -> AlignmentResult:
    """Locate a chirp in a recording using normalized matched filtering."""

    recording = _as_mono_float64(samples)
    reference = _as_mono_float64(reference_chirp)
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")
    if recording.size == 0 or reference.size == 0 or recording.size < reference.size:
        selected = max(0, expected_start_sample or 0)
        return AlignmentResult(
            method="matched_filter_log_chirp",
            confidence=0.0,
            detected_start_sample=None,
            expected_start_sample=expected_start_sample,
            selected_start_sample=selected,
            offset_samples=None,
            estimated_latency_ms=None,
            detected_start_seconds=None,
            expected_start_seconds=_seconds_or_none(expected_start_sample, sample_rate_hz),
        )

    centered_recording = recording - float(np.mean(recording))
    centered_reference = reference - float(np.mean(reference))
    reference_norm = float(np.linalg.norm(centered_reference))
    if reference_norm <= EPSILON:
        selected = max(0, expected_start_sample or 0)
        return AlignmentResult(
            method="matched_filter_log_chirp",
            confidence=0.0,
            detected_start_sample=None,
            expected_start_sample=expected_start_sample,
            selected_start_sample=selected,
            offset_samples=None,
            estimated_latency_ms=None,
            detected_start_seconds=None,
            expected_start_seconds=_seconds_or_none(expected_start_sample, sample_rate_hz),
        )

    valid_correlation = _valid_cross_correlation(centered_recording, centered_reference)
    window_energy = _rolling_energy(centered_recording, centered_reference.size)
    denominator = reference_norm * np.sqrt(np.maximum(window_energy, EPSILON))
    normalized = valid_correlation / denominator

    best_index = int(np.argmax(np.abs(normalized)))
    confidence = float(np.clip(abs(normalized[best_index]), 0.0, 1.0))
    detected_start_sample = best_index
    offset_samples = (
        None if expected_start_sample is None else detected_start_sample - expected_start_sample
    )
    selected_start_sample = _select_alignment_start(
        confidence=confidence,
        detected_start_sample=detected_start_sample,
        expected_start_sample=expected_start_sample,
        recording_size=recording.size,
        reference_size=reference.size,
    )

    estimated_latency_ms = None
    if offset_samples is not None:
        estimated_latency_ms = offset_samples * 1000.0 / sample_rate_hz

    return AlignmentResult(
        method="matched_filter_log_chirp",
        confidence=confidence,
        detected_start_sample=detected_start_sample,
        expected_start_sample=expected_start_sample,
        selected_start_sample=selected_start_sample,
        offset_samples=offset_samples,
        estimated_latency_ms=estimated_latency_ms,
        detected_start_seconds=detected_start_sample / sample_rate_hz,
        expected_start_seconds=_seconds_or_none(expected_start_sample, sample_rate_hz),
    )


def compute_spectral_summary(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float = 20.0,
    max_hz: float | None = None,
    max_points: int = 256,
) -> SpectralSummary:
    """Compute compact FFT data and basic spectral descriptors."""

    frequencies, magnitude_db, magnitude_linear = _magnitude_spectrum(
        samples,
        sample_rate_hz,
        min_hz=min_hz,
        max_hz=max_hz,
    )
    if frequencies.size == 0:
        return SpectralSummary(
            series=FrequencySeries(frequency_bins_hz=[], magnitude_db=[]),
            centroid_hz=None,
            bandwidth_hz=None,
            rolloff_hz=None,
            spectral_floor_db=None,
        )

    indices = _compact_indices(frequencies.size, max_points)
    weights = np.square(magnitude_linear)
    weight_sum = float(np.sum(weights))
    if weight_sum <= EPSILON:
        centroid = None
        bandwidth = None
        rolloff = None
    else:
        centroid_value = float(np.sum(frequencies * weights) / weight_sum)
        bandwidth_value = float(
            np.sqrt(np.sum(((frequencies - centroid_value) ** 2) * weights) / weight_sum)
        )
        cumulative = np.cumsum(weights)
        rolloff_index = int(np.searchsorted(cumulative, 0.95 * cumulative[-1], side="left"))
        centroid = centroid_value
        bandwidth = bandwidth_value
        rolloff = float(frequencies[min(rolloff_index, frequencies.size - 1)])

    return SpectralSummary(
        series=FrequencySeries(
            frequency_bins_hz=_float_list(frequencies[indices]),
            magnitude_db=_float_list(magnitude_db[indices]),
        ),
        centroid_hz=centroid,
        bandwidth_hz=bandwidth,
        rolloff_hz=rolloff,
        spectral_floor_db=float(np.percentile(magnitude_db, 20.0)),
    )


def compute_stft_grid(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    max_hz: float | None = None,
    window_size: int = 1024,
    hop_size: int = 256,
    max_time_bins: int = 120,
    max_frequency_bins: int = 128,
) -> SpectrogramGrid:
    """Compute a compact linear-frequency STFT magnitude grid."""

    times, frequencies, power = _stft_power(
        samples,
        sample_rate_hz,
        window_size=window_size,
        hop_size=hop_size,
    )
    if power.size == 0:
        return SpectrogramGrid(kind="stft", times_seconds=[], frequency_bins_hz=[], magnitude_db=[])

    if max_hz is not None:
        frequency_mask = frequencies <= max_hz
        frequencies = frequencies[frequency_mask]
        power = power[frequency_mask, :]

    frequency_indices = _compact_indices(frequencies.size, max_frequency_bins)
    time_indices = _compact_indices(times.size, max_time_bins)
    magnitude_db = _power_to_db(power[np.ix_(frequency_indices, time_indices)])

    return SpectrogramGrid(
        kind="stft",
        times_seconds=_float_list(times[time_indices]),
        frequency_bins_hz=_float_list(frequencies[frequency_indices]),
        magnitude_db=[_float_list(row) for row in magnitude_db],
    )


def compute_mel_spectrogram(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float,
    mel_bins: int = 40,
    window_size: int = 1024,
    hop_size: int = 256,
    max_time_bins: int = 120,
) -> SpectrogramGrid:
    """Compute a compact mel-spectrogram without importing librosa."""

    times, frequencies, power = _stft_power(
        samples,
        sample_rate_hz,
        window_size=window_size,
        hop_size=hop_size,
    )
    if power.size == 0:
        return SpectrogramGrid(kind="mel", times_seconds=[], frequency_bins_hz=[], magnitude_db=[])

    filters, centers = _mel_filterbank(
        sample_rate_hz=sample_rate_hz,
        frequencies=frequencies,
        min_hz=min_hz,
        max_hz=max_hz,
        mel_bins=mel_bins,
    )
    mel_power = filters @ power
    time_indices = _compact_indices(times.size, max_time_bins)
    magnitude_db = _power_to_db(mel_power[:, time_indices])

    return SpectrogramGrid(
        kind="mel",
        times_seconds=_float_list(times[time_indices]),
        frequency_bins_hz=_float_list(centers),
        magnitude_db=[_float_list(row) for row in magnitude_db],
    )


def compute_transfer_response(
    captured_chirp: npt.ArrayLike,
    reference_chirp: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float,
    bands_hz: tuple[tuple[float, float], ...] = DEFAULT_TRANSFER_BANDS_HZ,
) -> list[TransferBand]:
    """Estimate regularized transfer-response magnitude by frequency band."""

    captured = _as_mono_float64(captured_chirp)
    reference = _as_mono_float64(reference_chirp)
    if captured.size == 0 or reference.size == 0:
        return []

    size = max(captured.size, reference.size)
    captured = _slice_with_padding(captured, 0, size)
    reference = _slice_with_padding(reference, 0, size)
    window = np.hanning(size)
    if np.all(window == 0):
        window = np.ones(size)

    captured_spectrum = np.fft.rfft((captured - np.mean(captured)) * window)
    reference_spectrum = np.fft.rfft((reference - np.mean(reference)) * window)
    frequencies = np.fft.rfftfreq(size, d=1.0 / sample_rate_hz)
    response_db = 20.0 * np.log10(
        (np.abs(captured_spectrum) + EPSILON) / (np.abs(reference_spectrum) + EPSILON)
    )

    nyquist_hz = sample_rate_hz / 2.0
    constrained_max = min(max_hz, nyquist_hz)
    transfer_bands: list[TransferBand] = []
    for band_start, band_end in bands_hz:
        start = max(min_hz, band_start)
        end = min(constrained_max, band_end)
        if start >= end:
            continue
        mask = (frequencies >= start) & (frequencies < end)
        if not np.any(mask):
            continue
        values = response_db[mask]
        transfer_bands.append(
            TransferBand(
                start_hz=float(start),
                end_hz=float(end),
                center_hz=float((start + end) / 2.0),
                mean_db=float(np.mean(values)),
                peak_db=float(np.max(values)),
            )
        )

    return transfer_bands


def find_dominant_peaks(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float,
    max_peaks: int = 5,
    min_prominence_db: float = 6.0,
    min_distance_hz: float = 120.0,
) -> list[PeakFeature]:
    """Find dominant spectral peaks with simple local-max and spacing rules."""

    frequencies, magnitude_db, magnitude_linear = _magnitude_spectrum(
        samples,
        sample_rate_hz,
        min_hz=min_hz,
        max_hz=max_hz,
    )
    if frequencies.size < 3:
        return []

    baseline_db = float(np.percentile(magnitude_db, 35.0))
    candidates: list[tuple[float, int]] = []
    for index in range(1, magnitude_db.size - 1):
        value = magnitude_db[index]
        if value < baseline_db + min_prominence_db:
            continue
        if value >= magnitude_db[index - 1] and value >= magnitude_db[index + 1]:
            candidates.append((float(value), index))

    selected: list[int] = []
    for _, index in sorted(candidates, reverse=True):
        frequency = frequencies[index]
        if all(abs(frequency - frequencies[chosen]) >= min_distance_hz for chosen in selected):
            selected.append(index)
        if len(selected) >= max_peaks:
            break

    peaks: list[PeakFeature] = []
    for index in selected:
        peak_frequency = _quadratic_peak_frequency(frequencies, magnitude_db, index)
        q_factor = _estimate_q_factor(frequencies, magnitude_linear, index)
        peaks.append(
            PeakFeature(
                frequency_hz=peak_frequency,
                magnitude_db=float(magnitude_db[index]),
                prominence_db=float(magnitude_db[index] - baseline_db),
                q_factor=q_factor,
            )
        )

    return sorted(peaks, key=lambda peak: peak.magnitude_db, reverse=True)


def estimate_decay(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    window_start_seconds: float,
    frame_seconds: float = 0.01,
    hop_seconds: float = 0.005,
) -> DecayEstimate:
    """Fit an exponential decay to the RMS envelope of a post-chirp window."""

    array = _as_mono_float64(samples)
    window_duration_seconds = array.size / sample_rate_hz if sample_rate_hz > 0 else 0.0
    window_end_seconds = window_start_seconds + window_duration_seconds
    if array.size == 0 or sample_rate_hz <= 0:
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )

    frame_size = max(8, int(round(frame_seconds * sample_rate_hz)))
    hop_size = max(1, int(round(hop_seconds * sample_rate_hz)))
    times, envelope = _rms_envelope(array, sample_rate_hz, frame_size, hop_size)
    if envelope.size < 4:
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )

    peak_index = int(np.argmax(envelope))
    fit_times = times[peak_index:]
    fit_envelope = envelope[peak_index:]
    floor = max(
        float(np.percentile(envelope, 20.0)) * 1.5,
        float(np.max(envelope)) * 0.015,
        EPSILON,
    )
    fit_mask = fit_envelope > floor
    if int(np.sum(fit_mask)) < 4:
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )

    x = fit_times[fit_mask]
    y = np.log(np.maximum(fit_envelope[fit_mask], EPSILON))
    design = np.column_stack([x, np.ones_like(x)])
    slope, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = slope * x + intercept
    residual_sum = float(np.sum((y - predicted) ** 2))
    total_sum = float(np.sum((y - np.mean(y)) ** 2))
    fit_r2 = 1.0 - residual_sum / total_sum if total_sum > EPSILON else None

    if slope >= 0:
        decay_rate = None
        rt60 = None
        fit_r2 = None
    else:
        decay_rate = float(-slope)
        rt60 = float(math.log(1000.0) / decay_rate) if decay_rate > EPSILON else None

    return DecayEstimate(
        method="rms_envelope_log_linear",
        decay_rate_per_second=decay_rate,
        rt60_seconds=rt60,
        fit_r2=None if fit_r2 is None else float(min(fit_r2, 1.0)),
        window_start_seconds=window_start_seconds,
        window_end_seconds=window_end_seconds,
    )


def _as_mono_float64(samples: npt.ArrayLike) -> npt.NDArray[np.float64]:
    array = np.asarray(samples, dtype=np.float64)
    if array.ndim > 1:
        array = np.mean(array, axis=1)
    return np.nan_to_num(array.reshape(-1), copy=False)


def _cosine_fade(sample_count: int, fade_samples: int) -> npt.NDArray[np.float64]:
    fade_samples = min(fade_samples, sample_count // 2)
    gains = np.ones(sample_count, dtype=np.float64)
    if fade_samples <= 0:
        return gains

    ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, math.pi, fade_samples, endpoint=True))
    gains[:fade_samples] *= ramp
    gains[-fade_samples:] *= ramp[::-1]
    return gains


def _valid_cross_correlation(
    recording: npt.NDArray[np.float64],
    reference: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    size = recording.size + reference.size - 1
    fft_size = 1 << (size - 1).bit_length()
    correlation = np.fft.irfft(
        np.fft.rfft(recording, n=fft_size) * np.fft.rfft(reference[::-1], n=fft_size),
        n=fft_size,
    )[:size]
    return correlation[reference.size - 1 : recording.size]


def _rolling_energy(samples: npt.NDArray[np.float64], window_size: int) -> npt.NDArray[np.float64]:
    squared = np.square(samples)
    cumulative = np.concatenate([[0.0], np.cumsum(squared)])
    return cumulative[window_size:] - cumulative[:-window_size]


def _select_alignment_start(
    *,
    confidence: float,
    detected_start_sample: int,
    expected_start_sample: int | None,
    recording_size: int,
    reference_size: int,
) -> int:
    max_start = max(0, recording_size - reference_size)
    if confidence >= ALIGNMENT_ACCEPT_CONFIDENCE:
        return min(max_start, max(0, detected_start_sample))
    if expected_start_sample is not None:
        return min(max_start, max(0, expected_start_sample))
    return min(max_start, max(0, detected_start_sample))


def _slice_with_padding(
    samples: npt.ArrayLike,
    start: int,
    length: int,
) -> npt.NDArray[np.float64]:
    array = _as_mono_float64(samples)
    start = max(0, int(start))
    length = max(0, int(length))
    output = np.zeros(length, dtype=np.float64)
    if length == 0 or start >= array.size:
        return output

    available = min(length, array.size - start)
    output[:available] = array[start : start + available]
    return output


def _estimate_snr_db(
    samples: npt.NDArray[np.float64],
    *,
    signal_start: int,
    signal_end: int,
    noise_end: int,
) -> float | None:
    signal = samples[max(0, signal_start) : max(signal_start, signal_end)]
    noise = samples[: max(0, min(noise_end, samples.size))]
    if signal.size == 0 or noise.size < 8:
        return None
    signal_rms = _rms(signal)
    noise_rms = _rms(noise)
    return float(20.0 * math.log10((signal_rms + EPSILON) / (noise_rms + EPSILON)))


def _magnitude_spectrum(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float | None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    array = _as_mono_float64(samples)
    if array.size == 0 or sample_rate_hz <= 0:
        return np.array([]), np.array([]), np.array([])

    window = np.hanning(array.size)
    if np.all(window == 0):
        window = np.ones(array.size)
    centered = array - float(np.mean(array))
    spectrum = np.fft.rfft(centered * window)
    frequencies = np.fft.rfftfreq(array.size, d=1.0 / sample_rate_hz)
    magnitude = np.abs(spectrum) / max(float(np.sum(window)) / 2.0, EPSILON)
    magnitude_db = 20.0 * np.log10(magnitude + EPSILON)

    high = sample_rate_hz / 2.0 if max_hz is None else min(max_hz, sample_rate_hz / 2.0)
    mask = (frequencies >= min_hz) & (frequencies <= high)
    return frequencies[mask], magnitude_db[mask], magnitude[mask]


def _stft_power(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    window_size: int,
    hop_size: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    array = _as_mono_float64(samples)
    if array.size == 0 or sample_rate_hz <= 0:
        return np.array([]), np.array([]), np.empty((0, 0))

    # Round tiny inputs up to a power-of-two window so compact visualization grids stay
    # stable without requesting an oversized FFT for short fallback windows.
    max_window_size = max(64, int(2 ** math.ceil(math.log2(max(64, array.size)))))
    window_size = min(max(64, int(window_size)), max_window_size)
    hop_size = max(1, int(hop_size))
    if array.size < window_size:
        array = np.pad(array, (0, window_size - array.size))

    frame_count = 1 + max(0, (array.size - window_size) // hop_size)
    window = np.hanning(window_size)
    frequencies = np.fft.rfftfreq(window_size, d=1.0 / sample_rate_hz)
    power = np.empty((frequencies.size, frame_count), dtype=np.float64)
    times = np.empty(frame_count, dtype=np.float64)

    for frame_index in range(frame_count):
        start = frame_index * hop_size
        frame = array[start : start + window_size]
        spectrum = np.fft.rfft((frame - np.mean(frame)) * window)
        power[:, frame_index] = np.square(np.abs(spectrum))
        times[frame_index] = (start + window_size / 2.0) / sample_rate_hz

    return times, frequencies, power


def _mel_filterbank(
    *,
    sample_rate_hz: int,
    frequencies: npt.NDArray[np.float64],
    min_hz: float,
    max_hz: float,
    mel_bins: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    nyquist_hz = sample_rate_hz / 2.0
    min_hz = max(0.0, min(min_hz, nyquist_hz))
    max_hz = min(max_hz, nyquist_hz)
    if min_hz >= max_hz:
        max_hz = min(nyquist_hz, min_hz + max(100.0, nyquist_hz * 0.1))

    mel_points = np.linspace(_hz_to_mel(min_hz), _hz_to_mel(max_hz), mel_bins + 2)
    hz_points = _mel_to_hz(mel_points)
    filters = np.zeros((mel_bins, frequencies.size), dtype=np.float64)

    for mel_index in range(mel_bins):
        left, center, right = hz_points[mel_index : mel_index + 3]
        if center <= left or right <= center:
            continue
        lower = (frequencies >= left) & (frequencies <= center)
        upper = (frequencies >= center) & (frequencies <= right)
        filters[mel_index, lower] = (frequencies[lower] - left) / (center - left)
        filters[mel_index, upper] = (right - frequencies[upper]) / (right - center)
        total = np.sum(filters[mel_index])
        if total > EPSILON:
            filters[mel_index] /= total

    return filters, hz_points[1:-1]


def _hz_to_mel(hz: float | npt.NDArray[np.float64]) -> float | npt.NDArray[np.float64]:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return 700.0 * (np.power(10.0, mel / 2595.0) - 1.0)


def _power_to_db(power: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return 10.0 * np.log10(np.maximum(power, EPSILON))


def _compact_indices(size: int, max_points: int) -> npt.NDArray[np.int_]:
    if size <= 0:
        return np.array([], dtype=int)
    if size <= max_points:
        return np.arange(size, dtype=int)
    return np.unique(np.linspace(0, size - 1, max_points).round().astype(int))


def _next_power_of_two(size: int) -> int:
    return 1 << (max(1, int(size)) - 1).bit_length()


def _quadratic_peak_frequency(
    frequencies: npt.NDArray[np.float64],
    values_db: npt.NDArray[np.float64],
    index: int,
) -> float:
    # The windowed FFT peak is closer to parabolic on a log-magnitude scale for display
    # and dominant-resonance tracking, so interpolate on dB values intentionally.
    if index <= 0 or index >= values_db.size - 1:
        return float(frequencies[index])

    alpha = values_db[index - 1]
    beta = values_db[index]
    gamma = values_db[index + 1]
    denominator = alpha - 2.0 * beta + gamma
    if abs(denominator) <= EPSILON:
        return float(frequencies[index])

    bin_delta = 0.5 * (alpha - gamma) / denominator
    bin_delta = float(np.clip(bin_delta, -0.5, 0.5))
    bin_width = frequencies[1] - frequencies[0] if frequencies.size > 1 else 0.0
    return float(frequencies[index] + bin_delta * bin_width)


def _estimate_q_factor(
    frequencies: npt.NDArray[np.float64],
    magnitude_linear: npt.NDArray[np.float64],
    peak_index: int,
) -> float | None:
    if magnitude_linear.size < 3:
        return None

    half_power = magnitude_linear[peak_index] / math.sqrt(2.0)
    left = peak_index
    while left > 0 and magnitude_linear[left] > half_power:
        left -= 1
    right = peak_index
    while right < magnitude_linear.size - 1 and magnitude_linear[right] > half_power:
        right += 1

    if left == 0 or right == magnitude_linear.size - 1:
        return None

    left_frequency = _interpolated_threshold_frequency(
        frequencies,
        magnitude_linear,
        left,
        left + 1,
        half_power,
    )
    right_frequency = _interpolated_threshold_frequency(
        frequencies,
        magnitude_linear,
        right - 1,
        right,
        half_power,
    )
    if left_frequency is None or right_frequency is None:
        return None

    peak_frequency = _quadratic_peak_frequency(
        frequencies,
        20.0 * np.log10(np.maximum(magnitude_linear, EPSILON)),
        peak_index,
    )
    bandwidth = right_frequency - left_frequency
    if bandwidth <= EPSILON:
        return None
    return float(peak_frequency / bandwidth)


def _interpolated_threshold_frequency(
    frequencies: npt.NDArray[np.float64],
    values: npt.NDArray[np.float64],
    low_index: int,
    high_index: int,
    threshold: float,
) -> float | None:
    low_value = values[low_index]
    high_value = values[high_index]
    denominator = high_value - low_value
    if abs(denominator) <= EPSILON:
        return None

    fraction = float(np.clip((threshold - low_value) / denominator, 0.0, 1.0))
    return float(
        frequencies[low_index] + fraction * (frequencies[high_index] - frequencies[low_index])
    )


def _rms_envelope(
    samples: npt.NDArray[np.float64],
    sample_rate_hz: int,
    frame_size: int,
    hop_size: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    if samples.size < frame_size:
        samples = np.pad(samples, (0, frame_size - samples.size))

    frame_count = 1 + max(0, (samples.size - frame_size) // hop_size)
    envelope = np.empty(frame_count, dtype=np.float64)
    times = np.empty(frame_count, dtype=np.float64)
    for frame_index in range(frame_count):
        start = frame_index * hop_size
        frame = samples[start : start + frame_size]
        envelope[frame_index] = _rms(frame)
        times[frame_index] = (start + frame_size / 2.0) / sample_rate_hz
    return times, envelope


def _rms(samples: npt.NDArray[np.float64]) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def _seconds_or_none(sample: int | None, sample_rate_hz: int) -> float | None:
    if sample is None:
        return None
    return sample / sample_rate_hz


def _float_list(values: npt.ArrayLike) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64)]
