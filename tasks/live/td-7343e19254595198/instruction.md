# feat(memory): add structured schema and usage index

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This PR upgrades [redacted-repo] memory from loose Markdown notes into a structured, reviewable memory store while preserving compatibility with existing memory files.

It adds schema-v1 frontmatter, deterministic signatures, stable memory ids, soft-delete metadata, a usage index for recalled memories, and an explicit migration path for existing stores. Project memory and ohmo personal memory now share the same behavior.

## Why

The current memory system works for small manual stores, but it lacks stable identity, usage feedback, and safe pruning. As memory grows, filenames are not enough for dedupe, ranking, supersession, cleanup, or auto-dream review.

For an open-source project, users also cannot be forced through one synchronized migration. This keeps old Markdown readable while adding `/memory migrate --dry-run` and `/memory migrate --apply`.

## Value

- Stable ids and signatures enable reliable dedupe, ranking, cleanup, and future supersession.
- `usage_index.json` records which memories are actually recalled, improving search ranking and stale-memory review.
- Soft delete uses `disabled: true`, making cleanup reviewable instead of destructive.
- Auto-dream now receives usage-based stale candidates but treats them as review candidates, not delete instructions.
- Project memory and ohmo personal memory now behave consistently.

## Main Changes

- Add schema-v1 frontmatter fields for memory files.
- Add explicit migration via `/memory migrate --dry-run`, `/memory migrate --apply`, and `scripts/migrate_memory.py`.
- Add usage tracking when relevant memories are injected into the runtime prompt.
- Rank memory search by relevance plus importance, usage count, and recency.
- Keep existing memory injection length unchanged.
- Change `/memory remove` to soft-delete.
- Align ohmo personal memory with the same schema and soft-delete behavior.

## Validation

- `ruff check ...` passed
- focused tests: `34 passed`
- migration dry-run script passed
- `git diff --check` passed

A broader related suite produced `168 passed, 1 failed`; the failure is unrelated to memory and comes from a Windows gateway-process test that mocks `os.kill` while the implementation uses `taskkill`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
