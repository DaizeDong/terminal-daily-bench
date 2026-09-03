# feat(state-space): support quasi-periodic Periodic x Matern product SDEs

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Checklist

- [x] I've formatted the new code by running `uv run poe format` before committing.
- [x] I've added tests for new code.
- [x] I've added docstrings for the new code.

## Description

The state-space SDE registry rejected all `ProductKernel`s outright, citing Kronecker state-dimension blowup — blocking the canonical quasi-periodic kernel `TruncatedPeriodic × Matérn` (Solin & Särkkä 2014 §3), whose state dimension is only `(2K+1)·d`, much smaller than the general worst case. The module's own Mauna Loa example substitutes a sum as a documented workaround.

Adds a product-SDE construction specifically for the Periodic × stationary-Matérn case via the Kronecker of the two factor state-space models; keeps the explicit rejection for genuinely unsupported product combinations.

Addresses [redacted-ref].

## Test plan

- `uv run pytest tests/test_state_space/` — 319 passed, 1 skipped (pre-existing, unrelated)
- New tests cover the product-SDE construction and its equivalence to a dense-kernel GP with the same product kernel
- `uv run poe lint` — clean

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
