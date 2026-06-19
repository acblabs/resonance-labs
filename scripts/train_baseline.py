from __future__ import annotations

import argparse
import json
from pathlib import Path

from resonancelab.ml import (
    DEFAULT_REPEATED_HOLDOUTS,
    QualityThresholds,
    train_phase4_baseline,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a Phase 4 scikit-learn baseline model.")
    parser.add_argument("--manifest", required=True, help="Path to a Phase 4 dataset manifest.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "models" / "baseline_sklearn"),
        help="Directory for joblib model, metrics, feature schema, and model card.",
    )
    parser.add_argument(
        "--model-family",
        choices=("linear", "forest"),
        default="linear",
        help="scikit-learn baseline family to train.",
    )
    parser.add_argument(
        "--group-by",
        nargs="+",
        default=["session_id"],
        help="Context fields held out together to prevent leakage.",
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=17)
    parser.add_argument(
        "--repeated-holdouts",
        type=int,
        default=DEFAULT_REPEATED_HOLDOUTS,
        help="Number of seeded grouped holdouts to evaluate; the first split is exported.",
    )
    parser.add_argument("--min-alignment-confidence", type=float, default=0.20)
    parser.add_argument("--min-snr-db", type=float, default=12.0)
    parser.add_argument(
        "--allow-missing-quality",
        action="store_true",
        help="Retain rows missing alignment/SNR metadata; unsafe for release metrics.",
    )
    args = parser.parse_args()

    result = train_phase4_baseline(
        args.manifest,
        output_dir=args.output_dir,
        model_family=args.model_family,
        group_fields=args.group_by,
        holdout_fraction=args.holdout_fraction,
        random_state=args.random_state,
        repeated_holdouts=args.repeated_holdouts,
        quality_thresholds=QualityThresholds(
            min_alignment_confidence=args.min_alignment_confidence,
            min_signal_to_noise_db=args.min_snr_db,
            allow_missing_quality=args.allow_missing_quality,
        ),
    )

    regression = result.metrics["regression"]
    repeated_regression = result.metrics["repeated_holdout"]["regression"]
    repeated_mae = repeated_regression["mae_percent"] if repeated_regression else None
    summary = {
        "dataset_id": result.manifest.dataset_id,
        "model_family": result.model_family,
        "trained_record_count": result.trained_record_count,
        "skipped_record_count": len(result.skipped_records),
        "feature_count": len(result.feature_names),
        "dropped_feature_count": len(result.metrics["feature_selection"]["dropped_features"]),
        "classification_enabled": result.metrics["classification"] is not None,
        "quality_audit": result.metrics["quality_audit"],
        "warnings": result.metrics["warnings"],
        "split": result.metrics["split"],
        "repeated_holdout": {
            "n_splits": result.metrics["repeated_holdout"]["n_splits"],
            "random_states": result.metrics["repeated_holdout"]["random_states"],
            "mae_percent": repeated_mae,
        },
        "mae_percent": regression["mae_percent"],
        "within_one_bucket_rate": regression["within_one_bucket_rate"],
        "output_dir": str(result.output_dir) if result.output_dir else None,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
