# feat: add split-conformal prediction intervals

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
Replaces the heuristic `expected_error_eur` with statistically grounded
split-conformal prediction intervals derived from holdout residuals.

## Changes
- `config.py`: `PREDICTION_INTERVAL_COVERAGE` (default 0.80).
- `train_regression.py`: conformal half-width from holdout residuals; interval
  block in `metrics.json` (with empirical coverage) and in model metadata.
- `score_new_sites.py`: emits `prediction_low_eur`, `prediction_high_eur`,
  `interval_coverage`, `interval_half_width_eur`; `_risk_band` now returns
  (band, distance) and is documented as an extrapolation signal.
- Tests updated for the new `_risk_band` signature; added interval tests and
  interval assertions in the training smoke test.
- README: new "Prediction Intervals" section, updated Model Output and metrics.

## Verification
- ruff / black / mypy clean; 17 tests pass.
- 80% interval: ±€588.89, empirical holdout coverage 81.[redacted-ref]%.
- Point predictions and headline metrics unchanged (R² 0.647, MAE 383.58).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
