# Add statsutils.mode() for the most common value

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Adds a `mode` measure to `statsutils`, closing [redacted-ref].

`Stats` already exposes `mean` and `median` as central-tendency measures (each with a module-level convenience function), but there was no `mode`. This fills that gap.

Implementation follows the existing pattern exactly: `mode` is a `_StatsProperty` backed by `_calc_mode`, so it caches like the other measures and automatically gets a module-level `mode()` helper via the convenience-function loop. It uses the already-imported `collections.Counter`, so it works for non-numeric, categorical data as well as numbers:

```python
>>> from [redacted-repo].statsutils import mode, Stats
>>> mode([2, 1, 3, 1])
1
>>> mode(['a', 'b', 'b', 'c', 'c', 'c'])
'c'
>>> Stats(range(5)).mode
0
```

When several values are equally common, the one appearing first in the data is returned, matching the standard library's `statistics.mode`. Empty data falls back to the object's configured `default`, consistent with the other measures.

Added a `test_mode` case and doctests (which run under `--doctest-modules`); the module docstring's measure list now mentions `mode`. Full `test_statsutils` suite and doctests pass locally.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
