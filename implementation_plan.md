# ResonanceLab Implementation Plan

## 1. Project Summary

ResonanceLab is an open-source, sound-only active acoustic sensing platform. It uses a device speaker to emit a controlled chirp, records the response with the device microphone, and extracts digital signal processing features that describe the acoustic fingerprint of a room or capture position.

Current promise:

```text
ResonanceLab turns a short chirp capture into a room acoustic fingerprint and visual report.
```

The project avoids cameras and images entirely. The system uses browser audio capture, controlled chirp playback, matched filtering, FFT/STFT/mel-spectrogram features, transfer-response summaries, decay estimates, mode candidates, and optional LLM explanation over structured evidence.

## 2. Naming and Source of Truth

```text
Product name: ResonanceLab
GitHub repository: resonance-labs
Python package import: resonancelab
GCP resource prefix: resonancelab
Public docs title: ResonanceLab
```

GitHub is the collaboration surface. Cloud Build is the deploy-focused CI/CD surface. The public alpha should be usable on mobile by opening the Cloud Run HTTPS URL in a mobile browser, with Android Chrome as the primary mobile target.

## 3. Current Architecture

```text
SvelteKit web app
  - user opens the Cloud Run HTTPS URL on desktop or mobile
  - user starts probe with a button press
  - unlocks AudioContext
  - plays controlled chirp
  - records microphone response
  - uploads audio and metadata when analysis is requested
        |
        v
FastAPI Cloud Run API
  - validates upload size, duration, and content type
  - decodes PCM WAV
  - aligns recording to known chirp
  - extracts DSP features
  - returns compact room-fingerprint JSON
  - optionally calls Gemini over structured evidence only
        |
        v
Structured result JSON
  - Svelte visualizations
  - descriptors and caveats
  - future PNG/JSON acoustic report export
```

The live topology is one web service and one API service. There is no public write path for private recordings.

## 4. Important Decisions

### Use

- SvelteKit for the frontend web app.
- Web Audio API for microphone access and chirp playback.
- AudioWorklet PCM capture as the preferred browser capture path.
- ScriptProcessor as the compatibility fallback.
- Python + FastAPI for the backend API.
- NumPy-first DSP helpers in `packages/resonancelab`.
- `requirements.txt` and `requirements-dev.txt` for Python dependencies.
- Cloud Run for hosting the web app and API.
- Cloud Build for deploy-focused CI/CD from GitHub to Cloud Run.
- Vertex AI / Gemini through Cloud Run service identity and IAM, not API keys.
- Cloud Logging for runtime observability.
- Git hooks and CI checks for repo hygiene and docs freshness.

### Do Not Use Yet

- Firestore, Cloud SQL, BigQuery, Pub/Sub, Dataflow, or GKE.
- User accounts or cloud-synced personal history.
- Native mobile apps.
- Camera or image input.
- Raw audio uploads to hosted LLM providers.
- Heavy deep-learning frameworks in the API runtime.
- Unsupported claims about room geometry or spatial reconstruction.

## 5. Product Direction

The product path is now:

```text
Room Acoustic Fingerprint
+ Spectrogram / Acoustic Image Export
```

The app should show the actual measurement workflow as the first screen. A polished report should eventually include:

- Chirp response waveform.
- Impulse or deconvolution proxy.
- STFT or mel-spectrogram.
- Decay-band visualization.
- Detected mode candidates.
- Room character, brightness, echo/deadness descriptors.
- Quality flags and caveats.

Honesty caveat:

```text
A single speaker and single microphone can measure an acoustic fingerprint.
They cannot reconstruct room geometry or produce a spatial map.
```

## 6. Frontend Plan

Frontend responsibilities:

- Microphone permission flow.
- AudioContext unlock from user interaction.
- Chirp generation and playback.
- Microphone recording during pre-roll, chirp playback, and post-roll.
- Browser constraint reporting when available.
- Browser-side WAV encoding.
- Upload to FastAPI.
- Waveform, FFT, STFT, and mel-spectrogram rendering.
- Room descriptors and quality caveats.
- Optional lab-assistant explanation panel.
- Future PNG/JSON acoustic report export.
- Hearing-comfort guardrails: volume cap, short probe duration, no-headphones warning, and conservative defaults.

Routes:

```text
/
  Lab entry point.

/lab
  Main chirp probe and analysis workflow.

/physics
  Future deeper explorer for FFT, spectrogram, impulse proxy, and decay analysis.
```

## 7. Backend Plan

Current API endpoints:

```text
GET /health
  Health check.

GET /api/v1/probe-config
  Returns default chirp configuration and server-supported limits.

GET /api/v1/models
  Returns active model status. Current phase is phase_4_room_fingerprint.

POST /api/v1/analyze
  Upload PCM WAV plus chirp metadata.
  Return DSP features, compact grids, descriptors, and warnings.

POST /api/v1/explain
  Send structured analysis JSON with include_raw_audio=false.
  Return deterministic or hosted Gemini explanation.
```

Backend guardrails:

- Maximum upload size.
- Maximum recording duration.
- Allowed content types.
- WAV/PCM preferred.
- Request body caps on explanation payloads.
- No public unauthenticated write endpoint to private storage.
- LLM explanation off by default.
- Request logging without storing raw audio by default.
- Clear warning fields in every analysis response.

## 8. DSP Pipeline

```text
recorded audio + chirp metadata
  -> validate duration, sample rate, and channels
  -> decode to float PCM
  -> mono conversion
  -> preserve native sample rate
  -> estimate pre-roll noise floor
  -> align recording to emitted chirp with matched filtering
  -> analyze post-chirp and driven-response windows
  -> bandpass filter using validated range
  -> FFT/STFT/mel-spectrogram features
  -> regularized transfer-response bands
  -> dominant peak detection and Q proxy
  -> RMS-envelope decay and RT60 proxy
  -> room descriptors and caveats
  -> structured result JSON
```

Core features:

- Alignment confidence.
- Signal-to-noise ratio.
- Spectral centroid, bandwidth, rolloff, and floor.
- Transfer-response magnitude by band.
- Dominant peak frequencies, prominences, and Q-factor proxies.
- Decay rate, RT60 proxy, and weighted fit quality.
- STFT and mel-spectrogram grids.

## 9. Acoustic Report Export

The report exporter should use analysis JSON, not raw audio, whenever possible.

Minimum report sections:

- Metadata header.
- Waveform strip.
- Impulse/deconvolution proxy strip.
- Spectrogram heatmap.
- Decay-band panel.
- Mode candidate table.
- Descriptor summary.
- Caveat footer.

Export formats:

- PNG for sharing.
- JSON for reproducible measurement notes.

## 10. Cloud Run Alpha

Implemented:

- Artifact Registry push/deploy path in Cloud Build.
- `resonancelab-web` and `resonancelab-api` deploy to Cloud Run from Cloud Build.
- One web service and one API service.
- API and web deploys use second-generation Cloud Run execution and startup CPU boost.
- The web service receives the deployed API URL at runtime.
- API CORS is configured for generated Cloud Run web origins.
- Memory, CPU, concurrency, timeout, and max-instance guardrails are represented as deploy substitutions.
- A runtime Cloud Run service account is attached to deployed services.
- Gemini explanations can be enabled with `_LLM_ENABLED=true`.

Still pending:

- Configure and validate the GitHub-connected main-branch trigger.
- Validate the Cloud Run demo on Android Chrome.
- Document iOS Safari behavior after real testing.
- Run a small alpha load/cost smoke test.

## 11. Testing Strategy

Python tests:

- Audio decoding.
- WAV/PCM parsing.
- Sample-rate handling.
- Chirp generation.
- Chirp alignment.
- Filtering.
- FFT/STFT/mel feature extraction.
- Transfer-response feature extraction.
- Decay estimation.
- Upload validation limits.
- Explanation schema and evidence compaction.

Frontend tests:

- AudioContext unlock flow.
- Chirp playback controls.
- Recording state transitions.
- WAV encoding.
- Upload flow.
- Result rendering.

Golden fixtures:

- Deterministic generated signals.
- Analytic damped-sinusoid checks.
- Small recorded-style WAV fixture.
- Future real room fixtures with tolerant assertions.

## 12. LLM Layer

The LLM receives only structured analysis JSON, not raw audio.

Use it for:

- Result explanation.
- Experiment design.
- Physics tutoring.
- Debugging low confidence.
- Report text drafting.

Do not use it for:

- Raw audio inference.
- Replacing DSP.
- Spatial reconstruction claims.
- Unsupported accuracy claims.

LLM deployment rules:

- Off by default in public alpha.
- No LLM API keys stored for the primary GCP path.
- Hosted calls made through Vertex AI / Gemini using Cloud Run service identity and IAM.
- Cost capped with Cloud Run max instances and application-level limits.

## 13. Roadmap

### Phase 1: Browser Chirp Capture and API Upload

Desktop Chrome chirp to WAV upload to FastAPI analysis to browser result display.

### Phase 2: DSP MVP and Golden Tests

Matched filtering, bandpass filtering, FFT, STFT, transfer response, mel-spectrogram, dominant peaks, decay estimate, and golden tests.

### Phase 3: Room Fingerprint UI

First-screen room acoustic workflow with waveform/FFT/spectrogram views, descriptors, quality warnings, and lab assistant explanation.

### Phase 4: Acoustic Image Export

Polished PNG and JSON report generation with response plots, spectrograms, decay bands, mode candidates, descriptors, and caveats.

### Phase 5: Cloud Run Alpha

GitHub-connected Cloud Build trigger, Cloud Run web/API services, mobile browser validation, and public-safe deployment docs.

### Phase 6: Real Room Fixtures

Small real recordings across devices, browsers, rooms, and positions with metadata and tolerant tests.

## 14. Storage Summary

For the current product:

```text
Browser memory
  transient capture state
  current analysis result

Git repository
  docs
  source code
  golden test fixtures
  small public-safe examples

Cloud Run
  API and web runtime

Optional future export
  user-triggered PNG/JSON report download
```

Do not use Firestore in the current architecture.

## 15. Final Recommendation

Keep ResonanceLab narrow and honest:

```text
SvelteKit web app
+ Web Audio chirp probe
+ FastAPI
+ NumPy DSP
+ Cloud Build
+ Cloud Run
+ optional Gemini explanation over structured JSON
+ acoustic report export
```

The first real proof is not a broad classifier. It is a repeatable, visually rich acoustic fingerprint that behaves sensibly across repeated room captures and clearly states its limits.
