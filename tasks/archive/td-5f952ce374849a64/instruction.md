# Consolidate overlapping backend fixes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Consolidates the overlapping backend changes merged during the recent review:

- moves FalkorDB fulltext sanitizing, group-ID escaping, stopword handling, and query construction into one shared helper used by both the legacy driver and operations API;
- removes the duplicate stopword-only guard in those two implementations;
- reuses the canonical edge return projection in every remaining Neptune fulltext/BFS path, preserving `reference_time` consistently;
- routes community deletion through `graph_ops` and moves its identical provider implementations to the shared maintenance-operations base class.

## Why

The recent patches correctly fixed individual behavior, but several touched paths retained independent copies. Those copies had already drifted: Neptune's duplicated projections omitted `reference_time`, and the FalkorDB builders contained redundant guards.

## Validation

`uv run --extra dev ruff check` on all changed files

`uv run --extra dev pytest -q tests/test_edge_db_queries.py tests/utils/search/test_edge_bfs_query_shape.py tests/utils/search/test_search_security.py tests/test_handle_multiple_group_ids.py tests/driver/test_falkordb_ops_routing.py tests/utils/maintenance/test_remove_communities.py`

Result: 42 passed (one pre-existing Pydantic deprecation warning).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
