from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = (
    ROOT / "services/api/Dockerfile",
    ROOT / "apps/web/Dockerfile",
)
REQUIREMENT_FILES = (
    ROOT / "requirements.txt",
    ROOT / "requirements-dev.txt",
)
FROM_PATTERN = re.compile(r"^FROM\s+(?P<image>\S+)", re.MULTILINE)


def main() -> int:
    errors: list[str] = []
    errors.extend(check_dockerfiles())
    errors.extend(check_cloudbuild_images())
    errors.extend(check_requirements())

    if errors:
        print("Supply-chain checks failed:\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Supply-chain checks passed.")
    return 0


def check_dockerfiles() -> list[str]:
    errors: list[str] = []
    for path in DOCKERFILES:
        text = path.read_text(encoding="utf-8")
        for match in FROM_PATTERN.finditer(text):
            image = match.group("image")
            if "@sha256:" not in image:
                errors.append(f"{relative(path)} FROM image '{image}' must be digest-pinned.")
    return errors


def check_cloudbuild_images() -> list[str]:
    cloudbuild = ROOT / "cloudbuild.yaml"
    errors: list[str] = []
    for line_number, line in enumerate(cloudbuild.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("name:"):
            continue
        image = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        if image and "@sha256:" not in image:
            errors.append(
                f"cloudbuild.yaml:{line_number} step image '{image}' must be digest-pinned."
            )
    return errors


def check_requirements() -> list[str]:
    errors: list[str] = []
    for path in REQUIREMENT_FILES:
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(("-r ", "-e ")):
                continue
            if "==" not in line:
                errors.append(
                    f"{relative(path)}:{line_number} direct requirement '{line}' must use ==."
                )
    return errors


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


if __name__ == "__main__":
    sys.exit(main())
