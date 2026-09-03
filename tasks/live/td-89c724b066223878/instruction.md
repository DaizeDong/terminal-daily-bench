# 106 stability numpy compatibility and dispatch

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Harden NumPy compatibility and dispatch behavior for `[redacted-repo]` `0.5.0-dev2`.
- Align package metadata, runtime hooks, tests, and CI with supported ranges: Python `3.9`-`3.14` and NumPy `1.26.4`-`<3`.
- Replace legacy changelog format with a structured `CHANGELOG.md` and add compatibility guidance docs.

## Related issue(s)
- [redacted-ref] 

## Type of change
- [x] Bug fix
- [ ] Feature
- [x] Refactor
- [x] Documentation
- [x] Tests
- [x] CI/Build

## What changed
- Runtime/dispatch compatibility.
- Stopped import-time auto-mutation of `NUMPY_EXPERIMENTAL_ARRAY_FUNCTION` and fixed env parsing behavior in `[redacted-repo]/__init__.py`.
- Updated `Fxp.__array__` for NumPy 2.x-compatible `dtype`/`copy` semantics while keeping legacy positional compatibility.
- Extended `Fxp.__array_wrap__` with `return_scalar` handling and removed legacy `__array_prepare__`.
- Normalized `out=...` handling in operator core helpers so ellipsis is treated as omitted output.
- Tightened `_wrapped_numpy_func` routing for `out` and `out_like` extraction and type validation (`Fxp` only), with clearer fallback behavior on `TypeError`.
- Bumped runtime version to `0.5.0-dev2`.
- Updated Python support floor to `>=3.9`.
- Pinned NumPy dependency range to `numpy>=1.26.4,<3` in both `pyproject.toml` and `requirements.txt`.
- Reworked `.github/workflows/ci.yml` into explicit NumPy compatibility matrix lanes (`1.26.4` and `2.4.3`) across valid OS/Python combinations.
- Added stable required gate jobs: `Required NumPy compatibility` and `Required installation smoke`.
- Added artifact upload and per-job summary generation for traceability.
- Updated `.github/workflows/master-release-gate.yml` to run explicit NumPy matrix lanes.
- Added nightly pre-release workflow: `.github/workflows/nightly-numpy-prerelease.yml`.
- Expanded NumPy dispatch coverage in `tests/test_numpy_functions.py` for `out=...`, invalid `out` types, array protocol `dtype`/`copy`, unsupported kwargs, and mixed-input divide regression.
- Added function-level `out=...` and output-validation tests in `tests/test_functions.py`.
- Extended install smoke coverage in `tests/test_installation.py` to assert env-var preservation on import.
- Added `docs/compatibility_notes.md` and linked it from `index.md`.
- Migrated `changelog.txt` to structured `CHANGELOG.md` and updated `CONTRIBUTING.md` references accordingly.

## Testing
- [x] Added/updated tests
- [ ] Ran test suite locally (`pytest -q`)
- [ ] Added/updated issue regression test in `tests/test_issues.py` (when applicable)

## Compatibility and risk
- [x] Backward-compatible
- [ ] Potentially breaking (describe below)

### Breaking change notes (if any)
- None expected. This branch enforces stricter validation for unsupported or invalid dispatch kwargs/types, which now fail explicitly instead of being implicitly coerced.

## Checklist
- [x] Updated docs/readme if behavior changed
- [x] Updated changelog entry if needed

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
