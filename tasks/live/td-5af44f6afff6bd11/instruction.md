# 0.8.0.4: dict-schema pattern/text_type passthrough

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

- `from_dict_schema` now passes `pattern` and `text_type` through to the engine. Both were dropped before, which made the 0.8.0.3 pattern codes and explicit semantic text types unreachable from dict schemas (the contract Studio, MCP agents, and non-Python callers speak).
- An explicitly declared `text_type` now beats column-name inference. Previously a column named `contact` declared as `person_name` generated description text because inference outranked the declaration.

## Tests

759 passed ([redacted-ref] new regression tests in `test_enterprise_simulation.py`).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
