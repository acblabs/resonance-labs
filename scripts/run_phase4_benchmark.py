from __future__ import annotations

import argparse
import json
from pathlib import Path

from resonancelab.ml import DEFAULT_REPEATED_HOLDOUTS, QualityThresholds
from resonancelab.ml.benchmark import run_phase4_benchmark

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run compiled Phase 4 benchmarks across standard group-holdout regimes."
    )
    parser.add_argument("--manifest", required=True, help="Path to a Phase 4 dataset manifest.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "experiments" / "results" / "phase4_benchmark"),
        help="Directory for per-axis artifacts and compiled benchmark_report files.",
    )
    parser.add_argument("--model-family", choices=("linear", "forest"), default="linear")
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=17)
    parser.add_argument("--repeated-holdouts", type=int, default=DEFAULT_REPEATED_HOLDOUTS)
    parser.add_argument("--min-alignment-confidence", type=float, default=0.20)
    parser.add_argument("--min-snr-db", type=float, default=12.0)
    parser.add_argument(
        "--allow-missing-quality",
        action="store_true",
        help="Retain rows missing alignment/SNR metadata; unsafe for release metrics.",
    )
    args = parser.parse_args()

    report = run_phase4_benchmark(
        args.manifest,
        output_dir=args.output_dir,
        model_family=args.model_family,
        holdout_fraction=args.holdout_fraction,
        random_state=args.random_state,
        repeated_holdouts=args.repeated_holdouts,
        quality_thresholds=QualityThresholds(
            min_alignment_confidence=args.min_alignment_confidence,
            min_signal_to_noise_db=args.min_snr_db,
            allow_missing_quality=args.allow_missing_quality,
        ),
    )
    summary = {
        "dataset_id": report["dataset_id"],
        "dataset_hash": report["dataset_hash"],
        "axis_count": len(report["axes"]),
        "output_dir": str(Path(args.output_dir).resolve()),
        "axes": [
            {
                "name": axis["name"],
                "regime": axis["regime"],
                "mae_percent": axis["model_mae_percent"],
                "reference_deltas_mae_percent": axis["reference_deltas_mae_percent"],
            }
            for axis in report["axes"]
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
