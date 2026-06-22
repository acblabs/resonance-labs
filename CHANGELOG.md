# Changelog

All notable changes to ResonanceLab will be documented in this file.

## Unreleased

### Added

- README data-flow diagram showing the browser probe, FastAPI analysis, deterministic DSP, report export, and explanation path.
- Compact zero-padded regularized impulse-envelope proxy in `/api/v1/analyze`, report exports, and DSP regression tests.
- Matched-filter impulse-response traces alongside regularized deconvolved-response traces in `/api/v1/analyze`, the Lab UI, and PNG report exports.
- MFCC summary statistics from log-mel/DCT cepstral coefficients.
- Low-frequency mode grouping with warning labels for weak, narrow, broad, clustered, or unresolved peaks.
- Direct-path and room-response caveats for weak alignment, low SNR, direct/late response balance, unstable decay, high-Q peaks, and low-mode uncertainty.
- More conservative low/mid/high band-limited decay estimates for frequency-dependent decay diagnostics and report visualization.
- Lab UI tabs for matched impulse-response and deconvolved-response traces, plus a decay-band visualization panel.
- Polished PNG report panels for capture metadata, impulse-envelope proxy, and decay-band summaries.
- Lab UI JSON and PNG acoustic report export with derived DSP evidence, validation checks, descriptors, caveats, and optional explanation output.
- Device run-quality validation for alignment, SNR, duration, sample rate, peak amplitude, capture path, browser processing, and decay fit.
- Weighted validation scoring, high-Q proxy caveats, deferred report-download URL cleanup, and ellipsis-aware PNG text wrapping.
- Device validation protocol, public-history cleanup runbook, and real-room fixture manifest validator.
- Real-room fixture manifest example for reviewed public-safe report exports.
- Golden public-safe report analysis fixture and validator tests for privacy and fixture coverage rules.
- Room Acoustic Fingerprint product direction for chirp response, impulse/transfer evidence, spectrograms, decay, modes, and room descriptors.
- Acoustic Image export roadmap covering polished PNG reports with response plots, spectrograms, decay bands, detected modes, descriptors, and caveats.
- Structured `/api/v1/explain` endpoint with deterministic fallback summaries and optional Gemini lab-assistant calls over compact DSP evidence.
- Explainability versioning, leaf JSON Pointer evidence refs, refs-resolved claim metadata, and authoritative server-resolved values for `/api/v1/explain`.
- LLM claim grounding that logs and drops unresolvable claim refs before falling back to deterministic explanation text.
- Lab UI explanation panel for observations, acoustic hypotheses, experiment design assistance, physics tutoring, low-confidence troubleshooting, evidence critique, caveats, and next-measurement guidance.
- Validation and descriptor counterfactuals showing the margin or minimal change needed to flip run-quality and room-fingerprint labels.
- Explainability documentation covering evidence refs, claim verification, counterfactual semantics, and future sensitivity guardrails.
- Cloud Run deployment path in Cloud Build, gated by `_DEPLOY_TARGET=cloud-run` so default and PR builds do not deploy.
- Cloud Run API and web deploys now explicitly use the second-generation execution environment with startup CPU boost enabled.
- Structured API observability logs now include request IDs, request timing, analyze rejection reasons, analysis quality signals, LLM outcomes, and degradation markers.
- GCP Cloud Run deployment guide covering private trigger substitutions, service account hygiene, and public-safe project configuration.
- `.gcloudignore` coverage for local GCP notes, service account key files, private datasets, and generated artifacts.
- Analytic damped-sinusoid DSP regression coverage for independent peak and decay-rate checks.
- NumPy DSP pipeline with matched-filter chirp alignment, FFT-domain bandpass filtering, FFT/STFT/mel outputs, transfer-response bands, dominant peak detection, and decay estimates.
- Browser waveform, FFT, STFT, and mel-spectrogram signal views.
- Deterministic golden DSP tests for alignment, bandpass attenuation, spectrogram shape, peak detection, post-window fallback timing, and decay-fit edge cases.
- Committed recorded-style WAV fixture for chirp analysis tests.
- Cross-language chirp fixture and tests to keep browser and Python chirp generation aligned.
- Browser chirp capture and WAV upload scaffold.
- FastAPI analysis endpoint with WAV metrics and DSP features.
- Docker Compose development stack.
- Local Git hook and project freshness checker for README, CHANGELOG, FEATURES, and SKILL.md files.
- Supply-chain pin checker for Dockerfiles, Cloud Build step images, and direct Python requirements.

### Changed

- Documented ResonanceLab as an easy browser-based workflow that requires no special hardware or downloadable app for end-user probes.
- Documented ResonanceLab as an active acoustic machine listening project across the main README, feature list, and measurement/limitations docs.
- Cloud Build step images, Docker base images, and direct Python requirements are now pinned; API and web production containers now run as non-root users.
- Acoustic report exports now minimize reflected browser metadata while preserving repeatability signals.
- Operator questions for hosted explanations are treated as untrusted context and excluded from valid evidence references.
- Raised the default Gemini explanation output cap and wired it through Cloud Build deployment substitutions.
- Consolidated planned-feature documentation and removed completed phase labels from project docs.
- Lab layout now uses more of wide desktop viewports with sticky controls, a larger signal panel, and denser result grids.
- Reoriented the app and docs toward room acoustic fingerprints and acoustic report generation.
- Lab UI now presents room character, brightness, dominant mode, RT60 proxy, transfer bands, and acoustic hypotheses.
- `/api/v1/models` now reports room-fingerprint status.
- `/api/v1/explain` now accepts analysis JSON only and returns `acoustic_hypotheses`.
- Cloud Build deployment has been simplified to one web service and one API service with no capture-mode substitutions.
- API settings no longer include private capture flags, buckets, local inboxes, or operator tokens.
- Project Python package description now reflects DSP helpers rather than ML helpers.
- FFT-domain bandpass filtering now zero-pads before masking and crops the filtered result to reduce circular boundary wraparound.
- Analyze responses now return DSP features and matched-filter alignment metadata instead of placeholder alignment.
- FFT summary output now names `spectral_floor_db` instead of `noise_floor_db`.
- Browser chirp fade generation now matches the Python DSP reference endpoint sampling.
- Project license changed to MIT.
- Pre-commit freshness policy now requires `FEATURES.md` in every commit.
- API dummy metrics now report `dc_offset` instead of misleading signed mean amplitude.
- Web builds now use runtime `PUBLIC_API_URL` instead of an inert build argument.
- Cloud Build and local API scripts now run `python -m ruff check .` and `python -m pytest`.
- Cloud Build web checks now run the existing Vitest unit tests before building the SvelteKit app.

### Fixed

- Browser probes now prime Web Audio output from the Start Probe gesture, verify that the context is running before chirp playback, and fail visibly if playback is blocked or interrupted.
- Gemini explanation calls now request a single top-level JSON object and safely unwrap a single object returned inside an array before grounding.
- Hosted Gemini failures now return generic client-facing errors while preserving detailed diagnostics in structured logs.
- Empty Gemini explanation responses now include finish-reason and token-usage diagnostics.
- Lab UI and report exports now share room-character and brightness descriptor thresholds instead of duplicating frontend logic.
- LLM explanation requests now exclude raw WAV bytes and full high-dimensional signal grids from the hosted model path.
- Analyze rejects probe configurations whose chirp end frequency reaches the decoded WAV Nyquist limit.
- Analyze uses browser timing metadata, when available, for the expected chirp position and post-roll analysis window.
- Transfer-response features now use regularized complex deconvolution over the driven response window instead of subtracting magnitudes.
- Dominant-peak interpolation uses dB-domain parabolic interpolation while Q estimation keeps linear half-power bandwidth calculations.
- Decay fitting subtracts a local envelope floor and weights higher-SNR envelope frames.
- Analyze uploads are read in bounded chunks before size validation.
- SNR estimation excludes early detected chirp energy from the noise window.
- Non-decaying envelope fits suppress decay fit quality alongside decay rate and RT60.
- Browser chirp generation clamps unsafe probe values before playback.
- Chirp fade uses a cosine taper to reduce envelope clicks.
- AudioWorklet capture batches render blocks to reduce allocation churn.
- 8-bit WAV unsigned PCM normalization maps exactly across `[-1.0, 1.0]`.
- CI and Docker web dependency installs use `npm ci`.
- Web Docker build copies source files into the workspace package path before running the SvelteKit build.
- Cloud Build Python checks install the Starlette test client dependency required by current FastAPI releases.
- WAV PCM decoding uses vectorized NumPy paths for supported PCM widths.

### Removed

- Exported JSON report comparison references from the active feature list and forward-looking documentation.

- Browser-local object-state profile UI and IndexedDB helpers.
- Prior private capture endpoint, operator panel, capture settings, and GCS/local inbox storage code.
- Offline supervised object-state ML package, manifest tooling, benchmark scripts, model-card placeholder, notebook skeleton, and ML dependency file.
- Capture-mode Cloud Build substitutions, capture secrets, and the prior private Cloud Build pipeline.
- Obsolete docs for the prior object-state recording, private capture workflow, manifest schema, and supervised baseline workflow.
- GitHub Actions workflow in favor of GCP Cloud Build.
