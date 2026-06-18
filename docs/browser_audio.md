# Browser Audio Notes

Phase 1 uses a user-initiated Web Audio flow:

1. Create and resume `AudioContext` from the `Start Probe` button.
2. Request microphone access with echo cancellation, noise suppression, and automatic gain control set to `false`.
3. Capture mono PCM through an AudioWorklet when available.
4. Fall back to ScriptProcessor capture if the worklet cannot be loaded.
5. Encode captured PCM to a browser-side WAV file.
6. Upload the WAV plus probe metadata to FastAPI.
7. Render waveform, FFT, STFT, and mel-spectrogram views from the returned API data.
8. Store optional calibration anchors locally in IndexedDB and compute profile-relative estimates in the browser.
9. Compare probe settings, sample rate, capture path, browser family, and reported audio-processing flags against saved calibration samples.

Browsers and operating systems may ignore requested audio constraints. The API response warns when reported track settings show forced processing. ResonanceLab preserves the native browser WAV sample rate instead of forcing resampling; saved calibration samples include sample-rate and capture-path signatures so mismatches reduce confidence.

The API also warns when matched-filter alignment confidence is low or when SNR falls below the early `12 dB` feasibility target. These warnings are confidence signals, not hard proof that a recording is unusable.

Mobile testing remains manual. Android Chrome is the first supported mobile target. iOS Safari requires careful user-gesture testing and an HTTPS origin outside localhost.

Calibration profiles remain local to the browser. Probe uploads do not include local profile IDs or anchor vectors. Clearing site data deletes saved anchors and profiles. Phase 3 supports JSON export/import for local backup, but private browsing modes and browser storage pressure may still evict IndexedDB data.
