# Browser Audio Notes

The app uses a user-initiated Web Audio flow. End users do not need special acoustic hardware or a downloadable desktop/mobile app; a supported browser, speaker, and microphone are enough to run the probe workflow.

1. Create and resume `AudioContext` from the `Start Probe` button.
2. Request microphone access with echo cancellation, noise suppression, and automatic gain control set to `false`.
3. Capture mono PCM through an AudioWorklet when available.
4. Fall back to ScriptProcessor capture if the worklet cannot be loaded.
5. Encode captured PCM to a browser-side WAV file.
6. Upload the WAV plus probe metadata to FastAPI.
7. Render waveform, FFT, STFT, and mel-spectrogram views from the returned API data.
8. Display room-fingerprint descriptors, quality flags, and explanation output from structured DSP evidence.
9. Export reviewed JSON or PNG acoustic reports after a successful probe.

Browsers and operating systems may ignore requested audio constraints. The API response warns when reported track settings show forced processing. ResonanceLab preserves the native browser WAV sample rate instead of forcing resampling.

The API also warns when matched-filter alignment confidence is low or when SNR falls below the early `12 dB` feasibility target. These warnings are confidence signals, not hard proof that a recording is unusable.

Mobile testing remains manual. Android Chrome is the first supported mobile target. iOS Safari requires careful user-gesture testing and an HTTPS origin outside localhost. Use `docs/device_validation.md` for the current device matrix and run-quality gates.
