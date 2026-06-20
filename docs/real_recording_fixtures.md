# Real Recording Fixtures

The current fixture set has two roles:

- `phase2_golden_probe.json` drives a deterministic generated signal for stable math regression tests.
- `phase2_recorded_style_probe.wav` is a committed PCM WAV with synthetic channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down.

Neither fixture is a real device/session recording. They protect DSP code paths, but they do not validate real-world room fingerprint stability.

## Collection Workflow

The first public real-room set should use reviewed JSON acoustic reports from the Lab UI. Raw WAV recordings should stay private unless a specific release decision approves a small, consented, documented fixture.

Minimum first set:

- Three non-failing repeated chirp captures from one room position.
- One capture from a second position in the same room.
- One capture from a different room.
- One noisy or low-confidence recording that should trigger warnings.

Each fixture manifest entry should include:

- Device model or anonymized device label.
- Browser and operating system.
- Room label and position label.
- Session label.
- Expected quality: `pass`, `review`, or `fail`.
- Path to a reviewed JSON acoustic report export.

Acceptance criteria:

- Manifest validates with `scripts/validate_real_room_fixtures.py`.
- Report exports do not contain raw WAV bytes or PCM samples.
- Deliberately failing/noisy fixtures do not count toward the three-repeat stability gate.
- Expected assertions use tolerances and ranges rather than exact values.
- The tests do not claim room identity or geometry reconstruction.
- Fixtures cover more than one device/session before they are used for product claims.

Start from `data/real_room_fixtures/manifest.example.json`, then validate the collected manifest:

```powershell
python scripts/validate_real_room_fixtures.py data/real_room_fixtures/manifest.json --strict-coverage
```

This remains open until real recordings exist across multiple devices, browsers, rooms, and positions.
