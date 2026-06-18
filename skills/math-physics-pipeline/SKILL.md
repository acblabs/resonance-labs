---
name: math-physics-pipeline
description: |
  Specializes in digital signal processing (DSP), acoustic resonance modeling, calibration algorithms, and ML validation design for the ResonanceLab pipeline.
  Use when writing digital signal processing (DSP) logic, acoustic calculations, deconvolution, matched filtering, or designing calibration/evaluation pipelines.
license: Apache-2.0
metadata:
  version: v1
  publisher: google
---

# Math & Physics Pipeline Skill

This skill governs the mathematical, physical, and DSP implementations of the **ResonanceLab** acoustic pipeline. It outlines how physical interactions (sweeps, taps, chirps) map to digital features and calibration profiles.

For project context, repository layout details, and phase gates, refer to the [implementaion_plan.md](file:///c:/Users/pcaccount/.gemini/antigravity-ide/scratch/resonance-labs/implementaion_plan.md).

---

## 1. Physics of Acoustic Resonance

### 1.1 Structural Vibrations & Mass-Loading
*   **Object Resonance**: Everyday objects (like glass or plastic vessels) act as acoustic resonators. The structural resonant frequencies depend on geometry, material stiffness, wall thickness, and liquid volume.
*   **Mass-Loading Effect**: When liquid is added to a vessel:
    *   The total effective mass of the oscillating system increases.
    *   The stiffness of the walls is perturbed.
    *   Typically, the primary resonant peak ($f_0$) shifts **downward** as fill level increases.

### 1.2 Co-Equal Excitation Modes (Feasibility Phase)
*   **Active Chirp (Airborne)**: Emitting a continuous sweep of known frequencies to couple acoustic energy into the vessel. **Critical Risk:** Direct speaker-to-microphone bleed and room reflections can easily dominate the weaker object response. Chirp viability must be validated side-by-side with tapping during the initial spike.
*   **Tap / Impulse**: Exciting the structure via physical impact (e.g., spoon tap). Generates a transient impulse response with a broad-spectrum excitation. Tap-based excitation provides clean ring-down decay features without speaker-to-microphone bleed.

---

## 2. DSP Pipeline Mathematics

### 2.1 Excitation and Signal Processing

#### A. Active Chirp: Logarithmic Sweep & Matched Filtering
*   **Logarithmic Chirp Formula**:
    $$x(t) = A \sin \left( 2\pi f_0 \frac{k^t - 1}{\ln k} \right)$$
    where $k = (f_1 / f_0)^{1/T}$, $f_0$ is start frequency, $f_1$ is end frequency, and $T$ is duration.
*   **Matched Filtering & Pulse Compression**:
    Cross-correlation is utilized not only for time alignment but as a matched filter to recover the system's impulse response:
    $$h_{\text{est}}(t) = y(t) * x(-t)$$
    By compressing the chirp sweep into a narrow pulse, we can temporally separate the early direct-path speaker bleed from the delayed, reflected object resonance.

#### B. Tap/Impulse: Transient Ring-down Analysis
*   **Transient Segmentation**: Isolate the high-amplitude strike peak and extract the subsequent ring-down decay window.
*   **Decay Fitting**: Estimate damping parameters from the free vibration decay curve using Hilbert transform envelopes.

### 2.2 Spectral Estimation & Sub-Bin Peak Detection
*   **Downsampling Policy**: Keep the native capture sample rate (typically 44.1 kHz or 48.0 kHz) to preserve high-frequency resonance details. Do not downsample unless explicitly validated and authorized.
*   **Windowing**: Apply a Hann or Hamming window to the post-chirp or tap impulse segments to minimize spectral leakage before computing the Fast Fourier Transform (FFT).
*   **Sub-bin Peak Interpolation**: To estimate peak frequencies with precision exceeding the FFT bin width $\Delta f$, perform quadratic interpolation on the log-magnitude spectrum $|Y(f)|$:
    $$\delta = \frac{1}{2} \frac{\alpha - \gamma}{\alpha - 2\beta + \gamma}$$
    where $\beta$ is the log-magnitude of the peak bin, and $\alpha, \gamma$ are the log-magnitudes of the adjacent bins. The interpolated frequency is $f_{\text{peak}} = (k_{\text{peak}} + \delta) \Delta f$.

### 2.3 Decay and Damping Estimation
*   **Q-Factor**: Calculate the Quality Factor $Q$ of isolated resonance peaks to capture damping properties:
    $$Q = \frac{f_0}{\Delta f_{3\text{dB}}}$$
    where $\Delta f_{3\text{dB}}$ is the bandwidth at which the power drops to half of the peak value.
*   **Envelope Fitting**: Fit an exponential decay curve to the rectified Hilbert transform envelope of the post-excitation signal:
    $$A(t) = A_0 e^{-\alpha t}$$
    where $\alpha$ is the damping coefficient.

---

## 3. Calibration & Reference Subtraction (Experimental)

### 3.1 Bleed Mitigation (Unsettled / Under Feasibility Spike)
**IMPORTANT:** Simple magnitude subtraction ($|Y(f)| - |P_{\text{air}}(f)|$) is acoustically crude. Direct bleed and object response are complex signals that sum as vectors with phase. Subtracting magnitudes will over- or under-cancel badly, especially when bleed dominates.
Instead, treat bleed cancellation as an experimental task exploring:
1.  **Complex Transfer-Function Division (Deconvolution)**: Dividing in the frequency domain with regularization to avoid dividing by zeroes.
2.  **Log-ratio / Decibel Subtraction**: Analyzing ratios rather than absolute differences.
3.  **Temporal Windowing**: Rejecting the direct-path arrival window via impulse response gating (pulse compression).
*Observe strict clamping, phase constraints, and noise floor checks during evaluation.*

### 3.2 Anchor-Based Calibration
*   **Anchor Interpolation**: Relative fill level is computed by mapping extracted peak shifts and energy values between three local anchor states: `Empty`, `50%`, and `Full`.
*   **Algorithm**: Use piecewise linear interpolation or Euclidean distance in the multi-dimensional feature space of the calibration anchors to produce the relative fill estimation.

---

## 4. Feature Inventory & Pipeline Validation

### 4.1 Core Feature Vector
For each probe, extract and report:
*   Dominant resonance peaks ($f_{\text{peak}}$ and amplitude).
*   Quality factors ($Q$) and decay coefficients ($\alpha$).
*   Spectral shape descriptors: Centroid, Rolloff, Bandwidth, and Flux.
*   Transfer-response magnitude across configured frequency bands.
*   Mel-Spectrogram matrices and Mel-Frequency Cepstral Coefficients (MFCCs).
*   Root-Mean-Square (RMS) envelope statistics.
*   Alignment correlation strength and Signal-to-Noise Ratio (SNR).

### 4.2 Fail Gates & Uncertainty Handling
**IMPORTANT:** The pipeline must report high uncertainty or raise warning errors rather than outputting a forced fill estimate if any of the following conditions are met:
1.  **Low SNR**: Peak signal level is less than 12 dB above the pre-roll noise floor.
2.  **Weak Alignment**: Cross-correlation alignment coefficient is below a defined threshold (indicates distorted or missing chirp).
3.  **Bypassed Constraints**: Device properties show that AGC, echo cancellation, or noise suppression were forced active by the OS.
4.  **Signal Mismatch**: Disagreement between chirp and tap frequency peaks during mixed calibration testing.

### 4.3 Validation and Golden Tests
*   **Data Leakage Prevention**: Split training/eval datasets strictly by recording session, device, and individual object. Do not use random sample-level splitting.
*   **Golden Test Float Tolerances**: Ensure tests comparing DSP output fixtures utilize float assertions with specific tolerances (e.g., `pytest.approx(expected, rel=1e-5)`) to accommodate minor platform-specific floating-point arithmetic differences.
