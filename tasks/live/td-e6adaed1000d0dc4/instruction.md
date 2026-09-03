# Fix OverflowError in _compute_backoff for high attempt numbers

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

# Summary

[redacted-ref].

When retrying with the default float `wait_exp_base=2.0`, Python's `float` overflows at attempt 1025 (`2.0 ** 1024` exceeds `sys.float_info.max`), causing an `OverflowError` in `_compute_backoff()`.

This is a real-world problem when `wait_max` is set (e.g. 5 seconds) and retries run for extended periods — 1024 attempts with a 5-second cap is reached in roughly 85 minutes.

**Root cause:** `initial * (exp_base ** (num - 1))` overflows for float bases when `num > 1024`.

**Fix:** Catch `OverflowError` and return `max_backoff`. Any value that overflows Python's float necessarily exceeds `max_backoff`, so clamping is correct.

# Pull Request Check List

- [x] Do **not** open pull requests from your `main` branch – **use a separate branch**!
- [x] Added **tests** for changed code.
    - Added `test_backoff_no_overflow_on_high_attempt_numbers` that verifies attempts 1025, 2000, and 10,000 return `max_backoff` without raising.
- [x] **New APIs** are added to our typing tests in [`api.py`]([redacted-url]).
    - N/A — no new public APIs.
- [x] Updated **documentation** for changed code.
    - [x] N/A — no new functions/classes.
    - [x] N/A — no changed public API signatures.
- [x] Documentation in `.md` files is written using [**semantic newlines**]([redacted-url]).
- [x] Changes (and possible deprecations) are documented in the [**changelog**]([redacted-url]).
- [x] Consider granting [push permissions to the PR branch]([redacted-url]), so maintainers can fix minor issues themselves without pestering you.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
