# ✨ Add ROC bands and DeLong

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Goal

Add uncertainty visualization and paired AUC comparisons to rocplot without changing its default output or Axes return type.

## What changed

- Added opt-in 95% stratified bootstrap confidence bands.
- Added paired, two-sided DeLong tests for selected or all prediction pairs.
- Added optional Bonferroni, Holm, FDR-BH, and FDR-BY corrections.
- Added score and comparison validation, focused tests, and documentation.

## Testing

- make test — 506 passed with 100% coverage.
- make lint — all configured hooks passed.

## Risks and follow-ups

- Confidence bands use 1,000 deterministic bootstrap samples and add runtime only when enabled.
- No dependency, migration, or public return-type changes.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
