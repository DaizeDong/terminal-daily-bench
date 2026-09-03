# Add `excluded_urls` to `OpenTelemetryMiddleware`

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add an `excluded_urls` parameter to `OpenTelemetryMiddleware`
- accept a sequence of regular expressions or a comma-separated string
- compile each expression once when constructing the middleware
- skip spans when an expression matches the full request URL
- document exclusions for health checks and similar endpoints

## Validation

- `./scripts/check`
- `uv run pytest tests/middleware/test_opentelemetry.py`

## AI Disclaimer

This PR was developed with the assistance of either Claude or Codex. I've reviewed and verified the changes.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
