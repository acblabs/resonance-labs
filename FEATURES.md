# Features

ResonanceLab is an active acoustic sensing project for learning how everyday objects respond to sound. The first release is intentionally narrow: prove a reliable browser chirp capture and API analysis loop before making measurement claims.

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
- Dummy analysis endpoint that validates upload size, content type, WAV structure, duration, sample rate, RMS, peak amplitude, and mean amplitude.
- Placeholder alignment metadata that clearly marks matched-filter DSP as a future phase.
- Browser result display with duration, sample rate, RMS, peak amplitude, upload size, capture path, and warnings.
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

## Planned DSP Features

- Matched-filter chirp alignment.
- Direct-path and room-response caveat reporting.
- Bandpass filtering with validated frequency ranges.
- FFT and STFT feature extraction.
- Transfer-response features.
- Dominant resonance peak detection.
- Decay and damping estimates from post-chirp response.
- Signal-to-noise and alignment confidence scores.
- Golden audio fixtures with tolerance-based feature tests.

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
