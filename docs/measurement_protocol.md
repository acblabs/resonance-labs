# Measurement Protocol

ResonanceLab measures room acoustic fingerprints from active chirp captures. This places the project under machine listening, specifically active acoustic machine listening: a known sound is emitted, the response is recorded, and deterministic DSP evidence is derived from what the system hears. The API returns spectral, transfer-response, response-trace, decay, caveat, and quality features; it does not make calibrated physical-property predictions.

For early manual tests:

- Use speakers, not headphones or earbuds.
- Keep device placement fixed across repeated runs.
- Record the device, browser, room/setup label, and volume setting.
- Run at least three repeated probes before trusting a descriptor.
- Keep the probe geometry fixed: same device orientation, same surface, same height, and same room position.
- Treat browser sample-rate changes as a new capture condition.
- Treat alignment confidence below `0.20` or SNR below `12 dB` as a low-confidence measurement.
- Prefer exported JSON reports for reviewed validation records; they contain derived DSP evidence without raw WAV bytes.
- Keep at least `100 ms` of usable post-chirp audio for decay fitting. The default `1000 ms` post-roll is preferred because RT60 and peak estimates become fragile with short windows.

Repeat checks should stay within a controlled setup:

- Same device and browser.
- Same chirp settings.
- Same playback volume.
- Same room setup and device placement.

Any LLM explanation should consume structured DSP evidence only, not raw audio. The explanation layer should distinguish measured observations from acoustic hypotheses and caveats.
