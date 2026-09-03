# fix(deps): make h5py a core dependency; BrainCollection.fit() requires it

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

`BrainCollection.fit()` always writes an HDF5 fit bundle, and
`[redacted-repo]/data/collection/execution.py` imports `h5py` unguarded:

```python
def _write_bundle(...):
    import h5py                      # no try/except, no extras check
    with h5py.File(tmp, "w", locking=False) as f:
```

But `h5py` was declared only in the optional `h5` extra. Installing plain
`[redacted-repo]` and calling `BrainCollection.fit()` fails with:

```
[redacted-repo].data.collection.execution.BrainCollectionWorkerError:
  [idx=4] ModuleNotFoundError: No module named 'h5py'
```

Because it is raised inside a joblib worker, the traceback is ~20 frames of
`joblib/parallel.py` before the real cause, which makes it hard to diagnose —
especially for students, which is how I found it (porting the
[dartbrains]([redacted-url]) course to 0.6).

Two things hid this:

- The `dev` dependency group installs `h5py`, so it never reproduces in development.
- `[redacted-repo]/io/h5.py` *does* guard its import and raise an actionable error, but
  only for the `BrainData` `.h5` path. The collection path never goes through it.

## Fix

Move `h5py` to `[project].dependencies`. `BrainCollection` is a headline v0.6
feature and is unusable without it, so it is not an optional add-on.

`hdf5plugin` deliberately stays in the `h5` extra: it only registers
blosc/zstd/lz4 filters for reading compressed legacy files, the bundle writer
uses no compression filters, and `[redacted-repo]/io/h5.py` already guards it. The
`h5` extra keeps listing both so existing `[redacted-repo][h5]` pins resolve unchanged.

## Regression guard

Adds `[redacted-repo]/tests/support/test_packaging.py`, which parses `pyproject.toml`
and asserts that modules imported unconditionally by the collection execution
path are declared as core dependencies. Written red-first — it fails on
`master` with:

```
AssertionError: [redacted-repo]/data/collection/execution.py imports ['h5py']
unconditionally, but they are not in [project].dependencies.
```

The check walks the AST and ignores imports inside `try`/`except`, so guarding
an import (with a friendly message) is still a valid way to satisfy it.

## Docs

The migration guide still described `BrainCollection` as **"not yet available
(scaffold)"** in three places and pointed at `[redacted-repo]/data/collection/SPEC.md`,
deleted in [redacted-sha]. The class is fully functional — I verified
`from_paths` → `.smooth().fit(model='glm', X=...)` → `.compute_contrasts()` →
`.ttest()` / `.permutation_test()` / `.predict(spatial_scale=...)` end to end.

Replaced with a worked example plus the two contracts that aren't obvious from
the signatures:

- the `X=` callable receives a `_DesignContext`, not a `DesignMatrix`
- `from_paths(design_paths=...)` passes paths through unparsed, so the builder
  must construct the `DesignMatrix` (matching the source comment: *"DesignMatrix
  has no read() classmethod yet"*)

## Testing

- `uv run poe lint` — clean
- `[redacted-repo]/tests/support/` — 177 passed
- `[redacted-repo]/tests/data/collection` — 276 passed

(Both suites need `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` on my machine; a stale local
HF token 401s against the public `[redacted-repo]/niftis` dataset. Unrelated to this change.)

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
