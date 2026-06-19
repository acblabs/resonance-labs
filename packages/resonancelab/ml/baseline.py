"""Scikit-learn Phase 4 baseline training and evaluation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .dataset import (
    DatasetManifest,
    DatasetRecord,
    bucket_name,
    bucket_names,
    load_manifest,
    load_record_feature_vector,
    nearest_fill_bucket,
)
from .features import FEATURE_SCHEMA_VERSION, FeatureVector, feature_matrix
from .splits import SplitPlan, make_repeated_group_holdout_splits

ModelFamily = Literal["linear", "forest"]
MIN_FEATURE_VARIANCE = 1e-12
DEFAULT_REPEATED_HOLDOUTS = 5


@dataclass(frozen=True)
class QualityThresholds:
    """Minimum data-quality gates applied before baseline fitting."""

    min_alignment_confidence: float = 0.20
    min_signal_to_noise_db: float = 12.0
    allow_missing_quality: bool = False


@dataclass(frozen=True)
class TrainingRow:
    """One manifest record paired with canonical model features."""

    record: DatasetRecord
    feature_vector: FeatureVector

    @property
    def features(self) -> Mapping[str, float]:
        return self.feature_vector.as_mapping()


@dataclass(frozen=True)
class PreprocessedFeatures:
    """Train/test matrices after dropping unusable train-set columns."""

    x_train: np.ndarray
    x_test: np.ndarray
    feature_names: tuple[str, ...]
    model_feature_names: tuple[str, ...]
    dropped_features: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class BaselineTrainingResult:
    """Summary returned after training and optional artifact export."""

    manifest: DatasetManifest
    model_family: ModelFamily
    feature_names: tuple[str, ...]
    split_plan: SplitPlan
    split_plans: tuple[SplitPlan, ...]
    metrics: Mapping[str, Any]
    output_dir: Path | None
    trained_record_count: int
    skipped_records: tuple[str, ...]


@dataclass(frozen=True)
class SplitEvaluation:
    """Model and metrics for one group holdout split."""

    split_plan: SplitPlan
    feature_names: tuple[str, ...]
    model_feature_names: tuple[str, ...]
    input_feature_count: int
    dropped_features: tuple[Mapping[str, str], ...]
    regression: Mapping[str, float]
    classification: Mapping[str, Any] | None
    references: Mapping[str, Any]
    warnings: tuple[str, ...]
    regressor: Any
    classifier: Any


def train_phase4_baseline(
    manifest: str | Path | DatasetManifest,
    *,
    output_dir: str | Path | None = None,
    model_family: ModelFamily = "linear",
    group_fields: Sequence[str] = ("session_id",),
    holdout_fraction: float = 0.2,
    random_state: int = 17,
    repeated_holdouts: int = DEFAULT_REPEATED_HOLDOUTS,
    quality_thresholds: QualityThresholds | None = None,
) -> BaselineTrainingResult:
    """Train and evaluate a Phase 4 scikit-learn baseline from a dataset manifest."""

    resolved_manifest = (
        load_manifest(manifest) if not isinstance(manifest, DatasetManifest) else manifest
    )
    thresholds = quality_thresholds or QualityThresholds()
    rows, skipped, quality_audit = _load_training_rows(resolved_manifest, thresholds)
    if len(rows) < 4:
        raise ValueError("At least four usable feature rows are required for baseline training.")

    split_plans = make_repeated_group_holdout_splits(
        [row.record for row in rows],
        group_fields=group_fields,
        buckets_percent=resolved_manifest.label_buckets_percent,
        holdout_fraction=holdout_fraction,
        random_state=random_state,
        n_splits=repeated_holdouts,
    )
    evaluations = tuple(
        _evaluate_split(
            rows=rows,
            split_plan=split_plan,
            buckets_percent=resolved_manifest.label_buckets_percent,
            model_family=model_family,
            random_state=split_plan.random_state,
        )
        for split_plan in split_plans
    )
    primary = evaluations[0]
    warnings = sorted({warning for evaluation in evaluations for warning in evaluation.warnings})

    metrics = {
        "created_at": _utc_now(),
        "dataset_id": resolved_manifest.dataset_id,
        "dataset_hash": resolved_manifest.manifest_hash(),
        "model_family": model_family,
        "label_buckets_percent": list(resolved_manifest.label_buckets_percent),
        "trained_record_count": len(rows),
        "skipped_records": list(skipped),
        "quality_thresholds": asdict(thresholds),
        "quality_audit": quality_audit,
        "warnings": warnings,
        "split": _split_plan_json(primary.split_plan),
        "repeated_holdout": _repeated_holdout_summary(evaluations),
        "feature_selection": {
            "input_feature_count": primary.input_feature_count,
            "selected_feature_count": len(primary.feature_names),
            "model_feature_names": list(primary.model_feature_names),
            "dropped_features": list(primary.dropped_features),
        },
        "regression": primary.regression,
        "classification": primary.classification,
        "references": primary.references,
        "feature_importance": _feature_importance(
            regressor=primary.regressor,
            classifier=primary.classifier,
            feature_names=primary.model_feature_names,
        ),
    }

    destination = Path(output_dir).resolve() if output_dir is not None else None
    if destination is not None:
        _write_artifacts(
            output_dir=destination,
            manifest=resolved_manifest,
            model_family=model_family,
            feature_names=primary.feature_names,
            model_feature_names=primary.model_feature_names,
            metrics=metrics,
            regressor=primary.regressor,
            classifier=primary.classifier,
        )

    return BaselineTrainingResult(
        manifest=resolved_manifest,
        model_family=model_family,
        feature_names=primary.feature_names,
        split_plan=primary.split_plan,
        split_plans=split_plans,
        metrics=metrics,
        output_dir=destination,
        trained_record_count=len(rows),
        skipped_records=tuple(skipped),
    )


def _evaluate_split(
    *,
    rows: Sequence[TrainingRow],
    split_plan: SplitPlan,
    buckets_percent: Sequence[float],
    model_family: ModelFamily,
    random_state: int,
) -> SplitEvaluation:
    train_rows = [row for row in rows if split_plan.split_for(row.record.record_id) == "train"]
    test_rows = [row for row in rows if split_plan.split_for(row.record.record_id) == "test"]
    if not train_rows or not test_rows:
        raise ValueError("Train and test splits must both contain at least one usable row.")

    feature_names = tuple(sorted({name for row in train_rows for name in row.features}))
    if not feature_names:
        raise ValueError("No train-set features were available for baseline training.")

    x_train_raw, _ = feature_matrix(
        [row.features for row in train_rows],
        feature_names=feature_names,
    )
    x_test_raw, _ = feature_matrix([row.features for row in test_rows], feature_names=feature_names)
    preprocessed = _select_trainable_columns(x_train_raw, x_test_raw, feature_names)
    y_train_reg = np.asarray(
        [row.record.label.fill_percent for row in train_rows],
        dtype=np.float64,
    )
    y_test_reg = np.asarray([row.record.label.fill_percent for row in test_rows], dtype=np.float64)
    y_train_cls = np.asarray(
        [bucket_name(nearest_fill_bucket(value, buckets_percent)) for value in y_train_reg]
    )
    y_test_cls = np.asarray(
        [bucket_name(nearest_fill_bucket(value, buckets_percent)) for value in y_test_reg]
    )
    warnings: list[str] = []
    if len(preprocessed.model_feature_names) > y_train_reg.size:
        warnings.append(
            "Model feature count exceeds train row count; treat this split as high overfit risk."
        )

    sklearn_objects = _fit_models(
        x_train=preprocessed.x_train,
        y_train_reg=y_train_reg,
        y_train_cls=y_train_cls,
        model_family=model_family,
        random_state=random_state,
    )
    regressor = sklearn_objects["regressor"]
    classifier = sklearn_objects["classifier"]
    y_pred_reg = np.clip(
        np.asarray(regressor.predict(preprocessed.x_test), dtype=np.float64),
        0.0,
        100.0,
    )

    classification: Mapping[str, Any] | None = None
    if classifier is not None:
        y_pred_cls = np.asarray(classifier.predict(preprocessed.x_test))
        classification = _classification_metrics(y_test_cls, y_pred_cls, buckets_percent)
        regressor_buckets = np.asarray(
            [bucket_name(nearest_fill_bucket(value, buckets_percent)) for value in y_pred_reg]
        )
        classification["regressor_bucket_agreement_rate"] = float(
            np.mean(regressor_buckets == y_pred_cls)
        )
    else:
        warnings.append(
            "Classifier was not trained because the train split has fewer than 2 classes."
        )

    return SplitEvaluation(
        split_plan=split_plan,
        feature_names=preprocessed.feature_names,
        model_feature_names=preprocessed.model_feature_names,
        input_feature_count=len(feature_names),
        dropped_features=preprocessed.dropped_features,
        regression=_regression_metrics(y_test_reg, y_pred_reg, buckets_percent),
        classification=classification,
        references=_reference_metrics(
            y_train_reg,
            y_train_cls,
            y_test_reg,
            y_test_cls,
            buckets_percent,
        ),
        warnings=tuple(warnings),
        regressor=regressor,
        classifier=classifier,
    )


def _select_trainable_columns(
    x_train: np.ndarray,
    x_test: np.ndarray,
    feature_names: Sequence[str],
) -> PreprocessedFeatures:
    keep_indices: list[int] = []
    dropped: list[Mapping[str, str]] = []
    for index, name in enumerate(feature_names):
        column = x_train[:, index]
        finite = column[np.isfinite(column)]
        if finite.size == 0:
            dropped.append({"name": name, "reason": "all_missing_in_train"})
            continue
        if float(np.var(finite)) <= MIN_FEATURE_VARIANCE:
            dropped.append({"name": name, "reason": "constant_in_train"})
            continue
        keep_indices.append(index)

    if not keep_indices:
        raise ValueError("No trainable features remain after dropping missing/constant columns.")

    selected_names = tuple(feature_names[index] for index in keep_indices)
    selected_train = x_train[:, keep_indices]
    return PreprocessedFeatures(
        x_train=selected_train,
        x_test=x_test[:, keep_indices],
        feature_names=selected_names,
        model_feature_names=_model_feature_names(selected_names, selected_train),
        dropped_features=tuple(dropped),
    )


def _model_feature_names(
    feature_names: Sequence[str],
    x_train: np.ndarray,
) -> tuple[str, ...]:
    indicator_names = [
        f"{name}__missing"
        for name, has_missing in zip(feature_names, np.any(np.isnan(x_train), axis=0), strict=True)
        if bool(has_missing)
    ]
    return tuple(feature_names) + tuple(indicator_names)


def _load_training_rows(
    manifest: DatasetManifest,
    quality_thresholds: QualityThresholds,
) -> tuple[list[TrainingRow], list[str], Mapping[str, int]]:
    rows: list[TrainingRow] = []
    skipped: list[str] = []
    quality_audit = {
        "active_record_count": 0,
        "missing_alignment_confidence_count": 0,
        "missing_signal_to_noise_db_count": 0,
        "low_alignment_confidence_count": 0,
        "low_signal_to_noise_db_count": 0,
        "retained_missing_quality_count": 0,
        "retained_record_count": 0,
        "skipped_quality_record_count": 0,
    }
    for record in manifest.active_records():
        quality_audit["active_record_count"] += 1
        feature_vector = load_record_feature_vector(manifest, record)
        if not feature_vector.features:
            skipped.append(f"{record.record_id}: no finite features")
            continue
        quality = _combined_quality(record, feature_vector)
        _update_quality_audit(quality_audit, quality, quality_thresholds)
        allowed, reason = _passes_quality(quality, quality_thresholds)
        if not allowed:
            skipped.append(f"{record.record_id}: {reason}")
            quality_audit["skipped_quality_record_count"] += 1
            continue
        if _quality_is_missing(quality):
            quality_audit["retained_missing_quality_count"] += 1
        rows.append(TrainingRow(record=record, feature_vector=feature_vector))
        quality_audit["retained_record_count"] += 1
    return rows, skipped, quality_audit


def _combined_quality(
    record: DatasetRecord,
    feature_vector: FeatureVector,
) -> dict[str, Any]:
    return {**dict(feature_vector.quality or {}), **dict(record.quality or {})}


def _passes_quality(
    quality: Mapping[str, Any],
    thresholds: QualityThresholds,
) -> tuple[bool, str | None]:
    alignment = _finite_float(quality.get("alignment_confidence"))
    snr = _finite_float(quality.get("signal_to_noise_db"))
    if alignment is None and not thresholds.allow_missing_quality:
        return False, "missing alignment_confidence"
    if alignment is not None and alignment < thresholds.min_alignment_confidence:
        return False, f"alignment_confidence {alignment:.3f} below threshold"
    if snr is None and not thresholds.allow_missing_quality:
        return False, "missing signal_to_noise_db"
    if snr is not None and snr < thresholds.min_signal_to_noise_db:
        return False, f"signal_to_noise_db {snr:.2f} below threshold"
    return True, None


def _update_quality_audit(
    audit: dict[str, int],
    quality: Mapping[str, Any],
    thresholds: QualityThresholds,
) -> None:
    alignment = _finite_float(quality.get("alignment_confidence"))
    snr = _finite_float(quality.get("signal_to_noise_db"))
    if alignment is None:
        audit["missing_alignment_confidence_count"] += 1
    elif alignment < thresholds.min_alignment_confidence:
        audit["low_alignment_confidence_count"] += 1
    if snr is None:
        audit["missing_signal_to_noise_db_count"] += 1
    elif snr < thresholds.min_signal_to_noise_db:
        audit["low_signal_to_noise_db_count"] += 1


def _quality_is_missing(quality: Mapping[str, Any]) -> bool:
    return (
        _finite_float(quality.get("alignment_confidence")) is None
        or _finite_float(quality.get("signal_to_noise_db")) is None
    )


def _fit_models(
    *,
    x_train: np.ndarray,
    y_train_reg: np.ndarray,
    y_train_cls: np.ndarray,
    model_family: ModelFamily,
    random_state: int,
) -> dict[str, Any]:
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import ElasticNet, LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local environment.
        raise RuntimeError(
            "Phase 4 baseline training requires scikit-learn. "
            "Install it with: python -m pip install -r requirements-ml.txt"
        ) from exc

    if model_family == "linear":
        regressor = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                ("scaler", StandardScaler()),
                (
                    "estimator",
                    ElasticNet(
                        alpha=0.02,
                        l1_ratio=0.35,
                        max_iter=10000,
                        random_state=random_state,
                    ),
                ),
            ]
        )
        classifier = None
        if len(set(y_train_cls)) >= 2:
            classifier = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                    ("scaler", StandardScaler()),
                    (
                        "estimator",
                        LogisticRegression(
                            C=0.75,
                            class_weight="balanced",
                            l1_ratio=0.35,
                            max_iter=2000,
                            random_state=random_state,
                            solver="saga",
                        ),
                    ),
                ]
            )
    elif model_family == "forest":
        regressor = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                (
                    "estimator",
                    RandomForestRegressor(
                        n_estimators=300,
                        max_depth=8,
                        min_samples_leaf=2,
                        random_state=random_state,
                    ),
                ),
            ]
        )
        classifier = None
        if len(set(y_train_cls)) >= 2:
            classifier = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                    (
                        "estimator",
                        RandomForestClassifier(
                            n_estimators=300,
                            max_depth=8,
                            min_samples_leaf=2,
                            class_weight="balanced",
                            random_state=random_state,
                        ),
                    ),
                ]
            )
    else:
        raise ValueError(f"Unsupported model_family: {model_family}")

    regressor.fit(x_train, y_train_reg)
    if classifier is not None:
        classifier.fit(x_train, y_train_cls)
    return {"regressor": regressor, "classifier": classifier}


def _regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    buckets_percent: Sequence[float],
) -> dict[str, float]:
    errors = y_pred - y_true
    abs_errors = np.abs(errors)
    return {
        "mae_percent": float(np.mean(abs_errors)),
        "median_absolute_error_percent": float(np.median(abs_errors)),
        "rmse_percent": float(np.sqrt(np.mean(np.square(errors)))),
        "max_absolute_error_percent": float(np.max(abs_errors)),
        "within_15_percent_rate": float(np.mean(abs_errors <= 15.0)),
        "within_20_percent_rate": float(np.mean(abs_errors <= 20.0)),
        "within_one_bucket_rate": _within_one_bucket_rate(y_true, y_pred, buckets_percent),
    }


def _classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    buckets_percent: Sequence[float],
) -> dict[str, Any]:
    default_labels = list(bucket_names(buckets_percent))
    labels = sorted(
        set(default_labels) | {str(label) for label in y_true} | {str(label) for label in y_pred},
        key=lambda label: (_bucket_index(label, buckets_percent), label),
    )
    confusion = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for actual, predicted in zip(y_true, y_pred, strict=True):
        actual_label = str(actual)
        predicted_label = str(predicted)
        confusion.setdefault(actual_label, {label: 0 for label in labels})
        if predicted_label not in confusion[actual_label]:
            confusion[actual_label][predicted_label] = 0
        confusion[actual_label][predicted_label] += 1
    return {
        "accuracy": float(np.mean(y_true == y_pred)),
        "within_one_bucket_rate": float(
            np.mean(
                [
                    abs(
                        _bucket_index(actual, buckets_percent)
                        - _bucket_index(predicted, buckets_percent)
                    )
                    <= 1
                    for actual, predicted in zip(y_true, y_pred, strict=True)
                ]
            )
        ),
        "confusion_matrix": confusion,
    }


def _repeated_holdout_summary(evaluations: Sequence[SplitEvaluation]) -> dict[str, Any]:
    return {
        "n_splits": len(evaluations),
        "random_states": [evaluation.split_plan.random_state for evaluation in evaluations],
        "regression": _numeric_metric_summary(
            [evaluation.regression for evaluation in evaluations]
        ),
        "classification": _numeric_metric_summary(
            [
                evaluation.classification
                for evaluation in evaluations
                if evaluation.classification is not None
            ]
        ),
        "references": {
            name: _numeric_metric_summary(
                [
                    evaluation.references[name]
                    for evaluation in evaluations
                    if name in evaluation.references
                ]
            )
            for name in sorted(
                {name for evaluation in evaluations for name in evaluation.references}
            )
        },
        "splits": [_split_plan_json(evaluation.split_plan) for evaluation in evaluations],
    }


def _numeric_metric_summary(metrics: Sequence[Mapping[str, Any] | None]) -> dict[str, Any] | None:
    rows = [metric for metric in metrics if metric is not None]
    if not rows:
        return None
    keys = sorted(
        {
            key
            for metric in rows
            for key, value in metric.items()
            if _finite_float(value) is not None
        }
    )
    return {
        key: _mean_std(
            [
                float(metric[key])
                for metric in rows
                if _finite_float(metric.get(key)) is not None
            ]
        )
        for key in keys
    }


def _mean_std(values: Sequence[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "n": int(array.size),
    }


def _reference_metrics(
    y_train_reg: np.ndarray,
    y_train_cls: np.ndarray,
    y_test_reg: np.ndarray,
    y_test_cls: np.ndarray,
    buckets_percent: Sequence[float],
) -> dict[str, Any]:
    mean_prediction = np.full_like(y_test_reg, float(np.mean(y_train_reg)), dtype=np.float64)
    median_prediction = np.full_like(y_test_reg, float(np.median(y_train_reg)), dtype=np.float64)
    canonical_prediction = np.full_like(
        y_test_reg,
        nearest_fill_bucket(float(np.mean(y_train_reg)), buckets_percent),
        dtype=np.float64,
    )
    mode_bucket = _mode_label(y_train_cls, buckets_percent)
    mode_predictions = np.asarray([mode_bucket for _ in y_test_cls])
    return {
        "global_train_mean": _regression_metrics(y_test_reg, mean_prediction, buckets_percent),
        "global_train_median": _regression_metrics(y_test_reg, median_prediction, buckets_percent),
        "nearest_canonical_bucket_to_train_mean": _regression_metrics(
            y_test_reg,
            canonical_prediction,
            buckets_percent,
        ),
        "train_mode_bucket_classifier": _classification_metrics(
            y_test_cls,
            mode_predictions,
            buckets_percent,
        ),
    }


def _within_one_bucket_rate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    buckets_percent: Sequence[float],
) -> float:
    true_indices = [
        _bucket_index(bucket_name(nearest_fill_bucket(value, buckets_percent)), buckets_percent)
        for value in y_true
    ]
    pred_indices = [
        _bucket_index(bucket_name(nearest_fill_bucket(value, buckets_percent)), buckets_percent)
        for value in y_pred
    ]
    return float(
        np.mean(
            [
                abs(actual - predicted) <= 1
                for actual, predicted in zip(true_indices, pred_indices, strict=True)
            ]
        )
    )


def _feature_importance(
    *,
    regressor: Any,
    classifier: Any,
    feature_names: Sequence[str],
    max_features: int = 25,
) -> dict[str, list[dict[str, float | str]]]:
    return {
        "regressor": _estimator_importance(regressor, feature_names, max_features=max_features),
        "classifier": _estimator_importance(classifier, feature_names, max_features=max_features)
        if classifier is not None
        else [],
    }


def _estimator_importance(
    model: Any,
    feature_names: Sequence[str],
    *,
    max_features: int,
) -> list[dict[str, float | str]]:
    estimator = model
    if hasattr(model, "named_steps"):
        estimator = model.named_steps.get("estimator", model)
    values = None
    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=np.float64)
    elif hasattr(estimator, "coef_"):
        values = np.abs(np.asarray(estimator.coef_, dtype=np.float64))
        if values.ndim > 1:
            values = np.mean(values, axis=0)
    if values is None or values.size != len(feature_names):
        return []
    total = float(np.sum(values))
    if not math.isfinite(total) or total <= 0:
        return []
    normalized = values / total
    indices = np.argsort(normalized)[::-1][:max_features]
    return [
        {"name": feature_names[index], "importance": float(normalized[index])}
        for index in indices
        if normalized[index] > 0
    ]


def _write_artifacts(
    *,
    output_dir: Path,
    manifest: DatasetManifest,
    model_family: ModelFamily,
    feature_names: Sequence[str],
    model_feature_names: Sequence[str],
    metrics: Mapping[str, Any],
    regressor: Any,
    classifier: Any,
) -> None:
    try:
        import joblib
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local environment.
        raise RuntimeError(
            "Phase 4 artifact export requires joblib. "
            "Install it with: python -m pip install -r requirements-ml.txt"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "format": "resonancelab.phase4.baseline_artifact",
        "format_version": 1,
        "created_at": metrics["created_at"],
        "dataset_id": manifest.dataset_id,
        "dataset_hash": manifest.manifest_hash(),
        "model_family": model_family,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(feature_names),
        "model_feature_names": list(model_feature_names),
    }
    joblib.dump(
        {"metadata": metadata, "regressor": regressor, "classifier": classifier},
        output_dir / "baseline_sklearn.joblib",
    )
    _write_json(output_dir / "metrics.json", metrics)
    _write_json(output_dir / "feature_schema.json", metadata)
    (output_dir / "model-card.md").write_text(
        _model_card_markdown(metadata=metadata, metrics=metrics),
        encoding="utf-8",
    )


def _model_card_markdown(
    *,
    metadata: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> str:
    regression = metrics["regression"]
    repeated = metrics["repeated_holdout"]["regression"]
    repeated_mae = repeated["mae_percent"]
    reference_lines = _reference_markdown(metrics)
    split = metrics["split"]
    feature_selection = metrics["feature_selection"]
    warnings = metrics.get("warnings") or []
    return f"""# ResonanceLab Phase 4 scikit-learn Baseline

Status: experimental private baseline.

Dataset: `{metadata["dataset_id"]}`
Dataset hash: `{metadata["dataset_hash"]}`
Model family: `{metadata["model_family"]}`
Created: `{metadata["created_at"]}`

## Intended Use

Estimate fill level from ResonanceLab chirp-derived DSP features for controlled experiments.
This model is not a general object sensor and must be evaluated by session, glass, device, and
browser before any public claim.

## Evaluation Split

- Group fields: `{", ".join(split["group_fields"])}`
- Train records: `{split["train_count"]}`
- Test records: `{split["test_count"]}`
- Train groups: `{split["train_groups"]}`
- Test groups: `{split["test_groups"]}`
- Selected features: `{feature_selection["selected_feature_count"]}`
- Dropped features: `{len(feature_selection["dropped_features"])}`

## Metrics

- MAE: `{regression["mae_percent"]:.2f}%`
- RMSE: `{regression["rmse_percent"]:.2f}%`
- Within 15%: `{regression["within_15_percent_rate"]:.3f}`
- Within 20%: `{regression["within_20_percent_rate"]:.3f}`
- Within one bucket: `{regression["within_one_bucket_rate"]:.3f}`
- Repeated-holdout MAE mean/std: `{repeated_mae["mean"]:.2f}% / {repeated_mae["std"]:.2f}%`
- Repeated holdouts: `{metrics["repeated_holdout"]["n_splits"]}`

## Reference Comparison

{reference_lines}

## Limitations

- Direct speaker-to-microphone bleed and room response can dominate chirp captures.
- Metrics are invalid if group leakage exists or if low-quality captures are retained silently.
- Cross-glass, cross-device, and cross-browser results must be reported separately.
- This artifact should not be loaded by the production API until Phase 5 serving gates are met.

## Warnings

{_markdown_warning_list(warnings)}
"""


def _markdown_warning_list(warnings: Sequence[str]) -> str:
    if not warnings:
        return "- None."
    return "\n".join(f"- {warning}" for warning in warnings)


def _reference_markdown(metrics: Mapping[str, Any]) -> str:
    model_mae = metrics["repeated_holdout"]["regression"]["mae_percent"]["mean"]
    references = metrics["repeated_holdout"]["references"]
    lines: list[str] = []
    for name, values in references.items():
        mae = values.get("mae_percent") if isinstance(values, Mapping) else None
        if not isinstance(mae, Mapping) or "mean" not in mae:
            continue
        delta = float(mae["mean"]) - float(model_mae)
        verdict = "beats" if delta > 0 else "does not beat"
        lines.append(
            f"- `{name}`: reference MAE `{mae['mean']:.2f}%`; "
            f"model {verdict} by `{abs(delta):.2f}%`."
        )
    return "\n".join(lines) if lines else "- No numeric reference metrics available."


def _split_plan_json(split_plan: SplitPlan) -> dict[str, Any]:
    return {
        "group_fields": list(split_plan.group_fields),
        "holdout_fraction": split_plan.holdout_fraction,
        "random_state": split_plan.random_state,
        "train_count": split_plan.train_count,
        "test_count": split_plan.test_count,
        "train_groups": split_plan.train_groups,
        "test_groups": split_plan.test_groups,
        "label_distribution": {
            split: dict(counts)
            for split, counts in split_plan.label_distribution.items()
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mode_label(labels: np.ndarray, buckets_percent: Sequence[float]) -> str:
    ordered_labels = list(bucket_names(buckets_percent))
    counts = {label: int(np.sum(labels == label)) for label in ordered_labels}
    return max(
        ordered_labels,
        key=lambda label: (counts.get(label, 0), -ordered_labels.index(label)),
    )


def _bucket_index(label: str, buckets_percent: Sequence[float]) -> int:
    labels = list(bucket_names(buckets_percent))
    try:
        return labels.index(label)
    except ValueError:
        return len(labels)


def _finite_float(value: Any) -> float | None:
    try:
        finite = float(value)
    except (TypeError, ValueError):
        return None
    return finite if math.isfinite(finite) else None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
