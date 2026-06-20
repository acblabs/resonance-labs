# Phase 4 Private GCP Workflow

Phase 4 cannot be complete until real private recordings exist. The repository now has the tooling
to keep that dataset, generated features, benchmark reports, and model artifacts in a private GCP
bucket instead of the public repo.

Do not commit the GCP project identifier, bucket name, raw audio, generated feature JSON, benchmark
outputs, or model artifacts. Keep those values in a private Cloud Build trigger, local ignored env
file, or private notes.

## Private GCS Layout

Capture writes and training reads use different prefixes. Live captures land in a mutable inbox:

```text
gs://<private-bucket>/phase4/inbox/
  <session-id>/
    audio/
    analysis/
    records/
```

A manual finalization step materializes an immutable snapshot:

```text
gs://<private-bucket>/phase4/datasets/<snapshot-id>/
  manifest.json
  audio/
  analysis/
  features/
```

Do not write captures directly into `phase4/datasets/current/` or any prefix that a training build
can read. `current` may be a pointer or copy of the latest finalized snapshot, but it must not be
mutated while Cloud Build is training.

The manifest should use paths relative to `manifest.json`, not `gs://` URLs:

```json
{
  "id": "session-001-glass-a-empty-001",
  "analysis_path": "analysis/session-001/glass-a-empty-001.analysis.json"
}
```

For benchmark runs, prefer `features_path` or `analysis_path` records. Raw `audio_path` records are
supported when `_RUN_EXTRACTION=true`; the private Cloud Build pipeline writes a derived
`manifest.features.json` that points at generated feature JSON before training.

## Operator Capture Flow

1. Enable the private capture API only on a private deployment or local operator environment. For
   Cloud Run, prefer the dedicated `_DEPLOY_TARGET=cloud-run-capture` path in `cloudbuild.yaml`,
   which deploys separate capture API and web services.
2. Run probes in the Lab UI with `PUBLIC_PHASE4_CAPTURE_ENABLED=true`. The public Cloud Run demo
   should continue to deploy with `PUBLIC_PHASE4_CAPTURE_ENABLED=false`.
3. Save labeled captures to the private API. The API analyzes the WAV, writes analysis JSON, writes
   the WAV only when the server allows `PHASE4_CAPTURE_STORE_RAW_AUDIO=true`, validates the
   manifest-ready fragment, and writes one `.record.json` fragment last under
   `phase4/inbox/<session-id>/`.
4. Run the finalization script locally or in Cloud Build. The script itself works on filesystem
   paths. For a GCS inbox, prefer the Cloud Build path below or explicitly sync the inbox to a local
   operator workspace first:

```powershell
gcloud storage rsync --recursive gs://<private-bucket>/phase4/inbox path/to/inbox
python scripts/build_phase4_manifest.py --inbox-dir path/to/inbox --snapshot-dir path/to/snapshot --dataset-id phase4-private-2026-06-19
gcloud storage rsync --recursive path/to/snapshot gs://<private-bucket>/phase4/datasets/2026-06-19
```

5. Train from the finalized snapshot, not from the inbox.

## Operator Cloud Run Capture Deployment

Use the normal public Cloud Run deployment for demos and the dedicated capture deployment for private
collection. A capture deploy sets:

```text
_DEPLOY_TARGET=cloud-run-capture
_CAPTURE_WEB_SERVICE=resonancelab-web-capture
_CAPTURE_API_SERVICE=resonancelab-api-capture
_CAPTURE_RUN_SERVICE_ACCOUNT=resonancelab-capture-run
_PHASE4_CAPTURE_GCS_BUCKET=<private-bucket>
_PHASE4_CAPTURE_INBOX_PREFIX=phase4/inbox
_PHASE4_CAPTURE_OPERATOR_TOKEN_SECRET=phase4-capture-operator-token
```

The capture API receives `PHASE4_CAPTURE_ENABLED=true`, reads the operator token from Secret
Manager, and writes to the private GCS inbox through its Cloud Run service account. The capture web
service receives `PUBLIC_PHASE4_CAPTURE_ENABLED=true` and points at the capture API URL. The normal
public services are deployed with capture disabled.

Keep these identities separate:

- `resonancelab-run`: public web/API runtime identity, no private capture bucket write access.
- `resonancelab-capture-run`: capture API runtime identity, private bucket write access and access
  to the operator-token secret.

The capture API can remain unauthenticated at the Cloud Run ingress layer so mobile browsers can call
it directly, but the dataset capture endpoint still requires the operator bearer token. Do not
publish the operator URL, do not commit the bucket or token name when those values reveal private
infrastructure, and rotate the token after collection campaigns.

## Private Cloud Build Run

`cloudbuild.phase4.yaml` is a private-data pipeline. It:

1. Downloads either a finalized dataset prefix or the private inbox when `_FINALIZE_DATASET=true`.
2. Optionally finalizes the inbox into an immutable snapshot and uploads that snapshot.
3. Optionally extracts canonical Phase 4 features and writes a derived manifest.
4. Trains the session-holdout baseline.
5. Runs the compiled session, glass, device, and browser benchmark report.
6. Uploads outputs back to a private GCS prefix under the Cloud Build ID.

Configure these substitutions in a private trigger or manual build command:

| Name | Example | Notes |
| --- | --- | --- |
| `_PRIVATE_GCS_BUCKET` | `<private-bucket>` | Bucket name only, not `gs://...`. |
| `_PRIVATE_INPUT_PREFIX` | `phase4/datasets/2026-06-19` | Finalized snapshot prefix containing `manifest.json`. |
| `_FINALIZE_DATASET` | `false` | Set `true` to build a snapshot from `_PRIVATE_INBOX_PREFIX`. |
| `_PRIVATE_INBOX_PREFIX` | `phase4/inbox` | Mutable capture inbox used only by finalization. |
| `_PRIVATE_SNAPSHOT_PREFIX` | `phase4/datasets/finalized` | Finalized snapshots upload under this prefix plus `$BUILD_ID`. |
| `_DATASET_ID` | `phase4-private` | Dataset ID prefix for finalized manifests. |
| `_PRIVATE_OUTPUT_PREFIX` | `phase4/runs` | Outputs upload under this prefix plus `$BUILD_ID`. |
| `_MANIFEST_FILE` | `manifest.json` | Manifest filename under the input prefix. |
| `_RUN_EXTRACTION` | `true` | Use `false` if the manifest already points to feature JSON. |
| `_MODEL_FAMILY` | `linear` | Use `forest` only after the linear baseline is established. |

The bucket and project values must stay out of the committed config. Cloud Build injects
`$PROJECT_ID` from the selected GCP project at runtime.

For v1, prefer a manual "Finalize Dataset + Train" run over Eventarc. Eventarc on object finalize is
a later refinement after finalized snapshot objects are immutable.

Finalization derives `label.fill_bucket` from the snapshot's `label_schema.buckets_percent`.
Capture fragments should persist continuous `label.fill_percent` and mass-derived label fields, not
a capture-time bucket policy. Capture also persists raw quality metrics such as alignment confidence,
SNR, and warnings, but training and benchmark commands apply the inclusion thresholds.

## Private Capture Security

The capture endpoint is disabled unless `PHASE4_CAPTURE_ENABLED=true`, and it also requires an
operator bearer token from `PHASE4_CAPTURE_OPERATOR_TOKEN`. Treat those as soft gates. The hard gate
is IAM: only the private capture service or revision should run with a service account that can write
to the private bucket. The public demo service should not have the bucket configured or the storage
permission.

## Collection Minimum

A useful Phase 4 benchmark needs repeated captures across:

- Multiple sessions.
- At least one stable glass with repeated fills for session holdout.
- More than one glass for cross-glass claims.
- More than one device for cross-device claims.
- More than one browser or browser version for cross-browser claims.
- Clear fill labels from water mass or another documented ground-truth method.

Small single-device datasets are fine for smoke tests, but they should not be treated as Phase 4
exit evidence.
