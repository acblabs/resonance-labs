# Deferred Private Dataset Workflow

The supervised Phase 4 dataset path is no longer the immediate next milestone. The current product
direction is to first compare probes against free-air and known-object references using deterministic
DSP, physics constraints, and an LLM lab-assistant layer that receives structured summaries only.

Keep this workflow for the later supervised-training phase. It describes how to store private
recordings, finalize immutable dataset snapshots, and run the offline scikit-learn/XGBoost baseline
without committing raw audio, generated features, benchmark outputs, model artifacts, bucket names,
or project identifiers to the public repo.

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

1. Keep capture disabled while doing the math/physics reference-comparison work.
2. When supervised data collection resumes, enable capture only for a private operator campaign.
   Cloud Run uses the same `resonancelab-api` and `resonancelab-web` services; do not deploy a
   separate capture service pair.
3. Run probes in the Lab UI with `PUBLIC_PHASE4_CAPTURE_ENABLED=true`, and save labeled captures to
   the private API. The API analyzes the WAV, writes analysis JSON, writes the WAV only when the
   server allows `PHASE4_CAPTURE_STORE_RAW_AUDIO=true`, validates the manifest-ready fragment, and
   writes one `.record.json` fragment last under `phase4/inbox/<session-id>/`.
4. Run the finalization script locally or in Cloud Build. The script itself works on filesystem
   paths. For a GCS inbox, prefer the Cloud Build path below or explicitly sync the inbox to a local
   operator workspace first:

```powershell
gcloud storage rsync --recursive gs://<private-bucket>/phase4/inbox path/to/inbox
python scripts/build_phase4_manifest.py --inbox-dir path/to/inbox --snapshot-dir path/to/snapshot --dataset-id phase4-private-2026-06-19
gcloud storage rsync --recursive path/to/snapshot gs://<private-bucket>/phase4/datasets/2026-06-19
```

5. Train from the finalized snapshot, not from the inbox.
6. Redeploy the single service pair with capture disabled and remove no-longer-needed bucket/secret
   IAM after collection.

## Optional Cloud Run Capture Mode

Use the normal Cloud Run deployment target and enable capture on the existing service names only
when a private collection campaign is active:

```text
_DEPLOY_TARGET=cloud-run
_WEB_SERVICE=resonancelab-web
_API_SERVICE=resonancelab-api
_PHASE4_CAPTURE_ENABLED=true
_PUBLIC_PHASE4_CAPTURE_ENABLED=true
_PHASE4_CAPTURE_GCS_BUCKET=<private-bucket>
_PHASE4_CAPTURE_INBOX_PREFIX=phase4/inbox
_PHASE4_CAPTURE_OPERATOR_TOKEN_SECRET=phase4-capture-operator-token
```

The API receives `PHASE4_CAPTURE_ENABLED=true`, reads the operator token from Secret Manager, and
writes to the private GCS inbox through the configured Cloud Run service account. The web service
receives `PUBLIC_PHASE4_CAPTURE_ENABLED=true` and points at the same API URL.

For the ordinary public demo, deploy with:

```text
_PHASE4_CAPTURE_ENABLED=false
_PUBLIC_PHASE4_CAPTURE_ENABLED=false
```

The capture API can remain unauthenticated at the Cloud Run ingress layer so mobile browsers can
call it directly, but the dataset capture endpoint still requires the operator bearer token. Do not
publish the token, do not commit bucket or secret names when those values reveal private
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
a capture-time bucket policy. Capture also persists raw quality metrics such as alignment
confidence, SNR, and warnings, but training and benchmark commands apply the inclusion thresholds.

## Private Capture Security

The capture endpoint is disabled unless `PHASE4_CAPTURE_ENABLED=true`, and it also requires an
operator bearer token from `PHASE4_CAPTURE_OPERATOR_TOKEN`. Treat those as soft gates. The hard gate
is IAM: only the deployed API runtime identity should have permission to write private capture
objects during an active campaign.

Because the current topology intentionally has one API service and one web service, capture mode is
an operator window rather than a permanent second deployment. Keep capture disabled in the ordinary
public demo, and remove private bucket write access from the runtime identity when the campaign ends.

## Collection Minimum

A useful supervised benchmark needs repeated captures across:

- Multiple sessions.
- At least one stable glass with repeated fills for session holdout.
- More than one glass for cross-glass claims.
- More than one device for cross-device claims.
- More than one browser or browser version for cross-browser claims.
- Clear fill labels from water mass or another documented ground-truth method.

Small single-device datasets are fine for smoke tests, but they should not be treated as supervised
Phase 4 exit evidence.
