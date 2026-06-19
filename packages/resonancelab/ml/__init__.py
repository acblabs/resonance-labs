"""Phase 4 dataset and baseline-model helpers."""

from .baseline import (
    DEFAULT_REPEATED_HOLDOUTS,
    BaselineTrainingResult,
    QualityThresholds,
    train_phase4_baseline,
)
from .benchmark import BenchmarkAxis, run_phase4_benchmark
from .dataset import (
    DATASET_FORMAT,
    DATASET_FORMAT_VERSION,
    DatasetManifest,
    DatasetRecord,
    ManifestValidationError,
    RecordingContext,
    RecordingLabel,
    load_manifest,
)
from .features import (
    FEATURE_FORMAT,
    FEATURE_FORMAT_VERSION,
    FEATURE_SCHEMA_VERSION,
    FeatureVector,
    ModelFeature,
    extract_feature_vector_from_mapping,
    load_feature_vector,
    write_feature_vector,
)
from .splits import (
    SplitPlan,
    SplitValidationError,
    assert_no_group_leakage,
    make_group_holdout_split,
    make_repeated_group_holdout_splits,
)

__all__ = [
    "BaselineTrainingResult",
    "BenchmarkAxis",
    "DATASET_FORMAT",
    "DATASET_FORMAT_VERSION",
    "DEFAULT_REPEATED_HOLDOUTS",
    "DatasetManifest",
    "DatasetRecord",
    "FEATURE_FORMAT",
    "FEATURE_FORMAT_VERSION",
    "FEATURE_SCHEMA_VERSION",
    "FeatureVector",
    "ManifestValidationError",
    "ModelFeature",
    "QualityThresholds",
    "RecordingContext",
    "RecordingLabel",
    "SplitPlan",
    "SplitValidationError",
    "assert_no_group_leakage",
    "extract_feature_vector_from_mapping",
    "load_feature_vector",
    "load_manifest",
    "make_group_holdout_split",
    "make_repeated_group_holdout_splits",
    "run_phase4_benchmark",
    "train_phase4_baseline",
    "write_feature_vector",
]
