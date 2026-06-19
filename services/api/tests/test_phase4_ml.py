from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from resonancelab.ml import (
    DATASET_FORMAT,
    DATASET_FORMAT_VERSION,
    FEATURE_FORMAT,
    FEATURE_FORMAT_VERSION,
    ManifestValidationError,
    extract_feature_vector_from_mapping,
    load_manifest,
    make_group_holdout_split,
    run_phase4_benchmark,
    train_phase4_baseline,
)


class Phase4MlTests(unittest.TestCase):
    def test_extract_feature_vector_from_analysis_payload(self) -> None:
        payload = {
            "record_id": "probe-001",
            "audio": {"duration_seconds": 1.75, "sample_rate_hz": 48000},
            "alignment": {"confidence": 0.93},
            "dsp": {
                "signal_to_noise_db": 31.5,
                "fft": {
                    "centroid_hz": 1700.0,
                    "bandwidth_hz": 450.0,
                    "rolloff_hz": 2300.0,
                    "spectral_floor_db": -82.0,
                },
                "dominant_peaks": [
                    {
                        "frequency_hz": 1425.0,
                        "magnitude_db": -16.5,
                        "prominence_db": 24.0,
                        "q_factor": 21.0,
                    }
                ],
                "transfer_response": [
                    {"center_hz": 750.0, "mean_db": -7.0, "peak_db": -2.0},
                ],
                "decay": {
                    "decay_rate_per_second": 4.25,
                    "rt60_seconds": 1.1,
                    "fit_r2": 0.88,
                },
                "mel_spectrogram": {
                    "magnitude_db": [[-80.0, -70.0, -60.0], [-78.0, -68.0, -58.0]],
                },
                "stft": {
                    "magnitude_db": [[-90.0, -85.0, -81.0], [-75.0, -70.0, -66.0]],
                },
            },
            "warnings": ["synthetic warning"],
        }

        vector = extract_feature_vector_from_mapping(payload)
        features = vector.as_mapping()

        self.assertEqual(vector.record_id, "probe-001")
        self.assertAlmostEqual(features["peak_1_log_hz"], math.log2(1425.0))
        self.assertAlmostEqual(features["spectral_centroid_log_hz"], math.log2(1700.0))
        self.assertEqual(features["transfer_750hz_mean_db"], -7.0)
        self.assertIn("mel_band_01_mean_db", features)
        self.assertIn("mel_band_20_mean_db", features)
        self.assertNotIn("decay_fit_r2", features)
        self.assertFalse(any(name.startswith("stft_") for name in features))
        self.assertEqual(vector.quality["warning_count"], 1)

    def test_mel_feature_shape_is_fixed_when_input_band_count_changes(self) -> None:
        small = extract_feature_vector_from_mapping(_analysis_payload_with_mel_rows(12))
        large = extract_feature_vector_from_mapping(_analysis_payload_with_mel_rows(64))

        small_mel = sorted(name for name in small.as_mapping() if name.startswith("mel_band_"))
        large_mel = sorted(name for name in large.as_mapping() if name.startswith("mel_band_"))

        self.assertEqual(small_mel, large_mel)
        self.assertEqual(len([name for name in small_mel if name.endswith("_mean_db")]), 20)

    def test_manifest_validation_rejects_duplicate_record_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_feature_file(root / "a.features.json", {"fill_proxy": 0.0})
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    _manifest_payload(
                        root,
                        [
                            _record("dup", "s1", 0.0, "a.features.json"),
                            _record("dup", "s2", 25.0, "a.features.json"),
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ManifestValidationError) as error:
                load_manifest(manifest_path)

        self.assertIn("duplicate record id", str(error.exception))

    def test_group_holdout_split_prevents_session_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = _write_synthetic_manifest(Path(directory), session_count=6)
            manifest = load_manifest(manifest_path)

        split = make_group_holdout_split(
            manifest.active_records(),
            group_fields=("session_id",),
            holdout_fraction=0.34,
            random_state=11,
        )
        train_sessions = {
            record.context.session_id
            for record in manifest.active_records()
            if split.split_for(record.record_id) == "train"
        }
        test_sessions = {
            record.context.session_id
            for record in manifest.active_records()
            if split.split_for(record.record_id) == "test"
        }

        self.assertTrue(train_sessions)
        self.assertTrue(test_sessions)
        self.assertTrue(train_sessions.isdisjoint(test_sessions))
        self.assertEqual(split.test_count + split.train_count, len(manifest.active_records()))

    def test_group_holdout_split_changes_with_random_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = _write_synthetic_manifest(Path(directory), session_count=10)
            manifest = load_manifest(manifest_path)

        test_sets = set()
        for seed in range(5):
            split = make_group_holdout_split(
                manifest.active_records(),
                group_fields=("session_id",),
                holdout_fraction=0.3,
                random_state=seed,
            )
            test_sets.add(
                tuple(
                    sorted(
                        record.context.session_id
                        for record in manifest.active_records()
                        if split.split_for(record.record_id) == "test"
                    )
                )
            )

        self.assertGreater(len(test_sets), 1)

    def test_train_phase4_baseline_on_synthetic_monotone_dataset(self) -> None:
        try:
            import sklearn  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("scikit-learn is not installed in this environment.")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_synthetic_manifest(root, session_count=8)
            output_dir = root / "model"

            result = train_phase4_baseline(
                manifest_path,
                output_dir=output_dir,
                group_fields=("session_id",),
                holdout_fraction=0.25,
                random_state=5,
            )

            self.assertLess(result.metrics["regression"]["mae_percent"], 8.0)
            self.assertGreaterEqual(result.metrics["regression"]["within_one_bucket_rate"], 0.9)
            self.assertEqual(result.metrics["repeated_holdout"]["n_splits"], 5)
            self.assertEqual(len(result.split_plans), 5)
            self.assertIn("std", result.metrics["repeated_holdout"]["regression"]["mae_percent"])
            self.assertEqual(
                result.metrics["label_buckets_percent"],
                [0.0, 25.0, 50.0, 75.0, 100.0],
            )
            dropped_names = {
                feature["name"]
                for feature in result.metrics["feature_selection"]["dropped_features"]
            }
            self.assertIn("constant_room_gain", dropped_names)
            self.assertIn(
                "transfer_750hz_mean_db__missing",
                result.metrics["feature_selection"]["model_feature_names"],
            )
            self.assertTrue((output_dir / "baseline_sklearn.joblib").exists())
            self.assertTrue((output_dir / "metrics.json").exists())
            self.assertTrue((output_dir / "model-card.md").exists())

    def test_train_phase4_baseline_respects_manifest_bucket_schema(self) -> None:
        try:
            import sklearn  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("scikit-learn is not installed in this environment.")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_synthetic_manifest(
                root,
                session_count=8,
                buckets=(0.0, 33.0, 66.0, 100.0),
                fills=(0.0, 33.0, 66.0, 100.0),
            )

            result = train_phase4_baseline(manifest_path, repeated_holdouts=2)

        self.assertEqual(result.metrics["label_buckets_percent"], [0.0, 33.0, 66.0, 100.0])
        confusion = result.metrics["classification"]["confusion_matrix"]
        self.assertIn("33_percent", confusion)
        self.assertIn("66_percent", confusion)

    def test_phase4_benchmark_report_tags_standard_regimes(self) -> None:
        try:
            import sklearn  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("scikit-learn is not installed in this environment.")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_synthetic_manifest(root, session_count=8, varied_context=True)
            output_dir = root / "benchmark"

            report = run_phase4_benchmark(
                manifest_path,
                output_dir=output_dir,
                repeated_holdouts=2,
            )

            self.assertEqual(
                {axis["name"] for axis in report["axes"]},
                {"session", "glass", "device", "browser"},
            )
            self.assertTrue((output_dir / "benchmark_report.json").exists())
            self.assertTrue((output_dir / "benchmark_report.md").exists())

    def test_audio_path_records_require_exact_probe_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav_path = root / "dummy.wav"
            wav_path.write_bytes(b"not a real wav")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    _manifest_payload(
                        root,
                        [
                            {
                                **_record("audio-no-probe", "s1", 0.0, "features/unused.json"),
                                "audio_path": "dummy.wav",
                                "features_path": None,
                                "probe": None,
                            }
                        ],
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ManifestValidationError):
                load_manifest(manifest_path)


def _write_synthetic_manifest(
    root: Path,
    *,
    session_count: int,
    buckets: tuple[float, ...] = (0.0, 25.0, 50.0, 75.0, 100.0),
    fills: tuple[float, ...] = (0.0, 25.0, 50.0, 75.0, 100.0),
    varied_context: bool = False,
) -> Path:
    records = []
    for session_index in range(session_count):
        session_id = f"session-{session_index:02d}"
        session_shift = (session_index % 3) * 0.35
        for fill_percent in fills:
            record_id = f"{session_id}-{int(fill_percent):03d}"
            feature_path = f"features/{record_id}.json"
            peak_proxy = 100.0 - fill_percent + session_shift
            transfer_proxy = fill_percent * 0.5 - session_shift
            features = {
                "constant_room_gain": 1.0,
                "peak_1_log_hz": peak_proxy,
                "spectral_centroid_log_hz": peak_proxy * 0.9,
                "transfer_750hz_mean_db": transfer_proxy,
                "decay_rate_log2_per_second": 5.0 - fill_percent * 0.01,
            }
            if fill_percent == max(fills):
                del features["transfer_750hz_mean_db"]
            _write_feature_file(root / feature_path, features)
            records.append(
                _record(
                    record_id,
                    session_id,
                    fill_percent,
                    feature_path,
                    varied_context=varied_context,
                    session_index=session_index,
                )
            )

    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest_payload(root, records, buckets=buckets), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _manifest_payload(
    root: Path,
    records: list[dict],
    *,
    buckets: tuple[float, ...] = (0.0, 25.0, 50.0, 75.0, 100.0),
) -> dict:
    return {
        "format": DATASET_FORMAT,
        "format_version": DATASET_FORMAT_VERSION,
        "dataset_id": f"synthetic-{root.name}",
        "created_at": "2026-06-19T00:00:00Z",
        "label_schema": {"buckets_percent": list(buckets)},
        "records": records,
    }


def _record(
    record_id: str,
    session_id: str,
    fill_percent: float,
    feature_path: str,
    *,
    varied_context: bool = False,
    session_index: int = 0,
) -> dict:
    glass_id = f"glass-{session_index % 4}" if varied_context else "glass-a"
    device_id = f"device-{session_index % 3}" if varied_context else f"device-{session_id[-2:]}"
    browser_id = f"browser-{session_index % 3}" if varied_context else "chrome-125"
    return {
        "id": record_id,
        "features_path": feature_path,
        "label": {"fill_percent": fill_percent},
        "context": {
            "session_id": session_id,
            "glass_id": glass_id,
            "device_id": device_id,
            "browser_id": browser_id,
            "room_id": "room-a",
            "volume_setting": "system-60",
        },
        "quality": {
            "usable": True,
            "alignment_confidence": 0.95,
            "signal_to_noise_db": 30.0,
        },
    }


def _write_feature_file(path: Path, features: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "format": FEATURE_FORMAT,
                "format_version": FEATURE_FORMAT_VERSION,
                "schema_version": 1,
                "features": [
                    {"name": name, "value": value, "unit": "synthetic", "source": "test"}
                    for name, value in sorted(features.items())
                ],
                "quality": {
                    "alignment_confidence": 0.95,
                    "signal_to_noise_db": 30.0,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _analysis_payload_with_mel_rows(row_count: int) -> dict:
    mel = [
        [-90.0 + row_index * 0.5 + column_index for column_index in range(6)]
        for row_index in range(row_count)
    ]
    return {
        "dsp": {
            "fft": {"centroid_hz": 1600.0, "bandwidth_hz": 400.0, "rolloff_hz": 2400.0},
            "dominant_peaks": [{"frequency_hz": 1400.0, "prominence_db": 12.0}],
            "transfer_response": [],
            "decay": {"decay_rate_per_second": 4.0, "rt60_seconds": 1.0},
            "mel_spectrogram": {"magnitude_db": mel},
            "stft": {"magnitude_db": [[-1.0] * 513]},
        },
        "alignment": {"confidence": 0.9},
        "warnings": [],
    }


if __name__ == "__main__":
    unittest.main()
