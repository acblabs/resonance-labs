# ResonanceLab

ResonanceLab is an open-source, sound-only active acoustic sensing platform. Phase 1 proved the browser-to-API loop, Phase 2 added a NumPy DSP MVP, Phase 3 added a calibration-first browser demo with local fill-level estimates from empty, 50%, and full anchors, and the current Phase 4 work is focused on reference comparison, material hypotheses, and LLM-assisted interpretation before supervised model training.

## Phase 1 Status

Implemented:

- SvelteKit web app with a desktop-first active probe screen.
- Web Audio microphone permission and AudioContext unlock flow.
- Log chirp generation with conservative amplitude defaults.
- AudioWorklet PCM capture with ScriptProcessor fallback.
- Browser-side PCM16 WAV encoding.
- FastAPI `/health`, `/api/v1/probe-config`, `/api/v1/models`, and `/api/v1/analyze`.
- Upload validation and dummy analysis returning duration, sample rate, RMS, peak amplitude, and placeholder alignment metadata.
- Docker Compose for the web/API pair.
- Cloud Build configuration for GCP-based checks and container builds.
- Local Git hook checks for README, CHANGELOG, FEATURES, and project SKILL.md freshness.

Phase 2 DSP MVP implemented:

- Matched-filter logarithmic chirp alignment.
- FFT-domain bandpass filtering around the configured probe range.
- FFT spectral descriptors and dominant ring-down peak detection.
- STFT and mel-spectrogram feature grids for browser visualization.
- Regularized transfer-response band features.
- RMS-envelope decay and RT60 proxy estimates.
- Golden deterministic DSP tests and a committed recorded-style WAV fixture under the existing Python test runner.
- Browser UI tabs for waveform, FFT, STFT, and mel-spectrogram views.
- Dominant peak Q-factor estimates now interpolate sub-bin `-3 dB` bandwidth crossings.
- SNR windows exclude early detected chirps, FFT bandpass filtering zero-pads before cropping, and invalid non-decay fits suppress fit quality.

Phase 3 calibration demo implemented:

- Browser-local IndexedDB calibration profile storage.
- Empty, 50%, full, and free-air reference save workflow.
- Repeated anchor aggregation with local stability estimates.
- Local profile list with create, rename, delete, export, and import actions.
- Feature-vector extraction from Phase 2 DSP output.
- Piecewise feature-distance interpolation between calibration anchors.
- Profile-relative fill estimate, heuristic confidence label, reference-match display, and warnings.
- Free-air reference matching reports no-glass probes instead of forcing a glass fill estimate.
- Weighted geometric confidence aggregation with explicit caps for hard quality and compatibility failures.
- Probe/capture compatibility checks for sample rate, browser family, capture path, audio processing, and probe settings.
- Calibration workflow split into a dedicated Svelte component to keep the probe screen maintainable.
- Calibration math unit tests for incomplete profiles, interpolation, baseline beating, canonical capture signatures, and low-quality probes.

Supervised dataset and baseline tooling implemented, but deferred behind the current reference-comparison milestone:

- Private dataset manifest format for fill-level recordings with session, glass, device, browser, room, and quality metadata.
- Canonical DSP-to-tabular feature extraction for saved API analysis JSON or raw WAV records, using fixed mel summaries and excluding raw STFT-bin model inputs.
- Leakage-aware group holdout splits for session, glass, device, and browser evaluation, backed by scikit-learn grouped splitting when ML dependencies are installed.
- Offline scikit-learn baseline trainer for fill-percent regression and fill-bucket classification.
- Baseline artifact export with `joblib`, feature schema, dropped-feature audit, quality audit, metrics JSON, and generated model card.
- Compiled Phase 4 benchmark command for session, glass, device, and browser holdout regimes.
- Private capture endpoint and operator-only web mode for staging labeled captures into a GCS inbox.
- Dataset Capture form handling for browser number inputs such as fill percent and optional mass
  fields.
- Browser-local known-object references with weighted DSP distance comparison against free-air,
  calibration anchors, and saved material examples.
- `/api/v1/explain` endpoint and Lab UI explanation panel that summarize compact DSP, calibration,
  and reference-comparison evidence without sending raw WAV to the LLM path.
- Optional Gemini lab-assistant integration using `gemini-3.1-pro-preview`, global location, and
  high thinking level through Cloud Run service identity when explicitly enabled.
- Optional single-service Cloud Run capture mode for the existing web/API pair, with Secret Manager
  operator-token loading and private GCS inbox writes when explicitly enabled.
- Capture records enforce server raw-audio policy, validate manifest fragments before publishing, and
  defer bucket/quality inclusion policy to finalization and training.
- Manifest finalization tooling that turns capture inbox fragments into immutable dataset snapshots.
- Recording protocol, manifest JSON Schema, baseline workflow docs, benchmark result area, and evaluation notebook skeleton.

Still manual:

- Real-device mobile testing on Android Chrome and iOS Safari.
- HTTPS test setup for mobile microphone permissions outside localhost.
- Real-device calibrated validation across sessions, vessels, rooms, and browsers.
- Reference-comparison and material-hypothesis workflow before supervised dataset collection.

## Quickstart

Use Python 3.11+ and Node 22+.

```powershell
python -m pip install -r requirements-dev.txt
npm.cmd install
```

For ML-only environments that do not need frontend tooling, install:

```powershell
python -m pip install -r requirements-ml.txt
```

Copy `.env.example` when you want a local environment file. `PUBLIC_API_URL` is read at runtime by the SvelteKit node server; local dev falls back to `http://localhost:8000`, but deployed environments must set it explicitly.

Start the API:

```powershell
python scripts/run_api.py
```

In another shell, start the web app:

```powershell
npm.cmd --workspace @resonancelab/web run dev
```

Open `http://localhost:5173`, press `Start Probe`, allow the microphone, and keep speakers active. Do not use headphones or earbuds for active probing. The signal panel can switch between waveform, FFT, STFT, and mel-spectrogram views after the API returns. To use Phase 3 calibration, save current probe results into the Empty, 50%, and Full anchor slots for a local profile, ideally with repeated captures and a free-air reference. Subsequent probes show a profile-relative fill estimate in the browser.

## Phase 4 Baseline

Supervised Phase 4 training is offline and is now a later milestone. Keep private raw audio and feature files out of git unless explicitly approved. The checked-in example manifest documents schema shape only and is not large enough to train.

```powershell
python scripts/extract_phase4_features.py --manifest path/to/private_manifest.json --output-dir path/to/private_features --manifest-output path/to/private_manifest.features.json
python scripts/train_baseline.py --manifest path/to/private_manifest.features.json --group-by session_id --output-dir models/baseline_sklearn
python scripts/run_phase4_benchmark.py --manifest path/to/private_manifest.features.json --output-dir experiments/results/phase4_benchmark
```

The trainer runs repeated grouped holdouts by default and exports the first split's model. Use `--group-by glass_id`, `--group-by device_id`, and `--group-by browser_id` for separate generalization reports. See `docs/glass_recording_protocol.md`, `docs/phase4_baseline.md`, and `docs/schemas/phase4_dataset_manifest.schema.json`.

Private Cloud Run collection should be enabled only for a deliberate operator campaign on the
existing `resonancelab-web` and `resonancelab-api` services. Keep `_DEPLOY_TARGET=cloud-run`, set
`_PHASE4_CAPTURE_ENABLED=true` and `_PUBLIC_PHASE4_CAPTURE_ENABLED=true`, configure a private GCS
bucket and Secret Manager operator-token secret, then redeploy with both capture flags set to
`false` when collection ends. After collection, use `cloudbuild.phase4.yaml` to finalize a private
capture inbox into an immutable snapshot, or train from an existing snapshot, then upload generated
features, model artifacts, and reports back to private GCS without committing them. Do not train
from a prefix that is receiving live captures.

## Docker Compose

```powershell
docker compose up --build
```

The web app is exposed on `http://localhost:5173`; the API is exposed on `http://localhost:8000`.

## Features

See `FEATURES.md` for the current and planned feature list.

## API

- `GET /health`
- `GET /api/v1/probe-config`
- `GET /api/v1/models`
- `POST /api/v1/analyze`
- `POST /api/v1/explain`

`POST /api/v1/analyze` accepts multipart form data:

- `audio`: PCM WAV file.
- `metadata`: JSON encoded probe metadata.

The response includes upload/decode health, matched-filter alignment metadata, and Phase 2 DSP features. Fill estimates are computed in the browser against local Phase 3 calibration profiles; no local profile IDs or profile anchors are sent to the API.

`POST /api/v1/explain` accepts analysis JSON plus optional compact browser-local calibration and
reference-comparison summaries. It never accepts raw audio. By default it returns a deterministic
DSP/reference summary; set `RESONANCELAB_LLM_ENABLED=true` on the API service to call Gemini through
Vertex AI / Gemini Enterprise Agent Platform.

## Repository Layout

```text
apps/web/               SvelteKit probe UI
services/api/           FastAPI service
packages/resonancelab/  Shared Python audio and DSP helpers
docs/                   Measurement and browser notes
docs/calibration.md     Phase 3 local calibration notes
data/                   Public-safe dataset manifest examples
experiments/results/    Benchmark report landing zone
models/                 Model-card and artifact landing zone
notebooks/              Phase 4 evaluation notebook skeleton
scripts/                Local development helpers
skills/                 Project-specific Codex skill guidance
.githooks/              Local commit hooks
```

## Git Hooks

Install the repository hooks once after cloning:

```powershell
git config core.hooksPath .githooks
```

The pre-commit hook runs structural checks for README, CHANGELOG, FEATURES, and every `skills/*/SKILL.md`. The `commit-msg` hook runs staged freshness checks. Every commit must include an updated `FEATURES.md`; when implementation files are staged, the hook also requires README and CHANGELOG updates, and app/API/package behavior changes require a SKILL.md update.

Use `[skip docs]` in a commit message only when a docs update would be noise. The structural checks still run.

## Cloud Build

`cloudbuild.yaml` is the GCP CI/build entry point. It runs project hygiene checks, API tests, SvelteKit checks/builds, and builds the API and web container images. By default it does not push or deploy; a main-branch Cloud Build trigger can set `_DEPLOY_TARGET=cloud-run` to push images, deploy `resonancelab-api` and `resonancelab-web` to second-generation Cloud Run services with startup CPU boost, wire `PUBLIC_API_URL`, keep Phase 4 capture and LLM calls disabled by default, and update API CORS. Later private operator collection can enable capture on those same two services through `_PHASE4_CAPTURE_ENABLED=true` and `_PUBLIC_PHASE4_CAPTURE_ENABLED=true`; the repo no longer defines separate capture Cloud Run services. Gemini explanations can be enabled on the same API service with `_LLM_ENABLED=true` after granting the runtime service account Vertex AI access.

Keep project IDs, service account details, and deployment-specific substitutions in GCP trigger settings or ignored local files, not in the public repo. See `docs/gcp_cloud_run.md`.

## Validation

```powershell
python -m compileall packages services/api scripts
python -m ruff check .
python -m pytest
python scripts/check_project_docs.py --all
npm.cmd --workspace @resonancelab/web run check
npm.cmd --workspace @resonancelab/web run build
```

The frontend validation commands require `npm.cmd install` first.
