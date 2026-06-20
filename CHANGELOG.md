# Changelog

All notable changes to ResonanceLab will be documented in this file.

## Unreleased

### Added

- Phase 4 dataset manifest parser with required leakage-aware session, glass, device, browser, room, label, probe, and quality metadata.
- Canonical Phase 4 feature extraction from API analysis JSON and raw WAV records, with fixed mel summaries and no raw STFT-bin model inputs.
- Derived Phase 4 manifest output for feature extraction so raw WAV or analysis manifests can feed the trainer through generated feature JSON.
- Leakage-aware group holdout splitter for session, glass, device, and browser evaluation, plus repeated holdout helper support.
- Offline scikit-learn baseline trainer with repeated grouped holdout evaluation, regression/classification heads, reference metrics, quality gates, feature importance, and artifact export.
- Train-set feature filtering for all-missing and constant columns before baseline fitting.
- Manifest bucket schemas now drive Phase 4 class labels, references, confusion matrices, and within-one-bucket scoring.
- Missing alignment/SNR quality is rejected by default and counted in exported quality audits.
- Missingness indicators are included during baseline imputation.
- Compiled Phase 4 benchmark report command for session, glass, device, and browser regimes.
- Raw-audio Phase 4 feature extraction now requires exact probe metadata instead of falling back to guessed chirp settings.
- Phase 4 training and feature-extraction scripts.
- Browser-local known-object references and weighted DSP comparison against free-air, calibration
  anchors, and saved material examples.
- Structured `/api/v1/explain` endpoint with deterministic fallback summaries and optional Gemini
  lab-assistant calls over compact DSP/reference evidence.
- Lab UI explanation panel for observations, material hypotheses, caveats, and next-measurement
  guidance after a probe.
- Private Phase 4 capture endpoint with operator-token gating and GCS/local inbox storage.
- Operator-only Phase 4 capture panel for saving labeled probe captures from the Lab UI.
- Optional single-service Cloud Run Phase 4 capture mode with Secret Manager operator-token loading
  and private GCS inbox configuration on the existing web/API service pair.
- Phase 4 manifest finalization script for turning capture inbox fragments into immutable dataset snapshots.
- Private Phase 4 Cloud Build pipeline for GCS-hosted datasets, generated features, model artifacts, and benchmark reports.
- Phase 4 recording protocol, baseline workflow, dataset manifest JSON Schema, example manifest, model-card template, benchmark result landing zone, and evaluation notebook skeleton.
- Phase 4 unit coverage for feature extraction, manifest validation, split leakage prevention, and synthetic baseline training.
- Explain request body limits and schema caps for compact LLM evidence payloads.
- Cloud Run deployment path in Cloud Build, gated by `_DEPLOY_TARGET=cloud-run` so default and PR builds do not deploy.
- Cloud Run API and web deploys now explicitly use the second-generation execution environment with startup CPU boost enabled.
- Cloud Run API CORS now allows both generated Cloud Run web URL forms, and the web service uses the project-number API URL.
- Cloud Run deploys now force Phase 4 capture off by default, while optional capture flags can
  enable the existing web/API pair for a temporary operator campaign.
- GCP Cloud Run deployment guide covering private trigger substitutions, service account hygiene, and public-safe project configuration.
- Cloud Build substitutions for disabled-by-default Gemini explanations on the existing API Cloud
  Run service using `gemini-3.1-pro-preview`, `global`, and `HIGH` thinking level.
- `.gcloudignore` coverage for local GCP notes, service account key files, private datasets, and generated model artifacts.
- Phase 3 browser-local calibration profiles backed by IndexedDB.
- Empty, 50%, full, and free-air reference save workflow in the probe UI.
- Repeated anchor aggregation with profile stability and capture-compatibility confidence penalties.
- Free-air reference matching now suppresses fill estimates when the current probe looks closer to no-glass room response than to glass anchors.
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
- Cloud Build configuration for GCP-based checks, container builds, and opt-in Cloud Run deployment.
- Local Git hook and project freshness checker for README, CHANGELOG, FEATURES, and SKILL.md files.
- Feature inventory in `FEATURES.md`.
- `.env.example` documenting local API URL configuration.
- Commit-message docs freshness escape hatch through `[skip docs]`.
- Pytest and Ruff configuration for root-level contributor checks.

### Changed

- Phase 4 sequencing now prioritizes free-air and known-object reference comparison, deterministic
  DSP/physics interpretation, and an LLM lab assistant before private supervised dataset capture or
  scikit-learn/XGBoost model training.
- Cloud Run deployment has been simplified back to one web service and one API service; private
  capture is an optional mode on those services rather than a separate capture service pair.
- Project SKILL.md license metadata now matches the repository MIT license and uses the
  ResonanceLab publisher.
- Phase 4 capture now enforces the server raw-audio storage policy, omits capture-time fill buckets,
  defers quality threshold exclusion to training, and uses web-generated idempotency keys for
  duplicate-safe retries.
- Private Phase 4 Cloud Build can now train from an existing snapshot or finalize an inbox before training.
- Calibration anchor controls now use explicit save labels so users can see how to store the current probe as Empty, 50%, Full, or Free air.
- Calibration profiles can now clear individual anchors or the free-air reference after accidental saves.
- Calibration anchor cards now read the same normalized profile state as the header and estimator, fixing stale `n=0` displays after saves.
- Probe results now show a reference match instead of a nearest glass anchor when the saved free-air reference dominates.
- API model status now reports the Phase 3 calibration demo while keeping model inference disabled.
- Probe config warnings now distinguish API DSP features from browser-local fill estimates.
- Calibration UI state moved into a dedicated Svelte component while preserving the existing probe workflow.
- Repeated calibration frequency summaries now use log-domain averaging to match the feature space.
- Calibration estimates are memoized by analysis and profile update identity in the UI.
- Calibration feature extraction now emits canonical Phase 4 decay feature names and aliases older
  local profile decay names on import.
- Transfer-response features are now lower-weight same-setup path evidence in browser calibration
  and reference comparison.
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

- LLM explanation requests now exclude raw WAV bytes and full high-dimensional signal grids from the
  hosted model path.
- Analyze rejects probe configurations whose chirp end frequency reaches the decoded WAV Nyquist
  limit.
- Analyze uses browser timing metadata, when available, for the expected chirp position and post-roll
  analysis window.
- Transfer-response features now use regularized complex deconvolution over the driven response
  window instead of subtracting magnitudes.
- Dominant-peak interpolation now uses dB-domain parabolic interpolation while Q estimation keeps
  linear half-power bandwidth calculations.
- Decay fitting subtracts a local envelope floor and weights higher-SNR envelope frames.
- Phase 4 manifests now reject non-object records and bucket schemas whose rounded labels collide.
- Phase 4 baseline metrics now warn on missing or highly imbalanced fill-bucket coverage across
  train/test splits.
- Dataset Capture numeric inputs now accept browser-coerced number values, unblocking Save Dataset
  Capture when fill percent or mass fields are entered as number inputs.
- Calibration cards no longer describe saved anchors as having no samples when only the optional peak summary is unavailable.
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
- Web Docker build now copies source files into the workspace package path before running the SvelteKit build.
- Cloud Build Python checks now install the Starlette test client dependency required by current FastAPI releases.
- WAV PCM decoding now uses vectorized NumPy paths for supported PCM widths.

### Removed

- GitHub Actions workflow in favor of GCP Cloud Build.
- `_DEPLOY_TARGET=cloud-run-capture` and capture-specific Cloud Run service substitutions from the
  main Cloud Build deployment.
