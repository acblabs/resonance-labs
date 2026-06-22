# ResonanceLab

ResonanceLab is an open-source, sound-only active acoustic sensing platform for room acoustic fingerprints. This project falls under **machine listening**: it uses computational audio analysis to listen to an emitted chirp response and describe acoustic evidence from a space. The app plays a short logarithmic chirp, records the speaker/microphone response, extracts deterministic DSP features, and renders waveform, FFT, STFT, mel-spectrogram, matched impulse response, deconvolved response, decay, transfer-response, MFCC, caveat, and room-mode descriptors.

The current product direction is **Room Acoustic Fingerprint** plus **Acoustic Image Export**. In machine-listening terms, ResonanceLab is focused on active acoustic measurement and room-response evidence, not speech recognition, general audio event detection, object-state claims, or geometry reconstruction from a single speaker and microphone.

## Status

Implemented:

- SvelteKit web app with a desktop-first active probe screen.
- Web Audio microphone permission and AudioContext unlock flow.
- Log chirp generation with conservative amplitude defaults.
- AudioWorklet PCM capture with ScriptProcessor fallback.
- Browser-side mono PCM16 WAV encoding.
- FastAPI `/health`, `/api/v1/probe-config`, `/api/v1/models`, `/api/v1/analyze`, and `/api/v1/explain`.
- Upload validation for size, content type, WAV structure, sample rate, duration, RMS, peak amplitude, and DC offset.
- Matched-filter chirp alignment with detected/expected chirp timing.
- FFT-domain bandpass filtering, spectral descriptors, MFCC summary statistics, dominant peak detection, Q-factor proxy, low-mode grouping, STFT, mel-spectrogram, transfer-response bands, RMS-envelope decay, and RT60 proxy.
- Matched-filter impulse-response and regularized deconvolved-response traces, with low/mid/high decay-band summaries for diagnostics.
- Browser views for waveform, FFT, STFT, mel-spectrogram, matched impulse response, and deconvolved response.
- Room descriptors for dry/live character, brightness, dominant mode, SNR, alignment, centroid, rolloff, and warnings.
- Direct-path and room-response caveats for low SNR, weak alignment, unstable decay, direct/late response balance, high-Q peaks, and low-mode uncertainty.
- Run-quality validation for alignment, SNR, duration, sample rate, peak amplitude, capture path, browser processing, and decay fit, with required checks weighted above advisory checks.
- Exportable JSON and PNG acoustic reports from the Lab UI.
- Deterministic `/api/v1/explain` fallback plus optional Gemini lab-assistant integration for observations, acoustic hypotheses, experiment design, physics tutoring, low-confidence troubleshooting, evidence critique, and next-measurement guidance over compact structured DSP evidence only.
- Explainability metadata for `/api/v1/explain`, including leaf JSON Pointer evidence refs, refs-resolved claim objects, authoritative evidence values, and ungrounded-claim fallback behavior.
- LLM prompt-injection hardening that treats operator questions as untrusted context instead of citable evidence and returns generic hosted-provider failures to clients.
- Validation and descriptor counterfactuals that show the margin or minimal input change needed to flip run-quality and room-fingerprint labels.
- Docker Compose for the web/API pair.
- Cloud Build checks, supply-chain pin checks, image builds, and opt-in Cloud Run deployment with digest-pinned build images.
- Non-root API and web production containers with digest-pinned base images.
- Local Git hook checks for README, CHANGELOG, FEATURES, and project SKILL.md freshness.

Still manual:

- Real-device Android Chrome and iOS Safari validation.
- HTTPS mobile testing outside localhost.
- Real-device review of response caveats and decay-band visuals.

## Quickstart

Use Python 3.13+ and Node 22+.

```powershell
python -m pip install -r requirements-dev.txt
npm.cmd install
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

Open `http://localhost:5173`, press `Start Probe`, allow the microphone, and keep speakers active. Do not use headphones or earbuds for active probing. The signal panel can switch between waveform, FFT, STFT, mel-spectrogram, matched impulse-response, and deconvolved-response views after the API returns.

After a successful probe, export JSON or PNG reports from the Lab UI. JSON reports are the preferred public-safe artifact for validation records because they contain derived DSP evidence without raw WAV bytes and minimize reflected browser metadata.

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

The response includes upload/decode health, matched-filter alignment metadata, compact spectral grids, MFCC summaries, transfer-response bands, response traces, low-mode groups, dominant peaks, decay features, caveats, and warnings.

`POST /api/v1/explain` accepts analysis JSON and `include_raw_audio=false`. It never accepts raw audio. Optional `operator_question` text is treated as untrusted context and is not part of the citable evidence refs. By default it returns a deterministic DSP explanation with experiment design help, physics tutoring, low-confidence troubleshooting, and evidence critique; set `RESONANCELAB_LLM_ENABLED=true` on the API service to call Gemini through Vertex AI / Gemini Enterprise Agent Platform. The request body is capped by `RESONANCELAB_MAX_EXPLAIN_BODY_BYTES` and defaults to 512 KiB; Gemini output is capped by `RESONANCELAB_LLM_MAX_OUTPUT_TOKENS`, which defaults to 8192 so high-thinking calls have room to return compact JSON.

Explain responses include compatibility string arrays plus richer claim arrays with JSON Pointer evidence references. Hosted Gemini calls request single-object JSON claim output, and the API computes grounding metadata after resolving refs. See `docs/explainability.md` for grounding rules and counterfactual semantics.

## Repository Layout

```text
apps/web/               SvelteKit room-fingerprint UI
services/api/           FastAPI service
packages/resonancelab/  Shared Python audio and DSP helpers
docs/                   Measurement, browser, deployment, and room-fingerprint notes
data/                   Public-safe fixture metadata landing zone
experiments/results/    Public-safe report landing zone
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

`cloudbuild.yaml` is the GCP CI/build entry point. It runs project hygiene checks, supply-chain pin checks, API tests, SvelteKit checks/builds, and builds the API and web container images. Build-step images and Docker base images are digest-pinned. By default it does not push or deploy; a main-branch Cloud Build trigger can set `_DEPLOY_TARGET=cloud-run` to push images, deploy `resonancelab-api` and `resonancelab-web` to second-generation Cloud Run services with startup CPU boost, wire `PUBLIC_API_URL`, and update API CORS. Gemini explanations can be enabled on the same API service with `_LLM_ENABLED=true` after granting the runtime service account Vertex AI access; `_LLM_MAX_OUTPUT_TOKENS` controls the hosted explanation output budget.

Keep project IDs, service account details, and deployment-specific substitutions in GCP trigger settings or ignored local files, not in the public repo. See `docs/gcp_cloud_run.md`.

## Validation

```powershell
python -m compileall packages services/api scripts
python scripts/check_supply_chain.py
python -m ruff check .
python -m pytest
python scripts/check_project_docs.py --all
python scripts/validate_real_room_fixtures.py data/real_room_fixtures/manifest.example.json --allow-missing
npm.cmd --workspace @resonancelab/web run check
npm.cmd --workspace @resonancelab/web run test
npm.cmd --workspace @resonancelab/web run build
```

The frontend validation commands require `npm.cmd install` first.
