# fix: report early frame-cap exhaustion honestly

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- report the exact last sampled timestamp when scene changes exhaust the frame cap
- stop claiming whole-recording frame coverage for an early capped extraction
- keep the existing adaptive interval and exact-frame guidance

## Acceptance evidence
`brew.mp4` produced 600 frames through `t_ms=[redacted-sha]` for a `duration_ms=[redacted-sha]` recording. The old note claimed coverage across the whole recording; the new note exposes the gap.

## Tests
- `uv run pytest tests/unit -q` (273 passed)
- `uv run ruff check src/talkthrough_mcp/core/pipeline.py tests/unit/test_summarize.py`
- `uv run mypy src`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
