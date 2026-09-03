# Polish Smart Inspect edge cases

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Show one additional nested level so Smart Inspect includes deep leaf fields like a.b.c.d.e
- Prefer object/list samples when inspecting mixed arrays, instead of showing the first scalar item beside object fields
- Add not-null filters to suggested queries for mixed arrays so copy-paste suggestions avoid null-heavy rows

## Manual checks
- python -m [redacted-repo] tests/json_test_files/deeply_nested.json
- python -m [redacted-repo] tests/json_test_files/mixed_arrays.json
- python -m [redacted-repo] tests/json_test_files/mixed_arrays.json "select key where key is not null" -t

## Verification
- pytest -q tests/jq_main_test.py tests/test_main_edge_cases.py
- pytest -q
- uvx ruff check --force-exclude [redacted-repo] tests
- python -m compileall -q [redacted-repo]
- LC_ALL=C LANG=C python -m sphinx -b html docs/source /tmp/[redacted-repo]-docs-smart-inspect-edge
- python -m pre_commit run --all-files
- python -m pre_commit run --hook-stage pre-push --all-files

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
