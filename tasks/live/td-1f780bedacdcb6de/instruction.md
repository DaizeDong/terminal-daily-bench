# Support type aliases in union passthrough

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- unwrap PEP 695 type aliases when union passthrough checks native union members
- keep spillover handling for non-passthrough union members intact
- add Python 3.12 coverage for a type alias mixed with a dataclass in the target union

[redacted-ref]

## Tests
- `.venv/bin/python -m pytest tests/strategies/test_tagged_unions_695.py tests/strategies/test_union_passthrough.py tests/strategies/test_union_passthrough_695.py`
- `.venv/bin/ruff check src/[redacted-repo]/strategies/_unions.py tests/strategies/test_union_passthrough_695.py`
- `.venv/bin/ruff format --check src/[redacted-repo]/strategies/_unions.py tests/strategies/test_union_passthrough_695.py`
- `git diff --check`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
