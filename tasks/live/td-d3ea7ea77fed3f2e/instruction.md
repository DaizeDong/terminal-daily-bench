# Restructure notebook module and release 1.0.0

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Behaviour-preserving restructure plus the 1.0.0 release.

## What changed
- Extract `TensorVisual` and the shared rendering substrate (`_visual`,
  `_value_fn_for`, `_source_value`, `_preview_explanation`) into `visual.py`.
- Move the einsum view (constants, helpers, `einsum`) into `einsum.py`.
- Fold `transpose`/`swapaxes`/`moveaxis` into one `_permute_view` helper.
- `notebook.py` drops from ~1388 to ~1000 lines. No new files import `notebook`,
  so there is no import cycle.
- Bump version to 1.0.0.

## Unchanged
- Public API: `rt.einsum`, `rt.TensorVisual`, and every op keep the same import
  path and behaviour.
- Test imports for the relocated einsum internals were repointed; assertions are
  identical.

## Checks
- `pytest`: 338 passed, 3 skipped
- `ruff check .`: clean
- `python -m build`: builds `rainbow_tensor-1.0.0` wheel and sdist

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
