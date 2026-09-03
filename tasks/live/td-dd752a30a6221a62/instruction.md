# 🐛 Inherit panel label fonts

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Purpose
Fix [redacted-ref] by making panel labels inherit the configured sans-serif fallback chain.

## Changes
Default `panel_label_fontname` to `None`, add Linux-friendly fallbacks, and cover both label APIs with regression tests.

## Testing
- `make test` — 534 passed
- `make lint` — passed

## Risks
Low; explicit font overrides remain supported.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
