"""Compiled Phase 4 benchmark reports across evaluation regimes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .baseline import (
    DEFAULT_REPEATED_HOLDOUTS,
    BaselineTrainingResult,
    ModelFamily,
    QualityThresholds,
    train_phase4_baseline,
)
from .dataset import DatasetManifest, load_manifest


@dataclass(frozen=True)
class BenchmarkAxis:
    """One benchmark regime and its leakage boundary."""

    name: str
    regime: str
    group_fields: tuple[str, ...]
    description: str


DEFAULT_BENCHMARK_AXES = (
    BenchmarkAxis(
        name="session",
        regime="same_glass_supervised_repeatability",
        group_fields=("session_id",),
        description="Hold out recording sessions; the same glass may appear in train and test.",
    ),
    BenchmarkAxis(
        name="glass",
        regime="cross_glass_generalization",
        group_fields=("glass_id",),
        description="Hold out physical vessels.",
    ),
    BenchmarkAxis(
        name="device",
        regime="cross_device_generalization",
        group_fields=("device_id",),
        description="Hold out capture/playback devices.",
    ),
    BenchmarkAxis(
        name="browser",
        regime="cross_browser_generalization",
        group_fields=("browser_id",),
        description="Hold out browser families or major versions.",
    ),
)


def run_phase4_benchmark(
    manifest: str | Path | DatasetManifest,
    *,
    output_dir: str | Path,
    axes: Sequence[BenchmarkAxis] = DEFAULT_BENCHMARK_AXES,
    model_family: ModelFamily = "linear",
    holdout_fraction: float = 0.2,
    random_state: int = 17,
    repeated_holdouts: int = DEFAULT_REPEATED_HOLDOUTS,
    quality_thresholds: QualityThresholds | None = None,
) -> dict[str, Any]:
    """Run the standard Phase 4 benchmark axes and write a compiled report."""

    resolved_manifest = (
        load_manifest(manifest) if not isinstance(manifest, DatasetManifest) else manifest
    )
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for axis in axes:
        axis_dir = destination / axis.name
        result = train_phase4_baseline(
            resolved_manifest,
            output_dir=axis_dir,
            model_family=model_family,
            group_fields=axis.group_fields,
            holdout_fraction=holdout_fraction,
            random_state=random_state,
            repeated_holdouts=repeated_holdouts,
            quality_thresholds=quality_thresholds,
        )
        results.append(_axis_report(axis, result))

    report = {
        "format": "resonancelab.phase4.benchmark_report",
        "format_version": 1,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "dataset_id": resolved_manifest.dataset_id,
        "dataset_hash": resolved_manifest.manifest_hash(),
        "model_family": model_family,
        "holdout_fraction": holdout_fraction,
        "repeated_holdouts": repeated_holdouts,
        "axes": results,
    }
    (destination / "benchmark_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "benchmark_report.md").write_text(
        _benchmark_markdown(report),
        encoding="utf-8",
    )
    return report


def _axis_report(axis: BenchmarkAxis, result: BaselineTrainingResult) -> dict[str, Any]:
    metrics = result.metrics
    model_mae = metrics["repeated_holdout"]["regression"]["mae_percent"]
    references = metrics["repeated_holdout"]["references"]
    return {
        "name": axis.name,
        "regime": axis.regime,
        "description": axis.description,
        "group_fields": list(axis.group_fields),
        "artifact_dir": str(result.output_dir) if result.output_dir else None,
        "primary_split": metrics["split"],
        "repeated_holdout": metrics["repeated_holdout"],
        "quality_audit": metrics["quality_audit"],
        "feature_selection": metrics["feature_selection"],
        "model_mae_percent": model_mae,
        "reference_deltas_mae_percent": _reference_deltas(model_mae, references),
        "warnings": metrics["warnings"],
    }


def _reference_deltas(
    model_mae: Mapping[str, float | int],
    references: Mapping[str, Any],
) -> dict[str, float]:
    model_mean = float(model_mae["mean"])
    deltas: dict[str, float] = {}
    for name, values in references.items():
        mae = values.get("mae_percent") if isinstance(values, Mapping) else None
        if isinstance(mae, Mapping) and "mean" in mae:
            deltas[name] = float(mae["mean"]) - model_mean
    return deltas


def _benchmark_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# ResonanceLab Phase 4 Benchmark Report",
        "",
        f"Dataset: `{report['dataset_id']}`",
        f"Dataset hash: `{report['dataset_hash']}`",
        f"Model family: `{report['model_family']}`",
        f"Repeated holdouts: `{report['repeated_holdouts']}`",
        "",
        "| Axis | Regime | Group Fields | MAE mean | MAE std | Best Reference Delta |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for axis in report["axes"]:
        mae = axis["model_mae_percent"]
        deltas = axis["reference_deltas_mae_percent"]
        best_delta = max(deltas.values()) if deltas else float("nan")
        lines.append(
            "| {name} | {regime} | `{groups}` | {mean:.2f}% | {std:.2f}% | {delta:.2f}% |".format(
                name=axis["name"],
                regime=axis["regime"],
                groups=", ".join(axis["group_fields"]),
                mean=mae["mean"],
                std=mae["std"],
                delta=best_delta,
            )
        )
    lines.extend(
        [
            "",
            (
                "Positive reference deltas mean the model's repeated-holdout MAE is "
                "lower than the reference."
            ),
            (
                "Session holdout is same-glass supervised repeatability, not "
                "cross-glass generalization."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
