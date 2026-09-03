# fix: default RK ASR finalization to synchronous

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

RK3576 measurements show QWEN3_ASR_VAD_FINAL_ASYNC regresses close-out latency, while selected RK3588 profiles explicitly opt in where it helps. Make the backend fallback synchronous and cover the default with a regression test.\n\nValidation: uv run pytest -q tests/test_qwen3_true_streaming_config.py (7 passed).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
