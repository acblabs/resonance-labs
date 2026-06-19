# Phase 4 Benchmark Results

Write private benchmark exports here only when they are safe to commit.

Use the compiled benchmark command for standard Phase 4 reports:

```powershell
python scripts/run_phase4_benchmark.py --manifest path/to/private_manifest.json --output-dir experiments/results/phase4_benchmark
```

The baseline trainer writes artifact metrics to `models/<artifact>/metrics.json`. Benchmark reports
should compare at least these split axes:

- `session_id` for same-glass supervised repeatability.
- `glass_id` for cross-glass generalization.
- `device_id` for cross-device generalization.
- `browser_id` for browser audio robustness.
