# feat: add agent-safe Evidence API v1

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add the public `orbit.evidence.v1` read boundary for integrations and future Orbit Pro consumers
- return metadata-first normalized request-family evidence without raw payloads, SQL, headers, bodies, messages, or tracebacks
- distinguish read status from evidence completeness and provide structured, executable recovery actions for coding agents
- strip query strings and fragments, bound public identifiers, honor the configured storage alias, and fail without affecting the host app
- document the schema, action catalog, security boundary, compatibility policy, and safe consumption flow

## Verification

- `python -m pytest --tb=short -q` -> 302 passed, 1 skipped
- `python -m pytest tests/test_evidence.py -q` -> 21 passed
- Black and isort checks pass for the new Python files
- Python 3.9 grammar parse passes
- `python -m mkdocs build --strict` passes
- package build and `twine check` pass
- independent correctness/security review: no P0/P1/P2 findings
- independent developer/agent UX review: pass, no P0/P1 findings

## Integration note

This branch is based on `release/v0.13.0` at `[redacted-sha]`. There is separate unpublished AI-first work in progress outside this branch. Recheck and rebase this PR after that work is committed; do not overwrite those changes.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
