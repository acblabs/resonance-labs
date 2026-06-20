# GCP Cloud Run Deployment

This repository keeps GCP project-specific values out of git. `cloudbuild.yaml` uses public-safe
defaults and Cloud Build substitutions; the actual project ID comes from the Cloud Build project at
runtime as `$PROJECT_ID`.

Use `cloudbuild.yaml` for PR validation, main-branch public deployment, and the private Phase 4
operator capture deployment:

- Default and PR builds leave `_DEPLOY_TARGET` as `none`, so they run checks and container builds
  without pushing images or deploying services.
- The main-branch deploy trigger sets `_DEPLOY_TARGET=cloud-run`, pushes images to Artifact
  Registry, deploys the API, deploys the web service with the discovered API URL, and then updates
  API CORS to allow the deployed web origin. This public target explicitly keeps Phase 4 capture
  disabled in both services.
- A private operator trigger or manual build can set `_DEPLOY_TARGET=cloud-run-capture` to deploy
  separate `resonancelab-api-capture` and `resonancelab-web-capture` services. The capture web
  service exposes the operator-only capture panel, and the capture API writes labeled artifacts to a
  private GCS inbox.
- The web service uses the project-number API URL, and API CORS allows both Cloud Run URL forms for
  the web service: the `status.url` hostname and the project-number hostname.
- API and web deployments explicitly use the Cloud Run second-generation execution environment with
  startup CPU boost enabled.

## Required GCP Resources

Create these once in the GCP project that owns the Cloud Build trigger:

```powershell
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com
gcloud artifacts repositories create resonancelab --repository-format=docker --location=us-central1
gcloud iam service-accounts create resonancelab-run --display-name="ResonanceLab Cloud Run"
```

Grant the Cloud Build service account enough access to deploy Cloud Run and push images, and grant
the Cloud Run runtime service account only the roles needed by the running app. For the current app,
the runtime service does not need database access. Add Cloud Storage or Vertex AI roles later only
when model-artifact loading or LLM explanations are enabled.

For Phase 4 capture, use a separate runtime identity with write access only to the private capture
bucket and secret-read access only to the operator token:

```powershell
gcloud iam service-accounts create resonancelab-capture-run --display-name="ResonanceLab Capture Cloud Run"
gcloud storage buckets create gs://<private-bucket> --location=us-central1 --uniform-bucket-level-access
gcloud secrets create phase4-capture-operator-token --data-file=path/to/private-token.txt
gcloud storage buckets add-iam-policy-binding gs://<private-bucket> --member="serviceAccount:resonancelab-capture-run@<project-id>.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
gcloud secrets add-iam-policy-binding phase4-capture-operator-token --member="serviceAccount:resonancelab-capture-run@<project-id>.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Do not reuse the public runtime service account for private capture writes. The public web/API
services should not have the capture bucket configured and should not have bucket write IAM.

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
| `_CAPTURE_WEB_SERVICE` | `resonancelab-web-capture` | Private Phase 4 operator frontend service name. |
| `_CAPTURE_API_SERVICE` | `resonancelab-api-capture` | Private Phase 4 capture API service name. |
| `_CAPTURE_RUN_SERVICE_ACCOUNT` | `resonancelab-capture-run` | Capture API service account with private bucket write IAM. |
| `_API_MEMORY` | `1Gi` | Increase to `2Gi` if DSP/model loading needs it. |
| `_API_CONCURRENCY` | `2` | Keep low while DSP work is request-bound. |
| `_API_MAX_INSTANCES` | `3` | Cost and abuse guardrail. |
| `_EXTRA_CORS_ORIGINS` | `none` | Use `none` or a comma-separated list of extra origins. |
| `_CAPTURE_EXTRA_CORS_ORIGINS` | `none` | Optional additional origins for the capture API only. |
| `_PHASE4_CAPTURE_GCS_BUCKET` | `<private-bucket>` | Required for `_DEPLOY_TARGET=cloud-run-capture`; bucket name only. |
| `_PHASE4_CAPTURE_INBOX_PREFIX` | `phase4/inbox` | Mutable capture inbox prefix. Training must not read this prefix. |
| `_PHASE4_CAPTURE_STORE_RAW_AUDIO` | `true` | Server-side policy for saving raw capture WAVs. |
| `_PHASE4_CAPTURE_OPERATOR_TOKEN_SECRET` | `phase4-capture-operator-token` | Secret Manager secret containing the bearer token. |

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
The public API is deployed with `PHASE4_CAPTURE_ENABLED=false`, and the public web service is
deployed with `PUBLIC_PHASE4_CAPTURE_ENABLED=false`.

After the first deploy, open the web Cloud Run URL on desktop Chrome and Android Chrome. The browser
must use HTTPS for microphone access, which Cloud Run provides by default.

## Phase 4 Operator Capture Deployment

When `_DEPLOY_TARGET=cloud-run-capture`, Cloud Build uses the same tested container images but deploys
separate Cloud Run services:

1. Capture API deployment with `PHASE4_CAPTURE_ENABLED=true`, private GCS bucket settings, and the
   operator token mounted from Secret Manager as `PHASE4_CAPTURE_OPERATOR_TOKEN`.
2. Capture web deployment with `PUBLIC_PHASE4_CAPTURE_ENABLED=true` and `PUBLIC_API_URL` pointing to
   the capture API.
3. Capture API CORS update with both generated capture web URL forms.

The capture API remains unauthenticated at the Cloud Run ingress layer so a mobile browser can call
it directly, but `/api/v1/dataset/captures` still requires the operator bearer token. Treat that
token as a revocable operator credential, rotate it after collection campaigns, and keep capture
service max instances low. The harder boundary is IAM: only the capture API service account should be
able to write the private bucket.

Do not set `_CAPTURE_WEB_SERVICE` or `_CAPTURE_API_SERVICE` to the public service names. Keep the
operator URL out of public docs and use `cloudbuild.phase4.yaml` after collection to finalize the
mutable inbox into an immutable dataset snapshot before training.
