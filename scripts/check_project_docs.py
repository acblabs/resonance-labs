from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_REQUIRED_SECTIONS = [
    "Phase 1 Status",
    "Quickstart",
    "Docker Compose",
    "Features",
    "API",
    "Repository Layout",
    "Git Hooks",
    "Cloud Build",
    "Validation",
]
CHANGELOG_REQUIRED_SECTIONS = ["Unreleased"]
IMPLEMENTATION_PREFIXES = ("apps/", "services/", "packages/", "scripts/")
IMPLEMENTATION_FILES = {
    "docker-compose.yml",
    "cloudbuild.yaml",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
}
BEHAVIOR_PREFIXES = ("apps/", "services/", "packages/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate ResonanceLab project docs and skill files."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="Run structural checks only.")
    mode.add_argument(
        "--staged",
        action="store_true",
        help="Run structural checks and staged freshness policy.",
    )
    parser.add_argument(
        "--commit-message",
        help=(
            "Path to a commit message file. Freshness checks are skipped when it contains "
            "[skip docs]."
        ),
    )
    args = parser.parse_args()

    errors: list[str] = []
    errors.extend(check_readme())
    errors.extend(check_changelog())
    errors.extend(check_features())
    errors.extend(check_skills())

    if args.staged and not commit_message_skips_docs(args.commit_message):
        errors.extend(check_staged_freshness())

    if errors:
        print("Project documentation checks failed:\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Project documentation checks passed.")
    return 0


def check_readme() -> list[str]:
    readme = ROOT / "README.md"
    if not readme.exists():
        return ["README.md is missing."]

    text = readme.read_text(encoding="utf-8")
    errors = []
    for section in README_REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            errors.append(f"README.md is missing the '## {section}' section.")
    if "MIT" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
        errors.append("LICENSE must contain the MIT license text.")
    return errors


def check_changelog() -> list[str]:
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return ["CHANGELOG.md is missing."]

    text = changelog.read_text(encoding="utf-8")
    return [
        f"CHANGELOG.md is missing the '## {section}' section."
        for section in CHANGELOG_REQUIRED_SECTIONS
        if f"## {section}" not in text
    ]


def check_features() -> list[str]:
    features = ROOT / "FEATURES.md"
    if not features.exists():
        return ["FEATURES.md is missing."]

    text = features.read_text(encoding="utf-8")
    required = (
        "Current Phase 1 Features",
        "Planned DSP Features",
        "Planned Room Fingerprint Features",
    )
    return [
        f"FEATURES.md is missing the '## {section}' section."
        for section in required
        if f"## {section}" not in text
    ]


def check_skills() -> list[str]:
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return ["skills/ is missing."]

    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        return ["No skills/*/SKILL.md files were found."]

    errors: list[str] = []
    for skill_file in skill_files:
        relative = as_repo_path(skill_file)
        text = skill_file.read_text(encoding="utf-8")
        frontmatter = read_frontmatter(text)
        if frontmatter is None:
            errors.append(f"{relative} must start with YAML front matter delimited by '---'.")
            continue

        name = frontmatter_value(frontmatter, "name")
        if name != skill_file.parent.name:
            errors.append(f"{relative} name must match its folder name '{skill_file.parent.name}'.")

        for field in ("description", "license", "metadata"):
            if not has_frontmatter_key(frontmatter, field):
                errors.append(f"{relative} is missing front matter field '{field}'.")

        if "ResonanceLab" not in text:
            errors.append(f"{relative} should mention ResonanceLab project context.")
        if "implementation_plan.md" not in text:
            errors.append(f"{relative} should reference the implementation plan.")

    return errors


def check_staged_freshness() -> list[str]:
    staged = staged_files()
    if not staged:
        return []

    staged_set = set(staged)
    implementation_changed = any(is_implementation_file(path) for path in staged)
    behavior_changed = any(path.startswith(BEHAVIOR_PREFIXES) for path in staged)
    errors: list[str] = []

    if "FEATURES.md" not in staged_set:
        errors.append("Every commit must include an updated FEATURES.md file.")

    if implementation_changed:
        for required in ("README.md", "CHANGELOG.md"):
            if required not in staged_set:
                errors.append(
                    f"Implementation files are staged, so include {required} in this commit."
                )

    if behavior_changed and not any(is_skill_file(path) for path in staged):
        errors.append(
            "App/API/package behavior changed, so include at least one skills/*/SKILL.md update."
        )

    return errors


def staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [normalize_path(line) for line in result.stdout.splitlines() if line.strip()]


def commit_message_skips_docs(message_path: str | None) -> bool:
    if not message_path:
        return False

    path = Path(message_path)
    if not path.exists():
        return False

    return "[skip docs]" in path.read_text(encoding="utf-8").lower()


def is_implementation_file(path: str) -> bool:
    return path.startswith(IMPLEMENTATION_PREFIXES) or path in IMPLEMENTATION_FILES


def is_skill_file(path: str) -> bool:
    return path.startswith("skills/") and path.endswith("/SKILL.md")


def read_frontmatter(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    return match.group(1) if match else None


def frontmatter_value(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", frontmatter, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def has_frontmatter_key(frontmatter: str, key: str) -> bool:
    return re.search(rf"^{re.escape(key)}:", frontmatter, flags=re.MULTILINE) is not None


def as_repo_path(path: Path) -> str:
    return normalize_path(str(path.relative_to(ROOT)))


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


if __name__ == "__main__":
    sys.exit(main())
