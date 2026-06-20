from __future__ import annotations

import argparse
import json

from resonancelab.ml.manifest_builder import finalize_phase4_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize a Phase 4 capture inbox into an immutable dataset snapshot."
    )
    parser.add_argument(
        "--inbox-dir",
        required=True,
        help="Directory containing *.record.json fragments.",
    )
    parser.add_argument(
        "--snapshot-dir",
        required=True,
        help="Directory where the dataset snapshot is written.",
    )
    parser.add_argument("--dataset-id", required=True, help="Dataset identifier for manifest.json.")
    parser.add_argument("--manifest-name", default="manifest.json")
    parser.add_argument(
        "--buckets-percent",
        default="0,25,50,75,100",
        help="Comma-separated fill bucket percentages.",
    )
    parser.add_argument("--created-at", help="Optional manifest created_at timestamp.")
    parser.add_argument("--description", help="Optional manifest description.")
    parser.add_argument(
        "--owner",
        action="append",
        default=[],
        help="Optional owner label. Repeat for multiple owners.",
    )
    parser.add_argument("--notes", help="Optional manifest notes.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    buckets = tuple(
        float(value.strip()) for value in args.buckets_percent.split(",") if value.strip()
    )
    result = finalize_phase4_dataset(
        inbox_dir=args.inbox_dir,
        snapshot_dir=args.snapshot_dir,
        dataset_id=args.dataset_id,
        manifest_name=args.manifest_name,
        buckets_percent=buckets,
        created_at=args.created_at,
        description=args.description,
        owners=args.owner,
        notes=args.notes,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "manifest_path": str(result.manifest_path),
                "record_count": result.record_count,
                "copied_paths": list(result.copied_paths),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
