# Real Recording Fixture TODO

The current fixture set has two roles:

- `phase2_golden_probe.json` drives a deterministic generated signal for stable math regression tests.
- `phase2_recorded_style_probe.wav` is a committed PCM WAV with synthetic channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down.

Neither fixture is a real device/session recording. They protect DSP code paths, but they do not validate real-world room fingerprint stability.

## TODO: Add Real WAV Fixtures

Add small committed PCM WAV fixtures from real recordings when measurement data is available.

Minimum first set:

- Three repeated chirp captures from one room position.
- One capture from a second position in the same room.
- One capture from a different room.
- One noisy or low-confidence recording that should trigger warnings.

Each fixture should include sidecar JSON metadata:

- Device model or anonymized device label.
- Browser and operating system.
- Sample rate and capture path.
- Probe configuration.
- Room label and position label.
- Volume setting or repeatable volume note.
- Distance/orientation notes.
- Expected broad DSP behavior, such as alignment confidence range, SNR range, dominant peak band, and decay range.

Acceptance criteria:

- WAV files are short enough to keep the repo lightweight.
- Tests load the committed WAV bytes from disk.
- Expected assertions use tolerances and ranges rather than exact values.
- The tests do not claim room identity or geometry reconstruction.
- Fixtures cover more than one device/session before they are used for product claims.

This TODO should remain open until real recordings exist across multiple devices, browsers, rooms, and positions.
