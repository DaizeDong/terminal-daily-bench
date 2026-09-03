# Fix Box.sample never returning values near signed integer dtype limits

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

# Description

`Box.sample()` clips integer samples to the dtype's range before casting, but for every signed integer dtype it applied a `[dtype_min + 2, dtype_max - 2]` margin (introduced in [redacted-ref]). That margin only guards against float64's inexact representation of the **int64** limits — the same reason [redacted-ref] added the int64-specific re-clip after the cast — while the int8/int16/int32 limits are exactly representable in float64. The margin therefore only truncated the sampled support:

```python
import numpy as np
from [redacted-repo].spaces import Box

space = Box(low=125, high=127, dtype=np.int8)
print([space.contains(np.array([v])) for v in (125, 126, 127)])
# [True, True, True]
space.seed(0)
print({int(v) for _ in range(3000) for v in space.sample()})
# {125} — 126 and 127 can never be sampled
```

A full-range `Box(-128, 127, dtype=np.int8)` can never sample `-128`, `-127`, `126` or `127` (only 252 of 256 values are reachable), while unsigned dtypes were exempt from the margin, so `Box(253, 255, dtype=np.uint8)` samples all three values — the asymmetry suggests an oversight rather than a distribution choice.

This restricts the margin to `np.int64`, mirroring the existing `if self.dtype == np.int64:` special case directly below it, so int64 behaviour is unchanged. Adds a parametrised regression test asserting that a bounded integer Box samples every value in `[low, high]` for int8/int16/int32, with uint8 as a control.

This restores the documented contract (docstring: "`[a, b]`: uniform distribution") and the invariant `test_valid_low_high` already asserts via `space.contains(sample)`; its parameter list just never used bounds near a signed dtype's limits.

## Type of change

- [x] Bug fix (non-breaking change which fixes an issue)

# Checklist:

- [x] I have run the [`pre-commit` checks]([redacted-url]) with `pre-commit run --all-files` (see `CONTRIBUTING.md` instructions to set it up)
- [x] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [x] My changes generate no new warnings
- [x] I have added tests that prove my fix is effective or that my feature works
- [x] New and existing unit tests pass locally with my changes

Note: in my environment the `ty` hook reports the same 353 pre-existing diagnostics on unmodified `main` (missing optional dependencies); this diff adds no new `ty` diagnostics. ruff, ruff-format and pydocstyle pass.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
