# ✨ Support Spearman in regplot

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Goal

Allow `regplot` users to report Spearman rank correlation when a monotonic, rank-based association is more appropriate than Pearson correlation.

## What changed

- Add a keyword-only `method` parameter supporting `"pearson"` and `"spearman"`, with Pearson retained as the default.
- Display Spearman coefficients with the rho symbol across standard, hue-grouped, and color-column plots.
- Validate unsupported correlation methods before plotting.
- Add a gallery example and regression tests for the new behavior.

## Testing

- `make test` — 427 tests passed with 100% coverage.
- `make lint` — all hooks passed.
- `MPLBACKEND=Agg uv run python examples/regplot.py` — example completed successfully.

## Risks and follow-ups

Risk is low because existing calls continue to use Pearson correlation by default. The fitted regression line remains linear for either correlation method. No follow-up work is currently required.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
