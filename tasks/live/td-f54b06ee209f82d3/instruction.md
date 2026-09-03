# ✨ Add ridgeplot hue and overlap

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Goal

Make ridgeplot overlap configurable and support overlaid hue distributions with Matplotlib styling passthrough.

## What changed

- Added keyword-only hue and overlap parameters while preserving the existing default rendering.
- Overlaid observed hue groups at each ridge offset with consistent colors and a legend.
- Forwarded additional styling keywords to Axes.fill_between with caller values taking precedence.
- Added validation, regression coverage, and a gallery example.

## Testing

- make test: 533 passed with 100% coverage.
- make lint: passed.
- MPLBACKEND=Agg uv run python examples/ridgeplot.py: passed.

## Risks and follow-ups

The new parameters are keyword-only, so existing positional calls remain compatible. Each observed hue subset must contain at least two varying values for KDE estimation. No follow-up work is required.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
