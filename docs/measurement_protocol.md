# Measurement Protocol

Phase 1 validated plumbing. Phase 2 validates deterministic DSP features, not sensing accuracy.

For early manual tests:

- Use speakers, not headphones or earbuds.
- Keep device placement fixed across runs.
- Record the device, browser, room, and volume setting.
- Run repeated probes for the same glass and fill state.
- Compare chirp recordings against tap recordings before making product claims.
- Keep the probe geometry fixed: same device orientation, same distance to the rim or wall, and same room position.
- Capture a free-air reference when speaker-to-microphone bleed or room reflections appear to dominate the response.
- Capture empty-glass reference recordings before comparing filled states.
- Treat alignment confidence below `0.20` or SNR below `12 dB` as a low-confidence measurement.
- Keep at least `100 ms` of usable post-chirp audio for decay fitting. The default `1000 ms` post-roll is preferred for early experiments because RT60 and peak estimates become fragile with short windows.

Ground truth fill levels should be measured by mass in later feasibility testing.

The Phase 2 API returns spectral and decay features only. Fill-level estimates require calibrated profiles and anchor measurements in a later phase.
