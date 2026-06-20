"""Leakage-aware dataset splitting for Phase 4 model evaluation."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .dataset import DEFAULT_BUCKETS_PERCENT, DatasetRecord, bucket_name, nearest_fill_bucket

SplitName = Literal["train", "test"]


class SplitValidationError(ValueError):
    """Raised when a requested split leaks group identity or cannot be formed."""


@dataclass(frozen=True)
class SplitPlan:
    """Record-level train/test assignment and audit metadata."""

    assignments: Mapping[str, SplitName]
    group_fields: tuple[str, ...]
    holdout_fraction: float
    random_state: int
    train_count: int
    test_count: int
    train_groups: int
    test_groups: int
    label_distribution: Mapping[str, Mapping[str, int]]

    def split_for(self, record_id: str) -> SplitName:
        return self.assignments[record_id]


def make_group_holdout_split(
    records: Sequence[DatasetRecord],
    *,
    group_fields: Sequence[str] = ("session_id",),
    buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    holdout_fraction: float = 0.2,
    random_state: int = 17,
) -> SplitPlan:
    """Build a deterministic holdout split while keeping groups on one side only."""

    active_records = [record for record in records if record.usable]
    fields = tuple(group_fields)
    if not active_records:
        raise SplitValidationError("At least one usable record is required.")
    if not fields:
        raise SplitValidationError("At least one group field is required.")
    if not (0.0 < holdout_fraction < 1.0):
        raise SplitValidationError("holdout_fraction must be between 0 and 1.")

    grouped: dict[tuple[str, ...], list[DatasetRecord]] = {}
    for record in active_records:
        grouped.setdefault(record.group_key(fields), []).append(record)
    if len(grouped) < 2:
        raise SplitValidationError(
            "At least two distinct groups are required for a leakage-aware holdout split."
        )

    test_keys = _group_shuffle_test_keys(
        active_records=active_records,
        grouped=grouped,
        group_fields=fields,
        holdout_fraction=holdout_fraction,
        random_state=random_state,
    )

    assignments: dict[str, SplitName] = {}
    for group_key, group_records in grouped.items():
        split: SplitName = "test" if group_key in test_keys else "train"
        for record in group_records:
            assignments[record.record_id] = split

    assert_no_group_leakage(active_records, assignments, fields)
    train_records = [
        record for record in active_records if assignments[record.record_id] == "train"
    ]
    test_records = [record for record in active_records if assignments[record.record_id] == "test"]
    return SplitPlan(
        assignments=assignments,
        group_fields=fields,
        holdout_fraction=holdout_fraction,
        random_state=random_state,
        train_count=len(train_records),
        test_count=len(test_records),
        train_groups=len({record.group_key(fields) for record in train_records}),
        test_groups=len({record.group_key(fields) for record in test_records}),
        label_distribution={
            "train": dict(_label_counts(train_records, buckets_percent)),
            "test": dict(_label_counts(test_records, buckets_percent)),
        },
    )


def make_repeated_group_holdout_splits(
    records: Sequence[DatasetRecord],
    *,
    group_fields: Sequence[str] = ("session_id",),
    buckets_percent: Sequence[float] = DEFAULT_BUCKETS_PERCENT,
    holdout_fraction: float = 0.2,
    random_state: int = 17,
    n_splits: int = 5,
) -> tuple[SplitPlan, ...]:
    """Build repeated group holdouts for estimating metric variance across seeds."""

    if n_splits <= 0:
        raise SplitValidationError("n_splits must be positive.")
    return tuple(
        make_group_holdout_split(
            records,
            group_fields=group_fields,
            buckets_percent=buckets_percent,
            holdout_fraction=holdout_fraction,
            random_state=random_state + split_index,
        )
        for split_index in range(n_splits)
    )


def assert_no_group_leakage(
    records: Sequence[DatasetRecord],
    assignments: Mapping[str, SplitName],
    group_fields: Sequence[str],
) -> None:
    """Raise if a group key appears in both train and test assignments."""

    group_splits: dict[tuple[str, ...], SplitName] = {}
    for record in records:
        split = assignments.get(record.record_id)
        if split not in ("train", "test"):
            raise SplitValidationError(f"{record.record_id}: missing split assignment.")
        group_key = record.group_key(group_fields)
        previous = group_splits.get(group_key)
        if previous is not None and previous != split:
            fields = ", ".join(group_fields)
            raise SplitValidationError(
                f"Group leakage detected for {fields}={group_key!r}: {previous} and {split}."
            )
        group_splits[group_key] = split


def _label_counts(
    records: Sequence[DatasetRecord],
    buckets_percent: Sequence[float],
) -> Counter[str]:
    return Counter(
        bucket_name(nearest_fill_bucket(record.label.fill_percent, buckets_percent))
        for record in records
    )


def _group_shuffle_test_keys(
    *,
    active_records: Sequence[DatasetRecord],
    grouped: Mapping[tuple[str, ...], Sequence[DatasetRecord]],
    group_fields: Sequence[str],
    holdout_fraction: float,
    random_state: int,
) -> set[tuple[str, ...]]:
    try:
        from sklearn.model_selection import GroupShuffleSplit
    except ModuleNotFoundError:  # pragma: no cover - scikit-learn is in ML/dev deps.
        return _fallback_group_shuffle_keys(grouped, holdout_fraction, random_state)

    group_labels = [_stable_hash(repr(record.group_key(group_fields))) for record in active_records]
    key_by_label = {
        _stable_hash(repr(group_key)): group_key
        for group_key in grouped
    }
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=holdout_fraction,
        random_state=random_state,
    )
    _, test_indices = next(splitter.split(active_records, groups=group_labels))
    test_keys = {key_by_label[group_labels[index]] for index in test_indices}
    if not test_keys or len(test_keys) == len(grouped):
        return _fallback_group_shuffle_keys(grouped, holdout_fraction, random_state)
    return test_keys


def _fallback_group_shuffle_keys(
    grouped: Mapping[tuple[str, ...], Sequence[DatasetRecord]],
    holdout_fraction: float,
    random_state: int,
) -> set[tuple[str, ...]]:
    group_keys = sorted(grouped, key=repr)
    random.Random(random_state).shuffle(group_keys)
    shuffled_rank = {group_key: rank for rank, group_key in enumerate(group_keys)}
    total_records = sum(len(records) for records in grouped.values())
    target_count = max(1, min(total_records - 1, round(total_records * holdout_fraction)))
    test_keys: set[tuple[str, ...]] = set()
    test_count = 0
    remaining = set(group_keys)
    while remaining and len(test_keys) < len(group_keys) - 1:
        candidates = sorted(
            remaining,
            key=lambda group_key: (
                abs(target_count - (test_count + len(grouped[group_key]))),
                len(grouped[group_key]),
                shuffled_rank[group_key],
            ),
        )
        group_key = candidates[0]
        next_count = test_count + len(grouped[group_key])
        if test_keys and abs(target_count - test_count) <= abs(target_count - next_count):
            break
        remaining.remove(group_key)
        test_keys.add(group_key)
        test_count = next_count
        if test_count >= target_count:
            break
    return test_keys


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
