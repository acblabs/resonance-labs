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
- FFT-domain bandpass filtering around the configured sweep.
- FFT, STFT, and mel-spectrogram summaries. The FFT `spectral_floor_db` value is a percentile of the analysis-window spectrum, not the pre-roll recording noise floor.
- Regularized transfer-response magnitudes by frequency band.
- Dominant post-chirp ring-down peaks.
- RMS-envelope decay and RT60 proxy values.

Direct-path handling is still experimental. Speaker-to-microphone bleed and room reflections can dominate the object response, so free-air and empty-glass references remain part of the measurement protocol before making sensing claims.

Golden tests include deterministic generated probes and a committed recorded-style WAV fixture with channel coloration, attenuation, direct-path bleed, echoes, hum/noise, soft clipping, and ring-down. These fixtures are not real device/session recordings. The synthetic fixtures can be regenerated with `scripts/generate_phase2_fixtures.py`. Real device WAV fixtures should supplement them as soon as measurement data is available; see `docs/real_recording_fixtures.md` for the tracked TODO and acceptance criteria.
