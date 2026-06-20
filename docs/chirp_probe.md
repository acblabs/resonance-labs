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

The DSP pipeline currently derives:

- Matched-filter chirp alignment and confidence.
- FFT-domain bandpass filtering around the configured sweep, with zero-padding and cropping to reduce circular wraparound at capture boundaries.
- FFT, STFT, and mel-spectrogram summaries. The FFT `spectral_floor_db` value is a percentile of the analysis-window spectrum, not the pre-roll recording noise floor.
- Regularized transfer-response magnitudes by frequency band.
- Dominant post-chirp peaks with dB-domain sub-bin peak interpolation and interpolated half-power crossings for Q-factor estimates.
- RMS-envelope decay and RT60 proxy values; non-decaying or upward-sloping fits report no decay rate, RT60, or fit quality.

For room acoustic fingerprints, direct speaker-to-microphone energy and reflections are part of the measured response. The app reports quality and caveats instead of trying to remove every direct-path component. Future impulse/deconvolution views should keep regularization explicit and avoid claiming spatial reconstruction from a single speaker/microphone pair.

SNR is measured against pre-roll audio that ends before both the scheduled chirp start and the detected chirp start, so early-arriving chirps do not contaminate the noise estimate. Browser-native capture sample rates are preserved rather than resampled because OS/browser resampling can change feature portability.

Golden tests include deterministic generated probes, analytic damped-sinusoid checks, and a committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down. These fixtures are not real device/session recordings. The synthetic fixtures can be regenerated with `scripts/generate_phase2_fixtures.py`. Real device WAV fixtures should supplement them as soon as measurement data is available; see `docs/real_recording_fixtures.md` for the tracked TODO and acceptance criteria.
