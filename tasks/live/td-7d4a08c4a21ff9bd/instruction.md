# Retry tau-bench policy connects promptly

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- retry policy TCP connection failures in the HTTP transport, which limits retries to `ConnectError`/`ConnectTimeout` rather than replaying long read timeouts
- use three 10-second connection attempts per SDK request instead of one 30-second attempt
- retain the existing one OpenAI SDK retry and 10-minute inference read timeout

This keeps the failure-time bound approximately unchanged while giving transient Modal ingress/routing failures more chances to recover. It addresses the observed validation failure below [redacted-repo], without exception handling in experiment 046.

## Verification
- `tests/unit/test_tau_bench_client.py`: 11 passed
- Ruff check/format

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
