# Decouple retained phantoms from MC conditioning prefixes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- replace inverse phantom burn-in configuration with direct `max_phantom_samples`, retaining the generated-chain start-prefix and excluding the final classic replacement
- resolve the `NestedSampler` default retained capacity to `min(model dimension, num_slices - 1)` for both its default sampler and an otherwise unbounded supplied `UniDimSliceSampler`; an explicit low-level capacity takes precedence, while standalone unbounded slice samplers retain every eligible transition
- add `num_phantoms=None` to state/result MC evidence sampling; explicit values physically slice `log_L_phantom[:, :p]` before JIT and classic conditioning remains independent
- migrate repository benchmarks, document collection/storage versus evidence-time computation, and preserve deprecated `phantom_burn_in` with validation and a warning

## Correctness evidence
- new tests cover start-prefix ordering, final-classic exclusion, bounds/deprecation, automatic/custom resolved defaults, conflicting capacities, Python-static integer metadata, Pytree/checkpoint round trips, State/Results forwarding, exact physical-slice equivalence, invalid requests, and classic run/evidence invariance
- `PYTHONPATH=/tmp/[redacted-repo]-[redacted-ref]/src conda run -n [redacted-repo]_py pytest -q cicd/tests`: 310 passed
- post-review sampler/core/reviewer run: 48 passed
- hosted CI: all required jobs passed on Python 3.10 through 3.14
- fatal hosted flake8 gate: 0 findings
- Ruff: all touched Python files pass (the full repository still has unrelated pre-existing findings)

## Performance evidence
The reproducible 8D completed-result benchmark uses N=512 classic samples, G=512 blocks, P=8 retained states, and 256 draws in batches of 64. Public prefix selection is asserted draw-for-draw equal to a physically sliced result.

- p=1: 0.1333 s steady median; 10.41 MB compiler-planned peak
- p=8: 0.1413 s steady median; 13.59 MB compiler-planned peak

The shorter prefix removes 23.4% of compiler-planned peak memory. Runtime ranges overlap, while XLA input/temporary sizes directly confirm the unused suffix is absent from the compiled plan. Full details are in `benchmarks/issue_284/REPORT.md`.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
