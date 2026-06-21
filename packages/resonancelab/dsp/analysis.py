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
ALIGNMENT_WARN_CONFIDENCE = ALIGNMENT_ACCEPT_CONFIDENCE
SNR_WARN_DB = 12.0
MIN_POST_WINDOW_SECONDS = 0.10
MIN_NOISE_WINDOW_SECONDS = 0.05
MIN_DECAY_FIT_POINTS = 6
MIN_DECAY_DYNAMIC_RANGE_DB = 6.0
TRANSFER_RESPONSE_REGULARIZATION = 1e-4
IMPULSE_RESPONSE_MAX_SECONDS = 0.18
IMPULSE_RESPONSE_MAX_POINTS = 192
LOW_FREQUENCY_MODE_MAX_HZ = 500.0
LOW_MODE_GROUP_WIDTH_HZ = 120.0
VERY_HIGH_Q_THRESHOLD = 300.0
DIRECT_PATH_DOMINANCE_DB = 12.0
LATE_RESPONSE_DOMINANCE_DB = -6.0
AMBIGUOUS_DIRECT_PATH_SECONDS = 0.025
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
DEFAULT_DECAY_BANDS_HZ = (
    ("low", 100.0, 500.0),
    ("mid", 500.0, 2000.0),
    ("high", 2000.0, 8000.0),
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
class ResponseTrace:
    """Compact response envelope proxy for report visualization."""

    method: Literal["regularized_deconvolution", "matched_filter_envelope"]
    times_seconds: list[float]
    magnitude_db: list[float]
    regularization: float
    peak_time_seconds: float | None = None
    direct_to_late_db: float | None = None


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
class DecayBandEstimate:
    """Band-limited decay estimate for low/mid/high report comparisons."""

    label: Literal["low", "mid", "high"]
    start_hz: float
    end_hz: float
    decay_rate_per_second: float | None
    rt60_seconds: float | None
    fit_r2: float | None


@dataclass(frozen=True)
class MfccCoefficientSummary:
    """Time-summary statistics for one cepstral coefficient."""

    index: int
    mean: float
    std: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class MfccSummary:
    """Compact MFCC summary from log-mel energy and an orthonormal DCT-II."""

    method: Literal["log_mel_dct_ii"]
    coefficients: list[MfccCoefficientSummary]


@dataclass(frozen=True)
class ModeGroup:
    """Grouped low-frequency modal evidence with review labels."""

    start_hz: float
    end_hz: float
    center_hz: float
    peak_count: int
    frequencies_hz: list[float]
    dominant_frequency_hz: float
    max_prominence_db: float
    q_factor: float | None
    warning_labels: list[str]


@dataclass(frozen=True)
class ResponseCaveat:
    """Measured-response caveat derived from DSP evidence."""

    id: str
    severity: Literal["info", "review", "warning"]
    message: str


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
    impulse_response: ResponseTrace
    matched_response: ResponseTrace
    mfcc: MfccSummary
    dominant_peaks: list[PeakFeature]
    mode_groups: list[ModeGroup]
    decay: DecayEstimate
    decay_bands: list[DecayBandEstimate]
    response_caveats: list[ResponseCaveat]


def generate_log_chirp(spec: ChirpSpec, sample_rate_hz: int) -> npt.NDArray[np.float64]:
    """Generate the same cosine-tapered logarithmic chirp used by the browser."""

    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")
    if spec.start_hz <= 0 or spec.end_hz <= spec.start_hz:
        raise ValueError("chirp frequencies must satisfy 0 < start_hz < end_hz.")
    if spec.end_hz >= sample_rate_hz / 2.0:
        raise ValueError("chirp end_hz must be lower than the Nyquist frequency.")
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
    post_window_usable = post_window.size >= minimum_post_samples

    noise_end_candidates = [expected_start_sample, chirp_start]
    if alignment.detected_start_sample is not None:
        noise_end_candidates.append(alignment.detected_start_sample)
    signal_to_noise_db = _estimate_snr_db(
        filtered,
        sample_rate_hz=sample_rate_hz,
        signal_start=chirp_start,
        signal_end=chirp_end,
        noise_end=min(noise_end_candidates),
    )
    spectrum_window = post_window if post_window_usable else chirp_window
    fft = compute_spectral_summary(
        spectrum_window,
        sample_rate_hz,
        min_hz=max(20.0, chirp.start_hz * 0.5),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.35, chirp.start_hz + 100.0)),
    )
    response_window = _slice_with_padding(
        filtered,
        chirp_start,
        max(reference.size, post_end - chirp_start),
    )
    transfer_response = compute_transfer_response(
        response_window,
        reference,
        sample_rate_hz,
        min_hz=chirp.start_hz,
        max_hz=min(chirp.end_hz, nyquist_hz),
    )
    impulse_response = compute_impulse_response(
        response_window,
        reference,
        sample_rate_hz,
    )
    matched_response = compute_matched_response(
        response_window,
        reference,
        sample_rate_hz,
    )
    peaks = find_dominant_peaks(
        spectrum_window,
        sample_rate_hz,
        min_hz=max(80.0, chirp.start_hz * 0.5),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.25, chirp.start_hz + 100.0)),
    )
    mode_groups = group_low_frequency_modes(peaks)
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
    mfcc = compute_mfcc_summary(
        spectrum_window,
        sample_rate_hz,
        min_hz=max(20.0, chirp.start_hz * 0.4),
        max_hz=min(nyquist_hz, max(chirp.end_hz * 1.25, 8000.0)),
    )
    decay = estimate_decay(
        post_window,
        sample_rate_hz,
        window_start_seconds=post_start / sample_rate_hz,
    )
    decay_bands = estimate_decay_bands(
        post_window,
        sample_rate_hz,
        window_start_seconds=post_start / sample_rate_hz,
        max_hz=min(nyquist_hz * 0.98, max(chirp.end_hz, 8000.0)),
    )
    response_caveats = build_response_caveats(
        alignment=alignment,
        signal_to_noise_db=signal_to_noise_db,
        matched_response=matched_response,
        impulse_response=impulse_response,
        decay=decay,
        peaks=peaks,
        mode_groups=mode_groups,
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
        impulse_response=impulse_response,
        matched_response=matched_response,
        mfcc=mfcc,
        dominant_peaks=peaks,
        mode_groups=mode_groups,
        decay=decay,
        decay_bands=decay_bands,
        response_caveats=response_caveats,
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


def compute_mfcc_summary(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float,
    coefficient_count: int = 13,
    mel_bins: int = 32,
    window_size: int = 1024,
    hop_size: int = 256,
) -> MfccSummary:
    """Compute compact MFCC summary statistics from log-mel frame energies.

    The coefficients use an orthonormal DCT-II over natural-log mel energies.
    C0 is the scaled log-energy/DC cepstral term under that orthonormal basis.
    These values summarize the spectral envelope of the analysis window; they
    are not speaker-independent speech-recognition features in this project.
    """

    times, frequencies, power = _stft_power(
        samples,
        sample_rate_hz,
        window_size=window_size,
        hop_size=hop_size,
    )
    if power.size == 0 or times.size == 0:
        return MfccSummary(method="log_mel_dct_ii", coefficients=[])

    filters, _ = _mel_filterbank(
        sample_rate_hz=sample_rate_hz,
        frequencies=frequencies,
        min_hz=min_hz,
        max_hz=max_hz,
        mel_bins=mel_bins,
    )
    mel_power = filters @ power
    if mel_power.size == 0:
        return MfccSummary(method="log_mel_dct_ii", coefficients=[])

    log_mel = np.log(np.maximum(mel_power, EPSILON))
    coefficient_count = max(1, min(int(coefficient_count), log_mel.shape[0]))
    cepstra = _dct_type_ii_ortho(log_mel, coefficient_count)
    coefficients = [
        MfccCoefficientSummary(
            index=index,
            mean=float(np.mean(values)),
            std=float(np.std(values)),
            minimum=float(np.min(values)),
            maximum=float(np.max(values)),
        )
        for index, values in enumerate(cepstra)
    ]
    return MfccSummary(method="log_mel_dct_ii", coefficients=coefficients)


def compute_transfer_response(
    captured_response: npt.ArrayLike,
    reference_chirp: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    min_hz: float,
    max_hz: float,
    bands_hz: tuple[tuple[float, float], ...] = DEFAULT_TRANSFER_BANDS_HZ,
    regularization: float = TRANSFER_RESPONSE_REGULARIZATION,
) -> list[TransferBand]:
    """Estimate a regularized driven-path transfer response by frequency band.

    The estimate uses the chirp and the captured response window, including post-chirp
    ring-down when available. It is still a same-setup acoustic path feature, not an
    isolated target transfer function.
    """

    captured = _as_mono_float64(captured_response)
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
    reference_power = np.square(np.abs(reference_spectrum))
    regularizer = max(0.0, regularization) * max(float(np.max(reference_power)), EPSILON)
    response = (
        captured_spectrum
        * np.conj(reference_spectrum)
        / (reference_power + regularizer + EPSILON)
    )
    response_db = 20.0 * np.log10(np.abs(response) + EPSILON)

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


def compute_impulse_response(
    captured_response: npt.ArrayLike,
    reference_chirp: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    regularization: float = TRANSFER_RESPONSE_REGULARIZATION,
    max_seconds: float = IMPULSE_RESPONSE_MAX_SECONDS,
    max_points: int = IMPULSE_RESPONSE_MAX_POINTS,
) -> ResponseTrace:
    """Compute a compact regularized deconvolution impulse-envelope proxy.

    The FFT is padded for linear deconvolution, not circular deconvolution, and the
    returned trace is a local RMS envelope normalized after compaction. It is a
    single-device acoustic fingerprint feature, not a spatial impulse response or
    geometry estimate.
    """

    captured = _as_mono_float64(captured_response)
    reference = _as_mono_float64(reference_chirp)
    regularization_value = max(0.0, regularization)
    if captured.size == 0 or reference.size == 0 or sample_rate_hz <= 0:
        return ResponseTrace(
            method="regularized_deconvolution",
            times_seconds=[],
            magnitude_db=[],
            regularization=regularization_value,
        )

    fft_size = _next_power_of_two(captured.size + reference.size - 1)
    captured_centered = captured - float(np.mean(captured))
    reference_centered = reference - float(np.mean(reference))
    if (
        float(np.linalg.norm(captured_centered)) <= EPSILON
        or float(np.linalg.norm(reference_centered)) <= EPSILON
    ):
        return ResponseTrace(
            method="regularized_deconvolution",
            times_seconds=[],
            magnitude_db=[],
            regularization=regularization_value,
        )
    captured_spectrum = np.fft.rfft(captured_centered, n=fft_size)
    reference_spectrum = np.fft.rfft(reference_centered, n=fft_size)
    reference_power = np.square(np.abs(reference_spectrum))
    regularizer = regularization_value * max(float(np.max(reference_power)), EPSILON)
    response = (
        captured_spectrum
        * np.conj(reference_spectrum)
        / (reference_power + regularizer + EPSILON)
    )
    impulse = np.fft.irfft(response, n=fft_size)
    trace_samples = min(
        impulse.size,
        max(1, int(round(max(0.001, max_seconds) * sample_rate_hz))),
    )
    max_points = max(1, int(max_points))
    indices = _compact_indices(trace_samples, max_points)
    envelope_frame = max(8, int(round(0.001 * sample_rate_hz)))
    envelope_frame = min(envelope_frame, trace_samples)
    kernel = np.ones(envelope_frame, dtype=np.float64) / envelope_frame
    envelope_power = np.convolve(np.square(impulse[:trace_samples]), kernel, mode="same")
    envelope = np.sqrt(np.maximum(envelope_power, EPSILON))
    compact_magnitude_db = 20.0 * np.log10(envelope[indices] + EPSILON)
    peak_db = float(np.max(compact_magnitude_db)) if compact_magnitude_db.size else 0.0
    normalized_db = np.maximum(compact_magnitude_db - peak_db, -96.0)
    times = np.arange(trace_samples, dtype=np.float64) / sample_rate_hz
    peak_time_seconds, direct_to_late_db = _response_trace_shape(times, envelope)

    return ResponseTrace(
        method="regularized_deconvolution",
        times_seconds=_float_list(times[indices]),
        magnitude_db=_float_list(normalized_db),
        regularization=regularization_value,
        peak_time_seconds=peak_time_seconds,
        direct_to_late_db=direct_to_late_db,
    )


def compute_matched_response(
    captured_response: npt.ArrayLike,
    reference_chirp: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    max_seconds: float = IMPULSE_RESPONSE_MAX_SECONDS,
    max_points: int = IMPULSE_RESPONSE_MAX_POINTS,
) -> ResponseTrace:
    """Compute a compact matched-filter response envelope.

    This trace is an impulse-like view from chirp correlation. It complements the
    regularized deconvolution trace and keeps the direct-path peak visually explicit.
    """

    captured = _as_mono_float64(captured_response)
    reference = _as_mono_float64(reference_chirp)
    if (
        captured.size == 0
        or reference.size == 0
        or captured.size < reference.size
        or sample_rate_hz <= 0
    ):
        return ResponseTrace(
            method="matched_filter_envelope",
            times_seconds=[],
            magnitude_db=[],
            regularization=0.0,
        )

    captured_centered = captured - float(np.mean(captured))
    reference_centered = reference - float(np.mean(reference))
    reference_norm = float(np.linalg.norm(reference_centered))
    if reference_norm <= EPSILON or float(np.linalg.norm(captured_centered)) <= EPSILON:
        return ResponseTrace(
            method="matched_filter_envelope",
            times_seconds=[],
            magnitude_db=[],
            regularization=0.0,
        )

    correlation = _valid_cross_correlation(captured_centered, reference_centered)
    window_energy = _rolling_energy(captured_centered, reference_centered.size)
    normalized = np.abs(
        correlation / (reference_norm * np.sqrt(np.maximum(window_energy, EPSILON)))
    )
    trace_samples = min(
        normalized.size,
        max(1, int(round(max(0.001, max_seconds) * sample_rate_hz))),
    )
    if trace_samples <= 0:
        return ResponseTrace(
            method="matched_filter_envelope",
            times_seconds=[],
            magnitude_db=[],
            regularization=0.0,
        )

    envelope_frame = max(4, int(round(0.00075 * sample_rate_hz)))
    envelope_frame = min(envelope_frame, trace_samples)
    kernel = np.ones(envelope_frame, dtype=np.float64) / envelope_frame
    envelope_power = np.convolve(np.square(normalized[:trace_samples]), kernel, mode="same")
    envelope = np.sqrt(np.maximum(envelope_power, EPSILON))
    max_points = max(1, int(max_points))
    indices = _compact_indices(trace_samples, max_points)
    compact_magnitude_db = 20.0 * np.log10(envelope[indices] + EPSILON)
    peak_db = float(np.max(compact_magnitude_db)) if compact_magnitude_db.size else 0.0
    normalized_db = np.maximum(compact_magnitude_db - peak_db, -96.0)
    times = np.arange(trace_samples, dtype=np.float64) / sample_rate_hz
    peak_time_seconds, direct_to_late_db = _response_trace_shape(times, envelope)

    return ResponseTrace(
        method="matched_filter_envelope",
        times_seconds=_float_list(times[indices]),
        magnitude_db=_float_list(normalized_db),
        regularization=0.0,
        peak_time_seconds=peak_time_seconds,
        direct_to_late_db=direct_to_late_db,
    )


def estimate_decay_bands(
    samples: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    window_start_seconds: float,
    max_hz: float,
    bands_hz: tuple[
        tuple[Literal["low", "mid", "high"], float, float], ...
    ] = DEFAULT_DECAY_BANDS_HZ,
) -> list[DecayBandEstimate]:
    """Estimate low/mid/high decay from band-limited post-chirp windows.

    Each band intentionally receives its own zero-phase FFT mask from the same
    post-window source. The masks are non-overlapping, but filtering can introduce
    symmetric ringing around sharp onsets, so these band RT60 values are
    diagnostics rather than calibrated reverberation measurements.
    """

    array = _as_mono_float64(samples)
    if array.size == 0 or sample_rate_hz <= 0:
        return []

    nyquist_hz = sample_rate_hz / 2.0
    constrained_max = min(max_hz, nyquist_hz * 0.98)
    estimates: list[DecayBandEstimate] = []
    for label, band_start, band_end in bands_hz:
        start = max(20.0, float(band_start))
        end = min(float(band_end), constrained_max)
        if start >= end:
            continue
        try:
            filtered = apply_fft_bandpass(array, sample_rate_hz, start, end)
        except ValueError:
            continue
        decay = estimate_decay(
            filtered,
            sample_rate_hz,
            window_start_seconds=window_start_seconds,
        )
        estimates.append(
            DecayBandEstimate(
                label=label,
                start_hz=start,
                end_hz=end,
                decay_rate_per_second=decay.decay_rate_per_second,
                rt60_seconds=decay.rt60_seconds,
                fit_r2=decay.fit_r2,
            )
        )

    return estimates


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
        q_factor = _estimate_q_factor(
            frequencies,
            magnitude_linear,
            index,
            peak_frequency_hz=peak_frequency,
        )
        peaks.append(
            PeakFeature(
                frequency_hz=peak_frequency,
                magnitude_db=float(magnitude_db[index]),
                prominence_db=float(magnitude_db[index] - baseline_db),
                q_factor=q_factor,
            )
        )

    return sorted(peaks, key=lambda peak: peak.magnitude_db, reverse=True)


def group_low_frequency_modes(
    peaks: list[PeakFeature],
    *,
    max_hz: float = LOW_FREQUENCY_MODE_MAX_HZ,
    group_width_hz: float = LOW_MODE_GROUP_WIDTH_HZ,
) -> list[ModeGroup]:
    """Group low-frequency peak evidence into modal bands with review labels."""

    low_peaks = sorted(
        (peak for peak in peaks if peak.frequency_hz <= max_hz),
        key=lambda peak: peak.frequency_hz,
    )
    if not low_peaks:
        return []

    grouped: list[list[PeakFeature]] = []
    for peak in low_peaks:
        if not grouped:
            grouped.append([peak])
            continue
        previous = grouped[-1]
        previous_frequencies = [item.frequency_hz for item in previous]
        dominant = max(previous, key=lambda item: item.prominence_db)
        candidate_span = max(max(previous_frequencies), peak.frequency_hz) - min(
            min(previous_frequencies),
            peak.frequency_hz,
        )
        if (
            candidate_span <= group_width_hz
            and abs(peak.frequency_hz - dominant.frequency_hz) <= group_width_hz
        ):
            previous.append(peak)
        else:
            grouped.append([peak])

    mode_groups: list[ModeGroup] = []
    for group in grouped:
        dominant = max(group, key=lambda peak: peak.prominence_db)
        frequencies = [peak.frequency_hz for peak in group]
        warning_labels = _mode_group_warning_labels(
            group,
            dominant,
            group_width_hz=group_width_hz,
        )
        start = max(20.0, min(frequencies) - group_width_hz / 2.0)
        end = min(max_hz, max(frequencies) + group_width_hz / 2.0)
        mode_groups.append(
            ModeGroup(
                start_hz=float(start),
                end_hz=float(end),
                center_hz=float(np.mean(frequencies)),
                peak_count=len(group),
                frequencies_hz=_float_list(frequencies),
                dominant_frequency_hz=dominant.frequency_hz,
                max_prominence_db=max(peak.prominence_db for peak in group),
                q_factor=dominant.q_factor,
                warning_labels=warning_labels,
            )
        )

    return sorted(mode_groups, key=lambda group: group.max_prominence_db, reverse=True)


def build_response_caveats(
    *,
    alignment: AlignmentResult,
    signal_to_noise_db: float | None,
    matched_response: ResponseTrace,
    impulse_response: ResponseTrace,
    decay: DecayEstimate,
    peaks: list[PeakFeature],
    mode_groups: list[ModeGroup],
) -> list[ResponseCaveat]:
    """Build compact caveats that separate measured response from interpretation."""

    caveats: list[ResponseCaveat] = []
    if alignment.confidence < ALIGNMENT_WARN_CONFIDENCE:
        caveats.append(
            ResponseCaveat(
                id="weak_alignment",
                severity="warning",
                message=(
                    "Chirp alignment is weak; direct-path timing and room-response "
                    "summaries may be unstable."
                ),
            )
        )
    if signal_to_noise_db is None:
        caveats.append(
            ResponseCaveat(
                id="missing_snr",
                severity="review",
                message=(
                    "SNR was not estimated because the pre-roll noise window was not usable."
                ),
            )
        )
    elif signal_to_noise_db < SNR_WARN_DB:
        caveats.append(
            ResponseCaveat(
                id="low_snr",
                severity="warning",
                message=(
                    f"SNR is below {SNR_WARN_DB:.0f} dB; weak peaks and decay tails "
                    "should be treated as noise-sensitive."
                ),
            )
        )

    if matched_response.peak_time_seconds is None and impulse_response.peak_time_seconds is None:
        caveats.append(
            ResponseCaveat(
                id="missing_response_traces",
                severity="review",
                message="No usable matched or deconvolved response trace was available.",
            )
        )
    else:
        # Matched filtering is the cleaner direct-path timing estimator; the
        # regularized deconvolution trace is used for response-shape balance.
        if (
            matched_response.peak_time_seconds is not None
            and matched_response.peak_time_seconds > AMBIGUOUS_DIRECT_PATH_SECONDS
        ):
            caveats.append(
                ResponseCaveat(
                    id="ambiguous_matched_direct_path",
                    severity="review",
                    message=(
                        "The strongest matched-filter response peak arrives later than "
                        f"{AMBIGUOUS_DIRECT_PATH_SECONDS * 1000:.0f} ms; direct-path "
                        "timing may be affected by alignment, device latency, or reflections."
                    ),
                )
            )
        if matched_response.peak_time_seconds is None:
            caveats.append(
                ResponseCaveat(
                    id="missing_matched_response",
                    severity="review",
                    message="No usable matched-filter response trace was available.",
                )
            )
        if impulse_response.peak_time_seconds is None:
            caveats.append(
                ResponseCaveat(
                    id="missing_deconvolved_response",
                    severity="review",
                    message="No usable regularized deconvolved response trace was available.",
                )
            )
        caveats.extend(_response_balance_caveats("matched", matched_response))
        caveats.extend(_response_balance_caveats("deconvolved", impulse_response))

    if decay.rt60_seconds is None or decay.fit_r2 is None:
        caveats.append(
            ResponseCaveat(
                id="unstable_decay",
                severity="review",
                message="Decay fit did not produce a stable RT60 proxy for this capture.",
            )
        )
    elif decay.fit_r2 < 0.35:
        caveats.append(
            ResponseCaveat(
                id="weak_decay_fit",
                severity="review",
                message="Decay fit quality is weak; compare decay values cautiously.",
            )
        )

    if peaks and not mode_groups:
        caveats.append(
            ResponseCaveat(
                id="no_low_frequency_mode_group",
                severity="info",
                message=(
                    f"No dominant peaks below {LOW_FREQUENCY_MODE_MAX_HZ:.0f} Hz "
                    "cleared the grouping threshold."
                ),
            )
        )

    for group_index, group in enumerate(mode_groups[:3]):
        if group.warning_labels:
            caveats.append(
                ResponseCaveat(
                    id=(
                        f"low_mode_{group_index}_{round(group.center_hz)}hz_"
                        + "_".join(group.warning_labels[:2])
                    ),
                    severity="review",
                    message=(
                        f"Low-frequency mode group near {group.center_hz:.0f} Hz "
                        f"is labeled {', '.join(group.warning_labels)}."
                    ),
                )
            )

    top_peak = peaks[0] if peaks else None
    if top_peak and top_peak.q_factor is not None and top_peak.q_factor > VERY_HIGH_Q_THRESHOLD:
        caveats.append(
            ResponseCaveat(
                id="very_high_q_peak",
                severity="review",
                message=(
                    "Very narrow dominant peak; treat the Q proxy as device- and "
                    "tonal-artifact-sensitive rather than room-mode certainty."
                ),
            )
        )

    return _prioritized_caveats(caveats)


def _response_balance_caveats(
    trace_label: Literal["matched", "deconvolved"],
    trace: ResponseTrace,
) -> list[ResponseCaveat]:
    if trace.direct_to_late_db is None:
        return []

    if trace_label == "matched":
        source = "matched-filter response"
        caveat_prefix = "matched"
    else:
        source = "regularized deconvolved response"
        caveat_prefix = "deconvolved"

    ratio = trace.direct_to_late_db
    if ratio >= DIRECT_PATH_DOMINANCE_DB:
        return [
            ResponseCaveat(
                id=f"{caveat_prefix}_direct_path_dominant",
                severity="info",
                message=(
                    f"Direct-path energy dominates the {source}; room-response "
                    "descriptors may understate later reflections."
                ),
            )
        ]
    if ratio <= LATE_RESPONSE_DOMINANCE_DB:
        return [
            ResponseCaveat(
                id=f"{caveat_prefix}_late_response_dominant",
                severity="review",
                message=(
                    f"Late response energy exceeds the direct-path estimate in the {source}; "
                    "placement and nearby reflections may strongly shape this fingerprint."
                ),
            )
        ]
    return []


def _prioritized_caveats(
    caveats: list[ResponseCaveat],
    *,
    max_count: int = 8,
) -> list[ResponseCaveat]:
    unique: list[ResponseCaveat] = []
    seen: set[str] = set()
    for caveat in caveats:
        if caveat.id in seen:
            continue
        unique.append(caveat)
        seen.add(caveat.id)

    severity_rank = {"warning": 0, "review": 1, "info": 2}
    id_rank = {
        "weak_alignment": 0,
        "low_snr": 1,
        "very_high_q_peak": 2,
        "ambiguous_matched_direct_path": 3,
    }
    return sorted(
        unique,
        key=lambda caveat: (
            severity_rank[caveat.severity],
            id_rank.get(caveat.id, 50),
            unique.index(caveat),
        ),
    )[:max_count]


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
    if envelope.size < MIN_DECAY_FIT_POINTS:
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
    noise_floor = max(float(np.percentile(envelope, 15.0)), EPSILON)
    fit_floor = max(noise_floor * 1.5, float(np.max(envelope)) * 0.015, EPSILON)
    fit_mask = fit_envelope > fit_floor
    if int(np.sum(fit_mask)) < MIN_DECAY_FIT_POINTS:
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )

    x = fit_times[fit_mask]
    signal_above_floor = np.sqrt(
        np.maximum(np.square(fit_envelope[fit_mask]) - noise_floor**2, EPSILON)
    )
    dynamic_range_db = 20.0 * math.log10(
        (float(np.max(signal_above_floor)) + EPSILON)
        / (float(np.min(signal_above_floor)) + EPSILON)
    )
    if dynamic_range_db < MIN_DECAY_DYNAMIC_RANGE_DB:
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )
    y = np.log(signal_above_floor)
    if not np.all(np.isfinite(y)):
        return DecayEstimate(
            method="rms_envelope_log_linear",
            decay_rate_per_second=None,
            rt60_seconds=None,
            fit_r2=None,
            window_start_seconds=window_start_seconds,
            window_end_seconds=window_end_seconds,
        )
    design = np.column_stack([x, np.ones_like(x)])
    weights = np.square(signal_above_floor)
    normalized_weights = weights / max(float(np.max(weights)), EPSILON)
    weighted_design = design * np.sqrt(normalized_weights)[:, np.newaxis]
    weighted_y = y * np.sqrt(normalized_weights)
    slope, intercept = np.linalg.lstsq(weighted_design, weighted_y, rcond=None)[0]
    predicted = slope * x + intercept
    residual_sum = float(np.sum(normalized_weights * np.square(y - predicted)))
    weighted_mean = float(
        np.sum(normalized_weights * y) / max(float(np.sum(normalized_weights)), EPSILON)
    )
    total_sum = float(np.sum(normalized_weights * np.square(y - weighted_mean)))
    fit_r2 = 1.0 - residual_sum / total_sum if total_sum > EPSILON else None
    if not math.isfinite(float(slope)):
        robust_slope = _median_decay_slope(x, y)
        slope = robust_slope if robust_slope is not None else float("nan")
        fit_r2 = None
    elif fit_r2 is None:
        robust_slope = _median_decay_slope(x, y)
        if robust_slope is not None:
            slope = robust_slope

    if not math.isfinite(float(slope)) or slope >= 0:
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
    sample_rate_hz: int,
    signal_start: int,
    signal_end: int,
    noise_end: int,
) -> float | None:
    signal = samples[max(0, signal_start) : max(signal_start, signal_end)]
    noise = samples[: max(0, min(noise_end, samples.size))]
    minimum_noise_samples = max(8, int(round(MIN_NOISE_WINDOW_SECONDS * sample_rate_hz)))
    if signal.size == 0 or noise.size < minimum_noise_samples:
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


def _dct_type_ii_ortho(
    values: npt.NDArray[np.float64],
    coefficient_count: int,
) -> npt.NDArray[np.float64]:
    row_count = values.shape[0]
    if row_count <= 0:
        return np.empty((0, values.shape[1] if values.ndim == 2 else 0), dtype=np.float64)
    coefficient_count = max(1, min(int(coefficient_count), row_count))
    coefficient_indices = np.arange(coefficient_count, dtype=np.float64)[:, np.newaxis]
    mel_indices = np.arange(row_count, dtype=np.float64)[np.newaxis, :]
    basis = np.cos(math.pi / row_count * (mel_indices + 0.5) * coefficient_indices)
    basis[0, :] *= math.sqrt(1.0 / row_count)
    if coefficient_count > 1:
        basis[1:, :] *= math.sqrt(2.0 / row_count)
    return basis @ values


def _response_trace_shape(
    times: npt.NDArray[np.float64],
    envelope: npt.NDArray[np.float64],
    *,
    direct_half_window_seconds: float = 0.004,
    late_offset_seconds: float = 0.012,
    min_late_window_seconds: float = 0.050,
) -> tuple[float | None, float | None]:
    if times.size == 0 or envelope.size == 0 or times.size != envelope.size:
        return None, None
    peak_index = int(np.argmax(envelope))
    peak_time_seconds = float(times[peak_index])
    if times[-1] < peak_time_seconds + late_offset_seconds + min_late_window_seconds:
        return peak_time_seconds, None
    power = np.square(envelope)
    direct_mask = np.abs(times - peak_time_seconds) <= direct_half_window_seconds
    late_mask = times >= peak_time_seconds + late_offset_seconds
    if not np.any(direct_mask) or not np.any(late_mask):
        return peak_time_seconds, None
    direct_energy = float(np.sum(power[direct_mask]))
    late_energy = float(np.sum(power[late_mask]))
    if direct_energy <= EPSILON or late_energy <= EPSILON:
        return peak_time_seconds, None
    direct_to_late_db = 10.0 * math.log10((direct_energy + EPSILON) / (late_energy + EPSILON))
    return peak_time_seconds, float(direct_to_late_db)


def _mode_group_warning_labels(
    group: list[PeakFeature],
    dominant: PeakFeature,
    *,
    group_width_hz: float = LOW_MODE_GROUP_WIDTH_HZ,
) -> list[str]:
    labels: list[str] = []
    if dominant.q_factor is None:
        labels.append("unresolved_bandwidth")
    elif dominant.q_factor > VERY_HIGH_Q_THRESHOLD:
        labels.append("very_narrow_q")
    elif dominant.q_factor < 2.0:
        labels.append("broad_peak")
    if dominant.prominence_db < 10.0:
        labels.append("weak_prominence")
    frequencies = [peak.frequency_hz for peak in group]
    span_hz = max(frequencies) - min(frequencies) if len(frequencies) > 1 else 0.0
    has_unresolved_member = any(peak.q_factor is None for peak in group)
    if len(group) > 1 and (span_hz <= group_width_hz * 0.5 or has_unresolved_member):
        labels.append("clustered_peaks")
    return labels


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
    values: npt.NDArray[np.float64],
    index: int,
) -> float:
    if index <= 0 or index >= values.size - 1:
        return float(frequencies[index])

    alpha = values[index - 1]
    beta = values[index]
    gamma = values[index + 1]
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
    *,
    peak_frequency_hz: float | None = None,
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

    peak_frequency = (
        peak_frequency_hz
        if peak_frequency_hz is not None
        else _quadratic_peak_frequency(
            frequencies,
            20.0 * np.log10(magnitude_linear + EPSILON),
            peak_index,
        )
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


def _median_decay_slope(
    times: npt.NDArray[np.float64],
    log_envelope: npt.NDArray[np.float64],
    *,
    max_points: int = 80,
) -> float | None:
    if times.size < MIN_DECAY_FIT_POINTS or times.size != log_envelope.size:
        return None

    indices = _compact_indices(times.size, max_points)
    x = times[indices]
    y = log_envelope[indices]
    delta_x = x[np.newaxis, :] - x[:, np.newaxis]
    delta_y = y[np.newaxis, :] - y[:, np.newaxis]
    mask = delta_x > EPSILON
    slopes = delta_y[mask] / delta_x[mask]
    slopes = slopes[np.isfinite(slopes)]
    if slopes.size == 0:
        return None
    return float(np.median(slopes))


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
