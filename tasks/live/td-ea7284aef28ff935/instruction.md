# [PERF] reduce peak memory in _build_indexer_reorder_contents

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## PR Description

- Replace `_build_indexer_reorder_contents` double allocation with
  single NumPy allocation using direct row+column offset construction
- Old: `np.arange(length*reps).reshape().ravel('F')` creates temp copy
- New: `np.add(rows, columns).ravel()` constructs output directly

**Benchmark (length=1M, reps=8 → 8M output):**

| Metric | Current | New | Change |
|---|---|---|---|
| Peak memory | 122.07 MiB | 68.79 MiB | **43.6% less** |
| Runtime (median of 15 runs, `timeit`, GC disabled) | 16.41 ms | 16.98 ms | ~3.5% slower, within measurement noise |

This PR is a memory-efficiency optimization. An earlier version of this
description claimed a 1.52x runtime speedup — that number came from a
single untimed cold measurement (`time.time()` around one call) and did
not hold up under repeated, controlled benchmarking. Runtime is
essentially unchanged between the two implementations, possibly
marginally slower, likely since the new path builds the result via
broadcasting rather than a single `arange` + `reshape`. The memory
savings, however, are real, reproducible across multiple scales
(10M×4, 1M×16, 100×100k), and the actual motivation for this change.

**Tests added:**

- Zero length edge case
- Zero reps edge case (defensive coverage; not reachable via the
  public API today, but locked in in case that changes)
- Single rep / single length edge cases
- Row-heavy (1000×2) and column-heavy (2×1000) equivalence
- Peak memory assertion (< 70 MiB)
- End-to-end through `pivot_longer(..., sort_by_appearance=True)`
  with nullable Int64, string, categorical, and datetime columns,
  verifying both values and dtypes survive the reorder

All 101 `test_pivot_longer` tests pass ✅

**This PR [redacted-ref].**

## PR Checklist

- [x] PR in from a fork off your branch.
- [x] Add yourself to `AUTHORS.md`.
- [x] Add a line to `CHANGELOG.md` under the latest version header.

## Relevant Reviewers

@samukweku

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
