# Add the disconnected Scope-Link v4 live runner

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Why

Scope-link v4 passed its zero-network method gate but had no auditable boundary for any later authorized W01-W08 provider study. Running the provider directly would have lost the manifest-before-adapter, per-request journal, row-complete accounting, and review-provenance guarantees established by earlier experiments.

## What changed

- pre-registers the exact anonymous one-attempt W01-W08 execution and USD 0.01 soft-stop contract before implementation
- adds a production-disconnected write-once runner that records its observed self-hash and locks all decision/transport dependencies
- persists the complete manifest before adapter construction and each case journal before any later request
- carries required, scope, supporting, and same-segment link provenance to the aggregate CSV while sending only ACCEPT rows to a blank review boundary
- documents that no provider request, source review, or production authorization has occurred

## Verification

- 17/17 new runner tests
- 32/32 combined v4 decision, preflight, and runner tests
- 1,695 tests passed, 1 skipped, and 609 subtests passed in a clean detached worktree
- latest Ruff and narrow Pylint passed
- defect reinjection: dropping link_evidence only at the CSV seam made the client-boundary test fail before restoration

Production remains disconnected. This PR does not authorize or perform a live OpenAlex request.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
