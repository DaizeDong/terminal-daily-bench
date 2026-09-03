# Fix skills-only custom base URL resolution

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- make prompt-compression helper calls use the live runtime config instead of being overwritten by the default on-disk config
- fall back to the raw system prompt when compression fails so custom providers do not turn requests into 500s
- add regression tests for skills-only and RL config precedence plus the compression fallback path
- document that `llm.api_base` should point to the full OpenAI-compatible base URL, typically ending in `/v1`

## Testing
- `python -m pytest -q tests/test_utils.py tests/test_launcher.py tests/test_sdk_backend.py tests/test_openclaw_env_rollout.py`
- `python -m compileall -q [redacted-repo]`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
