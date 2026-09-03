# Avoid densifying sparse.COO data in to_series()/to_dataframe()

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Continuation of [redacted-ref], per @khaeru's offer there to close it in favor of a fresh PR ([redacted-url]).

## Summary

`DataArray.to_series()` and `Dataset.to_dataframe()` both densify `sparse.COO`-backed variables via `.values` before building the pandas result:

- For `to_dataframe()` this doesn't just defeat the purpose of using a sparse array - it **crashes outright** on current `main`, since `sparse.COO` refuses to densify implicitly (`RuntimeError: Cannot convert a sparse array to dense automatically`).
- For `to_series()`, [redacted-ref] already proposed avoiding this densification, but (per [this review comment]([redacted-url])) its `set_levels()` call maps `sparse.COO`'s stored integer coordinates back to coordinate labels incorrectly whenever a dimension doesn't have every one of its labels represented among the stored entries - i.e. almost always, for genuinely sparse data. I confirmed this experimentally: it silently returns wrong labels rather than raising.

This PR:
- Adds a `_sparse_coo_to_index()` helper that does this coordinate mapping correctly (mapping `sparse.COO.coords`' per-dimension integer codes back through each dimension's actual coordinate index, rather than assuming the codes already run in coordinate order), and returns a plain `Index` rather than a 1-level `MultiIndex` for 1-D data (matching the non-sparse code path).
- Uses it in `DataArray.to_series()`, which now returns only the array's stored (non-fill-value) entries for `sparse.COO` data, never materializing the full Cartesian product.
- Extends the same approach to `Dataset._to_dataframe()` (per [dcherian's review]([redacted-url]) on [redacted-ref] asking for this), indexing the resulting DataFrame by the union of stored coordinates across all matching sparse columns, with other columns (sparse or dense) reindexed onto that reduced index using each sparse column's own fill value. `dim_order` permutation is handled via a cheap `reorder_levels()` (metadata-only, no densifying).
- Both fall back to the original dense behavior for other `sparse.SparseArray` subclasses (e.g. `DOK`, which lack the `.coords`/`.data` attributes this relies on) and for variables that need broadcasting to reach the target dims - unchanged (and, for `to_dataframe()`, still broken) in exactly the way they are on `main` today, i.e. no regression.

## Testing

- New tests in `test_dataarray.py`: `test_to_series_sparse` (labeling-correctness, verified against a dense ground truth with a non-trivial/non-edge sparsity pattern) and `test_to_series_sparse_1d` (index-type fix).
- New tests in `test_dataset.py`: `test_to_dataframe_sparse_crash_regression` and `test_to_dataframe_sparse` (multiple sparse columns with different sparsity patterns + a dense column, verified against dense ground truth, including `dim_order` permutation).
- Full `test_dataset.py`, `test_dataarray.py`, and `test_sparse.py` suites pass locally.

Opening as a draft for initial feedback on the approach (particularly the `Dataset.to_dataframe()` union-of-coordinates strategy) before marking ready for review.

- [x] Closes/supersedes [redacted-ref] (to be closed once this is ready)
- [x] Tests added
- [x] `whats-new.rst` entry added

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
