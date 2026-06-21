# Room Acoustic Fingerprint

ResonanceLab now treats speaker-to-microphone bleed and room reflections as the signal instead of the nuisance. A single chirp capture can produce a repeatable acoustic fingerprint of a space: alignment quality, broad transfer-response coloration, spectrogram texture, decay behavior, and dominant modal peaks.

## What The Fingerprint Shows

- **Chirp response**: the recorded waveform aligned against the emitted logarithmic sweep.
- **Impulse envelope proxy**: a compact zero-padded regularized deconvolution envelope that highlights early-response structure for controlled comparisons.
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

## PNG Report Contents

The PNG export is a compact visual report:

- Header with timestamp, device/browser metadata, chirp settings, sample rate, and quality flags.
- Mel-spectrogram heatmap.
- Regularized impulse-envelope proxy strip for early-response comparison.
- Transfer-response band panel.
- Low, mid, and high decay-band panel.
- Detected mode table with frequency, prominence, and Q-factor.
- Descriptor row for room character, brightness, SNR, alignment, and caveats.
- Footer that states the single speaker/mic limitation.

Exported JSON reports can also be imported in pairs inside the Lab UI for browser-local metric and transfer-band deltas. The reports should be useful for comparison and documentation, not for asserting room geometry.
