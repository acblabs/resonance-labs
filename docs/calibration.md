# Calibration

Phase 3 is calibration-first and local-first. The API still returns chirp-aligned DSP features only; the browser stores calibration profiles in IndexedDB and computes profile-relative fill estimates without an account.

Each profile has three fill anchor slots:

- Empty: `0%`.
- 50%: `50%`.
- Full: `100%`.

Each slot can hold repeated captures. Repeats are aggregated into a mean feature vector and local stability statistics. Single-repeat anchors are accepted for the demo, but confidence is reduced because within-profile variance is unknown.

Profiles can also store a free-air reference. This captures the speaker-to-microphone and room path without the vessel in the measurement position. The current app uses this reference for confidence and warnings. It does not subtract free-air magnitudes because direct path, room reflections, and object response add as complex acoustic signals.

Profiles can store known-object references with operator-provided material labels. The app compares
the current probe against free-air, calibration anchors, and saved known references in the same
weighted DSP feature space, then reports the nearest reference, confidence, distance margin, and
whether free-air dominates. These are similarity hints under the same setup, not benchmarked material
classification claims.

Saving an anchor or reference stores the probe settings, a canonical browser capture signature, alignment/SNR quality signals, API warnings, and a compact feature vector extracted from dominant peaks, spectral descriptors, decay estimates, and transfer-response bands. Raw audio is not stored by default, and local profile IDs are not uploaded with probe analysis requests.

The estimator projects a new probe onto the nearest segment of the calibrated feature path:

```text
empty anchor -> 50% anchor -> full anchor
```

Distances are computed in a normalized weighted feature space. Log-frequency peak shifts receive the highest weight because mass loading usually shifts resonant modes downward as fill increases. Transfer-response, spectral-shape, and decay features add supporting evidence. Repeated frequency summaries are averaged in log-Hz space, matching the feature geometry.

Confidence uses a weighted geometric mean across soft quality factors, plus explicit caps for hard failures. This avoids multiplying many mild penalties into an artificially low score while still forcing low confidence for incompatible or unreliable measurements.

Confidence is reduced when:

- Any anchor is missing.
- Too few comparable features are available.
- Any fill anchor has only one repeat.
- Repeated anchors are unstable in normalized feature space.
- Current alignment confidence is below `0.20`.
- Current SNR is below `12 dB`.
- Probe settings differ from saved anchors.
- Sample rate, capture path, browser family, or reported audio-processing settings differ from saved samples.
- No free-air reference exists.
- The current probe is closer to the free-air reference than to calibrated anchors.
- Anchors are too close together in feature space.
- The primary peak is not monotonic across anchors, which may indicate mode switching or nonlinear behavior.
- The API returned browser-processing or DSP warnings.

The estimate is not a global model. It is only meaningful for the same vessel, device placement, room position, browser, volume setting, and probe configuration used to record the anchors.

Profiles are stored in IndexedDB and can be exported/imported as JSON. Export does not include raw audio.
