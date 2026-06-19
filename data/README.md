# ResonanceLab Data Directory

This directory contains public-safe dataset metadata examples only.

Keep private raw audio, API analysis JSON, feature JSON, and benchmark exports out of git unless a
specific release decision approves them. The Phase 4 manifest format supports relative paths into a
private local dataset root.

`data/manifests/phase4_manifest.example.json` is a schema example, not a runnable training dataset.
It intentionally has placeholder private paths and too few records/groups to satisfy the trainer.
