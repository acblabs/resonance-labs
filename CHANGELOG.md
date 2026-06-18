# Changelog

All notable changes to ResonanceLab will be documented in this file.

## Unreleased

### Added

- Phase 1 browser chirp capture and WAV upload scaffold.
- FastAPI dummy analysis endpoint with basic WAV metrics.
- Docker Compose development stack.
- Cloud Build configuration for GCP-based checks and container builds.
- Local Git hook and project freshness checker for README, CHANGELOG, FEATURES, and SKILL.md files.
- Feature inventory in `FEATURES.md`.
- `.env.example` documenting local API URL configuration.
- Commit-message docs freshness escape hatch through `[skip docs]`.
- Pytest and Ruff configuration for root-level contributor checks.

### Changed

- Project license changed to MIT.
- Pre-commit freshness policy now requires `FEATURES.md` in every commit.
- API dummy metrics now report `dc_offset` instead of misleading signed mean amplitude.
- Web builds now use runtime `PUBLIC_API_URL` instead of an inert build argument.
- Cloud Build and local API scripts now run `python -m ruff check .` and `python -m pytest`.
- Web runtime Docker image now installs production dependencies separately.

### Fixed

- Analyze uploads are read in bounded chunks before size validation.
- Browser chirp generation clamps unsafe probe values before playback.
- Chirp fade now uses a cosine taper to reduce envelope clicks.
- AudioWorklet capture batches render blocks to reduce allocation churn.
- 8-bit WAV unsigned PCM normalization now maps exactly across `[-1.0, 1.0]`.
- CI and Docker web dependency installs now use `npm ci`.
- WAV PCM decoding now uses vectorized NumPy paths for supported PCM widths.

### Removed

- GitHub Actions workflow in favor of GCP Cloud Build.
