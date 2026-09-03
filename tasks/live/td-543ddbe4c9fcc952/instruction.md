# strategy: support max effort on strict Responses-compatible gateways

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Add `max` to the Consulting Agent effort choices and documentation.
- Preserve explicitly requested `max` effort across compatibility fallbacks instead of silently dropping the reasoning effort.
- Use the canonical Responses message-list input and disable response storage.
- Selectively retry when a gateway rejects `background` or `max_output_tokens`.
- Recover replies from `response.output_text.delta` events when the completed response contains no output text.
- Reject unsupported Claude effort values instead of silently weakening them to `low`.

## Motivation

Some OpenAI-compatible Responses gateways support `max` reasoning effort while rejecting optional request parameters or returning text only through streaming delta events.

The previous fallback behavior could silently remove the requested reasoning effort or return an empty reply. As a result, callers could not reliably determine whether a strongest-effort consultation actually ran as requested.

`ultra` is intentionally not exposed because the tested Responses endpoint explicitly rejects it and reports `max` as the strongest supported effort level.

## Validation

- `pytest -q [redacted-repo]/strategy/tests` — 77 passed
- `pytest -q` — 497 passed, [redacted-ref] pre-existing warnings
- Live `gpt-5.6-sol` / `max` smoke test — completed successfully on the full attempt

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
