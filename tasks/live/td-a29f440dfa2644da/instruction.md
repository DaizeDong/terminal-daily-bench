# Define VJP and JVP for numpy.flip

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`numpy.flip` has no derivative rule registered, so any function that uses it dies at
gradient time:

```python
import [redacted-repo].numpy as np
from [redacted-repo] import grad

grad(lambda x: np.sum(np.flip(x)))(np.array([1.0, 2.0, 3.0]))
# NotImplementedError: VJP of flip wrt argnums (0,) not defined
```

This is inconsistent rather than intentional: `flipud`, `fliplr` and `rot90` — the
other members of the same reversal family, sitting on adjacent lines in
`numpy_vjps.py`/`numpy_jvps.py` — all have rules. `flip` is the general-axis
version of exactly those functions, so it just looks like it was missed.

## The fix

Two lines, registered next to their siblings:

- Reverse mode: `flip` is a permutation of the input, so it is its own adjoint —
  flipping the cotangent back along the same axes gives the gradient.
  Passing `axis` straight through covers all the forms numpy accepts (`None`,
  an int, or a tuple of ints).
- Forward mode: `"same"`, matching `flipud`/`fliplr`/`rot90`, since `flip` is a
  linear reindexing.

I registered the JVP as well as the VJP because `check_grads` exercises both
directions, and leaving forward mode out would have left `flip` half-broken in
the same way.

## Testing

Added `test_flip`, `test_flip_axis` and `test_flip_axis_tuple` to
`tests/test_numpy.py`, directly alongside the existing `test_flipud` /
`test_fliplr` / `test_rot90` and following the same `check_grads` pattern. They
cover the default (all-axes) case, a single named axis, and a tuple of axes on a
3-D array.

All three fail on `master` with `NotImplementedError: JVP of flip wrt argnums
(0,) not defined` and pass with the change.

Full suite on the branch:

```
$ python -m pytest tests/ -q
532 passed, 13 skipped, 37 warnings in 3.39s
```

(The 13 skips are the `xarray`-dependent tests in `test_ufunc_dispatch.py`;
`xarray` isn't installed in my env. Nothing else changed status.)

Linting with the version pinned in `.pre-commit-config.yaml` (ruff 0.15.22):

```
$ ruff check [redacted-repo]/numpy/numpy_vjps.py [redacted-repo]/numpy/numpy_jvps.py tests/test_numpy.py
All checks passed!
$ ruff format --check <same files>
3 files already formatted
```

I also checked the gradient values themselves rather than relying on `check_grads`
alone — comparing against central finite differences for shapes `(5,)`, `(4,5)`
and `(3,4,5)` across `axis=None/0/1/(0,2)` agrees to ~1e-8, and
`flip(x, 0)` / `flip(x, 1)` produce gradients identical to the existing
`flipud` / `fliplr` rules.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
