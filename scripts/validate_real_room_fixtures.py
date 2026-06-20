from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA_VERSION = "resonancelab.real_room_fixtures.v1"
REPORT_SCHEMA_VERSION = "resonancelab.acoustic_report.v1"
QUALITY_VALUES = {"pass", "review", "fail"}
REQUIRED_FIXTURE_FIELDS = (
    "id",
    "report_path",
    "room_label",
    "position_label",
    "device_label",
    "browser",
    "session_label",
)
FORBIDDEN_REPORT_KEYS = {"wavBlob", "raw_audio", "rawAudio", "samples"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate public-safe real-room fixture manifest metadata."
    )
    parser.add_argument("manifest", help="Path to a real-room fixture manifest JSON file.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow report_path targets that have not been collected yet.",
    )
    parser.add_argument(
        "--strict-coverage",
        action="store_true",
        help="Require the first public fixture coverage set to be complete.",
    )
    args = parser.parse_args()

    manifest_path = resolve_cli_manifest_path(args.manifest)
    errors, warnings = validate_manifest(
        manifest_path,
        allow_missing=args.allow_missing,
        strict_coverage=args.strict_coverage,
    )

    if warnings:
        print("Real-room fixture warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()

    if errors:
        print("Real-room fixture validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Real-room fixture validation passed.")
    return 0


def validate_manifest(
    manifest_path: Path,
    *,
    allow_missing: bool,
    strict_coverage: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest_path.exists():
        return [f"{relative_or_absolute(manifest_path)} does not exist."], warnings

    payload = load_json(manifest_path, errors)
    if not isinstance(payload, dict):
        return (
            errors
            or [f"{relative_or_absolute(manifest_path)} must contain a JSON object."],
            warnings,
        )

    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"{relative_or_absolute(manifest_path)} schema_version must be "
            f"{MANIFEST_SCHEMA_VERSION}."
        )

    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        errors.append("manifest fixtures must be a list.")
        return errors, warnings

    seen_ids: set[str] = set()
    loaded_reports: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            errors.append(f"fixtures[{index}] must be an object.")
            continue
        fixture_errors = validate_fixture_entry(
            fixture,
            index=index,
            seen_ids=seen_ids,
            manifest_path=manifest_path,
            allow_missing=allow_missing,
        )
        errors.extend(fixture_errors)
        if fixture_errors:
            continue

        report_path = resolve_repo_path(fixture["report_path"], manifest_path.parent)
        if report_path.exists():
            report = load_json(report_path, errors)
            if isinstance(report, dict):
                errors.extend(validate_report_payload(fixture, report, report_path))
                loaded_reports.append((fixture, report))
        elif not allow_missing:
            errors.append(f"{as_repo_path(report_path)} is missing.")

    coverage_errors, coverage_warnings = validate_coverage(fixtures, loaded_reports)
    if strict_coverage:
        errors.extend(coverage_errors)
    else:
        warnings.extend(coverage_errors)
    warnings.extend(coverage_warnings)
    return errors, warnings


def validate_fixture_entry(
    fixture: dict[str, Any],
    *,
    index: int,
    seen_ids: set[str],
    manifest_path: Path,
    allow_missing: bool,
) -> list[str]:
    errors: list[str] = []
    label = f"fixtures[{index}]"
    for field in REQUIRED_FIXTURE_FIELDS:
        value = fixture.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}.{field} must be a non-empty string.")

    fixture_id = fixture.get("id")
    if isinstance(fixture_id, str):
        if fixture_id in seen_ids:
            errors.append(f"{label}.id '{fixture_id}' is duplicated.")
        seen_ids.add(fixture_id)

    expected_quality = fixture.get("expected_quality")
    if expected_quality is not None and expected_quality not in QUALITY_VALUES:
        errors.append(f"{label}.expected_quality must be pass, review, or fail.")

    report_path_value = fixture.get("report_path")
    if isinstance(report_path_value, str) and report_path_value.strip():
        report_path = resolve_repo_path(report_path_value, manifest_path.parent)
        try:
            report_path.relative_to(ROOT)
        except ValueError:
            errors.append(f"{label}.report_path must stay inside the repository.")
        if not allow_missing and not report_path.exists():
            errors.append(f"{as_repo_path(report_path)} is missing.")

    return errors


def validate_report_payload(
    fixture: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
) -> list[str]:
    errors: list[str] = []
    relative = as_repo_path(report_path)
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        errors.append(f"{relative} schema_version must be {REPORT_SCHEMA_VERSION}.")

    forbidden = sorted(find_forbidden_keys(report))
    if forbidden:
        errors.append(f"{relative} contains forbidden raw-audio keys: {', '.join(forbidden)}.")

    validation = report.get("validation")
    if not isinstance(validation, dict) or validation.get("status") not in QUALITY_VALUES:
        errors.append(f"{relative} must include validation.status.")
    elif validation["status"] == "fail" and fixture.get("expected_quality") != "fail":
        errors.append(
            f"{relative} has failing validation; mark expected_quality='fail' only "
            "for a low-confidence fixture."
        )

    analysis = report.get("analysis")
    if not isinstance(analysis, dict):
        errors.append(f"{relative} must include analysis data from the JSON export.")
    elif "audio" not in analysis or "dsp" not in analysis or "alignment" not in analysis:
        errors.append(f"{relative} analysis must include audio, dsp, and alignment sections.")

    return errors


def validate_coverage(
    fixtures: list[Any],
    loaded_reports: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[str], list[str]]:
    valid_fixtures = [fixture for fixture in fixtures if isinstance(fixture, dict)]
    errors: list[str] = []
    warnings: list[str] = []
    if not valid_fixtures:
        errors.append("At least one fixture entry is required.")
        return errors, warnings

    failed_report_ids = {
        fixture.get("id")
        for fixture, report in loaded_reports
        if report.get("validation", {}).get("status") == "fail"
    }
    repeatable_fixtures = [
        fixture
        for fixture in valid_fixtures
        if fixture.get("expected_quality") != "fail" and fixture.get("id") not in failed_report_ids
    ]
    repeat_counter = Counter(
        (
            fixture.get("room_label"),
            fixture.get("position_label"),
            fixture.get("device_label"),
            fixture.get("browser"),
            fixture.get("session_label"),
        )
        for fixture in repeatable_fixtures
    )
    if max(repeat_counter.values(), default=0) < 3:
        errors.append(
            "At least one room/position/device/browser/session group needs three "
            "non-failing repeats."
        )

    positions_by_room: dict[str, set[str]] = defaultdict(set)
    for fixture in valid_fixtures:
        room = fixture.get("room_label")
        position = fixture.get("position_label")
        if isinstance(room, str) and isinstance(position, str):
            positions_by_room[room].add(position)
    if not any(len(positions) >= 2 for positions in positions_by_room.values()):
        errors.append("At least one room needs two position labels for within-room comparison.")
    if len(positions_by_room) < 2:
        errors.append("At least two room labels are needed for room-to-room comparison.")

    has_low_confidence_fixture = any(
        fixture.get("expected_quality") == "fail" for fixture in valid_fixtures
    ) or any(report.get("validation", {}).get("status") == "fail" for _, report in loaded_reports)
    if not has_low_confidence_fixture:
        warnings.append(
            "No low-confidence fixture is marked yet; keep one noisy/failing run for warnings."
        )

    has_review_fixture = any(
        fixture.get("expected_quality") == "review" for fixture in valid_fixtures
    ) or any(
        report.get("validation", {}).get("status") == "review" for _, report in loaded_reports
    )
    if not has_review_fixture:
        warnings.append(
            "No borderline review fixture is marked yet; add one when validation coverage matures."
        )

    return errors, warnings


def find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_REPORT_KEYS:
                found.add(key)
            found.update(find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_forbidden_keys(child))
    return found


def resolve_repo_path(path_value: str, base: Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_cli_manifest_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()

    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (ROOT / path).resolve()


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{relative_or_absolute(path)} is not valid JSON: {exc}.")
    except OSError as exc:
        errors.append(f"{relative_or_absolute(path)} could not be read: {exc}.")
    return None


def as_repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def relative_or_absolute(path: Path) -> str:
    try:
        return as_repo_path(path)
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
