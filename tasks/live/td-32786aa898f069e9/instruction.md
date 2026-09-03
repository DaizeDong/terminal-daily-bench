# feat: add completed/status filters to get_todos

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds `completed` and `status` parameters to `get_todos`.

The Basecamp to-dos endpoint returns only the **active (incomplete)** to-dos by default, and there's no project-wide activity feed — so today there's no way to enumerate *delivered* work through `get_todos`. This threads Basecamp's own query params through:

- `completed: true` → `?completed=true` (fetch the completed to-dos)
- `status: "archived" | "trashed"` → `?status=...` (fetch by recording status)

Both are optional; omitting them preserves the existing default-active behaviour. The params flow through the existing `get_all_pages()` helper, so completed sets are returned **in full** (all pages), not just the first 15. Invalid `status` values raise a clear `ValueError`.

Consistent with the recent pagination/param work ([redacted-ref], [redacted-ref]): the change is wired through `BasecampClient.get_todos` **and both tool surfaces** — the FastMCP server (`basecamp_fastmcp.py`) and the CLI server (`mcp_server_cli.py`).

## Motivation

Downstream we run first-sight backfills of Basecamp projects and could only report delivered work as a ratio (e.g. "~74/111 done") rather than by title, because completed to-dos were unreachable. `completed=true` closes that gap.

Refs: [redacted-url]

## Tests

`tests/test_get_todos_filters.py` — default (no filter params), `completed=True`, `completed=False` (treated as default), `status='archived'`, combined `completed`+`status`, and invalid-status → `ValueError`. Full suite green (73 passed). Changelog updated under **Unreleased › Added**.

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

- **New Features**
  - Added filters for retrieving completed to-dos.
  - Added support for filtering to-dos by archived or trashed status.
  - Filtered results now include all available pages.

- **Bug Fixes**
  - Invalid status values are rejected with a clear validation error.

- **Documentation**
  - Updated the changelog and tool descriptions to explain the new filtering options.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
