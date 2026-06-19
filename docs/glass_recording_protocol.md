# Phase 4 Glass Recording Protocol

Phase 4 records private chirp datasets for evaluating whether DSP features can predict fill level
under controlled conditions. The goal is not a public model yet; it is a leakage-resistant benchmark
that tells us when a baseline is genuinely better than simple references.

## Required Metadata

Record these fields for every capture:

- `session_id`: one uninterrupted collection session with fixed setup.
- `glass_id`: one physical vessel, not a product class.
- `device_id`: anonymized device model or stable device label.
- `browser_id`: browser family and major version.
- `room_id`: stable room or acoustic location.
- `volume_setting`: system and application volume when available.
- `fill_percent`: measured by mass when possible, otherwise marked as approximate.
- `probe`: chirp start/end frequency, duration, pre-roll, post-roll, amplitude, and fade.

## Collection Procedure

1. Keep device placement, vessel placement, room position, orientation, browser, and volume fixed for
   a whole `session_id`.
2. Capture a free-air reference before vessel recordings when practical.
3. For each glass, record `0%`, `25%`, `50%`, `75%`, and `100%` fill levels.
4. Prefer at least three repeats per fill level per session.
5. Measure fill by mass:
   `fill_percent = 100 * (filled_mass - empty_mass) / (full_mass - empty_mass)`.
6. Save raw WAV files privately and generate API analysis JSON or Phase 4 feature JSON.
7. Reject or mark unusable any recording with alignment confidence below `0.20`, SNR below `12 dB`,
   unexpected browser audio processing, clipped audio, or changed setup.

## Minimum Alpha Dataset

Before treating a baseline as meaningful, collect at least:

- 3 or more physical glasses.
- 3 or more recording sessions per glass.
- 2 or more devices.
- 2 or more browser families or major browser versions when feasible.
- At least 5 fill buckets per glass/session.

These are bare minimums for discovering obvious failure modes. Trustworthy generalization claims will
probably need dozens of sessions and hundreds of recordings across materially different vessels and
rooms.

## Split Policy

Never evaluate with random probe-level splits. Use holdout groups:

- Same-glass supervised repeatability: split by `session_id`.
- Cross-glass generalization: split by `glass_id`.
- Cross-device generalization: split by `device_id`.
- Browser robustness: split by `browser_id`.

Reports must name the grouping fields and include train/test record counts, group counts, label
distribution, MAE, within-15%, within-20%, within-one-bucket rates, and repeated-holdout variance
when the dataset is small.
