# Ensure a write inside a failing [redacted-repo] task never becomes visible, plus execute_write(transaction=False) option

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- explicitly start `BEGIN IMMEDIATE` before `transaction=True` write callbacks in threaded and non-threaded modes
- allow trusted stored `VACUUM` queries to use the documented `transaction=False` escape hatch
- document the `execute_write()` transaction option and add regression coverage for sqlite-utils 4.0 writes

## Root cause

Python's `with conn:` context manager does not open a transaction on entry. sqlite-utils 4.0 therefore saw no active transaction, opened and committed its own transaction, and could leave partial writes committed when the surrounding [redacted-repo] write callback later failed.

The regression test verifies that a sqlite-utils write is invisible to a concurrent reader while the callback is running and is fully rolled back after an exception, in both threaded and zero-thread modes.

## Validation

- `uv run pytest -q` — 2,294 passed, 40 skipped, 6 xfailed, 15 xpassed, 141 subtests passed
- `uv run black --check [redacted-repo]/database.py [redacted-repo]/views/database.py tests/test_internals_database.py`
- `uv run ruff check [redacted-repo]/database.py [redacted-repo]/views/database.py tests/test_internals_database.py`
- `uv run sphinx-build -W -q -b html docs /tmp/[redacted-repo]-muse-docs`

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
