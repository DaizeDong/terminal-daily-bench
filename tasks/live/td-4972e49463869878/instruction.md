# feat: add Reports API tools (person assignments, assignable people, overdue)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

Adds three read-only MCP tools wrapping the Basecamp [Reports API]([redacted-url]):

| Tool | Endpoint |
|---|---|
| `get_assignable_people` | `GET /reports/todos/assigned.json` |
| `get_person_assignments` | `GET /reports/todos/assigned/{person_id}.json` (optional `group_by: bucket\|date`) |
| `get_overdue_todos` | `GET /reports/todos/overdue.json` |

## Why

`get_person_assignments` is the API counterpart of the web report at `/reports/todos/assigned/{person_id}` and returns one person's active, pending to-dos **across all projects in a single call**. Without it, answering "what is assigned to person X?" requires iterating every project and todolist — slow, and projects missed by the iteration silently read as "no assignments" (false negatives in downstream reporting).

`get_assignable_people` provides the person IDs to feed into the report; `get_overdue_todos` is the third report endpoint of the same API section.

## Implementation notes

- All three tools are read-only (`get_*` naming, consistent with the existing toolset).
- `get_assignable_people` uses the shared `get_all_pages` pagination helper.
- The per-person report returns a single JSON object (`person`, `grouped_by`, `todos`); the embedded `todos` list follows `Link`-header pagination defensively and merges pages into one report, guarded by `MAX_PAGES`.
- Error handling mirrors the existing tools (auth check, 401-expired hint).

## Tests

`tests/test_assignment_reports.py` — endpoint/params wiring, `group_by` pass-through, multi-page merge, non-200 errors, `MAX_PAGES` cap. Full suite: **75 passed**.

🤖 Generated with [Claude Code]([redacted-url])


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

- **New Features**
  - Added Reports API–backed tools for assignable people, person assignment to-dos across all projects, and overdue to-dos.
  - `get_person_assignments` supports optional grouping by bucket or due date and returns aggregated results in a single response.
  - Added parity in both the FastMCP server tools and the legacy CLI for compatibility.
- **Bug Fixes**
  - Improved Basecamp request reliability by using explicit timeout settings.
- **Documentation**
  - Updated the changelog and README to list the new Reports tools and revised tool counts.
- **Tests**
  - Added coverage for pagination, grouping, response shape, and error handling for the new Reports tools.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
