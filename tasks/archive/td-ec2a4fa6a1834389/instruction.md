# Fix DictsView.dicts instance attr shadowing Table.dicts() method

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`fromdicts()` returns a `DictsView` that stores its input as `self.dicts`, which shadows the `dicts()` method `Table` picks up from `Table.dicts = dicts` in `[redacted-repo]/util/base.py`. The instance attribute wins attribute lookup, so:

```python
>>> import [redacted-repo] as etl
>>> etl.fromdicts(etl.dummytable().dicts()).dicts()
TypeError: 'DictsView' object is not callable
```

Renames the internal attribute to `self._dicts` in `DictsView` and `DictsGeneratorView`, following the `self._header` convention [redacted-sha] introduced on this same class for the same collision (released in 1.7.5 as "Fix `fromdicts(...).header()` raising TypeError").

The last commit is separable: it keeps `.dicts` readable as the input data via a property on `DictsView`, so the attribute behaves as it does today while `.dicts()` starts working. Drop that commit for the plain rename.

[redacted-ref].

---

This pull request was prepared with the assistance of AI, under my direction and review.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
