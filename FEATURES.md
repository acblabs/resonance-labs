# Features

ResonanceLab is an active acoustic sensing project for room fingerprints and acoustic reports. The current path is intentionally narrow: capture a reliable chirp response, extract deterministic DSP evidence, visualize the response, and avoid claims that a single speaker/microphone can produce a spatial room map.

## Current Platform Features

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
- Browser result display with duration, sample rate, alignment confidence, SNR, dominant mode, RT60 proxy, upload size, capture path, and warnings.
- Canvas waveform display for captured probe audio.
- Docker Compose development stack for web and API.
- Cloud Build configuration for GCP checks, container image builds, and opt-in Cloud Run deploys through private trigger substitutions.
- Local Git hooks for README, CHANGELOG, FEATURES, and SKILL.md freshness checks.
- Pre-commit enforcement that requires `FEATURES.md` to be updated in every commit.
- Cloud security architect skill covering GCP hardening, AppSec, AI/ML security, threat modeling, incident response, and framework mappings.
- Structured API logs with request IDs, request duration, analyze rejection reasons, analysis quality signals, LLM outcomes, and degradation markers.
- Configurable `RESONANCELAB_LOG_LEVEL` for API logging verbosity.
- Client-side probe safety clamping before chirp playback.
- Cosine-tapered chirps to reduce broadband envelope clicks.
- Batched AudioWorklet PCM capture to reduce allocation pressure.
- Bounded API upload reads for oversized request protection.
- Root-level `python -m pytest` and `python -m ruff check .` developer validation.
- Vectorized NumPy WAV decoding for PCM uploads.

## Current DSP Features

- Matched-filter chirp alignment against the configured logarithmic sweep.
- Alignment confidence, detected chirp start, expected chirp start, and estimated latency reporting.
- FFT-domain bandpass filtering with cosine transition bands, zero-padding, and cropped output to reduce boundary wraparound.
- FFT spectral trace with centroid, bandwidth, rolloff, and spectral floor summaries.
- Compact STFT grid for browser spectrogram rendering.
- Compact mel-spectrogram grid computed without Librosa or PyTorch.
- Regularized transfer-response magnitude by configured frequency bands.
- Compact regularized impulse-response proxy for early-response report visualization.
- Matched-filter impulse-response trace alongside the regularized deconvolved-response trace.
- MFCC summary statistics from log-mel energy and orthonormal DCT-II coefficients.
- Dominant post-chirp peak detection with prominence and Q-factor proxies.
- Low-frequency mode grouping with warning labels for weak, broad, narrow, clustered, or unresolved peaks.
- dB-domain sub-bin peak interpolation for dominant peak frequency estimates.
- Interpolated half-power crossings for Q-factor bandwidth estimates.
- RMS-envelope log-linear decay fitting with RT60 proxy output and weighted fit quality.
- Low, mid, and high band-limited decay estimates for frequency-dependent decay diagnostics.
- Signal-to-noise reporting against the pre-roll noise floor, clamped to exclude early detected chirp energy.
- Direct-path and room-response caveats for weak alignment, low SNR, direct/late response balance, unstable decay, and high-Q peaks.
- Browser tabs for waveform, FFT, STFT, mel-spectrogram, matched impulse response, and deconvolved response views.
- Deterministic golden DSP tests covering alignment, bandpass behavior, analytic damped sinusoids, peak detection, spectrogram shapes, post-window fallback timing, SNR windowing, and decay-fit edge cases.
- Committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down.
- Cross-language golden chirp fixture that guards browser and Python chirp parity.
- Deterministic fixture generator script for the synthetic fixtures.

## Current Room Fingerprint Features

- First-screen Room Acoustic Fingerprint workflow in the Lab UI.
- Acoustic Image panel with waveform, FFT, STFT, and mel-spectrogram views.
- Wider responsive Lab layout with sticky desktop controls and larger signal plots.
- Room character descriptor from the RT60 proxy: dry, balanced, or live.
- Brightness descriptor from spectral centroid: dark, neutral, or bright.
- Dominant low/mid-frequency mode display with Q-factor when available.
- Run-quality validation for alignment, SNR, duration, sample rate, peak amplitude, capture path, browser processing, and decay fit, with required checks weighted above advisory checks.
- High-Q dominant peak caveats for very narrow Q proxies that may be device- or tonal-artifact-sensitive.
- Response caveat panel for direct-path dominance, late-response dominance, unstable decay, and low-mode warnings.
- Transfer-response band table for broad spectral coloration.
- Decay-window and decay-fit diagnostics with low/mid/high decay-band visualization.
- MFCC summary table for compact spectral-envelope statistics.
- JSON acoustic report export with schema version, descriptors, validation results, compact DSP evidence, caveats, and optional explanation output.
- PNG acoustic report export with summary metrics, mel acoustic image, transfer bands, dominant modes, validation checks, and caveats.
- PNG acoustic report export now includes capture metadata, matched impulse/deconvolved response traces, and low/mid/high decay bands.
- Golden public-safe report analysis fixture covering report-building and validation semantics.
- Structured `/api/v1/explain` endpoint for compact DSP evidence.
- Explainability versioning for lab-assistant responses and acoustic reports.
- Leaf JSON Pointer evidence refs and refs-resolved claim metadata alongside legacy explanation string arrays.
- Ungrounded LLM claim rejection with deterministic fallback text and structured warning logs.
- Single-object Gemini JSON response prompting plus safe array unwrap before claim grounding.
- Lab UI explanation panel for observations, acoustic hypotheses, experiment design assistance, physics tutoring, low-confidence troubleshooting, evidence critique, caveats, and next-measurement guidance.
- Optional Gemini lab-assistant path using `gemini-3.1-pro-preview`, `global`, and `HIGH` thinking level through Cloud Run service identity.
- Raw WAV files are excluded from the LLM explanation request path by schema and UI behavior.
- Public Cloud Run deploys keep Gemini LLM calls disabled by default while preserving the deterministic explanation response.
- Run-quality validation counterfactuals that show the margin or minimal operational change needed to reach preferred thresholds.
- Shared descriptor thresholds for report and Lab UI room-character/brightness labels, with nearest-threshold counterfactual text.

## Current Cloud Deployment Features

- Cloud Build defaults that run checks and image builds without deploying from PR/default triggers.
- Cloud Build web validation runs Vitest unit tests before the production web build.
- Main-trigger opt-in Cloud Run deployment through `_DEPLOY_TARGET=cloud-run`.
- Artifact Registry push steps gated behind the deploy target.
- Cloud Run API and web service deployment with configurable memory, CPU, concurrency, timeout, min-instance, and max-instance substitutions.
- Explicit second-generation Cloud Run execution environment and startup CPU boost for API and web deploys.
- Runtime discovery of the deployed API URL before deploying the web service.
- API CORS update using both generated Cloud Run web service URL forms plus optional extra origins.
- Cloud Build substitutions for the API service can enable Vertex Gemini explanations without introducing another Cloud Run service.
- `.gcloudignore` and `.gitignore` coverage for local GCP notes, service account key files, private datasets, and generated artifacts.
- Public-safe GCP deployment guide in `docs/gcp_cloud_run.md`.
- Public-history cleanup runbook for private artifact removal coordination.
- Real-room fixture manifest example and validator for reviewed public-safe report exports, including privacy-key checks and non-failing repeat coverage.

## Planned Features

- No active planned DSP items.
- No active planned room fingerprint items.
- No active planned lab-assistant items.
