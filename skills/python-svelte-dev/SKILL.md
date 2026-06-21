---
name: python-svelte-dev
description: |
  Specializes in senior-level Python (FastAPI, NumPy, Pydantic) and Svelte (SvelteKit, Web Audio API, Canvas) development for the ResonanceLab room-fingerprint platform.
  Use when building SvelteKit routes, FastAPI endpoints, Web Audio/AudioWorklet capture, acoustic visualizations, or frontend/backend integration code.
license: MIT
metadata:
  version: v1
  publisher: resonance-labs
---

# Senior Python & Svelte Developer Skill

This skill governs the frontend and backend architecture of the **ResonanceLab** platform, emphasizing robust browser audio capture, deterministic DSP responses, and a premium lab-style interface.

For project context and repository layout details, refer to the root README, FEATURES, and docs directory.

---

## 1. SvelteKit & Frontend Architecture Guidelines

### 1.1 Web Audio API & AudioWorklet PCM Capture

*   **AudioContext User Gesture Unlock**: Always instantiate and unlock the `AudioContext` inside a direct user interaction event listener.
*   **AudioWorklet Integration**: Prefer a custom `AudioWorkletProcessor` for raw PCM capture. Fall back to `ScriptProcessorNode` only when the worklet cannot load.
*   **iOS Safari Caveats**: iOS devices aggressively silence playback and capture unless initiated via an explicit touch gesture.
*   **Audio Constraints & Device Quirks**: Request `echoCancellation`, `noiseSuppression`, and `autoGainControl` as `false`, then inspect reported settings because browsers may ignore these flags.

### 1.2 SSR Pitfalls & Client-Only Code

*   **SSR Safety**: Web Audio, media devices, and storage APIs do not exist during SSR. Browser-specific code belongs in `onMount` or behind `$app/environment` `browser` guards.
*   **Target Routing Layout**:
    *   `/lab`: Main room acoustic fingerprint workflow.
    *   `/physics`: Future deeper explorer for FFT, spectrogram, impulse-envelope proxy, and decay analysis.

### 1.3 UI/UX Design System Principles

*   **Styling Philosophy**: Use a clean lab-style UI optimized for signal and spectrogram visualization.
*   **No Static Signal Placeholders**: Render waveforms and spectrograms dynamically with Canvas.
*   **Room Fingerprint First**: Show the usable measurement experience immediately; do not turn the app into a marketing landing page.
*   **Report Export**: Keep JSON and PNG acoustic reports based on derived analysis data. Do not include raw WAV bytes or PCM samples in report exports.
*   **Report Comparison**: Compare exported JSON reports locally in the browser. Surface metric deltas, transfer-band deltas, and capture-condition caveats before encouraging fixture publication.
*   **Honest Wording**: Describe outputs as acoustic fingerprints and reports, not spatial images or geometry reconstruction.

### 1.4 State Management & Safety Guardrails

*   **Local State**: Keep transient probe state in Svelte component state. Store durable derived reports only when the user explicitly asks for export.
*   **Run Validation**: Surface alignment, SNR, duration, sample-rate, peak-amplitude, capture-path, browser-processing, decay-fit checks, and band-limited decay diagnostics as quality signals.
*   **Download Robustness**: Defer object URL cleanup after report download clicks so large PNG exports are not cancelled by strict browsers.
*   **LLM Explanation Boundary**: Explanations must call `/api/v1/explain` with compact analysis JSON only, including any experiment design, physics tutoring, troubleshooting, or evidence critique text. Do not upload the WAV blob to an LLM provider. Keep hosted calls disabled by default and use Cloud Run service identity/IAM for Vertex Gemini instead of API keys.
*   **Acoustic Safety**: Cap the amplitude multiplier to `0.35` by default, keep chirps short, fade the signal, and keep the no-headphones warning visible.

---

## 2. Python & FastAPI Backend Guidelines

### 2.1 Target Repository Layout

*   `services/api/app/api/`: FastAPI controller and router code.
*   `packages/resonancelab/`: Core audio and DSP helpers.
*   Keep API routes light; reusable DSP belongs in packages so tests and future reports can call it directly.
*   Use Pydantic v2 schemas for request/response validation and explicit upload limits.

### 2.2 Performance & Memory Guardrails

*   **DSP Optimization**: Use vectorized NumPy. Keep Librosa, PyTorch, and other heavy libraries out of the primary API container unless a future feature truly needs them.
*   **Audio Decoding**: Prefer PCM WAV decoding through the package helper. Lossy browser formats should remain fallback work, not default behavior.
*   **Report Export Boundary**: PNG/JSON acoustic report generation should use derived DSP grids and metadata. It should not store raw audio by default.

---

## 3. Testing & Validation

*   **Frontend Test Patterns**: Test chirp generation, WAV encoding, audio state transitions, and rendering helpers with mocked browser APIs.
*   **Golden Audio Fixtures**: Preserve deterministic generated fixtures and add small real room fixtures with tolerant assertions when available. Prefer reviewed JSON report fixtures and local comparison before publishing.
*   **API Tests**: Keep `/api/v1/analyze` and `/api/v1/explain` schema tests grounded in compact DSP evidence.

---

## 4. Best Practices Checklist

| Action | Recommended Practice | Prohibited Practice |
| :--- | :--- | :--- |
| **Dependency Management** | Use venv + `requirements.txt` / `requirements-dev.txt` in the root. | Running global `pip install` or introducing unapproved managers. |
| **Docker Workspaces** | Copy workspace package sources into their package paths before running workspace scripts in container builds. | Flattening a workspace package into the container root before running `npm --workspace`. |
| **Audio Capture** | AudioWorklet PCM to browser-side WAV encoding. | MediaRecorder WebM/Opus by default. |
| **UI Aesthetics** | Clean lab-style layout, canvas rendering, dark visualization mode. | Raw unstyled inputs, static image placeholders, or unsupported claims in visible UI. |
| **LLM Calls** | Compact structured DSP JSON only. | Sending raw WAV bytes or high-dimensional grids to hosted models. |
