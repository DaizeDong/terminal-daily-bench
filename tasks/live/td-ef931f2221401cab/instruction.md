# feat(llm): support configurable output language

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Add `[redacted-repo]_OUTPUT_LANGUAGE` for localizing human-readable LLM finding text.
- Apply the language instruction consistently to discovery analyzers, the meta-analyzer, and TP4's custom prompt path.
- Preserve rule IDs, severities, categories, file paths, code, and other machine-readable values.
- Document the new environment variable in `.env.example`, the README, and the development guide.

## Validation

- `.venv/bin/pytest tests/nodes/test_llm_analyzer_base.py tests/test_mcp_tool_poisoning.py -q -m 'not integration and not provider'` — 210 passed, 6 deselected; covers unset, blank, trimmed, discovery, meta-analyzer, and TP4 prompt behavior without live provider calls.
- `.venv/bin/ruff check src tests` — passed.
- `.venv/bin/ruff format --check src tests` — 192 files already formatted.
- `.venv/bin/pytest -m 'not integration and not provider' tests/ -q` — 2,804 passed, 13 skipped, 38 deselected, 4 xfailed.
- `git diff --check` — passed.

## Risk

- Unset or blank configuration preserves the existing prompts exactly.
- This controls prompt output language only; it does not translate deterministic static findings or machine-readable schema values.
- Live provider tests were not run because the behavior is covered at the mocked prompt boundary and requires no provider credentials.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
