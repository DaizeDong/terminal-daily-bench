# Fix strict evaluation for negative record counts

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Treat `record_count == 0` as empty in strict metrics evaluation.
- Treat negative legacy/unknown counts conservatively as `ROWS_MIGHT_NOT_MATCH`.
- Update the record-count short-circuit regression test.

This prevents strict evaluation from classifying files with unknown counts as fully matching, which can incorrectly authorize whole-file deletion.

Java validates newly built files with `recordCount >= 0` ([DataFiles.java]([redacted-url])), while manifest reads instantiate through Avro ([GenericDataFile.java]([redacted-url])). Its inclusive evaluator handles negative counts as unknown ([InclusiveMetricsEvaluator.java]([redacted-url])); the strict evaluator still groups them with empty files ([StrictMetricsEvaluator.java]([redacted-url])).

Related to [redacted-ref].

## Tests

- `uv run pytest tests/expressions/test_evaluator.py -q`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
