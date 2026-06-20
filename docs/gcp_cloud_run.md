# GCP Cloud Run Deployment

This repository keeps GCP project-specific values out of git. `cloudbuild.yaml` uses public-safe
defaults and Cloud Build substitutions; the actual project ID comes from the Cloud Build project at
runtime as `$PROJECT_ID`.

Use `cloudbuild.yaml` for PR validation and the single Cloud Run service pair:

- Default and PR builds leave `_DEPLOY_TARGET` as `none`, so they run checks and container builds
  without pushing images or deploying services.
- The main deploy trigger sets `_DEPLOY_TARGET=cloud-run`, pushes images to Artifact Registry,
  deploys `resonancelab-api`, deploys `resonancelab-web` with the discovered API URL, and then
  updates API CORS to allow the deployed web origin.
- Phase 4 dataset capture is an optional mode on the same API/web service pair. It is disabled by
  default through `PHASE4_CAPTURE_ENABLED=false` and `PUBLIC_PHASE4_CAPTURE_ENABLED=false`.
- Gemini explanations are also optional on the same API service. The deterministic `/api/v1/explain`
  endpoint is always available, but hosted LLM calls stay disabled by default through
  `RESONANCELAB_LLM_ENABLED=false`.
- The web service uses the project-number API URL, and API CORS allows both Cloud Run URL forms for
  the web service: the `status.url` hostname and the project-number hostname.
- API and web deployments explicitly use the Cloud Run second-generation execution environment with
  startup CPU boost enabled.

Do not create separate capture Cloud Run services for the current architecture. The live topology is
one API service and one web service.

## Required GCP Resources

Create these once in the GCP project that owns the Cloud Build trigger:

```powershell
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com
gcloud artifacts repositories create resonancelab --repository-format=docker --location=us-central1
gcloud iam service-accounts create resonancelab-run --display-name="ResonanceLab Cloud Run"
```

Grant the Cloud Build service account enough access to deploy Cloud Run and push images, and grant
the Cloud Run runtime service account only the roles needed by the running app. For the ordinary
public demo, the runtime service does not need private bucket write access or Secret Manager access.
Add Cloud Storage or Vertex AI roles only when model-artifact loading, private capture, or LLM
features are deliberately enabled. For Gemini explanations, grant the Cloud Run runtime service
account a scoped Vertex AI role such as `roles/aiplatform.user` before setting `_LLM_ENABLED=true`.

If a later private capture campaign uses the single deployed service pair, configure the same
service names with capture enabled and grant the configured runtime service account minimum access to
the private bucket and operator token for the campaign window:

```powershell
gcloud storage buckets create gs://<private-bucket> --location=us-central1 --uniform-bucket-level-access
gcloud secrets create phase4-capture-operator-token --data-file=path/to/private-token.txt
gcloud storage buckets add-iam-policy-binding gs://<private-bucket> --member="serviceAccount:<run-service-account>@<project-id>.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
gcloud secrets add-iam-policy-binding phase4-capture-operator-token --member="serviceAccount:<run-service-account>@<project-id>.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

After a capture campaign, redeploy with capture disabled and remove bucket/secret access that is no
longer needed. The operator bearer token protects the capture endpoint, but IAM remains the hard
boundary for private storage writes.

## Trigger Substitutions

Keep these values in the Cloud Build trigger UI or a private local note, not in committed files:

| Name | Example | Notes |
| --- | --- | --- |
| `_DEPLOY_TARGET` | `cloud-run` | Set only on the main deploy trigger. |
| `_REGION` | `us-central1` | Region for Artifact Registry and Cloud Run. |
| `_ARTIFACT_REGISTRY_REPO` | `resonancelab` | Must already exist. |
| `_RUN_SERVICE_ACCOUNT` | `resonancelab-run` | Service account name, not the full email. |
| `_WEB_SERVICE` | `resonancelab-web` | Cloud Run frontend service name. |
| `_API_SERVICE` | `resonancelab-api` | Cloud Run API service name. |
| `_API_MEMORY` | `1Gi` | Increase to `2Gi` if DSP/model loading needs it. |
| `_API_CONCURRENCY` | `2` | Keep low while DSP work is request-bound. |
| `_API_MAX_INSTANCES` | `3` | Cost and abuse guardrail. |
| `_EXTRA_CORS_ORIGINS` | `none` | Use `none` or a comma-separated list of extra origins. |
| `_PHASE4_CAPTURE_ENABLED` | `false` | Enables the API capture endpoint on the single API service only when set to `true`. |
| `_PUBLIC_PHASE4_CAPTURE_ENABLED` | `false` | Shows the web capture panel on the single web service only when set to `true`. |
| `_PHASE4_CAPTURE_GCS_BUCKET` | `<private-bucket>` | Required only when `_PHASE4_CAPTURE_ENABLED=true`; bucket name only. |
| `_PHASE4_CAPTURE_INBOX_PREFIX` | `phase4/inbox` | Mutable capture inbox prefix. Training must not read this prefix. |
| `_PHASE4_CAPTURE_STORE_RAW_AUDIO` | `true` | Server-side policy for saving raw capture WAVs. |
| `_PHASE4_CAPTURE_OPERATOR_TOKEN_SECRET` | `phase4-capture-operator-token` | Secret Manager secret containing the bearer token; required only when capture is enabled. |
| `_LLM_ENABLED` | `false` | Enables hosted Gemini explanations on the API service only when set to `true`. |
| `_LLM_PROVIDER` | `vertex_gemini` | Current supported hosted provider. |
| `_LLM_MODEL` | `gemini-3.1-pro-preview` | Gemini model ID used by `/api/v1/explain` when enabled. |
| `_LLM_LOCATION` | `global` | Gemini Enterprise Agent Platform / Vertex location. |
| `_LLM_THINKING_LEVEL` | `HIGH` | Gemini 3 thinking level for explanation calls. |

Do not add the GCP project ID to the repository. Cloud Build resolves `$PROJECT_ID` from the
selected GCP project, and deploy logs are private to that project unless you deliberately publish
them.

## Local Secret Hygiene

Use ignored local files for notes or one-off commands, for example `.env.gcp.local`. `.gitignore`
and `.gcloudignore` exclude common service account key patterns, local GCP notes, private datasets,
and generated model artifacts.

Prefer Application Default Credentials or Cloud Build service identities over downloaded service
account keys. If a key file is unavoidable for a temporary local experiment, keep it outside the
repository or under an ignored path and rotate/delete it after use.

## Deployment Flow

When `_DEPLOY_TARGET=cloud-run`, Cloud Build runs:

1. Python checks, docs checks, Ruff, and Pytest.
2. SvelteKit check and build.
3. API and web container builds.
4. Image pushes to Artifact Registry.
5. API deployment with upload and recording-duration guardrails.
6. Web deployment with `PUBLIC_API_URL` set to the project-number API URL.
7. API CORS update with both Cloud Run web URL forms.

Both Cloud Run services are deployed with `--execution-environment=gen2` and `--cpu-boost`.
The default API deployment sets `PHASE4_CAPTURE_ENABLED=false`, and the default web deployment sets
`PUBLIC_PHASE4_CAPTURE_ENABLED=false`. The default API deployment also sets
`RESONANCELAB_LLM_ENABLED=false`; the explanation endpoint still returns a deterministic
DSP/reference summary without making an LLM call.

## Optional Gemini Explanation Mode

The Phase 4 lab assistant uses structured evidence only:

```text
analysis JSON + compact calibration/reference summaries -> /api/v1/explain -> Gemini text JSON
```

Do not send browser WAV blobs, full IndexedDB profiles, or private capture artifacts to the LLM
path. The API schema rejects the raw-audio opt-in flag and compacts FFT/STFT/mel data before any
hosted model call.

To enable hosted Gemini explanations on the existing API service, keep `_DEPLOY_TARGET=cloud-run`
and set:

```text
_LLM_ENABLED=true
_LLM_PROVIDER=vertex_gemini
_LLM_MODEL=gemini-3.1-pro-preview
_LLM_LOCATION=global
_LLM_THINKING_LEVEL=HIGH
```

The deploy step sets `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`,
`GOOGLE_GENAI_USE_ENTERPRISE=true`, and matching `RESONANCELAB_LLM_*` values on the API service.
Use Cloud Run service identity and IAM; do not add Gemini API keys to the app.

After the first deploy, open the web Cloud Run URL on desktop Chrome and Android Chrome. The browser
must use HTTPS for microphone access, which Cloud Run provides by default.

## Optional Private Capture Mode

Dataset capture is now delayed behind the math/physics reference-comparison work. When capture is
needed later, enable it on the existing service names instead of deploying a second service pair:

```text
_DEPLOY_TARGET=cloud-run
_PHASE4_CAPTURE_ENABLED=true
_PUBLIC_PHASE4_CAPTURE_ENABLED=true
_PHASE4_CAPTURE_GCS_BUCKET=<private-bucket>
_PHASE4_CAPTURE_INBOX_PREFIX=phase4/inbox
_PHASE4_CAPTURE_OPERATOR_TOKEN_SECRET=phase4-capture-operator-token
```

The API receives `PHASE4_CAPTURE_ENABLED=true`, reads the operator token from Secret Manager, and
writes to the private GCS inbox through the configured Cloud Run service account. The web service
receives `PUBLIC_PHASE4_CAPTURE_ENABLED=true` and points at the same API service URL.

The API remains unauthenticated at the Cloud Run ingress layer so a mobile browser can call it
directly, but `/api/v1/dataset/captures` still requires the operator bearer token. Treat that token
as a revocable operator credential, rotate it after collection campaigns, keep max instances low,
and disable capture again when the campaign is over.

If older experiments created `resonancelab-api-capture` or `resonancelab-web-capture`, delete those
services after verifying the main `resonancelab-api` and `resonancelab-web` services are healthy.
