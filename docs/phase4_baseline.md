# Phase 4 Baseline Workflow

Phase 4 uses scikit-learn as the first baseline stack. Training is offline and writes artifacts under
`models/`; the production API should not load a model until a benchmark report and model card justify
serving it.

This is an absolute-label supervised baseline trained across recorded examples. It is distinct from
the Phase 3 browser-local profile calibration, which estimates fill relative to one vessel/session
profile.

## Install ML Dependencies

```powershell
python -m pip install -r requirements-ml.txt
```

`requirements.txt` remains the lightweight API runtime dependency set. `requirements-dev.txt`
includes `requirements-ml.txt` so CI can exercise baseline tests.

## Prepare Data

Create a manifest that follows `docs/schemas/phase4_dataset_manifest.schema.json`. Each record must
point to one of:

- `features_path`: canonical Phase 4 feature JSON.
- `analysis_path`: saved API analysis response JSON.
- `audio_path`: raw PCM WAV plus a `probe` object.

`label_schema.buckets_percent` is used by training and scoring. Keep it fixed for a benchmark run;
changing it changes class labels, confusion matrices, within-one-bucket metrics, and references.

Feature files can be produced with:

```powershell
python scripts/extract_phase4_features.py --manifest path/to/private_manifest.json --output-dir path/to/private_features --manifest-output path/to/private_manifest.features.json
```

For private datasets, keep raw audio and extracted feature files outside git unless explicitly
approved.

Use the derived manifest from `--manifest-output` for training when the source manifest contains raw
`audio_path` records. The trainer can consume `features_path` and `analysis_path` records directly.

The checked-in `data/manifests/phase4_manifest.example.json` is schema documentation only. It points
at placeholder private paths and is intentionally too small to train.

## Feature Representation

The baseline uses a conservative tabular feature schema:

- Log-scaled resonance, spectral centroid, bandwidth, rolloff, Q, RT60, and decay-rate features.
- Transfer-response band means and peaks from the Phase 2 DSP pipeline.
- Fixed 20-band mel-spectrogram summaries with mean, standard deviation, and temporal delta.

Raw STFT-bin features are excluded from the model input because their dimensionality depends on FFT
windowing and sample rate. `decay.fit_r2` is retained in feature-file summaries as a diagnostic, not
as a model feature.

The `decay_rate_log2_per_second` feature intentionally logs the exponential decay-rate parameter.
That makes multiplicative damping differences closer to linear for small tabular models.

dB-valued features are clipped to a finite guardrail range before training so a near-zero transfer
denominator or extreme spectrogram value cannot dominate a small baseline run.

Missing feature values are median-imputed with missingness indicators. A missing third peak, for
example, remains visible to the model instead of becoming only an average value.

## Train

```powershell
python scripts/train_baseline.py --manifest path/to/private_manifest.json --group-by session_id --output-dir models/baseline_sklearn
```

Use alternate split axes for benchmark reports:

```powershell
python scripts/train_baseline.py --manifest path/to/private_manifest.json --group-by glass_id --output-dir models/baseline_sklearn_glass_holdout
python scripts/train_baseline.py --manifest path/to/private_manifest.json --group-by device_id --output-dir models/baseline_sklearn_device_holdout
python scripts/train_baseline.py --manifest path/to/private_manifest.json --group-by browser_id --output-dir models/baseline_sklearn_browser_holdout
```

The trainer evaluates repeated grouped holdouts by default and exports the first split's fitted
model. Use `--repeated-holdouts 1` only for quick smoke tests. One 20% holdout can be noisy with
tens of recordings.

## Outputs

The trainer writes:

- `baseline_sklearn.joblib`: regressor, classifier, and metadata.
- `metrics.json`: primary split summary, repeated-holdout aggregate metrics, references, classification metrics, and feature importance.
- `feature_schema.json`: feature order and dataset hash.
- `model-card.md`: artifact-specific model card.

If a train split contains fewer than two fill buckets, classification is disabled and the CLI summary
prints `classification_enabled: false`.

Rows missing alignment confidence or SNR are skipped by default. Use `--allow-missing-quality` only
for exploratory runs that will not be used as release evidence.

Raw `audio_path` records must include exact `probe` metadata. The extractor does not guess chirp
settings for raw WAV files.

## Benchmark Report

Use the compiled benchmark command for release-facing evidence:

```powershell
python scripts/run_phase4_benchmark.py --manifest path/to/private_manifest.json --output-dir experiments/results/phase4_benchmark
```

It runs the standard `session_id`, `glass_id`, `device_id`, and `browser_id` regimes, writes per-axis
artifacts, and emits `benchmark_report.json` plus `benchmark_report.md`. Session holdout is
same-glass supervised repeatability; glass/device/browser holdouts are separate generalization
claims.

For private GCP storage and private Cloud Build execution, see `docs/phase4_private_gcp_workflow.md`.

## Release Gates

A Phase 4 baseline is not releasable unless:

- Holdout groups have no leakage.
- The model beats global mean, global median, nearest canonical bucket, and train-mode bucket references.
- Session-held-out same-glass absolute-label MAE is below `15%` to `20%`.
- Within-one-bucket rate is at least `90%` on the target holdout axis.
- Cross-glass and cross-device metrics are reported separately.
- Limitations mention direct-path bleed, room response, browser processing, and dataset scope.

The nearest-canonical-bucket reference predicts the bucket center nearest the train-set mean. Treat
it as an optimistic coarse baseline, not as a calibrated model.
