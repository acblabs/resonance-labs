from __future__ import annotations

import json
from pathlib import Path

import scripts.validate_real_room_fixtures as validator


def test_validator_rejects_forbidden_nested_report_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        [
            fixture("repeat-1", "reports/repeat-1.json"),
            fixture("repeat-2", "reports/repeat-2.json"),
            fixture("repeat-3", "reports/repeat-3.json"),
            fixture(
                "position-2",
                "reports/position-2.json",
                position="position-2",
                quality="review",
            ),
            fixture("room-b", "reports/room-b.json", room="room-b", quality="review"),
            fixture("noisy", "reports/noisy.json", quality="fail"),
        ],
    )
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    for path in report_dir.glob("*.json"):
        path.unlink()
    for fixture_entry in json.loads(manifest_path.read_text(encoding="utf-8"))["fixtures"]:
        write_json(report_dir / Path(fixture_entry["report_path"]).name, report_payload())
    write_json(
        report_dir / "repeat-1.json",
        report_payload({"analysis": {"audio": {}, "dsp": {}, "alignment": {}, "samples": [0.1]}}),
    )

    errors, _warnings = validator.validate_manifest(
        manifest_path,
        allow_missing=False,
        strict_coverage=False,
    )

    assert any("forbidden raw-audio keys: samples" in error for error in errors)


def test_validator_rejects_duplicate_fixture_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        [
            fixture("duplicate", "reports/a.json"),
            fixture("duplicate", "reports/b.json"),
        ],
    )

    errors, _warnings = validator.validate_manifest(
        manifest_path,
        allow_missing=True,
        strict_coverage=False,
    )

    assert any("duplicated" in error for error in errors)


def test_coverage_excludes_deliberately_failing_fixture_from_repeat_count(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        [
            fixture("repeat-1", "reports/repeat-1.json"),
            fixture("repeat-2", "reports/repeat-2.json"),
            fixture("noisy", "reports/noisy.json", quality="fail"),
            fixture(
                "position-2",
                "reports/position-2.json",
                position="position-2",
                quality="review",
            ),
            fixture("room-b", "reports/room-b.json", room="room-b", quality="review"),
        ],
    )

    errors, _warnings = validator.validate_manifest(
        manifest_path,
        allow_missing=True,
        strict_coverage=True,
    )

    assert any("three non-failing repeats" in error for error in errors)


def test_coverage_accepts_full_manifest_with_missing_future_reports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        [
            fixture("repeat-1", "reports/repeat-1.json"),
            fixture("repeat-2", "reports/repeat-2.json"),
            fixture("repeat-3", "reports/repeat-3.json"),
            fixture(
                "position-2",
                "reports/position-2.json",
                position="position-2",
                quality="review",
            ),
            fixture("room-b", "reports/room-b.json", room="room-b", quality="review"),
            fixture("noisy", "reports/noisy.json", quality="fail"),
        ],
    )

    errors, warnings = validator.validate_manifest(
        manifest_path,
        allow_missing=True,
        strict_coverage=True,
    )

    assert errors == []
    assert warnings == []


def test_cli_manifest_path_prefers_cwd_before_repo_root(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    cwd = tmp_path / "work"
    repo_root.mkdir()
    cwd.mkdir()
    cwd_manifest = cwd / "manifest.json"
    root_manifest = repo_root / "manifest.json"
    cwd_manifest.write_text("{}", encoding="utf-8")
    root_manifest.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(validator, "ROOT", repo_root)
    monkeypatch.chdir(cwd)

    assert validator.resolve_cli_manifest_path("manifest.json") == cwd_manifest.resolve()
    assert validator.resolve_cli_manifest_path("missing.json") == (repo_root / "missing.json")


def fixture(
    fixture_id: str,
    report_path: str,
    *,
    room: str = "room-a",
    position: str = "position-1",
    quality: str = "pass",
) -> dict[str, str]:
    return {
        "id": fixture_id,
        "report_path": report_path,
        "room_label": room,
        "position_label": position,
        "device_label": "device-a",
        "browser": "desktop-chrome",
        "session_label": "session-1",
        "expected_quality": quality,
    }


def write_manifest(tmp_path: Path, fixtures: list[dict[str, str]]) -> Path:
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": validator.MANIFEST_SCHEMA_VERSION,
            "fixtures": fixtures,
        },
    )
    return manifest_path


def report_payload(overrides: dict | None = None) -> dict:
    payload = {
        "schema_version": validator.REPORT_SCHEMA_VERSION,
        "validation": {"status": "pass"},
        "analysis": {
            "audio": {},
            "dsp": {},
            "alignment": {},
        },
    }
    if overrides:
        payload.update(overrides)
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
