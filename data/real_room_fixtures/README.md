# Real Room Fixture Manifests

This directory is for public-safe metadata and reviewed report exports.

Keep raw browser WAV files, private room notes, and unreviewed exports outside git. The preferred path is:

1. Run probes on real devices.
2. Export the JSON acoustic report from the Lab UI.
3. Review the report for privacy and quality.
4. Add the report JSON plus a manifest entry here only when it is safe to publish.

Validate a manifest with:

```powershell
python scripts/validate_real_room_fixtures.py data/real_room_fixtures/manifest.json --strict-coverage
```

Use `manifest.example.json` as the shape for the first collection pass. The validator requires three non-failing repeats for at least one room/position/device/browser/session group; deliberately noisy or failing captures are useful, but they do not count toward repeatability.
