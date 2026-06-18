# Chirp Probe

Default chirp settings:

```json
{
  "signal_type": "log_chirp",
  "start_hz": 500,
  "end_hz": 10000,
  "duration_ms": 500,
  "pre_roll_ms": 250,
  "post_roll_ms": 1000,
  "amplitude": 0.35,
  "fade_ms": 10
}
```

The chirp is intentionally conservative:

- Maximum default amplitude is capped at `0.35`.
- The waveform is faded in and out.
- The UI warns against headphones and earbuds.
- The API uses the configured chirp as a matched-filter reference.

Phase 2 DSP currently derives:

- Matched-filter chirp alignment and confidence.
- FFT-domain bandpass filtering around the configured sweep, with zero-padding and cropping to reduce circular wraparound at capture boundaries.
- FFT, STFT, and mel-spectrogram summaries. The FFT `spectral_floor_db` value is a percentile of the analysis-window spectrum, not the pre-roll recording noise floor.
- Regularized transfer-response magnitudes by frequency band.
- Dominant post-chirp ring-down peaks with sub-bin peak interpolation and interpolated `-3 dB` bandwidth crossings for Q-factor estimates.
- RMS-envelope decay and RT60 proxy values; non-decaying or upward-sloping fits report no decay rate, RT60, or fit quality.

Phase 3 uses those DSP outputs as browser-local calibration features. The app stores Empty, 50%, Full, and free-air reference vectors in IndexedDB, then estimates fill by projecting a new probe onto the nearest calibrated feature segment. Repeated anchors are aggregated into mean feature vectors with stability statistics. The API does not receive anchor vectors or raw profile history.

SNR is measured against pre-roll audio that ends before both the scheduled chirp start and the detected chirp start, so early-arriving chirps do not contaminate the noise estimate. Browser-native capture sample rates are preserved rather than resampled; calibration profiles record sample-rate and capture-path signatures because OS/browser resampling can change feature portability.

Direct-path handling is still experimental. Speaker-to-microphone bleed and room reflections can dominate the object response, so free-air and empty-glass references remain part of the measurement protocol before making sensing claims. The Phase 3 app does not subtract free-air magnitudes because direct bleed and object response combine as complex signals; it uses the free-air reference for warnings and confidence until a validated deconvolution or gating method exists.

Golden tests include deterministic generated probes, analytic damped-sinusoid checks, and a committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down. These fixtures are not real device/session recordings. The synthetic fixtures can be regenerated with `scripts/generate_phase2_fixtures.py`. Real device WAV fixtures should supplement them as soon as measurement data is available; see `docs/real_recording_fixtures.md` for the tracked TODO and acceptance criteria.
