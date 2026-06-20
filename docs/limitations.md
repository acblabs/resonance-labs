# Limitations

ResonanceLab produces acoustic fingerprints and visual reports, not room geometry.

Known limitations:

- A single speaker and single microphone cannot reconstruct a spatial map or floor plan.
- Browser audio processing can distort amplitude, decay, and spectral features.
- Device speaker-to-microphone direct path is part of the response and may dominate some captures.
- Mobile browser behavior is not verified until real devices are tested.
- The API returns DSP features and confidence signals, not calibrated predictions.
- Transfer-response bands are regularized magnitude ratios and should be interpreted as broad coloration, not exact acoustic transfer functions.
- The committed recorded-style WAV fixture exercises more realistic DSP paths than generated arrays, but it is not a substitute for real device/session recordings.
- Room comparisons require controlled repeats across device, browser, position, and volume.
