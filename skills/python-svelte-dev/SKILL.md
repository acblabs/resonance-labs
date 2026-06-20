---
name: python-svelte-dev
description: |
  Specializes in senior-level Python (FastAPI, NumPy/SciPy, Pydantic) and Svelte (SvelteKit, Web Audio API, IndexedDB) development for the ResonanceLab platform.
  Use when building SvelteKit routes, FastAPI endpoints, Web Audio/AudioWorklet capture, IndexedDB profiles, or writing frontend/backend integration code.
license: Apache-2.0
metadata:
  version: v1
  publisher: google
---

# Senior Python & Svelte Developer Skill

This skill governs the development of the frontend and backend architectures of the **ResonanceLab** platform, emphasizing high-performance, robust client-side audio capture, and a premium lab-style interface.

For project context, repository layout details, and phase gates, refer to the [implementation_plan.md](file:///c:/Users/pcaccount/.gemini/antigravity-ide/scratch/resonance-labs/implementation_plan.md).

---

## 1. SvelteKit & Frontend Architecture Guidelines

### 1.1 Web Audio API & AudioWorklet PCM Capture
*   **AudioContext User Gesture Unlock**: Always instantiate and unlock the `AudioContext` inside a direct user interaction event listener (e.g., `click`). Display clear prompts if the audio state is suspended.
*   **AudioWorklet Integration**: To capture raw PCM audio without blocking the UI thread, implement a custom `AudioWorkletProcessor`. Stream or buffer PCM float values in real-time, falling back to Web Audio `ScriptProcessorNode` or `MediaRecorder` only when necessary.
*   **iOS Safari Caveats**: iOS devices aggressively silence playback and capture unless initiated via an explicit touch gesture on a button. Ensure the gesture handler runs synchronously with the `AudioContext.resume()` call.
*   **Audio Constraints & Device Quirks**: Explicitly disable automatic gain control (AGC), echo cancellation, and noise suppression:
    ```javascript
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      }
    });
    ```
    *Note:* Be prepared for some browsers/devices to ignore these flags; the application must detect and flag device-level sample-rate variability (e.g., 44.1 kHz vs 48 kHz) by inspecting `AudioContext.sampleRate`.

### 1.2 SSR Pitfalls & Client-Only Code
*   **SSR Safety**: Web Audio, media devices, and storage APIs (`window`, `navigator`, `localStorage`, `IndexedDB`) do not exist during Server-Side Rendering (SSR). All audio capture, playback, and profile components must be loaded client-side only. Wrap browser-specific imports and calls in Svelte's `onMount` or guard them using:
    ```javascript
    import { browser } from '$app/environment';
    if (browser) {
      // safe to use window, AudioContext, etc.
    }
    ```
*   **Target Routing Layout**: SvelteKit routes under `apps/web/src/routes/` are planned as follows:
    *   `/lab`: Main interface for running active acoustic tests and visualization.
    *   `/calibrate`: Profiling wizard for recording empty, 50%, and full anchor points.
    *   `/physics`: Spectrogram, FFT, resonance frequency, and decay analysis explorer.

### 1.3 UI/UX Design System Principles
*   **Styling Philosophy**: Avoid hardcoding hyper-specific palettes (e.g., "deep purples/teals") or exact fonts to maintain design flexibility. Instead, follow a **premium lab-style UI** adhering to:
    *   Dark, high-contrast layouts optimized for signal/spectrogram visualization.
    *   Accessible contrast ratios and support for OS-level reduced motion preferences.
    *   Mobile-first, touch-friendly controls with responsive grids.
    *   **No Placeholders**: Do not use static mock images for waveforms. Render signals dynamically in real-time using HTML5 Canvas or high-performance SVG.
    *   Ensure styling is clean and intentional; do not rely blindly on Tailwind defaults.

### 1.4 State Management, IndexedDB, & Safety Guardrails
*   **Local Calibration Profiles**: Persist calibration anchors and profiles locally in IndexedDB to avoid server-side state.
*   **Storage Etiquette**: Store derived DSP features by default. Request explicit user opt-in before storing raw audio blobs to prevent quota exhaustion.
*   **Calibration Actions**: Anchor controls should use explicit command labels such as "Save Empty" or "Save Full" rather than relying on status-only anchor cards, and every save target needs a clear/reset path for accidental captures.
*   **Free-Air Controls**: Treat a close match to the saved free-air reference as a no-glass/reference-match result, not as a nearest-glass-anchor fill estimate.
*   **Dataset Capture Form State**: Browser `type="number"` fields can bind as numbers rather than strings in Svelte. Dataset capture helpers must tolerate `string | number | null | undefined` for fill percent and optional mass fields so valid zero-valued labels do not disable capture saves.
*   **Acoustic Safety**: Protect users and equipment by enforcing:
    *   Volume limits (e.g., capping the amplitude multiplier to `0.35` by default).
    *   Short probe durations (e.g., maximum chirp/sweep duration of 500-1000ms).
    *   Prominent warning banners advising users **not** to use headphones or earbuds during active acoustic probing.

---

## 2. Python & FastAPI Backend Guidelines

### 2.1 Target Repository Layout
*   **Code Monorepo Organization**: The target codebase separates components as follows:
    *   `services/api/app/api/`: FastAPI controller and router code.
    *   `packages/resonancelab/`: Core, independent DSP, features, and model libraries.
    *   Keep logic strictly separated: the API routes should act as light wrappers around package functions to facilitate offline scripts, notebook usage, and CLI testing.
*   **Pydantic Schema Validation**: Use Pydantic v2 schemas for all request validation, including strict checks and custom validation for sample rates, signal types, and duration parameters.

### 2.2 Performance & Memory Guardrails
*   **Model Caching**: Load machine learning models (e.g., XGBoost, scikit-learn) once at startup and cache them in process memory. Never reload models on a per-request basis.
*   **DSP Optimization**: Optimize DSP functions utilizing vectorized NumPy/SciPy operations. Minimize the import footprint of heavy libraries like Librosa or PyTorch in the primary API container to control cold-start latency.
*   **Audio Decoding**: Rely on fast binary decoding (such as `soundfile` or `scipy.io.wavfile`). Support lossy fallback formats via standard subprocess decoding only if ffmpeg is available.
*   **Phase 4 ML Boundary**: Keep scikit-learn training and artifact export in offline package/script paths (`packages/resonancelab/ml`, `scripts/train_baseline.py`, `scripts/run_phase4_benchmark.py`). Do not load a Phase 4 model in the API until compiled benchmark reports and a model card justify serving. Treat checked-in manifests as public-safe schema examples unless they contain enough groups and feature paths to train.

---

## 3. Testing & Validation

*   **Frontend Test Patterns**: Implement unit tests for audio recorders, WAV encoders, and utility modules using mocked `AudioContext` and mock audio buffers.
*   **Golden Audio Fixtures**: Store reference/golden WAV files representing various fill states and speaker-to-mic scenarios to validate both frontend encoding and backend decoding against baseline values.

---

## 4. Best Practices Checklist

| Action | Recommended Practice | Prohibited Practice |
| :--- | :--- | :--- |
| **Dependency Management** | Use venv + `requirements.txt` / `requirements-dev.txt` in the root. | Running global `pip install` or introducing unapproved managers. |
| **Docker Workspaces** | Copy workspace package sources into their package paths, such as `apps/web`, before running workspace scripts in container builds. | Flattening a workspace package into the container root before running `npm --workspace`. |
| **Audio Capture** | AudioWorklet PCM -> browser-side WAV encoding. | MediaRecorder WebM/Opus by default (lossy). |
| **ML Inference** | Ephemeral processing with scikit-learn/XGBoost baselines. | Heavy deep learning models in Phase 1 API images. |
| **Phase 4 Training** | Use `requirements-ml.txt`, private manifests, leakage-aware group splits, and generated model cards. | Committing private raw audio or evaluating with random probe-level splits. |
| **UI Aesthetics** | Clean lab-style layout, canvas rendering, dark visualization mode. | Raw unstyled inputs, static image placeholders, Tailwind defaults. |
