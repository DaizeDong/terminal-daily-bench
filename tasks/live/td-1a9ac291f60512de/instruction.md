# ✨ Add regplot equation annotations

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Goal

Make regression equations available directly through `regplot` and simplify the gallery example to demonstrate the public API.

## Changes

- Add the opt-in `add_equation` parameter to annotate fitted equations and R-squared values.
- Support ungrouped, color-mapped, and hue-grouped regressions with opaque, borderless bottom-right annotations.
- Move legends outside the axes when equation annotations would otherwise overlap them.
- Remove the redundant custom correlation-statistics example and update the equation example to use `add_equation=True`.
- Add behavior and public API contract coverage.

## Testing

- `make test` — 432 passed with 100% coverage.
- `make lint` — passed.

## Risks and follow-ups

The feature is opt-in, so existing plots retain their current behavior. No follow-up work is required.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
