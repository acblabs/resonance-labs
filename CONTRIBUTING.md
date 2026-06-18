# Contributing

ResonanceLab is early-stage research software. Keep changes small, testable, and honest about measurement limits.

## Local Setup

```powershell
python -m pip install -r requirements-dev.txt
npm.cmd install
```

Run API checks:

```powershell
python -m compileall packages services/api scripts
python -m ruff check .
python -m pytest
```

Run web checks:

```powershell
npm.cmd --workspace @resonancelab/web run check
npm.cmd --workspace @resonancelab/web run build
```

Run project documentation and skill checks:

```powershell
python scripts/check_project_docs.py --all
```

## Git Hooks

Install local hooks once:

```powershell
git config core.hooksPath .githooks
```

The pre-commit hook validates README, CHANGELOG, FEATURES, and every `skills/*/SKILL.md`. The commit-msg hook enforces staged freshness. Every commit must include an updated `FEATURES.md`. If staged implementation files change, include README and CHANGELOG updates in the same commit. If app/API/package behavior changes, include a relevant SKILL.md update too.

Use `[skip docs]` in the commit message only when a docs update would be noise. The structural checks still run.

Cloud Build runs the same structural project checks on every build.

## Measurement Notes

- Do not claim mobile support until the flow has been tested on real devices.
- Do not send raw audio to an LLM.
- Store calibration profiles locally unless a later phase explicitly introduces cloud sync.
- Prefer calibrated, within-object claims over broad zero-shot claims.
