# chore: release v0.8.1

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Release v0.8.1.

## Summary

- bump the Python package, lockfile, and desktop-extension manifest to `0.8.1`
- replace the accumulated implementation diary with concise, user-facing release notes
- align newly introduced deprecation metadata and documentation with the shipping version

## Impact

This release adds notebook collections, richer source/artifact/chat/research metadata,
improved citation and research workflows, and a set of authentication, idempotency,
decoding, and download fixes. The changelog calls out the default-host switch and the
`QuizQuantity.MORE` compatibility change.

## Validation

- `uv run pre-commit run --all-files`
- `uv run mypy src/notebooklm --ignore-missing-imports`
- `uv run pytest -n auto --dist=worksteal` — 16,674 passed, 77 skipped, 1 xfailed
- `uv run python scripts/audit_public_api_compat.py --check-stale`
- release documentation drift checks and example compilation
- live auth matrix — 19/19 executed cells passed, including both hosts, master-token,
  RPC, REST, MCP, concurrency, recovery, fault-injection, and crash-safety coverage

TestPyPI publication and package verification remain pending after PR CI and the
release-branch live workflow gates.


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **Release**
  * Updated the application and desktop extension version to **0.8.1**.

* **Deprecations**
  * Updated deprecation schedules for authentication-token, cookie, profile, citation, and notebook timestamp APIs to reflect availability in version 0.8.1.

* **Documentation**
  * Refreshed deprecation and stability documentation dates and version references.

* **Tests**
  * Updated validation checks to match the revised deprecation timeline.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
