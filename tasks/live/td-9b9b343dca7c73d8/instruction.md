# fix(ci): recognize Actions policy status identity

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- parse creator-less commit-status responses in the protected judge using GitHub Actions' server-owned global App attribution only as a coarse prefilter
- independently verify the exact current-repository workflow_dispatch run, protected-main SHA, workflow path, successful conclusion, unique artifact name/id/digest, and immutable evidence
- add behavioral API fixtures that accept the live response shape and reject wrong/missing attribution, status, repository, run, base SHA, workflow, artifact, and evidence bindings

## Live evidence
GitHub returned the valid approval status for run [redacted-sha] with no creator object and with the Actions integration avatar [redacted-url] The old verifier therefore rejected it before artifact verification.

## Validation
- 16 focused quality-ratchet tests pass
- focused Ruff and mypy pass
- workflow YAML parses
- the protected judge accepts the live status shape and keeps downstream authorization fail-closed

Follow-up for [redacted-ref]. Because this PR changes the protected ratchet workflow and judge, its ratchet check is expected to fail until the audited bootstrap merge; all other checks must pass first.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
