# GCP Cloud Run Deployment

This repository keeps GCP project-specific values out of git. `cloudbuild.yaml` uses public-safe
defaults and Cloud Build substitutions; the actual project ID comes from the Cloud Build project at
runtime as `$PROJECT_ID`.

Use `cloudbuild.yaml` for both PR validation and main-branch deployment:

- Default and PR builds leave `_DEPLOY_TARGET` as `none`, so they run checks and container builds
  without pushing images or deploying services.
- The main-branch deploy trigger sets `_DEPLOY_TARGET=cloud-run`, pushes images to Artifact
  Registry, deploys the API, deploys the web service with the discovered API URL, and then updates
  API CORS to allow the deployed web origin.
- The web service uses the project-number API URL, and API CORS allows both Cloud Run URL forms for
  the web service: the `status.url` hostname and the project-number hostname.
- API and web deployments explicitly use the Cloud Run second-generation execution environment with
  startup CPU boost enabled.

## Required GCP Resources

Create these once in the GCP project that owns the Cloud Build trigger:

```powershell
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create resonancelab --repository-format=docker --location=us-central1
gcloud iam service-accounts create resonancelab-run --display-name="ResonanceLab Cloud Run"
```

Grant the Cloud Build service account enough access to deploy Cloud Run and push images, and grant
the Cloud Run runtime service account only the roles needed by the running app. For the current app,
the runtime service does not need database access. Add Cloud Storage or Vertex AI roles later only
when model-artifact loading or LLM explanations are enabled.

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

After the first deploy, open the web Cloud Run URL on desktop Chrome and Android Chrome. The browser
must use HTTPS for microphone access, which Cloud Run provides by default.
