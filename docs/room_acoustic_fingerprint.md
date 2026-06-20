# Room Acoustic Fingerprint

ResonanceLab now treats speaker-to-microphone bleed and room reflections as the signal instead of the nuisance. A single chirp capture can produce a repeatable acoustic fingerprint of a space: alignment quality, broad transfer-response coloration, spectrogram texture, decay behavior, and dominant modal peaks.

## What The Fingerprint Shows

- **Chirp response**: the recorded waveform aligned against the emitted logarithmic sweep.
- **Impulse proxy**: a regularized deconvolution or matched-filter view that highlights early direct path and later reflections.
- **Spectrogram**: STFT or mel energy over time, useful for seeing decay texture and frequency-dependent persistence.
- **Decay map**: low, mid, and high frequency bands showing how quickly energy falls after the sweep.
- **Mode candidates**: prominent low/mid-frequency peaks with Q-factor and prominence estimates when the data supports them.
- **Descriptors**: dry/live, dark/bright, echo-prone, noisy, weak alignment, or unstable capture.

## What It Does Not Show

A single speaker and single microphone do not provide an acoustic aperture. The result is not a spatial image, floor plan, object detector, or geometry reconstruction. Phrase outputs as an **acoustic fingerprint of the space**, not as "seeing the room."

## Measurement Guidance

- Keep the device position, orientation, volume, and browser fixed when comparing captures.
- Avoid headphones and earbuds.
- Use the same chirp settings across comparisons.
- Repeat the capture without moving the device to estimate stability.
- Move to a second position only when you explicitly want a different fingerprint of the same room.
- Treat low SNR, weak alignment, and forced browser audio processing as caveats.

## PNG Report Target

The polished export should be a compact visual report:

- Header with timestamp, device/browser metadata, chirp settings, sample rate, and quality flags.
- Waveform strip with detected chirp start and post-chirp decay window.
- Impulse/deconvolution strip with direct-path and reflection markers when available.
- STFT or mel-spectrogram heatmap.
- Decay-band panel for low, mid, and high frequency bands.
- Detected mode table with frequency, prominence, and Q-factor.
- Descriptor row for room character, brightness, SNR, alignment, and caveats.
- Footer that states the single speaker/mic limitation.

The report should be useful for comparison and documentation, not for asserting room geometry.
