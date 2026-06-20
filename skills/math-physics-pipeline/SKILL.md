---
name: math-physics-pipeline
description: |
  Specializes in digital signal processing (DSP), acoustic measurement, deconvolution, matched filtering, room-response features, and validation design for the ResonanceLab pipeline.
  Use when writing DSP logic, acoustic calculations, chirp processing, decay estimation, or room-fingerprint evaluation.
license: MIT
metadata:
  version: v1
  publisher: resonance-labs
---

# Math & Physics Pipeline Skill

This skill governs the mathematical, physical, and DSP implementations of the **ResonanceLab** acoustic pipeline. It outlines how chirps map to room acoustic fingerprints and visual reports.

For project context and repository layout details, refer to the root README, FEATURES, and docs directory.

---

## 1. Physics Scope

*   **Room Fingerprint**: A chirp emitted by the device speaker and recorded by the microphone captures direct path, reflections, modal coloration, decay texture, and device/browser response.
*   **Single Mic Limitation**: One speaker and one microphone do not provide an aperture. Do not infer room geometry, floor plans, or spatial maps.
*   **Repeatability First**: Comparisons are meaningful only when device, browser, chirp settings, volume, and position are controlled.

---

## 2. DSP Pipeline Mathematics

### 2.1 Active Chirp: Logarithmic Sweep & Matched Filtering

*   **Logarithmic Chirp Formula**:
    $$x(t) = A \sin \left( 2\pi f_0 \frac{k^t - 1}{\ln k} \right)$$
    where $k = (f_1 / f_0)^{1/T}$, $f_0$ is start frequency, $f_1$ is end frequency, and $T$ is duration.
*   **Matched Filtering**: Use cross-correlation with the emitted sweep for time alignment and impulse-like response views.
*   **Deconvolution**: Use regularized complex frequency-domain division when estimating transfer or impulse proxies. Keep the regularization value visible in code/tests and avoid division by tiny reference bins.

### 2.2 Spectral Estimation & Sub-Bin Peak Detection

*   **Native Sample Rate**: Preserve the capture sample rate unless downsampling is explicitly validated.
*   **Windowing**: Apply Hann-style windows before spectral estimates when leakage matters.
*   **FFT-domain Filtering**: Zero-pad before frequency masking and crop back to the original interval.
*   **Peak Interpolation**: Estimate peak frequencies with quadratic interpolation on log-magnitude or dB spectra:
    $$\delta = \frac{1}{2} \frac{\alpha - \gamma}{\alpha - 2\beta + \gamma}$$
    where $\beta$ is the peak-bin dB value and $\alpha, \gamma$ are adjacent-bin dB values.

### 2.3 Decay and Damping Estimation

*   **Q-Factor**:
    $$Q = \frac{f_0}{\Delta f_{3\text{dB}}}$$
    where $\Delta f_{3\text{dB}}$ is the half-power bandwidth. Interpolate half-power crossings; do not regress to integer-bin bandwidths.
*   **Envelope Fitting**: Fit log RMS-envelope decay over a validated post-chirp window. Treat weighted fit quality as a diagnostic, not a proof of room identity.
*   **Noise Floor Handling**: Estimate SNR from pre-roll audio that ends before the expected and detected chirp starts.

---

## 3. Room Fingerprint Feature Inventory

For each probe, extract and report:

*   Alignment confidence and detected chirp start.
*   Signal-to-noise ratio.
*   Spectral centroid, bandwidth, rolloff, and floor.
*   Transfer-response magnitude across configured bands.
*   STFT and mel-spectrogram grids.
*   Dominant peak frequencies, prominence, and Q-factor.
*   RMS-envelope decay rate, RT60 proxy, and fit quality.
*   Caveats for low SNR, weak alignment, forced browser processing, or unstable decay.

---

## 4. Validation Rules

*   **No Forced Claims**: Report uncertainty rather than forcing a descriptor when SNR, alignment, or decay fit quality is weak.
*   **Golden Tests**: Preserve tests for matched-filter alignment, FFT-domain bandpass attenuation, spectrogram dimensions, dominant peak detection, decay-fit edge cases, and the committed recorded-style WAV fixture.
*   **Analytic Checks**: Maintain at least one closed-form damped-sinusoid regression test for peak frequency and exponential decay-rate recovery.
*   **Real Fixtures**: Add small real room recordings only with metadata, tolerances, and clear caveats.
*   **LLM Boundary**: A lab-assistant model may explain compact structured DSP summaries, but raw WAV and full high-dimensional grids must not be sent to the hosted path by default.
