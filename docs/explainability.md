# Explainability

ResonanceLab explanations are built around deterministic DSP evidence from an active acoustic machine listening workflow. The goal is traceability, not post-hoc approximation.

## Principles

- Explain from structured analysis evidence only.
- Keep raw WAV bytes and PCM samples out of the LLM request path.
- Treat room outputs as acoustic fingerprints, not geometry, object identity, material certainty, or safety claims.
- Prefer exact deterministic references over black-box attribution methods.
- Label sensitivity and uncertainty as proxy diagnostics when they are added; do not turn marginal effects into additive contributions.

## Evidence References

The API uses JSON Pointer references into the compact evidence packet returned by `/api/v1/explain`. Example references include:

- `/quality/alignment_confidence`
- `/quality/snr_db`
- `/dsp/decay/rt60_seconds`
- `/dsp/decay_bands/1/rt60_seconds`
- `/dsp/response_caveats/0/message`

Valid references are derived at runtime by walking leaf values in the actual evidence packet. This avoids a hand-maintained registry drifting away from the packet builder and prevents whole evidence subtrees from being copied into claim metadata.

## Claim Grounding

Legacy explanation fields remain string arrays for compatibility. `summary_claim` and new claim arrays sit beside them, such as `observation_claims` and `acoustic_hypothesis_claims`.

Each claim carries:

- `text`
- `evidence_refs`
- `refs_resolved`
- `grounding_status`
- `grounding_reason`
- `authoritative_values`

Deterministic claims are constructed with known references and marked with `grounding_status="deterministic_rule"` when their refs resolve. LLM claims must cite valid leaf JSON Pointer refs; unresolvable claims or container refs are logged and dropped from the compatible string views in favor of deterministic fallback text. The server resolves authoritative values from the packet instead of trusting LLM-restated numbers.

Hosted Gemini calls request JSON with a single top-level object and claim objects that contain only `text` plus `evidence_refs`; the API computes all grounding metadata after the response is received.

The `refs_resolved` flag means the cited evidence paths exist and point to leaf values. It does not claim semantic proof that free-form text matches those values.

Deterministic guidance sections such as troubleshooting, caveats, evidence critique, and next-measurement text may intentionally have empty claim arrays. That means the section is advisory prose without precise per-sentence provenance, not that grounding failed.

## Decision Explanations

Run-quality validation checks include status, target, score weighting, and counterfactual text. Numeric checks expose the margin required to reach the preferred threshold. Categorical checks describe the minimal operational change, such as using AudioWorklet capture or disabling browser processing.

Room-character and brightness labels use a single frontend descriptor path shared by the Lab UI and report builder. Counterfactual descriptor text explains the nearest threshold, for example the RT60 value that would move a label from balanced to live.

Descriptor thresholds are contract-tested between the backend explanation summary and frontend report helpers: dry below `0.25 s`, live above `0.75 s`, dark below `1200 Hz`, and bright above `3500 Hz`.

## Future Sensitivity Work

Signal-perturbation sensitivity should remain on demand because it requires rerunning the DSP pipeline. Raw audio may be re-uploaded to a DSP sensitivity endpoint, but it must still not be sent to the LLM path. Sensitivity results should report one-at-a-time, non-additive effects and separate alignment drift from descriptor changes.
