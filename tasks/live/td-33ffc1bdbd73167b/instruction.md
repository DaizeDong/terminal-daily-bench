# fix: `IntervalEncoder` average-method window predicate (`OR` should be `AND`)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`IntervalEncoder(method="average")` never applies the lower bound of its averaging window. In `_mk_average` the predicate is:

```python
predicate = (xs < (interval + span)) | (xs < (interval - span))
```

Since `interval - span < interval + span` always, the second condition is a subset of the first, so the OR collapses to just `xs < (interval + span)`: there is no lower bound. Every point below the interval (however far) leaks into the weighted average, which biases the smoothed height low.

The docstring describes `span` as "the span around the interval" (a symmetric, two-sided window), and the sibling `method="normal"` uses all points weighted by a Gaussian, so `average` is meant to be the hard-windowed version of the same idea. The fix uses AND:

```python
predicate = (xs < (interval + span)) & (xs > (interval - span))
```

Repro with a linear target `y = 2x` (the smoothed height at each quantile should track `2 * quantile`):

```python
import numpy as np
from sklego.preprocessing import IntervalEncoder

np.random.seed(0)
x = np.random.uniform(0, 10, 2000)
ie = IntervalEncoder(n_chunks=5, span=0.1, method="average").fit(x.reshape(-1, 1), 2 * x)
print(ie.heights_)   # before: biased low (~17.5 at the top quantile near 10); after: ~20
```

Added a regression test. The existing `method="average"` test only used a constant target, which cannot detect the bias (averaging any subset of a constant array still gives that constant).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
