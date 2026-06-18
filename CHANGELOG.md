# Changelog

All notable changes to ResonanceLab will be documented in this file.

## Unreleased

### Added

- Phase 3 browser-local calibration profiles backed by IndexedDB.
- Empty, 50%, full, and free-air reference save workflow in the probe UI.
- Repeated anchor aggregation with profile stability and capture-compatibility confidence penalties.
- Weighted geometric calibration confidence aggregation with explicit caps for hard quality and compatibility failures.
- Feature-distance fill interpolation with heuristic confidence, nearest-anchor, free-air-distance, and baseline reference reporting.
- Local calibration profile export/import and storage usage reporting.
- Calibration feature extraction, estimator, repeat, compatibility, reference, and import/export unit tests.
- Calibration tests for canonical capture signatures and beating global-mean/nearest-anchor baselines on a monotone synthetic profile.
- Calibration documentation for local profiles, anchor quality, and uncertainty handling.
- Analytic damped-sinusoid DSP regression coverage for independent peak and decay-rate checks.
- Sub-bin Q-factor bandwidth interpolation for dominant resonance peaks.
- Phase 2 NumPy DSP pipeline with matched-filter chirp alignment, FFT-domain bandpass filtering, FFT/STFT/mel outputs, transfer-response bands, dominant peak detection, and decay estimates.
- Browser waveform, FFT, STFT, and mel-spectrogram signal views.
- Deterministic golden DSP tests for alignment, bandpass attenuation, spectrogram shape, peak detection, post-window fallback timing, and decay-fit edge cases.
- Committed recorded-style WAV fixture for chirp analysis tests.
- Tracked real-recording WAV fixture TODO with metadata and acceptance criteria.
- Cross-language chirp fixture and tests to keep browser and Python chirp generation aligned.
- Deterministic script for regenerating Phase 2 synthetic fixtures.
- Phase 1 browser chirp capture and WAV upload scaffold.
- FastAPI dummy analysis endpoint with basic WAV metrics.
- Docker Compose development stack.
- Cloud Build configuration for GCP-based checks and container builds.
- Local Git hook and project freshness checker for README, CHANGELOG, FEATURES, and SKILL.md files.
- Feature inventory in `FEATURES.md`.
- `.env.example` documenting local API URL configuration.
- Commit-message docs freshness escape hatch through `[skip docs]`.
- Pytest and Ruff configuration for root-level contributor checks.

### Changed

- API model status now reports the Phase 3 calibration demo while keeping model inference disabled.
- Probe config warnings now distinguish API DSP features from browser-local fill estimates.
- Calibration UI state moved into a dedicated Svelte component while preserving the existing probe workflow.
- Repeated calibration frequency summaries now use log-domain averaging to match the feature space.
- Calibration estimates are memoized by analysis and profile update identity in the UI.
- FFT-domain bandpass filtering now zero-pads before masking and crops the filtered result to reduce circular boundary wraparound.
- Analyze responses now return Phase 2 DSP features and matched-filter alignment metadata instead of placeholder alignment.
- Analyze and models endpoints now expose typed FastAPI response schemas.
- FFT summary output now names `spectral_floor_db` instead of `noise_floor_db`.
- Browser chirp fade generation now matches the Python DSP reference endpoint sampling.
- Project license changed to MIT.
- Pre-commit freshness policy now requires `FEATURES.md` in every commit.
- API dummy metrics now report `dc_offset` instead of misleading signed mean amplitude.
- Web builds now use runtime `PUBLIC_API_URL` instead of an inert build argument.
- Cloud Build and local API scripts now run `python -m ruff check .` and `python -m pytest`.
- Web runtime Docker image now installs production dependencies separately.

### Fixed

- Analyze uploads are read in bounded chunks before size validation.
- SNR estimation now excludes early detected chirp energy from the noise window.
- Non-decaying envelope fits now suppress decay fit quality alongside decay rate and RT60.
- Probe uploads no longer attach local calibration profile IDs.
- Calibration capture signatures now use one canonical format for saved observations and compatibility checks.
- Browser chirp generation clamps unsafe probe values before playback.
- Chirp fade now uses a cosine taper to reduce envelope clicks.
- AudioWorklet capture batches render blocks to reduce allocation churn.
- 8-bit WAV unsigned PCM normalization now maps exactly across `[-1.0, 1.0]`.
- CI and Docker web dependency installs now use `npm ci`.
- WAV PCM decoding now uses vectorized NumPy paths for supported PCM widths.

### Removed

- GitHub Actions workflow in favor of GCP Cloud Build.
