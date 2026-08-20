# fix(chat): preserve provider stream failure boundaries

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- never replay a later agent round after provider output is already visible
- preserve retryable provider transport errors when the forced-finish request also fails
- add regressions for both multi-round failure boundaries

## Validation
- `pytest -q tests/agents/chat/test_agent_loop.py` (36 passed)
- `pytest -q tests/agents tests/services/llm tests/services/session` (597 passed)
- full local suite: 4143 passed, 14 skipped; 6 failures require the optional GraphRAG dependency absent locally
- `ruff check .`
- `ruff format --check .`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
