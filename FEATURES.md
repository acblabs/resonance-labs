# Features

ResonanceLab is an active acoustic sensing project for learning how everyday objects respond to sound. The early releases are intentionally narrow: prove a reliable browser chirp capture, add deterministic DSP features, and avoid measurement claims until calibration data exists.

## Current Phase 1 Features

- Browser-based active acoustic probe workflow.
- Conservative logarithmic chirp generation with configurable start frequency, end frequency, duration, pre-roll, post-roll, amplitude, and fade.
- Microphone permission flow from a direct user gesture.
- AudioContext unlock flow for browser playback and capture.
- PCM microphone capture through AudioWorklet when available.
- ScriptProcessor fallback for browsers that cannot load the AudioWorklet recorder.
- Browser-side mono PCM16 WAV encoding.
- WAV upload to FastAPI with JSON probe metadata.
- FastAPI health endpoint.
- Server-provided default probe configuration and upload limits.
- Analysis endpoint that validates upload size, content type, WAV structure, duration, sample rate, RMS, peak amplitude, and DC offset.
- Browser result display with duration, sample rate, alignment confidence, SNR, peak frequency, RT60 proxy, upload size, capture path, and warnings.
- Canvas waveform display for captured probe audio.
- Docker Compose development stack for web and API.
- Cloud Build configuration for GCP checks and container image builds.
- Local Git hooks for README, CHANGELOG, and SKILL.md freshness checks.
- Pre-commit enforcement that requires `FEATURES.md` to be updated in every commit.
- Commit-message `[skip docs]` escape hatch for low-signal documentation updates.
- Client-side probe safety clamping before chirp playback.
- Cosine-tapered chirps to reduce broadband envelope clicks.
- Batched AudioWorklet PCM capture to reduce allocation pressure.
- Bounded API upload reads for oversized request protection.
- Root-level `python -m pytest` and `python -m ruff check .` developer validation.
- Vectorized NumPy WAV decoding for Phase 1 PCM uploads.
- Slimmer web runtime container with production-only Node dependencies.

## Current Phase 2 Features

- Matched-filter chirp alignment against the configured logarithmic sweep.
- Alignment confidence, detected chirp start, expected chirp start, and estimated latency reporting.
- FFT-domain bandpass filtering with cosine transition bands.
- FFT spectral trace with centroid, bandwidth, rolloff, and spectral floor summaries.
- Compact STFT grid for browser spectrogram rendering.
- Compact mel-spectrogram grid computed without adding Librosa or PyTorch.
- Regularized transfer-response magnitude by configured frequency bands.
- Dominant ring-down peak detection with prominence and Q-factor proxies.
- RMS-envelope log-linear decay fitting with RT60 proxy output.
- Signal-to-noise reporting against the pre-roll noise floor.
- Browser tabs for waveform, FFT, STFT, and mel-spectrogram views.
- Deterministic golden DSP tests covering alignment, bandpass behavior, peak detection, spectrogram shapes, post-window fallback timing, and decay-fit edge cases.
- Committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down.
- Cross-language golden chirp fixture that guards browser and Python chirp parity.
- Deterministic fixture generator script for the Phase 2 synthetic fixtures.

## Planned DSP Features

- Direct-path and room-response caveat reporting.
- Free-air reference handling for speaker-to-microphone and room response.
- Empty-glass reference subtraction and comparison features.
- Repeated chirps and synchronous averaging.
- MFCC summary statistics.
- Real recorded WAV fixtures from multiple devices, rooms, and sessions, tracked in `docs/real_recording_fixtures.md`.
- Side-by-side chirp and tap feature comparison.

## Planned Calibration Features

- Local IndexedDB calibration profiles.
- Empty, 50%, and full anchor capture workflow.
- Local feature storage by default.
- Optional local raw-audio storage only with user opt-in.
- Profile-relative fill estimate.
- Calibration confidence and nearest-anchor reporting.
- Local profile deletion and cleanup.

## Planned ML Features

- Classical baseline models using extracted DSP features.
- Fill bucket classification for empty, 25%, 50%, 75%, and full.
- Fill percentage regression.
- Session-, glass-, device-, and browser-aware evaluation splits.
- Model cards and benchmark reports.
- Small neural audio models only after the baseline and dataset justify them.

## Planned Lab Assistant Features

- Structured-result explanations.
- Experiment design assistance.
- Physics tutoring for chirps, FFTs, resonance, and damping.
- Low-confidence troubleshooting guidance.
- No raw audio sent to LLM providers.
