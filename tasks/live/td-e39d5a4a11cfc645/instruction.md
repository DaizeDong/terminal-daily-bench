# Limit `FileResponse` to 100 ranges

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- cap `FileResponse` range processing at 100 entries
- serve the complete response when a request exceeds the limit
- test the boundary at 100 and 101 ranges

## Rationale

Multipart range responses perform work for each selected range. Bounding the number keeps response handling predictable while preserving normal multi-range requests. Requests over the limit are handled as ordinary complete responses, consistent with HTTP allowing servers to ignore `Range`.

## Tests

- `uv run pytest tests/test_responses.py -q --basetemp=/private/tmp/[redacted-repo]-range-tests-final` (132 passed, 2 skipped)
- `uv run ruff format --check --diff [redacted-repo]/responses.py tests/test_responses.py`
- `uv run ruff check [redacted-repo]/responses.py tests/test_responses.py`
- `uv run mypy [redacted-repo]/responses.py tests/test_responses.py`

<!-- This is an auto-generated description by cubic. -->
<a href="[redacted-url] target="_blank" rel="noopener noreferrer" data-no-image-dialog="true"><picture><source media="(prefers-color-scheme: dark)" srcset="[redacted-url]><source media="(prefers-color-scheme: light)" srcset="[redacted-url]><img alt="Review in cubic" src="[redacted-url]></picture></a>
<!-- End of auto-generated description by cubic. -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
