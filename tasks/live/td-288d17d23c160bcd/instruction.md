# fix(granularity): guard division when subsampling collapses an axis

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

For inputs with an axis shorter than `1/subsample_size`, `new_shape[k]` collapses to 1 and the back-projection upsample divides by `new_shape[k] - 1 == 0`. Added `_safe_ratio` to return 0 in that case (the single output sample along the collapsed axis just reads `back_pixels[0]`), used at all five 2D/3D call sites. Bit-identical behavior whenever `new_shape[k] > 1`.

Tests cover the 2D and 3D paths.

cc @timtreis — this overlaps with the same upsample geometry your fused-operator perf PR rewrites in [redacted-ref]; you may want to fold the guard in when rebasing.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
