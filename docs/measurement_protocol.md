# Measurement Protocol

Phase 1 validated plumbing. Phase 2 validates deterministic DSP features. Phase 3 adds local calibration estimates, but sensing accuracy still requires controlled anchor collection and real-device validation.

For early manual tests:

- Use speakers, not headphones or earbuds.
- Keep device placement fixed across runs.
- Record the device, browser, room, and volume setting.
- Run repeated probes for the same glass and fill state.
- Compare chirp recordings against tap recordings before making product claims.
- Keep the probe geometry fixed: same device orientation, same distance to the rim or wall, and same room position.
- Capture a free-air reference when speaker-to-microphone bleed or room reflections appear to dominate the response.
- Capture empty-glass reference recordings before comparing filled states.
- For Phase 4 reference comparison, keep free-air and known-object references under the same device,
  browser, volume, room position, and probe settings before asking for material hypotheses.
- For Phase 3 calibration, capture Empty, 50%, and Full anchors without changing device position, room position, browser, volume, or vessel.
- Capture at least two repeats per anchor when practical; single-repeat anchors intentionally reduce confidence.
- Capture a free-air reference with the same device, browser, volume, and probe settings to characterize direct-path and room response. The current app stores this reference for confidence and comparison; it does not perform magnitude subtraction.
- Re-run anchors if alignment confidence is below `0.20`, SNR is below `12 dB`, or browser audio processing warnings appear.
- Re-run anchors if the browser sample rate, capture path, or forced audio-processing settings change between calibration and measurement.
- Treat browser sample-rate changes as a new capture condition. The app preserves native sample rates and reduces confidence rather than resampling measurements into a false equivalence.
- Treat alignment confidence below `0.20` or SNR below `12 dB` as a low-confidence measurement.
- Keep at least `100 ms` of usable post-chirp audio for decay fitting. The default `1000 ms` post-roll is preferred for early experiments because RT60 and peak estimates become fragile with short windows.

Ground truth fill levels should be measured by mass in later feasibility testing.

The API returns spectral and decay features only. Phase 3 fill-level estimates are computed in the browser from local calibration anchors and should be treated as profile-relative experimental estimates, not global predictions. Any LLM explanation should consume structured DSP/reference summaries only, not raw audio.
