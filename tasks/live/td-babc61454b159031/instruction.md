# Fix argument order in scale_size_datetime.__post_init__

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Summary

`scale_size_datetime` is a `@dataclass` subclass of `scale_datetime`, so the generated `__init__` passes the `InitVar` pseudo-fields to `__post_init__` **positionally, in field order** — base class first: `(date_breaks, date_labels, date_minor_breaks, range)`.

But `__post_init__` declares them in a different order:

```python
def __post_init__(
    self, range, date_breaks, date_labels, date_minor_breaks   # transposed
):
    ...
    self.palette = area_pal(range)
```

So `range` receives the `date_breaks` value, `date_breaks` receives `date_labels`, etc. — every argument is misrouted.

### Reproduce

```python
from [redacted-repo].scales.scale_size import scale_size_datetime

s = scale_size_datetime(range=(2, 10))
s.palette([0, 0.5, 1.0])      # ValueError: object of too small depth for desired array
```

- `range=(2, 10)` is misrouted into `date_minor_breaks`; the real `range` local becomes `None`, so `area_pal(None)` is built and crashes when mapping.
- `scale_size_datetime(date_breaks="1 year")` misroutes `"1 year"` into `range`, so the user's `date_breaks` is silently dropped.

The sibling datetime scales all declare these InitVars correctly — e.g. `scale_alpha_datetime.__post_init__(self, date_breaks, date_labels, date_minor_breaks, range)`.

### Fix

Reorder the parameters to match the field order (the body was already correct):

```python
def __post_init__(
    self, date_breaks, date_labels, date_minor_breaks, range
):
```

After the fix, `scale_size_datetime(range=(2, 10)).palette([0.0, 1.0])` returns `[2.0, 10.0]`, defaults give `[1.0, 6.0]`, and `date_breaks` is honored.

### Tests

Added `test_size_datetime_palette`, which constructs the scale with `range=` and asserts the palette endpoints. It fails on `main` (`ValueError`) and passes with the fix. `pytest tests/test_scale_internals.py -k size` → passes. Added a changelog entry.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
