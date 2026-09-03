# fix: interpolate lazily-formatted connector logs in DbtCoreHandler

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

## Summary
- `DbtCoreHandler.emit` now calls `record.getMessage()` so lazily formatted `[redacted-repo].sql` log lines keep their interpolated arguments instead of arriving in dbt with literal `%s`.

## Test plan
- [x] `hatch run pytest tests/unit/events/test_logging.py -v` (new interpolation case failed on `record.msg`, passed after the change)
- [x] Live warehouse `dbt run` of a `select 1` model with connector logs at INFO: pre-fix `Successfully opened session %s`, post-fix the actual session UUID

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
