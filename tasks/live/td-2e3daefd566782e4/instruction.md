# feat: add multi-tenant session isolation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description

Adds customer-level tenant tagging, cost attribution, reporting, subject-access export, and auditable erasure across flat and workspace trace stores.

## Highlights

- Adds `tenant_id` to session metadata/events with `watch --tenant-id` and `AGENT_STRACE_TENANT_ID` propagation.
- Adds exact tenant filters to `list` and `cost`, plus `tenant report`, `tenant export`, and confirmed `tenant delete` commands.
- Includes tenant attributes in OTLP output and protects collector writes from tenant reassignment.
- Makes export/erasure complete across session sidecars, checkpoints, approvals, eval datasets, retention records, and all workspace stores.
- Adds durable tag/deletion journals, hash-only audit/tombstone records, immutable tenant assignment, cross-tenant tree protection, and fail-closed path/symlink validation.
- Preserves containment-safe legacy session/workspace IDs while keeping new ingress strict.
- Documents GDPR workflows and the collector boundary: one authenticated collector/storage root is one organization. Managed hosted infrastructure remains tracked by [redacted-ref].

## Version and release

Bumps `agent-strace` from `0.89.0` to `0.90.0`. After merge, the existing release workflow should create `v0.90.0`; the matching PyPI publish will be verified separately.

## Verification

- Ona full suite: 1,814 Python tests passed.
- VS Code extension: 3 tests passed.
- Independent adversarial review completed; all findings were fixed and re-reviewed.
- `git diff --check`, compilation, CLI smoke tests, and README 300-line policy passed.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
