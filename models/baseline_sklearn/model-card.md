# ResonanceLab Phase 4 scikit-learn Baseline

Status: template only. No released model artifact is committed.

## Intended Use

This model-card location is reserved for the first private scikit-learn baseline that predicts fill
level from Phase 2 DSP features. Generated model cards from `scripts/train_baseline.py` overwrite
this file in the artifact output directory.

## Required Evidence Before Release

- Dataset manifest hash and collection protocol.
- Session-held-out same-glass supervised metrics with repeated-holdout mean and standard deviation.
- Cross-glass and cross-device metrics reported separately.
- Comparisons against global mean, global median, nearest canonical bucket, and train-mode bucket references.
- Quality audit for missing alignment confidence, missing SNR, weak alignment, and low-SNR rows.
- Failure modes for direct-path bleed, room response, browser audio processing, low SNR, and weak alignment.
