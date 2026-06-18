# ResonanceLab

ResonanceLab is an open-source, sound-only active acoustic sensing platform. The Phase 1 milestone proves the browser-to-API loop: a browser emits a short chirp, records microphone PCM, uploads a WAV file to FastAPI, and displays returned signal sanity metrics.

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

Still manual:

- Real-device mobile testing on Android Chrome and iOS Safari.
- HTTPS test setup for mobile microphone permissions outside localhost.
- Phase 2 matched-filter alignment and DSP features.

## Quickstart

Use Python 3.11+ and Node 22+.

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

Open `http://localhost:5173`, press `Start Probe`, allow the microphone, and keep speakers active. Do not use headphones or earbuds for active probing.

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

`POST /api/v1/analyze` accepts multipart form data:

- `audio`: PCM WAV file.
- `metadata`: JSON encoded probe metadata.

The Phase 1 response confirms upload/decode health. It is not a fill-level prediction.

## Repository Layout

```text
apps/web/               SvelteKit probe UI
services/api/           FastAPI service
packages/resonancelab/  Shared Python audio and DSP helpers
docs/                   Measurement and browser notes
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

`cloudbuild.yaml` is the GCP CI/build entry point. It runs project hygiene checks, API tests, SvelteKit checks/builds, and builds the API and web container images for Artifact Registry.

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
