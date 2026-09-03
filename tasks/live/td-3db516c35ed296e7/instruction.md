# Expose catalog operations as direct MCP tools

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- derive one direct MCP `Tool` from every admitted immutable `MathTool`, using the unchanged operation ID as the tool name
- publish each owner's request and result schemas directly, parse strict JSON inside one request-scoped execution envelope, invoke the catalog's checked typed binding, and return the owner result without a generic dispatch envelope
- preserve bounded `INVALID_PARAMS`, cancellation, timeout, and unexpected-failure projection without reflecting raw caller values
- keep `math.find` as a separate semantic discovery surface and isolate `math.run` as transitional pending catalog-scale discovery evaluation
- update the product/architecture/tool documentation and the real-client MCP tests for the direct surface

## Experiments and design evidence

Before implementation, a real in-memory MCP client confirmed that the server listed only `math.find` and `math.run`. The pinned MCP 2.1 SDK exposes native `Tool` construction through the server's `tools` argument; its ordinary function metadata path pre-parses/coerces Python arguments, so the adapter uses the SDK argument hook only to carry the raw object and performs [redacted-repo]'s existing strict JSON parse inside the complete request envelope.

The real client then exercised direct calls for `integer.compute.extended_gcd`, `matrix.determinant.compute`, and `universal_algebra.term.evaluate.compute`, including structural, canonicalization, and domain-invalid calls. Adding/removing declarations from a test catalog changed the direct tool list automatically.

All 768 current operation IDs satisfy the MCP name grammar, so the naming transform is the reversible identity and fixed-tool collisions fail closed. One current request model is a root union of object branches; MCP requires an object root, so projection adds only the required top-level `type: object` after verifying every branch is object-shaped. Non-object request schemas fail server construction.

A full direct-only catalog experiment registered 768 tools in about 1.087 seconds, listed them in about 0.039 seconds, and serialized a roughly 2,673,284-byte tool list. The transport works, but that payload size is why this PR does not yet claim that generic execution can be removed safely.

## Scope and follow-up

This is the largest coherent vertical slice: all admitted operations are directly callable, the catalog is the only membership source, and native Python APIs are unchanged. It does not add another registry, dispatcher, backend path, workflow, or durable state.

Removing `math.run` still requires a frozen control/treatment evaluation of client tool discovery and correct invocation with the full catalog-sized list, including deferred-search clients and context/token costs. `math.find` should be evaluated separately for semantic mathematical vocabulary discovery rather than conflated with direct execution. Those are follow-ups; `math.run` is not needed by the direct path introduced here.

## Validation

Passed:

- `make test-mcp` — 30 passed, including real-client listing/invocation, stdio, concurrency, and cancellation
- `.venv/bin/pytest -q -n0 tests/mcp/test_direct_operations.py` — 7 passed
- scoped Ruff formatting/lint and mypy for all changed Python paths
- `make docs-linkcheck`
- `git diff --check`

The prescribed `make affected AFFECTED_BASE=origin/main` reached 6,092 passed and 57 skipped math tests, then stopped on 16 failures in untouched math paths (primarily the macOS factor worker's address-space-limit setup, plus an existing topology bound assertion). Isolated reruns reproduced those failures, and this branch has no diff under `src/[redacted-repo]/math` or `tests/math`. Additional selected baseline failures were `make test-process` (189 passed, 1 skipped, one 1-second timing test failed) and `make test-dispatch` (107 passed, one existing determinant bound mismatch failed). The MCP, static, and documentation lanes above are clean.

Refs [redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
