# refactor(sessions): deepen session search application seam

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This is the first `sessions.search` vertical slice after [redacted-ref]. It deepens the `SessionDirectory` application module without changing the v4 wire contract or any client surface.

### Changes

- Move search input normalization, title lookup (including the bounded legacy fallback), ASCII/Unicode routing, deduplication, transcript-title enrichment, and best-effort transcript failure handling into `SessionDirectory.search()`.
- Keep the Gateway handler limited to session-storage lookup, a presentation projector, and mapping the domain result back to the existing v4 payload.
- Keep `RpcContext`, WebSocket transport, storage schema/SQL, WebUI, CLI, MCP, and all other session methods unchanged.
- Add application-level tests for normalization, FTS/LIKE routing, deduplication, legacy fallback, enrichment, and failure semantics.
- Rebaseline the authored-runtime gate at the merged S1 baseline with a bounded S2a budget; the final closure gate still owns the cumulative deletion check.

### Compatibility

The following semantics are intentionally unchanged: `operator.read`/guest policy, empty-query response, limit coercion and clamp, title-index failure propagation, transcript failure degradation, CJK LIKE search, title/content deduplication, response field names, and timestamps.

### Evidence

- GitNexus was indexed against this branch (`115,495` nodes, `223,816` edges). `SessionDirectory` has one incoming Gateway edge and no application-to-Gateway dependency; the previous handler's dynamic RPC incoming edge remains a known graph blind spot.
- Targeted application, Gateway search, architecture-import, and RPC architecture tests: `86 passed`.
- Mypy, Ruff, compileall, and `git diff --check` pass.

### Non-goals

No Contract schema or generated code, WebUI migration, Python-client migration, `sessions.preview`, chat history, subscriptions, runtime, transport, or database changes are included. Those remain separate S2b–S2d slices.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
