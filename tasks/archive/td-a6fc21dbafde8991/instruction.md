# fix: keep deployments successful when verification fails

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- make explorer verification best-effort after a successful deployment
- preserve strict behavior for explicit `NetworkAPI.publish_contract()` calls
- cover both account and contract-container deployment entry points

## Root cause

Both deployment paths cached a successfully deployed contract and then called the active explorer synchronously. Any explorer error, including a missing explorer, API rejection, timeout, or plugin failure, propagated from `deploy()` even though the on-chain deployment had already succeeded.

## User impact

`deploy(..., publish=True)` now returns the deployed contract instance when explorer verification fails and logs the original error instead. Deployment tracking and the existing local-network guard keep their current behavior.

## Validation

- `137 passed` across `tests/functional/test_accounts.py` and `tests/functional/test_contract_container.py`
- focused publish regression tests pass for both deployment APIs
- Ruff lint and formatting checks pass for all changed files
- `git diff --check` passes

Local pre-commit mypy currently reports seven errors in three unrelated files; the same errors reproduce on a clean `upstream/main` worktree.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
