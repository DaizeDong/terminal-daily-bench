# Fix filldown RuntimeError on header-only tables

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`filldown` reads the first data row up front to seed its fill values, so a table that has a header but no data rows blows up with `RuntimeError: generator raised StopIteration` instead of just passing the header through. `fillright` and `fillleft` don't have this problem — they return the header unchanged — so it's really an inconsistency between the three fill transforms.

It's easy to hit, e.g. after a `select` that filters everything out:

```python
>>> import [redacted-repo] as etl
>>> empty = etl.select([['foo', 'bar'], [1, 2]], lambda r: r.foo > 100)
>>> list(etl.filldown(empty))
RuntimeError: generator raised StopIteration
```

Same PEP 479 class as the `iterrowslice` fix in [redacted-ref]: the `StopIteration` from `next()` escapes the generator. I wrapped the seed read in the same `try/except StopIteration: return` the function already uses for the header read just above it, so a header-only table now yields just the header like the other fill transforms.

Added a regression test next to the existing `*_headerless` ones and a changelog note. Verified with `pytest --cov=[redacted-repo] [redacted-repo]` and `pytest --doctest-modules [redacted-repo]` (all green) plus the `sphinx-build -W` docs build.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
