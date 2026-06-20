# Device Validation

Use this protocol before trusting room-fingerprint comparisons from a new browser or device class.

## Capture Matrix

Minimum first-pass matrix:

| Target | Origin | Required checks |
| --- | --- | --- |
| Desktop Chrome | `localhost` or HTTPS | AudioWorklet path, sample rate, alignment, SNR, export JSON, export PNG |
| Android Chrome | HTTPS | User gesture, speaker playback, microphone permission, AudioWorklet or ScriptProcessor fallback |
| iOS Safari | HTTPS | Touch gesture unlock, microphone prompt, audible playback, fallback behavior |

## Per-Run Gates

The Lab UI now computes a run-quality summary from the returned analysis:

- Alignment confidence: `>= 0.50` preferred, `>= 0.20` usable.
- SNR: `>= 18 dB` preferred, `>= 12 dB` usable.
- Duration: within `0.90x` to `1.15x` of configured capture time preferred.
- Sample rate: `>= 44.1 kHz` preferred.
- Peak amplitude: between `0.02` and `0.95` preferred.
- Capture path: AudioWorklet preferred; ScriptProcessor is acceptable for fallback validation.
- Browser processing: reported echo cancellation, noise suppression, or auto gain control should stay off.
- Decay fit: RT60 with fit `>= 0.55` is preferred, but weak decay fit is a diagnostic rather than a hard identity claim.

The headline score is an evidence-quality score, not a count of mandatory checks. Required checks carry double the weight of advisory checks; `pass` counts as `1`, `review` as `0.5`, and `fail` as `0`. The status remains the stronger signal: any required failure makes the run `fail`, while advisory failures make it `review`.

Q-factor values above `300` are shown as `Q >300` and should be treated as very narrow peak proxies. They can be caused by clean synthetic tones, device artifacts, browser processing, or room resonances; do not interpret them as calibrated room-mode certainty.

## Session Notes

Record these fields for every validation session:

- device label, browser, operating system, and origin URL
- room label and position label
- playback volume setting
- device orientation and surface
- probe configuration
- three repeated runs without moving the device
- exported JSON reports for reviewed runs

Do not publish private room names, addresses, raw audio, or unreviewed report exports.
