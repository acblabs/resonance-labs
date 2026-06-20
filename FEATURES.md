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
- Cloud Build configuration for GCP checks, container image builds, and opt-in Cloud Run deploys through private trigger substitutions.
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
- Workspace-correct web Docker build path for Cloud Build image builds.

## Current Phase 2 Features

- Matched-filter chirp alignment against the configured logarithmic sweep.
- Alignment confidence, detected chirp start, expected chirp start, and estimated latency reporting.
- FFT-domain bandpass filtering with cosine transition bands, zero-padding, and cropped output to reduce boundary wraparound.
- FFT spectral trace with centroid, bandwidth, rolloff, and spectral floor summaries.
- Compact STFT grid for browser spectrogram rendering.
- Compact mel-spectrogram grid computed without adding Librosa or PyTorch.
- Regularized transfer-response magnitude by configured frequency bands.
- Dominant ring-down peak detection with prominence and Q-factor proxies.
- Sub-bin interpolation for Q-factor `-3 dB` bandwidth crossings.
- RMS-envelope log-linear decay fitting with RT60 proxy output and null fit quality for non-decaying fits.
- Signal-to-noise reporting against the pre-roll noise floor, clamped to exclude early detected chirp energy.
- Browser tabs for waveform, FFT, STFT, and mel-spectrogram views.
- Deterministic golden DSP tests covering alignment, bandpass behavior, analytic damped sinusoids, peak detection, spectrogram shapes, post-window fallback timing, SNR windowing, and decay-fit edge cases.
- Committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down.
- Cross-language golden chirp fixture that guards browser and Python chirp parity.
- Deterministic fixture generator script for the Phase 2 synthetic fixtures.

## Current Phase 3 Features

- Browser-local IndexedDB calibration profile storage.
- Automatic local profile creation for account-free use.
- Local profile list with create, rename, delete, export, import, and active-profile selection.
- Empty, 50%, full, and free-air reference capture/save workflow.
- Repeated anchor aggregation with mean feature vectors and stability statistics.
- Anchor records storing extracted DSP feature vectors, probe settings, capture signatures, quality signals, and warnings.
- Canonical capture signatures for sample rate, capture path, browser family, and reported audio processing.
- Feature-distance interpolation over the empty-to-50% and 50%-to-full calibration segments.
- Profile-relative fill estimate with confidence label, reference-match display, and global-mean/nearest-anchor baselines.
- Free-air reference matching that suppresses fill estimates when a probe is closer to the no-glass reference than to calibrated glass anchors.
- Weighted geometric confidence aggregation with hard caps for weak alignment, probe mismatch, capture mismatch, free-air dominance, too few comparable features, and close anchor spacing.
- Calibration uncertainty penalties for missing anchors, low SNR, weak chirp alignment, mismatched probe settings, sample-rate/capture mismatch, missing free-air reference, unstable repeats, and close anchor spacing.
- Browser UI display of fill estimate, confidence, reference match, anchor count, repeat count, storage usage, and calibration warnings.
- Explicit save controls for storing the current probe as Empty, 50%, Full, or Free air calibration samples.
- Per-anchor and free-air clearing controls to recover from accidental calibration saves.
- Unit tests for calibration feature extraction, incomplete profiles, interpolation behavior, baseline beating, repeat aggregation, capture mismatch, free-air references, import/export, and low-quality probe confidence.
- Dedicated calibration manager component separated from the main probe/visualization component.
- Probe uploads keep calibration profile IDs and anchor vectors local to the browser.

## Current Phase 4 Features

- Private dataset manifest format for chirp recordings with required session, glass, device, browser, room, label, probe, and quality metadata.
- Public JSON Schema for Phase 4 dataset manifests.
- Glass recording protocol with mass-based fill labeling, repeated captures, free-air references, and quality rejection rules.
- Canonical Python feature extraction from saved API analysis JSON or raw PCM WAV records.
- Optional derived Phase 4 manifest generation that points raw WAV or analysis records at extracted feature JSON.
- Stable tabular ML feature names for resonance peaks, spectral summaries, decay estimates, transfer-response bands, and fixed 20-band mel-spectrogram summaries.
- Raw STFT-bin features excluded from Phase 4 model inputs to avoid sample-rate/window-dependent dimensionality.
- Leakage-aware group holdout splitting by session, glass, device, browser, or combined context fields, with repeated group-holdout helper support.
- Offline scikit-learn baseline trainer with repeated grouped holdout evaluation, fill-percent regression, and fill-bucket classification heads using sparse linear or random-forest model families.
- Manifest-defined fill buckets threaded through classification, references, confusion matrices, and within-one-bucket metrics.
- Quality gates for missing/weak chirp alignment and missing/low SNR before model fitting.
- Quality audit metrics for retained, skipped, missing-quality, weak-alignment, and low-SNR records.
- Train-set feature filtering for all-missing and constant columns before imputation/model fitting.
- Missingness indicators added during imputation so absent feature families remain visible to models.
- Reference metrics for global mean, global median, nearest canonical bucket, and train-mode bucket classification baselines.
- Baseline artifact export with `joblib`, metrics JSON, feature schema, feature importance, and generated model card.
- Compiled benchmark reports across session, glass, device, and browser holdout regimes.
- Phase 4 evaluation notebook skeleton that delegates to the checked-in training script.
- Public-safe data, benchmark, and model-card landing zones without committing private audio.
- Private dataset capture endpoint gated by operator token and explicit capture settings.
- Operator-only web capture panel, hidden unless `PUBLIC_PHASE4_CAPTURE_ENABLED=true`, for saving labeled probe captures.
- Private capture inbox layout for WAV, analysis JSON, and manifest-ready `.record.json` fragments.
- Server-enforced raw-audio capture policy, capture-fragment validation, and idempotency keys for
  duplicate-safe operator retries.
- Manifest finalization script that materializes immutable dataset snapshots from inbox fragments.
- Private GCP Phase 4 Cloud Build pipeline for finalizing private GCS inbox data, training, benchmarking, and uploading generated artifacts back to private GCS.

## Current Cloud Deployment Features

- Cloud Build defaults that run checks and image builds without deploying from PR/default triggers.
- Main-trigger opt-in Cloud Run deployment through `_DEPLOY_TARGET=cloud-run`.
- Artifact Registry push steps gated behind the deploy target.
- Cloud Run API and web service deployment with configurable memory, CPU, concurrency, timeout, min-instance, and max-instance substitutions.
- Explicit second-generation Cloud Run execution environment and startup CPU boost for API and web deploys.
- Runtime discovery of the deployed API URL before deploying the web service.
- API CORS update using both generated Cloud Run web service URL forms plus optional extra origins.
- `.gcloudignore` and `.gitignore` coverage for local GCP notes, service account key files, private datasets, and generated model artifacts.
- Public-safe GCP deployment guide in `docs/gcp_cloud_run.md`.

## Planned DSP Features

- Direct-path and room-response caveat reporting.
- Free-air reference handling for speaker-to-microphone and room response.
- Empty-glass reference subtraction and comparison features.
- Repeated chirps and synchronous averaging.
- MFCC summary statistics.
- Real recorded WAV fixtures from multiple devices, rooms, and sessions, tracked in `docs/real_recording_fixtures.md`.
- Side-by-side chirp and tap feature comparison.

## Planned Calibration Features

- Repeated-anchor averaging with within-profile variance estimates.
- Free-air and empty-vessel reference comparison views.
- Optional local raw-audio storage only with user opt-in.
- Tap and chirp side-by-side calibration profiles.
- Cross-session calibration drift reporting.

## Planned ML Features

- Initial private chirp dataset across multiple devices, browsers, sessions, rooms, and glasses.
- Cross-session, cross-glass, cross-device, and cross-browser benchmark reports from private captures.
- Optional XGBoost challenger after scikit-learn references are established.
- Small neural audio models only after the baseline and dataset justify them.

## Planned Lab Assistant Features

- Structured-result explanations.
- Experiment design assistance.
- Physics tutoring for chirps, FFTs, resonance, and damping.
- Low-confidence troubleshooting guidance.
- No raw audio sent to LLM providers.
