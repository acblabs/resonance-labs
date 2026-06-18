# Browser Audio Notes

Phase 1 uses a user-initiated Web Audio flow:

1. Create and resume `AudioContext` from the `Start Probe` button.
2. Request microphone access with echo cancellation, noise suppression, and automatic gain control set to `false`.
3. Capture mono PCM through an AudioWorklet when available.
4. Fall back to ScriptProcessor capture if the worklet cannot be loaded.
5. Encode captured PCM to a browser-side WAV file.
6. Upload the WAV plus probe metadata to FastAPI.

Browsers and operating systems may ignore requested audio constraints. The API response warns when reported track settings show forced processing.

Mobile testing remains manual for Phase 1B. Android Chrome is the first supported mobile target. iOS Safari requires careful user-gesture testing and an HTTPS origin outside localhost.
