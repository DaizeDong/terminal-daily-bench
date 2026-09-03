# feat(runtime): surface FloodWait rate limits with actionable wait instructions ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

[redacted-ref].

Telegram rate limits (`FloodWaitError`) previously suffered from two failure modes in the tool runtime:
1. **Silent latency accumulation:** `_build_client()` did not configure `flood_sleep_threshold`, inheriting Telethon's default of 60s silent sleep. When multiple operations (e.g. scanning dialogs) encountered short flood waits, sleeps stacked up past MCP client idle timeouts, creating false "server dead" hangs.
2. **Type erasure on long waits:** When a wait exceeded 60s, `FloodWaitError` was caught by `log_and_format_error()` and formatted as an opaque generic error (`GEN-ERR-...`), stripping the wait duration and exception type. AI/LLM agents would immediately retry the request, escalating the rate limit and risking account restrictions or bans.

## Changes

- **`telegram_mcp/runtime.py`**:
  - Added `_get_flood_sleep_threshold()` to read `TELEGRAM_FLOOD_SLEEP_THRESHOLD` (default: `60`s). Set to `0` to fail fast and let the agent manage backoff.
  - Configured `kwargs["flood_sleep_threshold"]` during `TelegramClient` initialization in `_build_client()`.
  - Added `_is_flood_wait()` helper and specialized handling in `log_and_format_error()`:
    - Logs a `WARNING` with the required wait duration instead of an unhandled error.
    - Returns an explicit, actionable message to LLMs containing the required wait seconds and a directive not to retry immediately:
      `"Rate limit exceeded (FloodWait): Telegram requires waiting N seconds before repeating this operation. Do NOT retry immediately (code: ...)."`
- **`README.md`**:
  - Documented `TELEGRAM_FLOOD_SLEEP_THRESHOLD` under environment configuration.
- **`tests/test_flood_wait.py`**:
  - Added 9 unit tests covering threshold parsing, custom and invalid fallbacks, client builder kwargs, warning logging, custom user messages, and explicit LLM instructions.

## Verification

```bash
uv run pytest tests/test_flood_wait.py
# 9 passed in 0.70s

uv run pytest
# 439 passed

uv run black --check telegram_mcp/ tests/test_flood_wait.py
uv run flake8 telegram_mcp/ tests/test_flood_wait.py --select=E9,F63,F7,F82
# Clean
```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
