# Limitations

ResonanceLab Phase 2 does not estimate fill level.

Known limitations:

- Browser audio processing can distort amplitude, decay, and spectral features.
- Device speaker-to-microphone bleed may dominate the object response.
- Mobile browser behavior is not verified until real devices are tested.
- The API returns DSP features and confidence signals, not calibrated predictions.
- Transfer-response bands are regularized magnitude ratios and do not remove direct-path bleed by themselves.
- The committed recorded-style WAV fixture exercises more realistic DSP paths than generated arrays, but it is not a substitute for real device/session recordings.
- Accuracy claims require calibrated datasets, reference recordings, and Phase 3+ validation.
